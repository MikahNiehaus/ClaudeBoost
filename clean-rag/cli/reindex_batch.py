#!/usr/bin/env python
"""Reindex every registered project once, under a bounded resource budget.

    python clean-rag/cli/reindex_batch.py              # run it
    python clean-rag/cli/reindex_batch.py --dry-run    # show the plan only
    python clean-rag/cli/reindex_batch.py --stop       # ask a running one to stop

The one shot backfill counterpart to the server's hourly incremental sweep.
Both drive the same plan and the same per project work (server/reindex_unit.py);
what differs is the schedule and the policy, which is the only thing that should
differ.

Why it is a separate process rather than an endpoint: a single project can take
hours, so driving it over HTTP would mean a request open that long, and torch
never returns CPU memory, so the only real way to reclaim a ratcheting heap is
to exit and start again. A server cannot do that without dropping every request.

Exit codes:
    0   finished, or stopped on request
    1   finished with failures
    75  over the memory ceiling on purpose. Run the same command again and it
        picks up where it left off.

There is deliberately NO supervisor process. Progress is saved after every
project, so re-running the bare command is already a complete recovery story,
and a wrapper would only be automating one keystroke. The obvious candidate,
ManagedServer in scripts/rag-supervisor.py, is actively wrong here: it
restarts on ANY exit code, so it would relaunch this job forever after it
finished successfully.
"""

from __future__ import annotations

import argparse
import gc
import json
import os
import sys
import time
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

# Keep the activation spike down before anything imports config, which reads
# this at import time. Measured peak RSS while embedding: batch 32 costs
# 3077 MB on CodeRankEmbed and 4149 MB on SFR, batch 8 costs 1559 MB and
# 2886 MB. Batch 128 is barely worse than 32, so the spike saturates early and
# going small is close to free.
os.environ.setdefault("CLEAN_RAG_EMBED_BATCH_SIZE", "8")

_CLEAN_RAG_HOME = Path(os.environ.get("CLEAN_RAG_HOME") or Path(__file__).resolve().parent.parent)
sys.path.insert(0, str(_CLEAN_RAG_HOME))

import psutil  # noqa: E402

from server.auto_reindex import wait_for_system_headroom  # noqa: E402
from server.indexing import (  # noqa: E402
    acquire_index_lock,
    index_is_incomplete,
    index_project,
    release_index_lock,
)
from server.lang_router import ModelCache  # noqa: E402
from server.reindex_unit import (  # noqa: E402
    Outcome,
    PlannedProject,
    model_groups,
    plan_sweep,
    release_project_resources,
)
from server.resource_guard import PressureCheckpoint, prime_cpu_sampling  # noqa: E402

STATE_DIR = _CLEAN_RAG_HOME / "state"
PROGRESS = STATE_DIR / "reindex-progress.json"
STOP_FILE = STATE_DIR / "reindex-STOP"

#: The reason ``index_project`` records when it stops because the user asked
#: it to. Deliberately not shaped like a pressure reason ("CPU 91% (limit
#: 80%)"), because the two mean opposite things about what happens next: a
#: pressure pause is "retry when the machine is quiet", a stop is "do not
#: retry until asked again", and the driver branches on exactly this string.
STOP_REASON = "stop requested"

#: Exit above this RSS and let the caller relaunch. Comfortably above the
#: 4.2 GB measured worst case (SFR resident plus its activation spike) so a
#: healthy run never trips it, low enough to catch a real ratchet early.
RSS_CEILING_MB = float(os.environ.get("CLEAN_RAG_REINDEX_RSS_CEILING_MB", "6000"))
EXIT_RESTART_ME = 75

#: A project that keeps yielding to the resource guard gets many attempts; one
#: that keeps raising gets few. Counting both against one budget meant a
#: genuinely broken project burned two hundred attempts looking exactly like a
#: healthy one waiting for a quiet machine.
#: Outer backstop only. A project yielding to the machine but still doing work
#: must not trip this, so it is set far above what any real project needs:
#: Nectar at 4492 files takes roughly 900 cycles at the observed 3 to 30 files
#: per pause. It exists so a project that somehow progresses one file per cycle
#: forever still terminates, which the stall counter alone cannot catch because
#: any progress resets it.
MAX_PAUSES_PER_PROJECT = 5000

#: The real give up signal: consecutive pauses that indexed NOTHING. Reset by
#: any progress. Small, because genuinely making no progress several times in a
#: row means something is wrong rather than busy.
MAX_STALLED_PAUSES = 25

MAX_ERRORS_PER_PROJECT = 3

#: Floor between attempts. Without it a project that fails instantly spins its
#: whole attempt budget in a burst; the resource guard's own wait only paces the
#: paused path, not the errored one.
RETRY_FLOOR_S = 5.0

#: Gap between attempts to take the index lock. Longer than RETRY_FLOOR_S
#: because the thing being waited on is another process finishing a whole
#: project, not a moment of CPU pressure. Together with MAX_STALLED_PAUSES this
#: is the real deadline for acquiring the lock: 25 x 30s, so a project gives up
#: after roughly 12 minutes of a lock it cannot get, records GAVE_UP, and lets
#: the run move on. Progress is saved per project, so re-running picks it up.
LOCK_WAIT_S = 30.0

_proc = psutil.Process(os.getpid())


def rss_mb() -> float:
    return _proc.memory_info().rss / 1024**2


def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def stop_requested() -> bool:
    """Has someone run ``--stop`` since this process started?"""
    return STOP_FILE.exists()


def abort_check(checkpoint: PressureCheckpoint) -> Callable[[], str | None]:
    """The one abort callable ``index_project`` consults before every file.

    ``index_project`` takes a single ``should_abort``, so a stop request and
    resource pressure have to compose into one callable. Handing it only
    ``checkpoint.pressure`` left the stop file checked nowhere but the top of
    the retry loop and between projects, which means ``--stop`` did nothing for
    as long as a single project takes -- hours, by this module's own docstring,
    and 4492 files on the largest registered project. A flag that silently does
    nothing for hours reads as a broken flag.

    Stop wins over pressure and returns its own reason, so the caller can tell a
    deliberate stop from "the machine got busy" without re-stat'ing the file and
    racing itself.

    The stop check is a single ``stat`` and is not interval throttled the way
    the pressure sample is. Sampling CPU has a real cost and a documented
    minimum useful interval; a ``stat`` next to a measured 4.65s average per
    file does not, and throttling it would only add latency to the one thing
    the user is waiting on.
    """
    def should_abort() -> str | None:
        if stop_requested():
            return STOP_REASON
        return checkpoint.pressure()

    return should_abort


def _usable_progress(loaded: object) -> dict | None:
    """Return *loaded* only if it is actually shaped like progress.

    Syntactically valid JSON of the wrong TYPE never reaches the except below,
    so widening the exception tuple did nothing for it: a file holding
    ``[1, 2, 3]`` parsed fine and then blew up later on ``pid in
    state["done"]`` with a TypeError, and it did so even under --dry-run, the
    one mode that is supposed to be a safe preflight.

    Same fault class as the byte level corruption, so it gets the same answer:
    start over and say why, rather than crash.
    """
    if not isinstance(loaded, dict):
        return None
    done = loaded.get("done")
    failed = loaded.get("failed")
    if not isinstance(done, dict) or not isinstance(failed, dict):
        return None
    return loaded


def load_progress() -> dict:
    if PROGRESS.exists():
        try:
            usable = _usable_progress(json.loads(PROGRESS.read_text(encoding="utf-8")))
            if usable is not None:
                return usable
            log(f"{PROGRESS} is not shaped like progress data; "
                f"starting from the first project")
        except (OSError, ValueError) as exc:
            # ValueError, not json.JSONDecodeError. Both JSONDecodeError and
            # UnicodeDecodeError subclass ValueError, and only the first
            # subclasses nothing else, so naming JSONDecodeError alone let a
            # UnicodeDecodeError straight through. That is not hypothetical:
            # this file records real project paths, which can hold non ASCII,
            # and a kill mid write (the same interruption this driver already
            # handles for the memory ceiling) truncates a multi byte sequence
            # and makes the next run crash instead of starting over.
            #
            # Starting over is the right fallback, but doing it silently is not:
            # it looks identical to a first run while quietly re-indexing every
            # project that was already done.
            log(f"could not read {PROGRESS} ({type(exc).__name__}: {exc}); "
                f"starting from the first project")
    return {"done": {}, "failed": {}}


def save_progress(state: dict) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    PROGRESS.write_text(json.dumps(state, indent=2), encoding="utf-8")


async def reindex_project_fully(
    project: PlannedProject, cache: ModelCache, checkpoint: PressureCheckpoint
) -> tuple[Outcome, dict]:
    """Drive one project to completion, resuming across pauses.

    Always a full rebuild on the first pass: the embedding model is changing,
    and without force the files whose content did not change keep their vectors
    from the OLD model. Same dimension, different embedding space, so nothing
    downstream can tell those apart from real hits.

    Termination invariant: every path through the loop either returns or
    advances one of `pauses`, `stalled` or `errors`. Adding a branch that only
    sleeps and continues breaks it, and that is not hypothetical: the index
    lock branch did exactly that and could spin without bound.
    """
    pauses = errors = 0
    #: Consecutive pauses that indexed NOTHING. Reset by any real progress.
    #: This, not `pauses`, is what decides a project is stuck: see
    #: MAX_STALLED_PAUSES.
    stalled = 0
    last: dict = {}

    abort = abort_check(checkpoint)

    while (
        pauses < MAX_PAUSES_PER_PROJECT
        and stalled < MAX_STALLED_PAUSES
        and errors < MAX_ERRORS_PER_PROJECT
    ):
        if stop_requested():
            return Outcome.GAVE_UP, last
        if rss_mb() > RSS_CEILING_MB:
            return Outcome.OVER_MEMORY, last

        # The one waiting mechanism, shared with the hourly sweep. Do not add a
        # second one here: two loops disagreeing about what "busy" means is how
        # a throttle becomes advisory.
        if not await wait_for_system_headroom():
            # Never even started, so nothing could have progressed. Counts
            # against both budgets.
            pauses += 1
            stalled += 1
            time.sleep(RETRY_FLOOR_S)
            continue

        resuming = index_is_incomplete(project.path)
        if not acquire_index_lock("reindex-batch"):
            # Counted, not just slept through. This branch used to `continue`
            # without touching any of the three budgets, so a lock holder that
            # never let go (the server's own hourly sweep on a big project is
            # exactly that) spun this loop with no cap at all: mocked to always
            # fail, it produced 180,000+ log lines before needing a force kill.
            #
            # It counts the same way the headroom branch above does, because it
            # is the same class of event: the pass never started, so nothing
            # could have progressed. `stalled` is the budget that matters here,
            # and its reset semantics still hold, since any pass that indexes
            # files clears it.
            pauses += 1
            stalled += 1
            log(f"    index lock held elsewhere, waiting "
                f"(pause {pauses}/{MAX_PAUSES_PER_PROJECT}, "
                f"stalled {stalled}/{MAX_STALLED_PAUSES})")
            time.sleep(LOCK_WAIT_S)
            continue
        try:
            last = index_project(
                project.path, cache,
                force=not resuming,
                should_abort=abort,
            )
        except Exception as exc:
            errors += 1
            log(f"    ERROR ({errors}/{MAX_ERRORS_PER_PROJECT}) "
                f"{type(exc).__name__}: {exc}")
            time.sleep(RETRY_FLOOR_S)
            continue
        finally:
            try:
                release_index_lock()
            except Exception:
                pass

        if last.get("stopped_early") == STOP_REASON:
            # Not a pause. Counting a stop against the pause budget would sleep
            # RETRY_FLOOR_S and log "paused" for something the user asked to
            # end now, and the retry would only be turned away by the check at
            # the top of this loop anyway.
            return Outcome.GAVE_UP, last

        if index_is_incomplete(project.path):
            pauses += 1
            # A pause that indexed files is PROGRESS, not a stall. Counting
            # those against the give up budget is what would have abandoned a
            # healthy project: ClaudeBoost reached 98 of 200 pauses while
            # steadily doing 3 to 30 files a cycle, and Nectar at 4492 files
            # needs roughly 900 such cycles, so it would have been recorded
            # GAVE_UP having never once failed to make progress.
            #
            # files_indexed counts only what THIS pass re-embedded (unchanged
            # files go to files_unchanged), so it is exactly the "did anything
            # happen" signal, and it was already being logged and discarded.
            progressed = last.get("files_indexed", 0) > 0
            stalled = 0 if progressed else stalled + 1
            log(f"    paused after {last.get('files_indexed', 0)} files "
                f"(pause {pauses}/{MAX_PAUSES_PER_PROJECT}, "
                f"stalled {stalled}/{MAX_STALLED_PAUSES}), rss {rss_mb():.0f} MB")
            if rss_mb() > RSS_CEILING_MB:
                return Outcome.OVER_MEMORY, last
            time.sleep(RETRY_FLOOR_S)
            continue

        return Outcome.COMPLETED, last

    return (Outcome.ERRORED if errors >= MAX_ERRORS_PER_PROJECT else Outcome.GAVE_UP), last


async def run(dry_run: bool = False) -> int:
    # for_rebuild: this driver discards each index and rebuilds it, so group by
    # the model the router will pick now, not the one the old vectors were made
    # with. It also gets an exact file count from the same walk.
    planned = plan_sweep(for_rebuild=True)
    if not planned:
        log("no indexable projects registered")
        return 0

    state = load_progress()
    groups = model_groups(planned)
    total = sum(p.size for p in planned)

    log(f"{len(planned)} projects across {len(groups)} model group(s), "
        f"~{total} files, rss {rss_mb():.0f} MB, ceiling {RSS_CEILING_MB:.0f} MB")
    for model, members in groups:
        name = (model or "unindexed").split("/")[-1]
        log(f"  {name}: {len(members)} project(s), ~{sum(m.size for m in members)} files")
        for m in members:
            mark = " [done]" if m.pid in state["done"] else ""
            log(f"      {m.size:>6}  {m.path}{mark}")

    if dry_run:
        log("dry run, nothing indexed")
        return 0

    prime_cpu_sampling()
    checkpoint = PressureCheckpoint()
    started = time.time()
    failures = 0

    for model, members in groups:
        # One resident embedder: this loop finishes an entire group before
        # moving on, so a second slot could only hold a model it will not use
        # again.
        cache = ModelCache(max_resident=1)
        log(f"model group {(model or 'unindexed').split('/')[-1]} "
            f"({len(members)} projects)")

        for project in members:
            if stop_requested():
                log("stop requested")
                save_progress(state)
                return 0
            if project.pid in state["done"]:
                continue

            log(f"START {project.path} (~{project.size} files, rss {rss_mb():.0f} MB)")
            t0 = time.time()
            outcome, result = await reindex_project_fully(project, cache, checkpoint)

            if outcome is Outcome.OVER_MEMORY:
                log(f"    rss {rss_mb():.0f} MB over ceiling; exiting {EXIT_RESTART_ME} "
                    f"to be relaunched clean (progress is saved)")
                save_progress(state)
                return EXIT_RESTART_ME

            if outcome is Outcome.COMPLETED:
                log(f"    DONE {result.get('files_indexed', 0)} files, "
                    f"{result.get('chunks_created', 0)} chunks, "
                    f"{(time.time() - t0) / 60:.1f} min, rss {rss_mb():.0f} MB")
                state["done"][project.pid] = {
                    "path": project.path,
                    "files": result.get("files_indexed", 0),
                    "chunks": result.get("chunks_created", 0),
                    "model": project.model,
                    "finished": datetime.now(timezone.utc).isoformat(),
                }
                state["failed"].pop(project.pid, None)
            elif stop_requested():
                # It did not finish because the user asked it to stop, which is
                # not a failure. Recording it under "failed" would make --stop
                # report a broken project and, once the last group ended, a
                # nonzero exit code for doing exactly what it was asked.
                #
                # The partial index is deliberately left in place and stays
                # resumable. index_project writes a file into the manifest only
                # once its chunks are really in the store, so what is on disk is
                # a truthful subset rather than a half written index, and
                # __incomplete__ is what keeps search from serving it as
                # finished. Discarding it would throw away hours of real
                # embedding to honour a request that means "give me my machine
                # back", not "undo what you have done"; the next run sees
                # index_is_incomplete() and resumes with force off.
                log(f"    stopped on request after "
                    f"{result.get('files_indexed', 0)} files; the partial index "
                    f"is kept and will resume on the next run")
                save_progress(state)
                return 0
            else:
                failures += 1
                log(f"    {outcome.value.upper()}, moving on")
                state["failed"][project.pid] = outcome.value

            save_progress(state)
            release_project_resources(project.pid)

        cache.evict_all()
        gc.collect()
        log(f"    group done, rss {rss_mb():.0f} MB")

    log(f"FINISHED: {len(state['done'])} done, {failures} failed, "
        f"{(time.time() - started) / 3600:.1f} h")
    return 1 if failures else 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Reindex every registered project once, under a resource budget"
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Print the plan and exit without indexing")
    parser.add_argument("--stop", action="store_true",
                        help="Ask a running batch reindex to stop after the current file")
    parser.add_argument("--reset", action="store_true",
                        help="Forget recorded progress and start from the first project")
    args = parser.parse_args()

    STATE_DIR.mkdir(parents=True, exist_ok=True)

    if args.stop:
        STOP_FILE.write_text(f"stop requested {datetime.now():%Y-%m-%d %H:%M:%S}\n",
                             encoding="utf-8")
        print(f"Stop requested. Remove {STOP_FILE} before starting again.")
        return 0

    if STOP_FILE.exists():
        # A leftover stop file would end the run instantly and look like a
        # silent no op, so clear it on an explicit start.
        STOP_FILE.unlink()

    if args.reset and PROGRESS.exists():
        PROGRESS.unlink()
        print("Progress reset.")

    import asyncio

    return asyncio.run(run(dry_run=args.dry_run))


if __name__ == "__main__":
    sys.exit(main())
