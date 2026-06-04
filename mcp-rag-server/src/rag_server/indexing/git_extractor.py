"""Co-change graph extractor using git history.

Files that change together in the same commit often have implicit dependencies
that imports alone can't capture — shared concepts, coordinated feature work,
coupled tests. Walking git history surfaces these relationships.

Algorithm: for each of the last N commits, collect all modified file paths.
Any two files in the same commit are a co-change pair. Pairs that appear
together in at least MIN_COCHANGE_COUNT commits become graph edges.

Requires PyDriller: pip install pydriller
Falls back to [] when PyDriller is not installed or the path is not a git repo.
"""

import logging
from collections import defaultdict
from pathlib import Path

logger = logging.getLogger(__name__)

_MAX_COMMITS = 1000
_MIN_COCHANGE_COUNT = 2


def extract_co_change_edges(project_path: str) -> list:
    """Walk git history and return co-change GraphEdge objects.

    Returns [] when PyDriller is not installed, the path is not a git repo,
    or on any other error — never blocks indexing.
    """
    try:
        from pydriller import Repository
    except ImportError:
        logger.debug("PyDriller not installed — skipping co-change graph extraction")
        return []

    try:
        return _extract(project_path, Repository)
    except Exception:
        logger.warning("Co-change extraction failed unexpectedly — git history will not contribute graph edges", exc_info=True)
        return []


def _extract(project_path: str, Repository) -> list:
    from rag_server.ports.graph_port import GraphEdge

    co_changes: dict[tuple[str, str], int] = defaultdict(int)

    for i, commit in enumerate(Repository(project_path).traverse_commits()):
        if i >= _MAX_COMMITS:
            break
        files = []
        for m in commit.modified_files:
            path = m.new_path or m.old_path
            if path:
                files.append(path.replace("\\", "/"))

        # All pairs of files in this commit co-changed
        for a in range(len(files)):
            for b in range(a + 1, len(files)):
                pair = (min(files[a], files[b]), max(files[a], files[b]))
                co_changes[pair] += 1

    edges = [
        GraphEdge(
            source_file=src,
            source_symbol="<co_change>",
            target_file=tgt,
            target_symbol=f"<co_change:count={n}>",
            edge_type="co_change",
            confidence="GIT",
        )
        for (src, tgt), n in co_changes.items()
        if n >= _MIN_COCHANGE_COUNT
    ]

    logger.info(
        "Co-change graph: %d pairs from %d commits, %d edges (count >= %d)",
        len(co_changes), min(i + 1, _MAX_COMMITS), len(edges), _MIN_COCHANGE_COUNT,
    )
    return edges
