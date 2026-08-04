"""bad-cop FINAL RE-CHECK adversarial test, NOT part of the reviewed diff.

Attacks the sentinel argument in graph_store.py's
`delete_edges_referencing_file` docstring:

    "It needs no target_file != '' / != _EXTERNAL_SENTINEL guard the way
    that one [delete_ghost_edges] does: this is an equality test against a
    real project-relative path, and both sentinels are values a scanned
    path can never take (every indexed path carries a CODE_EXTENSIONS
    suffix, so it is neither empty nor _external_)."

That claim is about paths the SCANNER indexed. It is not actually a
property of `reindex_file`'s deletion branch, which is where
`delete_edges_referencing_file` is called from. That branch
(indexing.py, "Resolved before the embedder on purpose" through
"Removed deleted file from index: %s") is reached whenever
`abs_file.is_file()` is False, and it computes `rel_path` and calls
`delete_edges_referencing_file(rel_path)` BEFORE any CODE_EXTENSIONS
suffix check -- that check (`if suffix not in CODE_EXTENSIONS: return
{"skipped": ...}`) only runs later, in the branch reached when the file
STILL exists. A file with no extension at all -- literally named
`_external_`, sitting at the project root -- reaches the deletion branch
with rel_path == "_external_" == graph_store._EXTERNAL_SENTINEL exactly.

`delete_edges_referencing_file` then runs:

    DELETE FROM edges WHERE source_file = '_external_' OR target_file = '_external_'

`target_file = '_external_'` is not one path's sentinel, it is the value
`resolve_target_files` stamps onto EVERY unresolved external/stdlib import
edge, project-wide (graph_store.py, `_EXTERNAL_SENTINEL`, `updates.append((_EXTERNAL_SENTINEL, row["id"]))`).
So this single delete call wipes every external-import edge for every
file in the project, not just the one nonexistent path someone asked to
delete.

Reachability: the per-edit reindex hook (hooks/reindex-after-edit.py) and
the auto-reindex sweep's deletion loop (auto_reindex.py, `for rel_path in
deleted: ... reindex_file(project_path, abs_path, model_cache)`) both feed
arbitrary project-relative paths straight into reindex_file with no
extension filter before the deletion check. Any project that ever had (and
then deleted, or is asked to reindex-after-edit for) a no-extension file
literally named `_external_` at its root hits this.

FIXED in `delete_edges_referencing_file` itself, which is the code that owns
the sentinel: it now returns 0 for `''` and for `_EXTERNAL_SENTINEL` instead
of running the equality test against them. Placed there rather than at the
call site because there are three independent callers and only that method
knows which values its own columns reserve.
"""

import hashlib
import json
import math
import sys
from pathlib import Path

import pytest

CLEAN_RAG = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(CLEAN_RAG))

from server import file_scan, indexing  # noqa: E402
from server.auto_reindex import find_changed_files  # noqa: E402
from server.graph_store import SQLiteGraphStore  # noqa: E402

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
    """Ring import graph, same shape as the ghost-edge suite, PLUS a real
    stdlib import (`import os`, `import json`) on every file so
    resolve_target_files stamps real _external_ target_file rows -- the
    thing this test is trying to collaterally destroy."""
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


def _external_edge_count(graph_db: Path) -> int:
    import sqlite3

    conn = sqlite3.connect(str(graph_db))
    try:
        return conn.execute(
            "SELECT COUNT(*) FROM edges WHERE target_file = '_external_'"
        ).fetchone()[0]
    finally:
        conn.close()


def test_deleting_a_file_literally_named_external_sentinel_wipes_every_external_edge(rig):
    """The collision the docstring in graph_store.py claims cannot happen.

    Never even needs to be created: reindex_file's deletion branch is taken
    whenever abs_file.is_file() is False, which includes "never existed".
    """
    project, (_root, _pid, index_dir, _chroma, _manifest) = rig
    indexing.index_project(str(project), StubEmbedder(), force=True)
    graph_db = index_dir / "graph.db"

    before = _external_edge_count(graph_db)
    assert before > 0, (
        "fixture must have real external (stdlib import) edges for this "
        "test to mean anything -- resolve_target_files should have stamped "
        "os/json imports as _external_"
    )

    poison = project / "_external_"  # no extension, never created
    assert not poison.exists()

    result = indexing.reindex_file(str(project), str(poison), StubEmbedder())
    assert result.get("deleted") is True, f"expected the deletion branch, got {result}"

    after = _external_edge_count(graph_db)
    assert after == before, (
        f"deleting/reindexing a nonexistent file named exactly '_external_' "
        f"collided with the graph's external-import sentinel and wiped "
        f"{before - after} of {before} external edges project-wide via "
        f"delete_edges_referencing_file's unguarded "
        f"'target_file = ?' equality test"
    )


def test_sentinel_delete_removes_nothing_on_either_side_of_the_or(rig):
    """The OR clause is symmetric, so the guard has to cover both sides.

    Originally asserted `after_total < before_total`, i.e. that the poisoned
    delete really did remove rows, a control proving the collision reproduced
    rather than being a fixture artifact. That assertion asserted the presence
    of the defect, so it inverts once the defect is fixed. It is replaced by
    the contract it was controlling for, which is strictly stronger: the
    sentinel delete removes NOTHING (total edge count, so both the source_file
    and the target_file side of the OR are covered), while the identical code
    path on a genuinely deleted file still does remove rows. That second half
    keeps the original control: it proves the zero above is the guard working,
    not the delete silently never running.
    """
    project, (_root, _pid, index_dir, _chroma, _manifest) = rig
    indexing.index_project(str(project), StubEmbedder(), force=True)
    graph_db = index_dir / "graph.db"

    before_total = SQLiteGraphStore(str(graph_db)).count_edges()
    assert before_total > 0, "fixture must have edges for this test to mean anything"

    poison = project / "_external_"
    result = indexing.reindex_file(str(project), str(poison), StubEmbedder())
    assert result.get("deleted") is True

    after_poison = SQLiteGraphStore(str(graph_db)).count_edges()
    assert after_poison == before_total, (
        f"a delete for the reserved path '_external_' removed "
        f"{before_total - after_poison} edge(s); it must match no row on "
        f"either side of 'source_file = ? OR target_file = ?'"
    )

    # Control: same branch, same call, a real deleted file. Must still bite.
    victim = project / "module_00.py"
    victim.unlink()
    victim_result = indexing.reindex_file(str(project), str(victim), StubEmbedder())
    assert victim_result.get("deleted") is True

    after_real = SQLiteGraphStore(str(graph_db)).count_edges()
    assert after_real < before_total, (
        "deleting a real indexed file must still remove its edges. If this "
        "fails, the sentinel guard is too broad and has disabled the whole "
        "deletion path, not just the reserved values"
    )


def test_deletion_branch_still_cleans_a_manifest_key_that_is_no_longer_indexable(rig):
    """Why the guard is in the store and NOT a suffix check at the call site.

    The tempting fix for the collision above is to hoist reindex_file's
    `if suffix not in CODE_EXTENSIONS` check above the deletion branch, so a
    path named `_external_` never reaches the graph at all. That breaks
    cleanup, and this pins it.

    The manifest is on disk and outlives any single version of
    CODE_EXTENSIONS. Drop an extension from that set and every existing
    manifest key with it is now non-indexable, so scan_project stops
    returning those files, and find_changed_files reports each one as
    deleted (auto_reindex.py, `deleted = [rel for rel in known if rel not in
    seen]`). With the suffix check hoisted, reindex_file would answer
    `{"skipped": True}`, never drop the manifest key, and be handed the same
    path again on every sweep from then on, with its chunks never removed.
    """
    project, (_root, _pid, _index_dir, _chroma, manifest_path) = rig
    indexing.index_project(str(project), StubEmbedder(), force=True)

    stale_key = "legacy/old.legacy"
    assert ".legacy" not in file_scan.CODE_EXTENSIONS, "pick an unindexable suffix"

    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    raw[stale_key] = "deadbeef"
    manifest_path.write_text(json.dumps(raw, indent=2), encoding="utf-8")

    _changed, deleted = find_changed_files(str(project))
    assert stale_key in deleted, (
        "find_changed_files must hand a non-indexable manifest key to the "
        "deletion path, otherwise the premise of this test is wrong"
    )

    result = indexing.reindex_file(str(project), str(project / stale_key), StubEmbedder())
    assert result.get("deleted") is True, (
        f"a manifest key whose extension is no longer indexable must still be "
        f"cleanable, got {result}"
    )

    after = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert stale_key not in after, (
        "the stale manifest key survived, so every future sweep will report "
        "the same path as deleted forever"
    )


@pytest.mark.parametrize("reserved", ["", "_external_"])
def test_store_refuses_every_reserved_edges_table_value(tmp_path, reserved):
    """The store level contract, both in-band values, no indexing rig.

    `edges.source_file` and `edges.target_file` are TEXT NOT NULL, so NULL is
    impossible and these two are the complete set of values the columns hold
    that are not paths: '' is unresolved, '_external_' is the external import
    stamp `resolve_target_files` applies. Reached directly here because the
    other two tests only exercise '_external_' through reindex_file, which
    leaves the '' half of the guard untested.

    Asserts the returned count as well as the surviving rows. The count is
    what reindex_file logs, so a wrong count is a wrong answer even on a run
    where no row was harmed.
    """
    from server.graph_store import GraphEdge

    def edge(source, target):
        return GraphEdge(
            source_file=source, source_symbol="", target_file=target,
            target_symbol="dead", edge_type="imports", confidence="EXTRACTED",
        )

    store = SQLiteGraphStore(str(tmp_path / "graph.db"))
    store.add_edges([
        edge("live.py", "other.py"),    # ordinary resolved edge
        edge("live.py", ""),            # unresolved
        edge("live.py", "_external_"),  # stdlib or third party import
    ])
    before = {(x.source_file, x.target_file) for x in store.get_all_edges()}

    removed = store.delete_edges_referencing_file(reserved)

    assert removed == 0, (
        f"delete for reserved value {reserved!r} reported {removed} row(s) "
        f"deleted; no edge can belong to a value that is not a path"
    )
    assert {(x.source_file, x.target_file) for x in store.get_all_edges()} == before, (
        f"delete for reserved value {reserved!r} changed the edge table"
    )


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
