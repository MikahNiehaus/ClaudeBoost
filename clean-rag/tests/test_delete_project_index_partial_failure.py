"""A delete that cannot finish must never leave search on a stale directory.

server/search.py resolves a project's data through resolve_project_dir(),
which prefers the current naming scheme and falls back to an older one when
the current directory is missing. Remove the directories one at a time and a
failure halfway through produces exactly that: the current scheme gone, an
older stale one left to answer every search, and nothing in the response or
the registry entry saying so.

So the property under test is not "the delete succeeded". It is that whatever
the delete manages to do, the directory resolve_project_dir lands on is never
one the delete has already orphaned.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server import indexing  # noqa: E402
from server.project_id import (  # noqa: E402
    leaf_only_dir_name,
    project_dir_name,
    resolve_project_dir,
)


class _FakeStore:
    @staticmethod
    def evict_cache(persist_dir: str) -> None:
        pass


@pytest.fixture
def env(tmp_path, monkeypatch):
    databases = tmp_path / "databases"
    state = tmp_path / "state"
    (databases / "_projects").mkdir(parents=True)
    state.mkdir()

    monkeypatch.setattr(indexing, "DATABASES_DIR", databases)
    monkeypatch.setattr(indexing, "STATE_DIR", state)
    monkeypatch.setattr(indexing, "ChromaStore", _FakeStore)

    source = tmp_path / "MyProject"
    source.mkdir()

    return {
        "source": source,
        "projects_root": databases / "_projects",
        "state": state,
    }


def _make_index_dir(projects_root: Path, name: str, marker: str) -> Path:
    d = projects_root / name
    (d / "chroma").mkdir(parents=True)
    (d / "chroma" / "vectors.db").write_bytes(b"x")
    (d / "MARKER.txt").write_text(marker, encoding="utf-8")
    return d


def _two_schemes(env):
    """A fresh current-scheme directory and a stale older-scheme one."""
    src = str(env["source"])
    root = env["projects_root"]
    current_name = project_dir_name(src)
    leaf_name = leaf_only_dir_name(src)
    assert current_name != leaf_name, "fixture needs two distinct scheme names"

    current = _make_index_dir(root, current_name, "FRESH")
    leaf = _make_index_dir(root, leaf_name, "STALE")
    reg = env["state"] / "projects.json"
    reg.write_text(json.dumps({"mine": {"project_path": src}}), encoding="utf-8")
    return src, root, current, leaf, reg


def _served_marker(root: Path, src: str):
    """What search would read, or None when the project resolves to nothing."""
    resolved = resolve_project_dir(root, src)
    marker = resolved / "MARKER.txt"
    return marker.read_text(encoding="utf-8") if marker.exists() else None


def test_a_stale_directory_that_will_not_delete_is_never_served(env, monkeypatch):
    """The stale directory refuses to go. Search must not end up on it.

    Removal is the failure injected here rather than the rename, because that
    is the half the caller cannot retry its way out of: whatever is holding
    those files is holding them now.
    """
    src, root, current, leaf, reg = _two_schemes(env)

    real_rmtree = indexing._rmtree_clearing_readonly

    def _fail_on_leaf(path):
        # Matched on the name, so this bites whether the directory is removed
        # where it sits or after being renamed out of the lookup path. Not a
        # substring test: the current scheme's name ends with the older one.
        name = Path(path).name
        if name == leaf.name or name.startswith(f"{indexing._QUARANTINE_PREFIX}{leaf.name}-"):
            raise PermissionError(32, "locked")
        real_rmtree(path)

    monkeypatch.setattr(indexing, "_rmtree_clearing_readonly", _fail_on_leaf)

    result = indexing.delete_project_index(src)

    assert _served_marker(root, src) != "STALE", (
        f"resolve_project_dir() lands on the stale older-scheme directory "
        f"after a delete that could not remove it, so every search against "
        f"this project is silently served from data the delete was supposed "
        f"to have taken away. Result was {result}"
    )
    assert not leaf.exists(), (
        "the stale directory is still where resolve_project_dir looks for it"
    )


def test_a_directory_that_will_not_rename_leaves_everything_alone(env, monkeypatch):
    """The other half. Nothing may be orphaned before every directory can go.

    The rename is the point of no return: a directory that cannot be taken out
    of the lookup path has to abort the whole delete, with the ones already
    renamed put back.
    """
    src, root, current, leaf, reg = _two_schemes(env)

    real_quarantine = indexing._quarantine_index_dir

    def _fail_on_leaf(directory):
        if directory == leaf:
            raise PermissionError(5, "access is denied")
        return real_quarantine(directory)

    monkeypatch.setattr(indexing, "_quarantine_index_dir", _fail_on_leaf)

    result = indexing.delete_project_index(src)

    assert _served_marker(root, src) == "FRESH", (
        f"the delete orphaned the current-scheme directory even though it "
        f"could not remove the older one, so search fell back to stale data. "
        f"Result was {result}"
    )
    assert current.is_dir() and leaf.is_dir(), "both directories stay put"
    assert result["dirs_removed"] == []
    assert "mine" in json.loads(reg.read_text(encoding="utf-8"))
    assert "error" in result
