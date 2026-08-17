"""A partially indexed project must never be served as if it were complete.

Originally written by bad-cop to prove the defect: search.py's provenance gate
only consulted the recorded ``model_id``, so a project whose indexing run was
aborted partway (manifest marked ``__incomplete__``) came back with real chunk
hits and an empty ``meta_out``. A caller reading a thin result set could not
tell "the code is genuinely not there" from "the index never finished".

Inverted here to assert the corrected contract, keeping the same attack: build
a real project, abort the index after 2 of 6 files through the same
``should_abort`` path auto_reindex uses, patch the manifest's model_id to match
the live embedder so the unrelated model gate cannot mask the result, then call
the real ``search.search()``.

The corrected contract is serve plus warn, not refuse:
  * the hits that exist are real, so they are still returned
  * ``meta_out["stale_projects"]`` carries an entry naming the incompleteness
  * that entry is marked ``served: True``, so it cannot be confused with the
    ``served: False`` entry a provenance mismatch produces
"""
import json
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
        body = "\n".join(
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
            for i in range(12)
        )
        (root / f"module_{f:02d}.py").write_text(body, encoding="utf-8")
    return root


def _index_two_of_six(tmp_path, monkeypatch):
    """Build a 6 file project, abort indexing after 2, return its path."""
    from server import indexing, search

    monkeypatch.setattr(indexing, "DATABASES_DIR", tmp_path / "databases")
    monkeypatch.setattr(indexing, "STATE_DIR", tmp_path / "state")
    monkeypatch.setattr(search, "DATABASES_DIR", tmp_path / "databases")

    project = _make_project(tmp_path / "proj", n_files=6)

    seen = {"n": 0}

    def abort_after_two():
        seen["n"] += 1
        return "CPU 95% (limit 80%)" if seen["n"] > 2 else None

    result = indexing.index_project(
        str(project), StubEmbedder(), force=True, should_abort=abort_after_two
    )
    assert result["files_indexed"] == 2, "test setup: abort must have fired early"
    assert indexing.index_is_incomplete(str(project)) is True, (
        "test setup: manifest must be marked incomplete"
    )

    # Isolate the variable under test: give the manifest a model_id matching
    # the live embedder so the model mismatch gate does not fire too and mask
    # whether the incompleteness gate exists on its own.
    _root, _pid, _idx, _chroma, manifest_path = indexing._project_paths(str(project))
    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert raw.get("__incomplete__") is True, raw
    raw["__model_id__"] = "stub-embedder"
    manifest_path.write_text(json.dumps(raw), encoding="utf-8")

    return project


def test_partial_index_is_served_but_flagged_as_incomplete(tmp_path, monkeypatch):
    from server import search

    project = _index_two_of_six(tmp_path, monkeypatch)

    meta_out = {}
    results = search.search(
        "handler payload retries",
        [f"project:{project}"],
        StubEmbedder(),
        mode="vector",
        min_score=0.0,
        meta_out=meta_out,
    )

    # The hits are real, so refusing them would throw away correct results and
    # make an interrupted sweep un-searchable until it finishes.
    assert len(results) > 0, (
        "the 2 files that were indexed are correctly embedded and must still "
        "be searchable"
    )

    stale = meta_out.get("stale_projects")
    assert stale, (
        "a project missing 4 of its 6 files was served with no signal at all; "
        "the caller cannot tell a thin result set from a missing index"
    )
    entry = next(e for e in stale if e["project"] == f"{project}")
    assert "incomplete" in entry["reason"].lower(), entry
    assert entry["served"] is True, (
        "an incomplete index is served, not refused, so served must say so; "
        "otherwise results plus a stale_projects entry reads as 'refused'"
    )


def test_a_complete_index_is_not_flagged(tmp_path, monkeypatch):
    """The warning has to mean something, so a finished index must not carry
    it. Without this, always flagging would pass the test above."""
    from server import indexing, search

    monkeypatch.setattr(indexing, "DATABASES_DIR", tmp_path / "databases")
    monkeypatch.setattr(indexing, "STATE_DIR", tmp_path / "state")
    monkeypatch.setattr(search, "DATABASES_DIR", tmp_path / "databases")

    project = _make_project(tmp_path / "proj", n_files=3)
    result = indexing.index_project(str(project), StubEmbedder(), force=True)
    assert result["files_indexed"] == 3
    assert indexing.index_is_incomplete(str(project)) is False

    _root, _pid, _idx, _chroma, manifest_path = indexing._project_paths(str(project))
    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    raw["__model_id__"] = "stub-embedder"
    manifest_path.write_text(json.dumps(raw), encoding="utf-8")

    meta_out = {}
    results = search.search(
        "handler payload retries",
        [f"project:{project}"],
        StubEmbedder(),
        mode="vector",
        min_score=0.0,
        meta_out=meta_out,
    )

    assert len(results) > 0
    assert "stale_projects" not in meta_out, (
        f"a fully indexed project was flagged: {meta_out.get('stale_projects')}"
    )


def test_refused_and_partial_are_distinguishable_in_the_same_channel(tmp_path, monkeypatch):
    """Both faults ride ``stale_projects``, so a caller has to be able to tell
    "returned nothing, refused" from "returned a subset". ``served`` is the
    only field that carries that, and getting it wrong turns a partial answer
    into a silently ignored one."""
    from server import search

    project = _index_two_of_six(tmp_path, monkeypatch)

    class OtherModelEmbedder(StubEmbedder):
        model_name = "some-other-model"

    meta_out = {}
    results = search.search(
        "handler payload retries",
        [f"project:{project}"],
        OtherModelEmbedder(),
        mode="vector",
        min_score=0.0,
        meta_out=meta_out,
    )

    # A model mismatch is refused outright: the vectors are in another
    # embedding space, so every score would be confident nonsense.
    assert results == [], "an index from a different model must not be served"
    entry = meta_out["stale_projects"][0]
    assert entry["served"] is False, entry
    assert "some-other-model" in entry["reason"]


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v", "-s"]))
