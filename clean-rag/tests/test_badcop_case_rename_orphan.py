"""Adversarial (bad-cop) test: force_drop's rel_path re-derivation can target
the WRONG manifest key and the wrong store rows when the caller's reconstructed
absolute path resolves to different casing than the manifest key it came from.

Root cause: the auto_reindex drop loop reconstructs
    abs_path = str(Path(project_path) / rel_path)
from a manifest key it already knows is stale (`deleted`), then calls
    reindex_file(project_path, abs_path, model_cache, force_drop=True)

reindex_file re-derives its OWN rel_path independently:
    abs_file = Path(file_path).resolve()
    rel_path = str(abs_file.relative_to(project_root))

On a case-insensitive, case-preserving filesystem (default on Windows and
macOS), Path.resolve() normalizes to the file's REAL on-disk casing regardless
of what casing was used to build the Path. So if a file was indexed as
"Foo.py" and is later renamed (by git, an editor, a case-normalizing tool) to
"foo.py" with the same content, the drop loop asks to evict "Foo.py" but
reindex_file's re-derived rel_path is "foo.py" instead.

Proven by direct execution (see scratchpad test_case_rename_bug.py): the call
reports `{"deleted": True}` for "foo.py", NOT "Foo.py" -- looking like success
-- while:
  1. The stale "Foo.py" manifest entry is never removed. The next sweep sees
     it as deleted again: NON-CONVERGENCE, the exact property the diff's own
     docstring says is "the entire bug being fixed".
  2. store.delete_by_source("codebase", "foo.py") deletes rows that (at this
     point in the sweep, before the `changed` loop runs) do not exist yet,
     while the REAL orphaned chunks are still sitting in the store under the
     old "Foo.py" source_file key forever -- duplicate/stale content in every
     future search result for this file.

This is not a synthetic worst case: any git checkout, IDE refactor, or `git
mv` that only changes a path's case reproduces it.
"""
import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server import indexing  # noqa: E402
from server.auto_reindex import find_changed_files  # noqa: E402


def _read_manifest(manifest_path):
    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    return {k: v for k, v in raw.items() if not k.startswith("__")}


class _FakeStore:
    """Mimics ChromaStore just enough to observe which source key gets a
    delete call, without touching real chromadb."""

    def __init__(self, *a, **k):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def collection_exists(self, _name):
        return True

    def delete_by_source(self, _collection, rel_path):
        DELETE_CALLS.append(rel_path)
        return 1

    def vacuum_if_needed(self):
        pass


DELETE_CALLS: list[str] = []


@pytest.fixture(autouse=True)
def _reset_calls():
    DELETE_CALLS.clear()
    yield
    DELETE_CALLS.clear()


def test_force_drop_survives_a_case_only_rename(tmp_path, monkeypatch):
    """Correctness property: force_drop must evict the STALE manifest key the
    sweep actually identified as deleted, not whatever key the filesystem
    happens to resolve the reconstructed path to.

    This currently FAILS: the stale "Foo.py" key survives in the manifest
    (never evicted), so the sweep never converges, and the wrong store key
    ("foo.py") receives the delete call instead of the intended "Foo.py".
    """
    # _project_paths resolves against DATABASES_DIR, which points at the live
    # clean-rag databases dir by default. Without this redirect every run of
    # this test registers another fixture directory under the real
    # databases/_projects, and they accumulate there as junk that looks like an
    # indexed project. Nine other test modules already do this; this one was
    # missed. Same reason the eviction test file does it.
    monkeypatch.setattr(indexing, "DATABASES_DIR", tmp_path / "databases")

    project = tmp_path / "proj"
    project.mkdir()
    f = project / "Foo.py"
    content = "x = 1\n"
    f.write_text(content, encoding="utf-8")
    h = indexing.file_hash(content)

    _root, _pid, index_dir, chroma_dir, manifest_path = indexing._project_paths(str(project))
    chroma_dir.mkdir(parents=True, exist_ok=True)
    index_dir.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps({"__project_path__": str(project), "Foo.py": h}), encoding="utf-8"
    )

    # Case-only rename: same file, same content, same inode, different casing.
    os.rename(str(f), str(project / "foo.py"))

    changed, deleted = find_changed_files(str(project))
    assert deleted == ["Foo.py"], f"sweep must flag the old-cased key as deleted, got {deleted}"

    monkeypatch.setattr(indexing, "ChromaStore", _FakeStore)

    # What the real auto_reindex drop loop does: hand each manifest key to
    # drop_manifest_key untouched. It used to rebuild an absolute path around
    # the key and let reindex_file derive a key back out, which is what lost the
    # casing. Convergence through the real _sweep_project driver is covered in
    # test_phantom_deletion_eviction.py; this test is specifically about which
    # key the eviction lands on.
    for rel_path in deleted:
        outcome = indexing.drop_manifest_key(str(project), rel_path)

    manifest_after = _read_manifest(manifest_path)

    # The correctness property: the STALE key must actually be gone.
    assert "Foo.py" not in manifest_after, (
        "BUG: force_drop did not evict the stale manifest key 'Foo.py' -- it "
        f"evicted {DELETE_CALLS!r} instead. manifest now: {manifest_after!r}. "
        "This is the rel_path re-derivation mismatch: reindex_file resolved "
        "the reconstructed path to the file's real on-disk casing instead of "
        "the manifest key the caller asked to drop."
    )

    # The correctness property: the store delete call must target the same
    # key that was evicted from the manifest, not a different one.
    assert DELETE_CALLS == ["Foo.py"], (
        f"BUG: store.delete_by_source was called with {DELETE_CALLS!r}, not "
        "the stale key 'Foo.py' -- the real orphaned chunks under 'Foo.py' "
        "are never removed from the vector store."
    )

    # Convergence property: a second sweep with no further real change must
    # not report anything deleted again.
    changed2, deleted2 = find_changed_files(str(project))
    assert deleted2 == [], (
        f"BUG: non-convergence. Second sweep still reports {deleted2!r} as "
        "deleted; the sweep never reaches a steady state for this file."
    )
