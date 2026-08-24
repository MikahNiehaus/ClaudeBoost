"""Periodic reindex of every project clean-rag knows about.

Every project's index lives under clean-rag itself, at
databases/_projects/<pid>/, holding chroma/, graph.db, and manifest.json. The
registry of which projects exist is state/projects.json.

This walks that registry on a timer, compares each project's files against its
manifest hashes, and reindexes only what actually changed. Files that never
changed are never re-embedded.

The per edit hook (hooks/reindex-after-edit.py) already covers edits Claude
makes. This covers everything else: edits from another editor, a git pull, a
branch switch, a teammate's commit. Without it the index silently drifts out of
date and search starts confidently returning code that no longer exists.
"""

import asyncio
import json
import logging
import time
from functools import partial
from pathlib import Path

from .config import (
    CPU_BACKOFF_MAX_WAIT_S,
    CPU_BACKOFF_S,
    CPU_MAX_PERCENT,
    MIN_FREE_RAM_MB,
    STATE_DIR,
    SWEEP_INTERVAL_S,
)
from .indexing import (
    UNREADABLE_SENTINEL,
    _project_paths,
    acquire_index_lock,
    drop_manifest_key,
    file_hash,
    index_is_incomplete,
    index_project,
    reindex_file,
    release_index_lock,
    scan_project,
)
from .reindex_unit import (
    Outcome,
    PlannedProject,
    model_groups,
    plan_sweep,
    read_registry,
    release_project_resources,
)
from .resource_guard import PressureCheckpoint, prime_cpu_sampling, sample_pressure

logger = logging.getLogger(__name__)

INTERVAL_S = SWEEP_INTERVAL_S

# A sweep that finds this many changed files is not an incremental edit, it's a
# branch switch or a fresh pull. Rebuilding wholesale is cheaper than several
# hundred single file round trips, and it rebuilds the graph in one pass.
FULL_REINDEX_THRESHOLD = 50

#: Guards against a sweep starting while the previous one is still going. A
#: single asyncio loop runs this, so a plain flag is enough; there is no
#: preemption between the check and the set.
_sweep_in_progress = False
_sweep_started_at = 0.0


#: Re-exported from reindex_unit so the batch driver and this loop cannot drift
#: apart. Kept importable from here because that is where callers and tests
#: already reach for it.
_release_project_resources = release_project_resources


async def wait_for_system_headroom(
    max_percent: float = CPU_MAX_PERCENT,
    min_free_ram_mb: float = MIN_FREE_RAM_MB,
    poll_s: float = CPU_BACKOFF_S,
    max_wait_s: float = CPU_BACKOFF_MAX_WAIT_S,
) -> bool:
    """Block until the machine has both CPU and RAM headroom.

    Returns True when there is room to work, False if the machine stayed
    pressured for max_wait_s, in which case the caller should skip rather than
    pile on. This is the adaptive half of the resource budget and the only half
    that can see load this process did not create, which is the whole point:
    the user's own work has to win.

    This is the gate that decides whether to start work at all. The equivalent
    check *during* a long running index is PressureCheckpoint in
    resource_guard, which shares the same sampling rule but is synchronous,
    because index_project runs in a worker thread with no event loop to await.

    Degrades to "there is headroom" when psutil is unavailable, because a
    missing optional dependency must not silently disable reindexing. That
    falls out of sample_pressure returning None, so there is no second copy of
    the rule here to drift away from it.
    """
    waited = 0.0
    # The first cpu_percent() call with no interval returns a meaningless 0.0
    # (it has no previous sample to diff against), so prime it and throw the
    # result away rather than reading it as an idle machine.
    prime_cpu_sampling()
    await asyncio.sleep(0.1)

    while True:
        detail = sample_pressure(max_percent, min_free_ram_mb)
        if detail is None:
            return True

        if waited >= max_wait_s:
            logger.warning(
                "Machine under pressure for %.0fs (%s), skipping this sweep",
                waited, detail,
            )
            return False
        logger.info("Waiting %.0fs for headroom: %s", poll_s, detail)
        await asyncio.sleep(poll_s)
        waited += poll_s


# Old name kept so nothing that already imported it breaks.
wait_for_cpu_headroom = wait_for_system_headroom


#: Re-exported from reindex_unit. There were three readers of
#: state/projects.json differing only in which exceptions they caught; this
#: name stays so existing callers keep working, but the body lives in one place.
_read_registry = read_registry


def _decodes_as_utf8(abs_path: str) -> bool:
    """Would index_project be able to read this file?

    Mirrors its strict read (indexing.py:628) exactly, because that is the
    read whose failure put the file in quarantine in the first place. Any
    other test here would let the two disagree again.
    """
    try:
        Path(abs_path).read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return False
    except OSError as e:
        # Unreadable for a different reason now. Still nothing the indexer can
        # do with it, so leave it quarantined rather than offer a file that
        # will only fail again.
        logger.warning("Could not re-check quarantined %s: %s", abs_path, e)
        return False
    return True


def _log_quarantined(project_path: str, quarantined: list[str]) -> None:
    """Leave one trace per sweep for the files being held out of the index.

    A permanent silent skip is how a file goes missing from search with
    nothing to grep for. A line per file per hour is its own kind of
    unreadable, so this summarises instead.
    """
    if not quarantined:
        return
    names = sorted(quarantined)
    logger.info(
        "%d file(s) still unreadable in %s, not indexed: %s%s",
        len(names), project_path, ", ".join(names[:5]),
        ", ..." if len(names) > 5 else "",
    )


def find_changed_files(project_path: str) -> tuple[list[str], list[str]]:
    """Compare the project on disk against its manifest.

    Returns (changed, deleted). Changed covers new and modified files alike,
    since reindex_file handles either.

    `deleted` means "in the manifest, not in the scan set". That is two
    situations, not one: the file was removed from disk, or it is still there
    and is no longer indexable because the skip rules or the project's
    .gitignore changed since it was indexed. Both are reported here and both
    get evicted, because either way the stored chunks no longer describe
    anything the index should return. The caller evicts them with
    drop_manifest_key, which acts on the key; an is_file() check alone cannot
    see the second case, since that file is still sitting there readable.

    Uses scan_project, which is the same function index_project uses, so
    SKIP_DIRS, SKIP_FILES, SKIP_SUFFIXES, CODE_EXTENSIONS and the 500KB cap all
    still apply. Nothing gets picked up here that wouldn't have been indexed in
    the first place, and the skip rules only live in one place.
    """
    project_root, _pid, _index_dir, _chroma, manifest_path = _project_paths(project_path)

    if not manifest_path.exists():
        # Never indexed. Not this loop's job to decide it should be.
        return [], []

    try:
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        logger.error("Manifest unreadable for %s: %s", project_path, e)
        return [], []

    known = {k: v for k, v in raw.items() if not k.startswith("__")}

    changed = []
    seen = set()
    quarantined = []
    for abs_path in scan_project(project_path):
        try:
            rel = str(Path(abs_path).resolve().relative_to(project_root)).replace("\\", "/")
        except ValueError:
            continue
        seen.add(rel)

        # Recorded unreadable by a previous index.
        #
        # This function reads with errors="replace" and therefore always
        # succeeds, while index_project reads strictly and fails. Without a
        # check here the two disagree permanently: this function hashes the
        # replacement characters, sees no match against the sentinel, calls the
        # file changed, and hands it to an indexer that refuses it every time.
        # That is the loop that logged the same UnicodeDecodeError 98 times in
        # one run.
        #
        # But the skip has to be provisional, not a blacklist. It used to be
        # unconditional, which meant repairing the file to valid UTF-8 did not
        # bring it back: the hourly sweep skipped it forever and only a manual
        # force=True rebuild could recover it, silently, with the file missing
        # from search the whole time.
        #
        # So re-ask the only question that matters, the same strict way
        # index_project asks it: can this be decoded now? Still no, skip, and
        # the retry loop stays closed. Yes, the file was repaired, so lift the
        # quarantine and let the indexer have it.
        if known.get(rel) == UNREADABLE_SENTINEL:
            if _decodes_as_utf8(abs_path):
                logger.info(
                    "Unreadable quarantine lifted for %s: decodes as UTF-8 again", rel
                )
                changed.append(abs_path)
            else:
                quarantined.append(rel)
            continue

        # file_hash takes content, not a path. Read it the same way index_project
        # does (indexing.py:595) so the hashes are comparable.
        try:
            content = Path(abs_path).read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            logger.warning("Could not read %s: %s", abs_path, e)
            continue

        if known.get(rel) != file_hash(content):
            changed.append(abs_path)

    _log_quarantined(project_path, quarantined)

    deleted = [rel for rel in known if rel not in seen]
    return changed, deleted


async def _sweep_project(
    pid: str, entry: dict, model_cache, checkpoint: PressureCheckpoint | None = None
) -> bool:
    """Sweep one project. Returns True only if this call actually held the index
    lock and did the work, False if it bailed without touching the project's
    databases.

    The return value is what tells the caller whether releasing this project's
    cached database handles is safe. It is not cosmetic. Returning None here and
    releasing unconditionally is what closed the shared sqlite connection out
    from under a running /index-project, which then died with
    "Cannot operate on a closed database" and left large projects permanently
    __incomplete__ because they take longer than one sweep interval to index.
    """
    project_path = entry.get("project_path")
    if not project_path or not Path(project_path).exists():
        logger.warning("Project %s no longer exists on disk: %s", pid, project_path)
        return False

    # One project can take hours on its own, so the headroom gate has to reach
    # inside it. The same checkpoint covers both branches below: index_project
    # calls it from its worker thread, the per file loop calls it from here.
    if checkpoint is None:
        checkpoint = PressureCheckpoint()

    loop = asyncio.get_running_loop()

    changed, deleted = await loop.run_in_executor(
        None, partial(find_changed_files, project_path)
    )

    if not changed and not deleted:
        logger.debug("No changes in %s", project_path)
        return False

    logger.info(
        "Changes in %s: %d changed, %d deleted", project_path, len(changed), len(deleted)
    )

    # The lock is what stops this racing a manual /index-project. If someone is
    # already indexing, skip the sweep and catch it on the next pass one hour
    # from now. Waiting would just pile up sweeps behind a slow index.
    if not acquire_index_lock():
        logger.info("Index lock held by another job, skipping %s this pass", project_path)
        return False

    try:
        # Deletions first, one file at a time, never by rebuilding.
        #
        # This used to force a full rebuild of the whole project the moment any
        # file vanished, on the grounds that stale chunks could not be cleared
        # any other way. That was never true of the store: delete_by_source and
        # delete_edges_referencing_file are plain SQL deletes on the stored path and do
        # not care whether the file still exists. reindex_file just refused to
        # get that far for a missing file. It no longer does, so a deletion now
        # costs one SQL delete instead of re embedding thousands of untouched
        # files.
        #
        # Handled before the branch below so the rebuild decision is about
        # `changed` alone. No pressure check in this loop: these are row deletes
        # measured in milliseconds, not embedding work.
        #
        # find_changed_files returns `deleted` as manifest keys, and they stay
        # keys all the way down. They are not joined onto the project root,
        # because every path in `deleted` is already known to be outside the
        # scan set: find_changed_files built it as (manifest keys) minus (what
        # scan_project returned). That covers a file that vanished and a file
        # that is still on disk but no longer indexable, and both
        # mean its stored chunks are stale. The second kind used to never drop:
        # this loop asked reindex_file to do it, its is_file() gate saw a live
        # file, fell through, hashed it, matched the manifest, and returned
        # unchanged without saving, so the same paths came back as deleted on
        # every sweep. 74,358 log lines and 377 files re-read every ten minutes.
        #
        # Safe for quarantined files specifically, and the ordering that makes
        # it safe is load bearing: find_changed_files adds every scanned path to
        # `seen` before it checks UNREADABLE_SENTINEL, so a quarantined file is
        # never in `deleted` and never reaches this loop.
        dropped = 0
        for rel_path in deleted:
            # The key goes straight through. No absolute path is built around it
            # and none is derived back out, because that round trip is what kept
            # losing the key: a case only rename came back respelled, an
            # absolute out of root key could not be rebuilt at all, and a key
            # holding '..' collapsed somewhere else entirely. Each shape got its
            # own guard here and each guard was followed by a new shape. The
            # shapes were never the bug. drop_manifest_key takes the key itself
            # and never consults the filesystem, so there is nothing left to
            # lose it in.
            try:
                outcome = await loop.run_in_executor(
                    None, partial(drop_manifest_key, project_path, rel_path)
                )
                # `was_in_manifest`, not `deleted`. The delete is keyed on a
                # string and reports success for any string, so counting on
                # `deleted` alone let a key that matched no entry log
                # "Dropped 1 of 1" while the real entry sat there and came back
                # every sweep. A stuck entry that claims success is worse than
                # one that complains: nothing in the log points at it.
                if outcome.get("was_in_manifest"):
                    dropped += 1
                else:
                    logger.warning(
                        "Could not drop deleted %s from %s: %s",
                        rel_path, project_path, outcome,
                    )
            except Exception as e:
                logger.error(
                    "Failed dropping deleted %s: %s: %s", rel_path, type(e).__name__, e
                )
        if deleted:
            logger.info(
                "Dropped %d of %d deleted file(s) from %s",
                dropped, len(deleted), project_path,
            )

        # A change set big enough that per file calls stop being the cheap
        # option. Deletions no longer reach this branch on their own.
        if len(changed) >= FULL_REINDEX_THRESHOLD:
            reason = f"{len(changed)} files changed"
            # A previous pass that gave the machine back left a manifest naming
            # exactly the files whose chunks really are in the store, so
            # resuming keeps that work instead of wiping it and starting the
            # same large project over.
            #
            # Requiring every deletion to have actually been dropped before
            # resuming, rather than assuming it: a deletion that failed above
            # leaves stale chunks that only a wipe clears, which is the one
            # thing the old force-on-any-deletion rule got right.
            resuming = index_is_incomplete(project_path) and dropped == len(deleted)
            if resuming:
                reason += ", resuming an index that stopped early"
            logger.info("Full reindex of %s (%s)", project_path, reason)
            result = await loop.run_in_executor(
                None,
                partial(
                    index_project, project_path, model_cache,
                    force=not resuming, should_abort=checkpoint.pressure,
                ),
            )
            logger.info(
                "Reindexed %s: %d files, %d chunks, %d failed%s",
                project_path,
                result.get("files_indexed", 0),
                result.get("chunks_created", 0),
                result.get("files_failed", 0),
                f" (stopped early: {result['stopped_early']})"
                if result.get("stopped_early") else "",
            )
            return True

        done = 0
        for abs_path in changed:
            pressure = checkpoint.pressure()
            if pressure:
                logger.warning(
                    "Giving the machine back after %d of %d changed files in %s: %s "
                    "(the rest wait for the next sweep)",
                    done, len(changed), project_path, pressure,
                )
                break
            try:
                await loop.run_in_executor(
                    None, partial(reindex_file, project_path, abs_path, model_cache)
                )
                done += 1
            except Exception as e:
                logger.error("Failed to reindex %s: %s: %s", abs_path, type(e).__name__, e)

        logger.info("Reindexed %d of %d changed files in %s", done, len(changed), project_path)
        return True

    finally:
        release_index_lock()


async def auto_reindex_loop(get_model_cache) -> None:
    """Sweep every registered project every INTERVAL_S.

    Takes a callable rather than the model cache itself because the server
    loads models lazily, so at startup there may be nothing to hand over yet.
    """
    global _sweep_in_progress, _sweep_started_at

    logger.info(
        "Auto reindex running every %d minutes (CPU ceiling %.0f%%)",
        INTERVAL_S // 60, CPU_MAX_PERCENT,
    )

    while True:
        await asyncio.sleep(INTERVAL_S)

        model_cache = get_model_cache()
        # `is None`, not truthiness. ModelCache defines __len__ but not
        # __bool__, so an empty but perfectly usable cache is falsy, and this
        # skipped every sweep for as long as no model happened to be loaded
        # yet. index_project and reindex_file each resolve and load the model
        # they need, so an empty cache is not a reason to skip: it is the
        # normal state before the first sweep. When it was a truthiness test
        # this loop went silent for three days at logger.debug, which nothing
        # was reading, while search failed loudly for the same root cause.
        if model_cache is None:
            logger.warning("No model cache available, skipping this sweep")
            continue

        registry = _read_registry()
        if not registry:
            continue

        # Overlap guard. A full sweep of every registered project can take far
        # longer than the interval, and an hourly timer firing into a sweep
        # that has not finished stacks them until the machine has no cores
        # left. Skipping is always correct here: the next tick picks up
        # whatever this one would have.
        if _sweep_in_progress:
            logger.warning(
                "Previous sweep still running after %.0f minutes, skipping this tick",
                (time.time() - _sweep_started_at) / 60.0,
            )
            continue

        if not await wait_for_cpu_headroom():
            continue

        _sweep_in_progress = True
        _sweep_started_at = time.time()
        started = _sweep_started_at
        swept = 0
        try:
            # Ordered by embedding model rather than whatever order the registry
            # happens to be in. An embedder is 1 to 2 GB resident and ModelCache
            # holds only a couple, so an arbitrary order makes a single pass
            # evict and reload the same models repeatedly. Same plan the batch
            # driver uses, so the two cannot disagree about ordering.
            planned = plan_sweep(registry)
            last_model: str | None = None
            #: Did ANY project in the current model group actually do work? Not
            #: the last one alone. plan_sweep groups several projects under one
            #: model, and the eviction below fires once per group boundary, so a
            #: group whose earlier members worked and whose last member skipped
            #: would read as idle if this were a single project flag.
            group_did_work = False
            for project in planned:
                # Re-check between projects, not just once up front. A sweep
                # runs for hours, and the user can sit down at the machine at
                # any point during it.
                if not await wait_for_system_headroom():
                    logger.warning(
                        "Machine under pressure, abandoning the rest of this sweep",
                    )
                    break

                # Finished with the previous model group: let it go rather than
                # holding it for the rest of the sweep. This process cannot exit
                # to reclaim memory the way the batch driver can, so evicting
                # what it demonstrably no longer needs is the only lever it has.
                #
                # Only when the group actually did work. evict_all throws away
                # every resident model, including one a concurrently running
                # /index-project is embedding with right now, and reloading SFR
                # costs 135s. A sweep that skipped every project on a busy lock
                # has nothing to release and no reason to charge the running job
                # for it. Measured before this gate: 4 evictions in 104 minutes
                # during one reindex, about 8.6 percent of its wall clock.
                #
                # Safe to skip, never unbounded: ModelCache._enforce_max_resident
                # caps residency at DEFAULT_MAX_RESIDENT on every load, and
                # evict_all's own docstring says bounding is the caller's job.
                # This is a release sooner optimisation, not the safety net.
                if last_model is not None and project.model != last_model and group_did_work:
                    try:
                        model_cache.evict_all()
                    except AttributeError:
                        pass  # a plain embedder was passed, nothing to evict
                if last_model is not None and project.model != last_model:
                    group_did_work = False
                last_model = project.model

                entry = registry.get(project.pid) or {"project_path": project.path}
                try:
                    proceeded = await _sweep_project(project.pid, entry, model_cache)
                    # Drop this project's database handles before moving on.
                    # ChromaStore caches a connection per database forever, so
                    # a sweep across every registered project otherwise ends
                    # holding one open handle per project for the life of the
                    # process, and each carries its own page cache.
                    #
                    # Only when this pass actually held the lock and did the
                    # work. ChromaStore.evict_cache asks for the shared
                    # connection to be closed, and a manual /index-project holds
                    # the lock for its whole run, so releasing after a skipped
                    # pass targets a database a live index job is still writing
                    # through. The count is gated the same way: a pass that
                    # skipped every project on a busy lock reported one project
                    # per registered project, which made lock contention read as
                    # a healthy sweep in the log below.
                    if proceeded:
                        _release_project_resources(project.pid)
                        swept += 1
                    # Accumulated across the whole model group, never reset per
                    # project, so the eviction above sees the group's real state.
                    group_did_work = group_did_work or proceeded
                except Exception as e:
                    # One bad project must not kill the loop for the others, or
                    # a single unreadable repo silently stops all reindexing
                    # forever.
                    logger.error(
                        "Sweep failed for %s: %s: %s",
                        project.path, type(e).__name__, e,
                        exc_info=True,
                    )
        finally:
            _sweep_in_progress = False

        logger.info(
            "Reindex sweep done: %d project(s) in %.1fs",
            swept, time.time() - started,
        )
