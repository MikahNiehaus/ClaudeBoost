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

from .config import STATE_DIR
from .indexing import (
    _project_paths,
    acquire_index_lock,
    file_hash,
    index_project,
    reindex_file,
    release_index_lock,
    scan_project,
)

logger = logging.getLogger(__name__)

INTERVAL_S = 60 * 60

# A sweep that finds this many changed files is not an incremental edit, it's a
# branch switch or a fresh pull. Rebuilding wholesale is cheaper than several
# hundred single file round trips, and it rebuilds the graph in one pass.
FULL_REINDEX_THRESHOLD = 50


def _read_registry() -> dict:
    path = STATE_DIR / "projects.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        logger.error("Could not read the project registry: %s", e)
        return {}


def find_changed_files(project_path: str) -> tuple[list[str], list[str]]:
    """Compare the project on disk against its manifest.

    Returns (changed, deleted). Changed covers new and modified files alike,
    since reindex_file handles either.

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
    for abs_path in scan_project(project_path):
        try:
            rel = str(Path(abs_path).resolve().relative_to(project_root)).replace("\\", "/")
        except ValueError:
            continue
        seen.add(rel)

        # file_hash takes content, not a path. Read it the same way index_project
        # does (indexing.py:595) so the hashes are comparable.
        try:
            content = Path(abs_path).read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            logger.warning("Could not read %s: %s", abs_path, e)
            continue

        if known.get(rel) != file_hash(content):
            changed.append(abs_path)

    deleted = [rel for rel in known if rel not in seen]
    return changed, deleted


async def _sweep_project(pid: str, entry: dict, code_embedder) -> None:
    project_path = entry.get("project_path")
    if not project_path or not Path(project_path).exists():
        logger.warning("Project %s no longer exists on disk: %s", pid, project_path)
        return

    loop = asyncio.get_running_loop()

    changed, deleted = await loop.run_in_executor(
        None, partial(find_changed_files, project_path)
    )

    if not changed and not deleted:
        logger.debug("No changes in %s", project_path)
        return

    logger.info(
        "Changes in %s: %d changed, %d deleted", project_path, len(changed), len(deleted)
    )

    # The lock is what stops this racing a manual /index-project. If someone is
    # already indexing, skip the sweep and catch it on the next pass ten minutes
    # from now. Waiting would just pile up sweeps behind a slow index.
    if not acquire_index_lock():
        logger.info("Index lock held by another job, skipping %s this pass", project_path)
        return

    try:
        # Deletions leave stale chunks behind that reindex_file cannot clear on
        # its own, so a deletion always means a full rebuild. Same for a change
        # set big enough that per file calls stop being the cheap option.
        if deleted or len(changed) >= FULL_REINDEX_THRESHOLD:
            reason = "files were deleted" if deleted else f"{len(changed)} files changed"
            logger.info("Full reindex of %s (%s)", project_path, reason)
            result = await loop.run_in_executor(
                None, partial(index_project, project_path, code_embedder, force=True)
            )
            logger.info(
                "Reindexed %s: %d files, %d chunks, %d failed",
                project_path,
                result.get("files_indexed", 0),
                result.get("chunks_created", 0),
                result.get("files_failed", 0),
            )
            return

        for abs_path in changed:
            try:
                await loop.run_in_executor(
                    None, partial(reindex_file, project_path, abs_path, code_embedder)
                )
            except Exception as e:
                logger.error("Failed to reindex %s: %s: %s", abs_path, type(e).__name__, e)

        logger.info("Reindexed %d changed files in %s", len(changed), project_path)

    finally:
        release_index_lock()


async def auto_reindex_loop(get_embedder) -> None:
    """Sweep every registered project every INTERVAL_S.

    Takes a callable rather than the embedder itself because the server loads the
    model lazily, so at startup there may be nothing to hand over yet.
    """
    logger.info("Auto reindex running every %d minutes", INTERVAL_S // 60)

    while True:
        await asyncio.sleep(INTERVAL_S)

        embedder = get_embedder()
        if not embedder:
            logger.debug("No embedder yet, skipping this sweep")
            continue

        registry = _read_registry()
        if not registry:
            continue

        started = time.time()
        for pid, entry in registry.items():
            try:
                await _sweep_project(pid, entry, embedder)
            except Exception as e:
                # One bad project must not kill the loop for the others, or a
                # single unreadable repo silently stops all reindexing forever.
                logger.error(
                    "Sweep failed for %s: %s: %s",
                    entry.get("project_path", pid), type(e).__name__, e,
                    exc_info=True,
                )

        logger.info(
            "Reindex sweep done: %d project(s) in %.1fs",
            len(registry), time.time() - started,
        )
