"""A file the chunker returns zero chunks for must still get a manifest entry.

Without it, find_changed_files (auto_reindex.py) sees a path with no hash,
calls it changed forever, and index_project reprocesses it forever, producing
zero chunks again every time. On a real project this pushed the changed count
past FULL_REINDEX_THRESHOLD (auto_reindex.py line 60) every 10 hour sweep and
forced a full wipe and rebuild of the whole index, permanently, never
converging. See clean-rag/state/server.log for the measured repro (identical
"1818 files, 9561 chunks" on every completed run, 67 changed every sweep).
"""
import json
from pathlib import Path

import pytest

from server import auto_reindex, indexing


class StubEmbedder:
    """Deterministic vectors. Keeps this a test of the manifest and indexing
    loop, not of sentence transformers."""

    model_name = "stub-embedder"

    def embed(self, texts):
        return [[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8] for _ in texts]


@pytest.fixture()
def isolated_project(tmp_path, monkeypatch):
    """Pin indexing.py (and therefore auto_reindex, which imports the same
    _project_paths function object) at temp dirs, instead of the real
    databases/_projects/ and state/projects.json."""
    monkeypatch.setattr(indexing, "DATABASES_DIR", tmp_path / "databases")
    monkeypatch.setattr(indexing, "STATE_DIR", tmp_path / "state")
    return tmp_path


def _manifest_entries(project: Path) -> dict:
    *_, manifest_path = indexing._project_paths(str(project))
    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    return {k: v for k, v in raw.items() if not k.startswith("__")}


def _real_indexable_file(name: str) -> str:
    """A file with actual chunkable content, so the fixture project is never
    all zero chunk files (which would make every 'still indexes real content'
    assertion vacuous)."""
    body = "\n".join(
        f'''
def handler_{name}_{i}(payload, retries=3):
    """Process one payload and return a normalised record."""
    total = 0
    for index, item in enumerate(payload.get("items", [])):
        if item.get("skip"):
            continue
        total += int(item.get("amount", 0)) * (index + 1)
    if total > 1000 and retries > 0:
        return handler_{name}_{i}({{"items": []}}, retries - 1)
    return {{"total": total, "count": len(payload.get("items", []))}}
'''
        for i in range(12)
    )
    return body


# ---------------------------------------------------------------------------
# Which real inputs make chunk_code / chunk_markdown return []. Verified by
# actually calling them, not assumed. A single top level def/class becomes its
# own chunk regardless of size (no min_tokens filter on definition chunks in
# _chunk_from_tree), so the zero chunk fixture must have NO recognized
# top level definition and stay under MIN_CHUNK_TOKENS*4 (about 200 chars).
# ---------------------------------------------------------------------------

def test_which_contents_the_real_chunker_treats_as_zero_chunks():
    from server.code_chunker import chunk_code

    zero_chunk_cases = {
        "empty": "",
        "whitespace_only": "   \n\n\t  \n",
        "one_byte": "x",
        "comment_only": "# just a comment\n# another comment\n",
        "single_short_statement": "x = 1\n",
    }
    for name, content in zero_chunk_cases.items():
        chunks = chunk_code(content, "test.py", max_tokens=500, min_tokens=50, chunk_overlap=50)
        assert chunks == [], f"{name!r} was expected to produce zero chunks, got {len(chunks)}"

    # Sanity check on the boundary itself: a single tiny *function* still
    # produces a chunk (no min_tokens gate on definition chunks), and 200 or
    # more chars of plain text with no definition clears MIN_CHUNK_TOKENS
    # (50 tokens times 4 chars per token).
    one_def = chunk_code("def f():\n    return 1\n", "test.py", max_tokens=500, min_tokens=50, chunk_overlap=50)
    assert len(one_def) == 1, "a lone top level function was expected to produce exactly one chunk"

    over_boundary = chunk_code("a" * 205, "test.py", max_tokens=500, min_tokens=50, chunk_overlap=50)
    assert len(over_boundary) == 1, "205 chars of plain text was expected to clear MIN_CHUNK_TOKENS"


# ---------------------------------------------------------------------------
# Property 1 & 2: a zero chunk file gets a manifest entry equal to its
# content hash, and stops being reported changed on the next sweep.
# ---------------------------------------------------------------------------

def test_zero_chunk_file_gets_manifest_entry_and_converges(isolated_project):
    project = isolated_project / "proj"
    project.mkdir()
    (project / "real_module.py").write_text(_real_indexable_file("a"), encoding="utf-8")
    (project / "empty_marker.py").write_text("# just a comment\n", encoding="utf-8")

    result = indexing.index_project(str(project), StubEmbedder(), force=True)
    assert result["chunks_created"] > 0, "test setup: nothing was actually indexed"

    entries = _manifest_entries(project)
    assert "empty_marker.py" in entries, (
        "the zero chunk file has no manifest entry at all. This is the exact "
        "bug: find_changed_files has no hash to compare against and will call "
        "it changed on every sweep forever"
    )
    assert entries["empty_marker.py"] == indexing.file_hash("# just a comment\n"), (
        "manifest entry for the zero chunk file is not its real content hash"
    )

    changed, deleted = auto_reindex.find_changed_files(str(project))
    assert changed == [], (
        f"second sweep with no content change still reports {changed} as "
        f"changed. The loop that wipes and rebuilds the whole project every "
        f"sweep is not closed"
    )
    assert deleted == []


def test_zero_chunk_file_content_change_is_still_detected(isolated_project):
    """Property 3: once the file's content actually changes, it must be
    reported changed again. The fix must not paper over real edits."""
    project = isolated_project / "proj"
    project.mkdir()
    (project / "real_module.py").write_text(_real_indexable_file("b"), encoding="utf-8")
    marker = project / "empty_marker.py"
    marker.write_text("# just a comment\n", encoding="utf-8")

    indexing.index_project(str(project), StubEmbedder(), force=True)
    changed, _ = auto_reindex.find_changed_files(str(project))
    assert changed == []

    marker.write_text("# a different comment now\n", encoding="utf-8")
    changed, _ = auto_reindex.find_changed_files(str(project))
    assert changed == [str((project / "empty_marker.py").resolve())] or any(
        Path(c).name == "empty_marker.py" for c in changed
    ), f"content actually changed but find_changed_files reported {changed}"


def test_zero_chunk_file_that_gains_real_content_indexes_normally(isolated_project):
    """Property 4: once a file that was previously zero chunk grows real
    content, it must be chunked and indexed like any other file."""
    project = isolated_project / "proj"
    project.mkdir()
    (project / "real_module.py").write_text(_real_indexable_file("c"), encoding="utf-8")
    marker = project / "empty_marker.py"
    marker.write_text("# just a comment\n", encoding="utf-8")

    indexing.index_project(str(project), StubEmbedder(), force=True)

    marker.write_text(_real_indexable_file("grown"), encoding="utf-8")
    result = indexing.reindex_file(str(project), str(marker), StubEmbedder())
    assert result.get("chunks_created", 0) > 0, (
        f"file grew real content but reindex_file reported {result}"
    )


# ---------------------------------------------------------------------------
# Property 7: index_project and reindex_file must agree on the zero chunk
# case. reindex_file already wrote the manifest entry before this fix; if
# index_project now does the same, a file first touched by one entry point
# and later touched by the other must not disagree about whether it's "known".
# ---------------------------------------------------------------------------

def test_index_project_and_reindex_file_agree_on_zero_chunk_case(isolated_project):
    project_a = isolated_project / "proj_a"
    project_a.mkdir()
    (project_a / "real_module.py").write_text(_real_indexable_file("d"), encoding="utf-8")
    (project_a / "empty_marker.py").write_text("# just a comment\n", encoding="utf-8")
    indexing.index_project(str(project_a), StubEmbedder(), force=True)
    entries_a = _manifest_entries(project_a)

    project_b = isolated_project / "proj_b"
    project_b.mkdir()
    (project_b / "real_module.py").write_text(_real_indexable_file("e"), encoding="utf-8")
    # Index WITHOUT the marker file present yet, so the manifest has no entry
    # for it at all. Only then add it and hand it to reindex_file directly,
    # exactly as the per file sweep path in auto_reindex.py does for a newly
    # discovered file. This is the only way to actually force reindex_file
    # down its own zero chunk branch instead of hitting the unchanged hash
    # short circuit at indexing.py line 1022.
    indexing.index_project(str(project_b), StubEmbedder(), force=True)
    marker_b = project_b / "empty_marker.py"
    marker_b.write_text("# just a comment\n", encoding="utf-8")
    reindex_result = indexing.reindex_file(str(project_b), str(marker_b), StubEmbedder())
    assert "error" not in reindex_result, f"reindex_file failed: {reindex_result}"
    entries_b = _manifest_entries(project_b)

    assert "empty_marker.py" in entries_b, (
        f"reindex_file did not record a manifest entry for the newly "
        f"discovered zero chunk file: {reindex_result}"
    )
    assert entries_a["empty_marker.py"] == entries_b["empty_marker.py"], (
        "index_project and reindex_file recorded different manifest values "
        "for the identical zero chunk file content"
    )


# ---------------------------------------------------------------------------
# Property 6: a real content hash can never collide with UNREADABLE_SENTINEL.
# ---------------------------------------------------------------------------

def test_content_hash_cannot_collide_with_unreadable_sentinel():
    import re
    import string

    assert indexing.UNREADABLE_SENTINEL == "__unreadable__"
    # file_hash is documented and used elsewhere as "exactly 16 lowercase hex
    # characters" (indexing.py, near the UNREADABLE_SENTINEL comment). Confirm
    # that claim for real, then show the sentinel structurally cannot be
    # produced by it.
    samples = ["", "a", "def f(): pass", "x" * 10000, "unicode: é中文"]
    hex16 = re.compile(r"^[0-9a-f]{16}$")
    for s in samples:
        h = indexing.file_hash(s)
        assert hex16.match(h), f"file_hash({s!r}) = {h!r} is not 16 lowercase hex chars"

    assert len(indexing.UNREADABLE_SENTINEL) != 16, (
        "UNREADABLE_SENTINEL is 16 chars long, the ambiguity guard on length "
        "alone no longer holds"
    )
    assert not hex16.match(indexing.UNREADABLE_SENTINEL), (
        "UNREADABLE_SENTINEL matches the shape of 16 lowercase hex characters "
        "that a real hash produces, so collision is now possible"
    )


# ---------------------------------------------------------------------------
# force=True interaction: the unchanged hash skip is bypassed under force,
# but the zero chunk file must still get a manifest entry written.
# ---------------------------------------------------------------------------

def test_zero_chunk_file_gets_manifest_entry_under_force(isolated_project):
    project = isolated_project / "proj"
    project.mkdir()
    (project / "real_module.py").write_text(_real_indexable_file("f"), encoding="utf-8")
    (project / "empty_marker.py").write_text("# just a comment\n", encoding="utf-8")

    # First pass, not forced (nothing exists yet, force is irrelevant here but
    # matches the manual /index-project path).
    indexing.index_project(str(project), StubEmbedder(), force=True)
    # Second pass, force=True: the unchanged hash skip at indexing.py line 658
    # is bypassed entirely (`if not force and manifest.get(...) == ...`), so
    # this exercises the zero chunk branch a second time under force.
    result = indexing.index_project(str(project), StubEmbedder(), force=True)
    entries = _manifest_entries(project)
    assert entries.get("empty_marker.py") == indexing.file_hash("# just a comment\n"), (
        f"force=True re run lost the manifest entry for the zero chunk file: {result}"
    )


# ---------------------------------------------------------------------------
# The actual bug, reproduced in miniature: a project with more than
# FULL_REINDEX_THRESHOLD (50) zero chunk files must NOT report all of them
# changed on the very next sweep. Before the fix this is exactly the
# condition that forces the full rebuild path (auto_reindex.py line 342)
# every single sweep, forever.
# ---------------------------------------------------------------------------

def test_abort_right_after_zero_chunk_file_still_persists_its_entry(isolated_project):
    """The manifest write for a zero chunk file lands in the in memory dict
    the moment its processing finishes (indexing.py line 712), before the
    cooperative abort check runs again on the next file. The end of run save
    after the loop's `break` (indexing.py line 845) is unconditional, so an
    abort immediately after a zero chunk file must not lose that entry, even
    though the periodic checkpoint interval never elapsed during this test."""
    project = isolated_project / "proj"
    project.mkdir()
    (project / "aaa_zero.py").write_text("# just a comment\n", encoding="utf-8")
    (project / "zzz_real.py").write_text(_real_indexable_file("h"), encoding="utf-8")

    seen = {"n": 0}

    def abort_after_first_file():
        seen["n"] += 1
        return "pressure" if seen["n"] > 1 else None

    result = indexing.index_project(
        str(project), StubEmbedder(), force=True, should_abort=abort_after_first_file
    )
    assert result["stopped_early"] == "pressure"
    assert result["files_indexed"] == 0, "test setup: only the zero chunk file was reachable"

    entries = _manifest_entries(project)
    assert "aaa_zero.py" in entries, (
        f"the run aborted right after the zero chunk file finished, and the "
        f"entry was lost by the time the manifest was saved: {entries}"
    )


def test_many_zero_chunk_files_do_not_retrigger_full_reindex_threshold(isolated_project):
    project = isolated_project / "proj"
    project.mkdir()
    (project / "real_module.py").write_text(_real_indexable_file("g"), encoding="utf-8")
    n_zero_chunk = 60  # > FULL_REINDEX_THRESHOLD (50)
    for i in range(n_zero_chunk):
        (project / f"zero_{i:03d}.py").write_text(f"# marker file {i}\n", encoding="utf-8")

    result = indexing.index_project(str(project), StubEmbedder(), force=True)
    assert result["chunks_created"] > 0, "test setup: the real file must have indexed"

    changed, deleted = auto_reindex.find_changed_files(str(project))
    assert len(changed) == 0, (
        f"{len(changed)} files reported changed on the very next sweep with no "
        f"edits. {n_zero_chunk} zero chunk files crosses "
        f"FULL_REINDEX_THRESHOLD (50) and would force a full wipe and rebuild "
        f"every sweep, which is the exact bug measured in server.log"
    )
    assert changed != list(range(n_zero_chunk))  # sanity, not a real assertion path
    assert len(changed) < auto_reindex.FULL_REINDEX_THRESHOLD
