"""Direct exercise of handle_delete_project (server/app.py), which nothing in
the diff under review actually calls end to end.

test_console_delete_button.py only proves the console SENDS confirm: true; it
mocks _post entirely, so the real handler never runs. test_delete_project_index.py
only exercises indexing.delete_project_index() directly, bypassing the route.
Nothing in the diff calls handle_delete_project itself, so its own refusal
logic -- confirm required, project must be registered, the lock is always
released -- has zero direct coverage. This fills that gap for the closing
adversarial re-check (correctness property 7 and 10 from the review brief).
"""
import asyncio
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server import app as app_mod  # noqa: E402
from server import indexing  # noqa: E402


class _StubRequest:
    def __init__(self, body):
        self._body = body

    async def json(self):
        return self._body


@pytest.fixture
def env(tmp_path, monkeypatch):
    state = tmp_path / "state"
    state.mkdir()
    monkeypatch.setattr(app_mod, "STATE_DIR", state)
    monkeypatch.setattr(indexing, "STATE_DIR", state)
    monkeypatch.setattr(indexing, "_INDEX_LOCK_PATH", state / "index-lock.json")

    project = tmp_path / "MyProject"
    project.mkdir()
    (state / "projects.json").write_text(
        json.dumps({"mine": {"project_path": str(project)}}), encoding="utf-8",
    )
    return {"project": project, "state": state}


def _run(coro):
    return asyncio.run(coro)


def test_refuses_without_confirm_true(env):
    response = _run(app_mod.handle_delete_project(
        _StubRequest({"project_path": str(env["project"])}),
    ))
    assert response.status == 400, response.body
    assert "confirm" in json.loads(response.body.decode("utf-8"))["error"].lower()
    assert not indexing._INDEX_LOCK_PATH.exists(), "a refused request must never take the lock"


def test_refuses_confirm_false(env):
    response = _run(app_mod.handle_delete_project(
        _StubRequest({"project_path": str(env["project"]), "confirm": False}),
    ))
    assert response.status == 400, response.body


def test_refuses_confirm_as_truthy_string_not_boolean_true(env):
    """``confirm: "true"`` must not slip past ``is not True``."""
    response = _run(app_mod.handle_delete_project(
        _StubRequest({"project_path": str(env["project"]), "confirm": "true"}),
    ))
    assert response.status == 400, response.body


def test_refuses_an_unregistered_path(env, tmp_path):
    unregistered = tmp_path / "NeverIndexed"
    unregistered.mkdir()
    response = _run(app_mod.handle_delete_project(
        _StubRequest({"project_path": str(unregistered), "confirm": True}),
    ))
    assert response.status == 404, response.body
    assert not indexing._INDEX_LOCK_PATH.exists(), "an unregistered path must never take the lock"


def test_refuses_missing_project_path(env):
    response = _run(app_mod.handle_delete_project(_StubRequest({"confirm": True})))
    assert response.status == 400, response.body


def test_accepts_a_registered_path_with_confirm_and_succeeds(env, monkeypatch):
    calls = []
    monkeypatch.setattr(
        indexing, "delete_project_index",
        lambda p: (calls.append(p), {
            "project_path": p, "dirs_removed": [], "dirs_failed": [],
            "dirs_left_on_disk": [], "registry_removed": ["mine"],
        })[1],
    )
    monkeypatch.setattr(app_mod, "delete_project_index", indexing.delete_project_index)

    response = _run(app_mod.handle_delete_project(
        _StubRequest({"project_path": str(env["project"]), "confirm": True}),
    ))
    assert response.status == 200, response.body
    assert calls == [str(env["project"])]
    assert not indexing._INDEX_LOCK_PATH.exists(), "the lock must be released after success"


def test_lock_is_released_even_when_delete_project_index_raises(env, monkeypatch):
    """property 7: every path out of the handler releases the lock, including
    an exception raised from inside the executor call."""

    def _boom(p):
        raise RuntimeError("disk exploded")

    monkeypatch.setattr(indexing, "delete_project_index", _boom)
    monkeypatch.setattr(app_mod, "delete_project_index", _boom)

    with pytest.raises(RuntimeError):
        _run(app_mod.handle_delete_project(
            _StubRequest({"project_path": str(env["project"]), "confirm": True}),
        ))

    assert not indexing._INDEX_LOCK_PATH.exists(), (
        "the index lock was left held after an exception mid-delete, so every "
        "other index operation is now stuck behind a lock nothing will ever "
        "release until the server restarts"
    )


def test_refuses_when_lock_already_held(env, monkeypatch):
    assert indexing.acquire_index_lock("index", str(env["project"]))
    try:
        response = _run(app_mod.handle_delete_project(
            _StubRequest({"project_path": str(env["project"]), "confirm": True}),
        ))
        assert response.status == 423, response.body
    finally:
        indexing.release_index_lock()
