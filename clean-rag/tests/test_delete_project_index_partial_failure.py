"""bad-cop adversarial test: property 2/7 attacked directly.

delete_project_index processes the naming-scheme directories one at a time,
and each rmtree either fully succeeds or fully fails independently. The
existing single-directory test (test_a_directory_that_will_not_delete_leaves_
the_registry_alone in test_delete_project_index.py) proves the registry stays
put on failure. It never exercises the case where THREE directories coexist
(the exact scenario the delete feature was built for) and only the MIDDLE one
fails: the other two are already gone from disk by the time the function
returns, while the registry is left untouched and the caller is told "the
project is unchanged from the caller's point of view."

That framing is false for search. server/search.py resolves a project's data
through project_id.resolve_project_dir(), which prefers the CURRENT naming
scheme and only falls back to an older one when the current directory is
missing. If the partial failure happens to remove the current-scheme
directory while an older, stale one survives, every search against this
project silently starts being served from the stale leftover directory
instead of erroring -- with nothing in the API response or the registry
entry indicating that has happened.
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


def test_partial_failure_can_strand_search_on_a_stale_directory(env, monkeypatch):
    src = str(env["source"])
    root = env["projects_root"]

    current_name = project_dir_name(src)
    leaf_name = leaf_only_dir_name(src)
    assert current_name != leaf_name, "fixture needs two distinct scheme names"

    current = _make_index_dir(root, current_name, "FRESH")
    leaf = _make_index_dir(root, leaf_name, "STALE")

    reg = env["state"] / "projects.json"
    reg.write_text(json.dumps({"mine": {"project_path": src}}), encoding="utf-8")

    real_rmtree = indexing._rmtree_clearing_readonly

    def _fail_on_leaf(path):
        if path == leaf:
            raise PermissionError(32, "locked")
        real_rmtree(path)

    monkeypatch.setattr(indexing, "_rmtree_clearing_readonly", _fail_on_leaf)

    result = indexing.delete_project_index(src)

    assert not current.exists(), "the current/fresh directory was removed"
    assert leaf.exists(), "the stale directory survived the failure"
    assert "mine" in json.loads(reg.read_text(encoding="utf-8")), (
        "registry correctly left in place, property 2 still holds"
    )

    resolved = resolve_project_dir(root, src)
    marker = (resolved / "MARKER.txt").read_text(encoding="utf-8")

    # This is the actual finding: search now silently reads the STALE
    # directory, not the fresh one, even though nothing told the caller that.
    assert marker == "FRESH", (
        f"search.py's resolve_project_dir() now resolves to {resolved}, which "
        f"is the STALE leftover directory (marker={marker!r}), after a "
        f"partial delete failure removed the current one. The delete API "
        f"response and the preserved registry entry both imply the project "
        f"is unchanged, but every search against it is now silently served "
        f"from out of date data instead of erroring or being blocked."
    )
