"""bad-cop adversarial test, NOT part of the reviewed diff.

Proves: reindex_file's new incremental deletion path
(clean-rag/server/indexing.py, "Resolved before the embedder on purpose"
block) only calls graph.delete_edges_for_file(rel_path), which is
`DELETE FROM edges WHERE source_file = ?` (graph_store.py:458-461). It never
calls delete_ghost_edges(), which is the only code path that also matches on
target_file. delete_ghost_edges is called exclusively from index_project's
post-processing step (indexing.py ~line 770), which a deletion no longer
reaches now that auto_reindex._sweep_project drops single deleted files via
reindex_file instead of forcing a full index_project rebuild
(auto_reindex.py, "Deletions first, one file at a time, never by rebuilding").

Net effect: an edge whose TARGET is the deleted file (some other file that
imports/calls into it) survives forever. There is no file left to reindex it
away, and no other code path re-runs delete_ghost_edges outside a full
force rebuild. mode=graph search can keep walking into a file that no
longer exists in the store.

This is the same project rig and StubEmbedder used by
test_manifest_checkpoint_and_deletion.py so the fixtures are proven
already; only the assertion differs.
"""

import hashlib
import math
import sys
from pathlib import Path

import pytest

CLEAN_RAG = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(CLEAN_RAG))

from server import indexing  # noqa: E402

COLLECTION = "codebase"


class StubEmbedder:
    model_name = "stub-embedder"
    _DIM = 256

    def _vec(self, text: str) -> list[float]:
        v = [0.0] * self._DIM
        for tok in text.lower().split():
            h = int(hashlib.sha256(tok.encode("utf-8")).hexdigest(), 16)
            v[h % self._DIM] += 1.0 if (h // self._DIM) % 2 == 0 else -1.0
        norm = math.sqrt(sum(x * x for x in v)) or 1.0
        return [x / norm for x in v]

    def embed(self, texts):
        return [self._vec(t) for t in texts]

    def embed_query(self, text):
        return self._vec(text)


def _project(root: Path, n_files: int = 6) -> Path:
    """Ring import graph: file f imports module (f+1) % n.

    So module_05 imports module_00 -- an edge whose TARGET is module_00,
    living on a DIFFERENT source file. That is exactly the edge
    delete_edges_for_file(module_00) cannot reach, because it only matches
    source_file.
    """
    root.mkdir(parents=True, exist_ok=True)
    for f in range(n_files):
        header = f"import os\nimport json\nfrom module_{(f + 1) % n_files:02d} import helper\n"
        body = header + "\n".join(
            f'''
def handler_{f}_{i}(payload, retries=3):
    """Process one payload and return a normalised record."""
    total = 0
    for index, item in enumerate(payload.get("items", [])):
        if item.get("skip"):
            continue
        total += int(item.get("amount", 0)) * (index + 1)
    if total > 1000 and retries > 0:
        return handler_{f}_{i}({{"items": []}}, retries - 1)
    return {{"total": total, "count": len(payload.get("items", []))}}
'''
            for i in range(4)
        )
        (root / f"module_{f:02d}.py").write_text(body, encoding="utf-8")
    return root


@pytest.fixture
def rig(tmp_path, monkeypatch):
    monkeypatch.setattr(indexing, "DATABASES_DIR", tmp_path / "databases")
    monkeypatch.setattr(indexing, "STATE_DIR", tmp_path / "state")
    monkeypatch.setattr(indexing, "INDEX_MANIFEST_CHECKPOINT_S", 0.0)
    project = _project(tmp_path / "proj")
    paths = indexing._project_paths(str(project))
    return project, paths


def _edges_targeting(graph_db: Path, rel_path: str) -> int:
    import sqlite3

    conn = sqlite3.connect(str(graph_db))
    try:
        return conn.execute(
            "SELECT COUNT(*) FROM edges WHERE target_file = ?", (rel_path,)
        ).fetchone()[0]
    finally:
        conn.close()


def _all_edges(graph_db: Path) -> set:
    import sqlite3

    conn = sqlite3.connect(str(graph_db))
    try:
        return set(
            conn.execute(
                "SELECT source_file, source_symbol, target_file, target_symbol,"
                " edge_type FROM edges"
            ).fetchall()
        )
    finally:
        conn.close()


def test_edges_targeting_a_deleted_file_survive_incremental_deletion(rig):
    """The bug. delete_ghost_edges is only reachable through a full
    index_project rebuild's post-processing step; the incremental deletion
    path in reindex_file never calls it, only delete_edges_for_file, which
    matches source_file, not target_file."""
    project, (_root, _pid, index_dir, _chroma, _manifest) = rig
    indexing.index_project(str(project), StubEmbedder(), force=True)

    graph_db = index_dir / "graph.db"
    before = _edges_targeting(graph_db, "module_00.py")
    assert before > 0, (
        "module_05 should hold a resolved edge targeting module_00.py "
        "(ring import); the fixture proves nothing without it"
    )

    victim = project / "module_00.py"
    victim.unlink()
    result = indexing.reindex_file(str(project), str(victim), StubEmbedder())
    assert result.get("deleted") is True, f"expected a deletion, got {result}"

    after = _edges_targeting(graph_db, "module_00.py")
    assert after == 0, (
        f"{after} edge(s) still target module_00.py after it was deleted "
        f"through the incremental path (had {before} before); "
        f"delete_edges_for_file only matches source_file, so mode=graph "
        f"search can still walk into a file that no longer exists"
    )


def test_graph_traversal_stops_at_a_deleted_file(rig):
    """The user-visible half of the same bug: search.py builds mode=graph
    neighbours straight out of get_neighbours() edges (search.py:566-577), so
    while a ghost edge exists, a live file's neighbours still include a file
    that is not on disk. Asserted through the store's real API, not SQL."""
    from server.graph_store import SQLiteGraphStore

    project, (_root, _pid, index_dir, _chroma, _manifest) = rig
    indexing.index_project(str(project), StubEmbedder(), force=True)
    graph_db = index_dir / "graph.db"

    def neighbours_of(rel: str) -> set:
        edges = SQLiteGraphStore(str(graph_db)).get_neighbours(rel, depth=1)
        return {e.target_file for e in edges} | {e.source_file for e in edges}

    assert "module_00.py" in neighbours_of("module_05.py"), (
        "fixture is meaningless unless module_05 reaches module_00 before deletion"
    )

    (project / "module_00.py").unlink()
    indexing.reindex_file(str(project), str(project / "module_00.py"), StubEmbedder())

    assert "module_00.py" not in neighbours_of("module_05.py"), (
        "mode=graph search can still walk from module_05 into deleted module_00"
    )


def test_deleting_one_file_leaves_every_unrelated_edge_intact(rig):
    """C2. Over-deleting is not a fix: only edges incident to the deleted path
    may go. Everything else must be byte-identical."""
    project, (_root, _pid, index_dir, _chroma, _manifest) = rig
    indexing.index_project(str(project), StubEmbedder(), force=True)
    graph_db = index_dir / "graph.db"

    before = _all_edges(graph_db)
    expected = {e for e in before if e[0] != "module_00.py" and e[2] != "module_00.py"}
    assert expected, "fixture must leave unrelated edges behind to be meaningful"
    assert len(expected) < len(before), "fixture must have edges to delete"

    (project / "module_00.py").unlink()
    indexing.reindex_file(str(project), str(project / "module_00.py"), StubEmbedder())

    after = _all_edges(graph_db)
    assert after == expected, (
        f"collateral damage: {len(expected - after)} unrelated edge(s) deleted, "
        f"{len(after - expected)} incident edge(s) left behind"
    )


def test_deleting_twice_and_deleting_a_never_indexed_file_do_not_error(rig):
    """C3. The deletion branch runs on a path with no rows at all: the second
    delete of the same file, and a file the index never saw."""
    project, (_root, _pid, index_dir, _chroma, _manifest) = rig
    indexing.index_project(str(project), StubEmbedder(), force=True)
    graph_db = index_dir / "graph.db"

    victim = project / "module_00.py"
    victim.unlink()
    first = indexing.reindex_file(str(project), str(victim), StubEmbedder())
    assert first.get("deleted") is True, first

    after_first = _all_edges(graph_db)
    second = indexing.reindex_file(str(project), str(victim), StubEmbedder())
    assert second.get("deleted") is True, f"second delete must be a no-op, got {second}"
    assert "error" not in second, second
    assert second.get("chunks_removed") == 0, second
    assert _all_edges(graph_db) == after_first, "second delete changed the graph"

    never = indexing.reindex_file(
        str(project), str(project / "sub" / "never_indexed.py"), StubEmbedder()
    )
    assert never.get("deleted") is True, f"unknown path must delete cleanly, got {never}"
    assert "error" not in never, never
    assert _all_edges(graph_db) == after_first, "deleting an unknown path touched edges"


def test_store_deletes_both_directions_and_leaves_the_sentinels_alone(tmp_path):
    """The store-level contract, including the count the caller logs.

    Also C4 proved by execution rather than by argument: delete_ghost_edges
    needs its ``target_file != ''`` / ``!= '_external_'`` guards because it
    tests membership in a whole current_files set. An equality test against
    ``"dead.py"`` cannot match either sentinel, so unresolved and external
    edges are untouched here.

    That holds for ``"dead.py"``. It does NOT generalise to every argument
    delete_edges_referencing_file is called with, which is what this docstring
    used to claim, and the claim was wrong: reindex_file reaches that method
    with any path, before any CODE_EXTENSIONS filter, so a project root file
    named ``_external_`` arrives as the sentinel itself. See
    test_badcop_external_sentinel_collision.py. The method now guards its own
    reserved values, so the argument here is about this input, not about the
    method needing no guard.
    """
    from server.graph_store import GraphEdge, SQLiteGraphStore

    def e(source, target):
        return GraphEdge(source_file=source, source_symbol="", target_file=target,
                         target_symbol="dead", edge_type="imports",
                         confidence="EXTRACTED")

    survivors = [
        e("live.py", "other.py"),    # unrelated to the deleted file
        e("live.py", ""),            # unresolved
        e("live.py", "_external_"),  # external
    ]
    store = SQLiteGraphStore(str(tmp_path / "graph.db"))
    store.add_edges([e("dead.py", "live.py"), e("live.py", "dead.py")] + survivors)

    removed = store.delete_edges_referencing_file("dead.py")

    assert removed == 2, f"expected both incident edges removed, reported {removed}"
    remaining = {(x.source_file, x.target_file) for x in store.get_all_edges()}
    assert remaining == {(x.source_file, x.target_file) for x in survivors}

    assert store.delete_edges_referencing_file("dead.py") == 0, "second pass must be a no-op"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
