"""bad-cop adversarial: a deleted dunder prefixed file is never evicted.

good-cop left ``auto_reindex.py:219`` on the old ``startswith("__")`` filter,
reasoning the consequence is bounded to wasted re embedding because
``reindex_file`` now writes the reserved key set correctly. That reasoning
covers the add and modify paths. It does not cover deletion: ``known`` is
built by the same prefix filter, so a real file whose relative path happens
to start with two underscores, the exact Jest ``__tests__/`` layout this
whole change exists for, is invisible to both sides of the deleted
computation. ``find_changed_files`` never reports it, ``drop_manifest_key``
is never called on it, and its manifest key and vector chunks are never
evicted after the file is actually removed from disk. Since ``files_total``
is now read straight from the manifest key count, this inflates the number
the console renders and never self corrects short of a full rebuild.
"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server import auto_reindex  # noqa: E402
from server.indexing import _project_paths, file_hash  # noqa: E402


def test_a_deleted_dunder_prefixed_file_is_reported_as_deleted(tmp_path, monkeypatch):
    proj = tmp_path / "proj"
    (proj / "__tests__").mkdir(parents=True)
    (proj / "__tests__" / "Foo.test.js").write_text("test(1)", encoding="utf-8")
    (proj / "real.js").write_text("console.log(1)", encoding="utf-8")

    manifest_path = _project_paths(str(proj))[4]
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps({
        "__project_path__": str(proj),
        "__tests__/Foo.test.js": file_hash("test(1)"),
        "real.js": file_hash("console.log(1)"),
    }), encoding="utf-8")

    # The file is genuinely removed from disk, the way a real deletion works.
    (proj / "__tests__" / "Foo.test.js").unlink()

    changed, deleted = auto_reindex.find_changed_files(str(proj))

    assert "__tests__/Foo.test.js" in deleted, (
        "a real deletion of a dunder-prefixed path is invisible to the sweep, "
        f"deleted={deleted!r}, so its manifest key and vectors are never evicted"
    )
