"""Tests for delete_project_index and its helpers.

The properties that matter here are the ones where getting it wrong is silent:
a directory left behind under an older naming scheme, a registry entry removed
while the data is still on disk, or an rmtree that reaches outside
databases/_projects.

Every test points DATABASES_DIR and STATE_DIR at tmp_path. Nothing here touches
the real index.
"""
import json
import stat
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server import indexing  # noqa: E402
from server.project_id import (  # noqa: E402
    leaf_only_dir_name,
    legacy_project_dir_name,
    project_dir_name,
)


class _FakeStore:
    """Records evict_cache calls so the ordering property can be asserted."""

    evicted: list[str] = []

    @staticmethod
    def evict_cache(persist_dir: str) -> None:
        _FakeStore.evicted.append(persist_dir)


@pytest.fixture
def env(tmp_path, monkeypatch):
    """A whole fake clean-rag: databases dir, state dir, and a source project."""
    databases = tmp_path / "databases"
    state = tmp_path / "state"
    (databases / "_projects").mkdir(parents=True)
    state.mkdir()

    monkeypatch.setattr(indexing, "DATABASES_DIR", databases)
    monkeypatch.setattr(indexing, "STATE_DIR", state)
    _FakeStore.evicted = []
    monkeypatch.setattr(indexing, "ChromaStore", _FakeStore)

    source = tmp_path / "MyProject"
    (source / "src").mkdir(parents=True)
    (source / "src" / "main.py").write_text("print('hello')", encoding="utf-8")

    return {
        "databases": databases,
        "state": state,
        "source": source,
        "projects_root": databases / "_projects",
    }


def _make_index_dir(projects_root: Path, name: str) -> Path:
    """A directory shaped like a real project index."""
    d = projects_root / name
    (d / "chroma").mkdir(parents=True)
    (d / "chroma" / "vectors.db").write_bytes(b"not really sqlite")
    (d / "graph.db").write_bytes(b"not really sqlite")
    (d / "manifest.json").write_text('{"__project_path__": "x"}', encoding="utf-8")
    return d


def _write_registry(state: Path, entries: dict) -> Path:
    p = state / "projects.json"
    p.write_text(json.dumps(entries, indent=2), encoding="utf-8")
    return p


def test_removes_every_naming_scheme_not_just_the_preferred_one(env):
    """The bug this exists to catch: resolve_project_dir returns the FIRST
    match, so a delete built on it leaves the older directories on disk."""
    src = str(env["source"])
    root = env["projects_root"]

    current = _make_index_dir(root, project_dir_name(src))
    leaf = _make_index_dir(root, leaf_only_dir_name(src))
    legacy = _make_index_dir(root, legacy_project_dir_name(src))
    assert len({current, leaf, legacy}) == 3, "the three schemes must differ here"

    _write_registry(env["state"], {"myproject-abc": {"project_path": src}})

    result = indexing.delete_project_index(src)

    assert not current.exists()
    assert not leaf.exists()
    assert not legacy.exists()
    assert len(result["dirs_removed"]) == 3
    assert result["dirs_failed"] == []


def test_evict_cache_runs_before_the_directory_is_removed(env):
    """Without this the live SQLite handle makes rmtree fail with WinError 32."""
    src = str(env["source"])
    d = _make_index_dir(env["projects_root"], project_dir_name(src))
    _write_registry(env["state"], {"p": {"project_path": src}})

    indexing.delete_project_index(src)

    assert len(_FakeStore.evicted) == 1
    assert Path(_FakeStore.evicted[0]) == d / "chroma"


def test_registry_entry_is_removed_and_others_are_left_alone(env):
    src = str(env["source"])
    other = env["source"].parent / "OtherProject"
    other.mkdir()
    _make_index_dir(env["projects_root"], project_dir_name(src))
    reg = _write_registry(env["state"], {
        "mine": {"project_path": src},
        "theirs": {"project_path": str(other)},
    })

    result = indexing.delete_project_index(src)

    after = json.loads(reg.read_text(encoding="utf-8"))
    assert "mine" not in after
    assert "theirs" in after
    assert result["registry_removed"] == ["mine"]


def test_registry_match_is_by_path_not_by_pid(env):
    """An entry written under an older naming scheme has a pid that no longer
    matches what project_dir_name computes. Matching on pid would strand it."""
    src = str(env["source"])
    _make_index_dir(env["projects_root"], project_dir_name(src))
    reg = _write_registry(env["state"], {
        "a-pid-from-some-older-scheme-0000": {"project_path": src},
    })

    result = indexing.delete_project_index(src)

    assert json.loads(reg.read_text(encoding="utf-8")) == {}
    assert result["registry_removed"] == ["a-pid-from-some-older-scheme-0000"]


def test_a_directory_that_will_not_delete_leaves_the_registry_alone(env, monkeypatch):
    """Ordering property. An orphaned registry entry makes the project read as
    indexed while every search silently returns nothing, so the registry write
    must not happen when the data is still on disk."""
    src = str(env["source"])
    _make_index_dir(env["projects_root"], project_dir_name(src))
    reg = _write_registry(env["state"], {"mine": {"project_path": src}})

    def _refuse(path):
        raise PermissionError(32, "The process cannot access the file")

    monkeypatch.setattr(indexing, "_rmtree_clearing_readonly", _refuse)

    result = indexing.delete_project_index(src)

    assert "mine" in json.loads(reg.read_text(encoding="utf-8"))
    assert result["registry_removed"] == []
    assert len(result["dirs_failed"]) == 1
    assert "error" in result


def test_a_read_only_file_inside_the_tree_still_gets_removed(env):
    """Git writes pack files read only and Windows refuses to delete those."""
    src = str(env["source"])
    d = _make_index_dir(env["projects_root"], project_dir_name(src))
    locked = d / "chroma" / "vectors.db"
    locked.chmod(stat.S_IREAD)
    _write_registry(env["state"], {"mine": {"project_path": src}})

    result = indexing.delete_project_index(src)

    assert not d.exists()
    assert result["dirs_failed"] == []


def test_the_projects_own_source_is_never_touched(env):
    src = str(env["source"])
    _make_index_dir(env["projects_root"], project_dir_name(src))
    _write_registry(env["state"], {"mine": {"project_path": src}})

    indexing.delete_project_index(src)

    assert env["source"].is_dir()
    assert (env["source"] / "src" / "main.py").read_text(encoding="utf-8") == "print('hello')"


def test_deleting_an_unindexed_project_is_not_an_error(env):
    """Idempotent: deleting something already gone reports nothing removed
    rather than raising, so a retry after a partial failure is safe."""
    src = str(env["source"])
    _write_registry(env["state"], {})

    result = indexing.delete_project_index(src)

    assert result["dirs_removed"] == []
    assert result["dirs_failed"] == []
    assert result["registry_removed"] == []
    assert "error" not in result


def test_project_index_dirs_skips_names_that_escape_the_projects_root(env, monkeypatch):
    """The containment guard. Nothing today can produce such a name, but the
    thing on the other side of this check is an rmtree."""
    root = env["projects_root"]
    outside = env["databases"] / "not_projects"
    outside.mkdir()

    monkeypatch.setattr(indexing, "project_dir_name", lambda p: "../not_projects")
    monkeypatch.setattr(indexing, "leaf_only_dir_name", lambda p: "../not_projects")
    monkeypatch.setattr(indexing, "legacy_project_dir_name", lambda p: "../not_projects")

    found = indexing.project_index_dirs(str(env["source"]))

    assert found == []
    assert outside.is_dir()
    assert root.is_dir()


def test_nested_and_root_paths_are_rejected_by_the_containment_guard(env):
    root = env["projects_root"]
    (root / "a" / "b").mkdir(parents=True)

    assert indexing._is_inside_projects_root(root / "a", root) is True
    assert indexing._is_inside_projects_root(root / "a" / "b", root) is False
    assert indexing._is_inside_projects_root(root, root) is False
