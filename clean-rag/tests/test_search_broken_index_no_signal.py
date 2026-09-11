"""A project with a valid, provenance matching manifest but a missing or
corrupted chroma collection must not read as "nothing matched".

CLAUDE.md's own contract for the ``stale_projects`` channel: "zero results
plus that field is a broken index, not an empty codebase" -- a caller cannot
tell a genuine no-match apart from a broken index unless every refusal path
populates the field, not just the two _check_index_before_search already
covers (provenance mismatch, incomplete index).

This is the third way an index can be untrustworthy that the existing gate
never asks about: the manifest says "I am indexed, by the right model, in
full" (so _provenance_mismatch and index_is_incomplete both say "fine"), but
the chroma/ directory backing that claim is gone -- a partial disk cleanup, an
interrupted move, a bad restore, or a project moved off a full disk mid write.
_search_project and _search_project_graph both hit this with a bare
``logger.warning`` and an early ``return []``, never touching meta_out.

Same StubEmbedder/monkeypatch harness as test_search_incomplete_index.py, so
this never loads a real embedding model and never touches a real project's
databases.
"""
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class StubEmbedder:
    model_name = "stub-embedder"

    def embed(self, texts):
        return [[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8] for _ in texts]

    def embed_query(self, text):
        return [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8]


def _make_project(root: Path, n_files: int) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    for f in range(n_files):
        (root / f"module_{f:02d}.py").write_text(
            f"def handler_{f}(payload):\n    return len(payload)\n",
            encoding="utf-8",
        )
    return root


def _index_complete_project(tmp_path, monkeypatch):
    from server import indexing, search

    monkeypatch.setattr(indexing, "DATABASES_DIR", tmp_path / "databases")
    monkeypatch.setattr(indexing, "STATE_DIR", tmp_path / "state")
    monkeypatch.setattr(search, "DATABASES_DIR", tmp_path / "databases")

    project = _make_project(tmp_path / "proj", n_files=3)
    result = indexing.index_project(str(project), StubEmbedder(), force=True)
    assert result["files_indexed"] == 3, "test setup: index must complete fully"
    assert indexing.index_is_incomplete(str(project)) is False

    # Provenance matching, so neither existing gate fires.
    _root, _pid, _idx, chroma_dir, manifest_path = indexing._project_paths(str(project))
    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    raw["__model_id__"] = "stub-embedder"
    manifest_path.write_text(json.dumps(raw), encoding="utf-8")

    return project, chroma_dir


def test_missing_chroma_dir_is_surfaced_not_silent(tmp_path, monkeypatch):
    """The chroma/ directory disappears (disk cleanup, bad restore) while the
    manifest -- the only thing _check_index_before_search reads -- still
    claims a complete, correctly provenanced index. search() must not answer
    with a bare empty list."""
    from server import search
    from server.store import ChromaStore

    project, chroma_dir = _index_complete_project(tmp_path, monkeypatch)

    # Release the cached sqlite handle before deleting, same as production
    # code has to when a store is being torn down.
    ChromaStore.clear_cache()
    shutil.rmtree(chroma_dir)

    meta_out = {}
    results = search.search(
        "handler payload",
        [f"project:{project}"],
        StubEmbedder(),
        mode="vector",
        min_score=0.0,
        meta_out=meta_out,
    )

    assert results == [], "test setup: no chroma dir means no chunks to return"

    # This is the actual defect: a caller reading this response sees an empty
    # result list and an empty meta_out, exactly the shape a genuine "your
    # query matched nothing in a healthy index" response has. There is no way
    # to tell the two apart from the response alone.
    assert meta_out.get("stale_projects"), (
        "search() returned [] for a project whose manifest claims a complete, "
        "correctly provenanced index but whose chroma/ directory is missing -- "
        "with no stale_projects entry, this is indistinguishable from a real "
        "no-match and violates clean-rag/CLAUDE.md's own contract: 'zero "
        "results plus that field is a broken index, not an empty codebase'"
    )


def test_missing_collection_in_graph_mode_is_also_surfaced(tmp_path, monkeypatch):
    """Same defect, reached through mode='graph' / mode='both', which hits its
    own early `if not chroma_dir.exists(): return []` in
    _search_project_graph before ever calling graph.has_graph()."""
    from server import search
    from server.store import ChromaStore

    project, chroma_dir = _index_complete_project(tmp_path, monkeypatch)

    ChromaStore.clear_cache()
    shutil.rmtree(chroma_dir)

    meta_out = {}
    results = search.search(
        "handler payload",
        [f"project:{project}"],
        StubEmbedder(),
        mode="graph",
        min_score=0.0,
        meta_out=meta_out,
    )

    assert results == []
    assert meta_out.get("stale_projects"), (
        "mode='graph' against a project with a missing chroma/ directory "
        "also returns [] with no stale_projects entry"
    )


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v", "-s"]))
