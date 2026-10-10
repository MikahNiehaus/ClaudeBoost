"""The off-hours limit on automatic sweeps: the clock check, the route, and the console toggle."""
import asyncio
import json
import sys
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server import app as app_mod  # noqa: E402
from server import auto_reindex as ar  # noqa: E402


def _at(hour: int, minute: int = 0) -> time.struct_time:
    return time.struct_time((2026, 9, 29, hour, minute, 0, 1, 272, -1))


@pytest.fixture(autouse=True)
def _reset_flags():
    paused, hours = ar._paused, ar._hours_only
    cache = app_mod._model_cache
    yield
    ar._paused, ar._hours_only = paused, hours
    app_mod._model_cache = cache


@pytest.mark.parametrize("hour,minute,inside", [
    (8, 59, False), (9, 0, True), (12, 30, True), (16, 59, True), (17, 0, False), (23, 0, False), (0, 0, False),
])
def test_window_boundaries_when_on(hour, minute, inside):
    ar.set_hours_only(True)
    assert ar.in_work_hours(_at(hour, minute)) is inside


@pytest.mark.parametrize("hour", [0, 9, 12, 16, 23])
def test_off_never_blocks(hour):
    ar.set_hours_only(False)
    assert ar.in_work_hours(_at(hour)) is False


def _post(body):
    request = MagicMock()
    request.json = AsyncMock(return_value=body)
    resp = asyncio.run(app_mod.handle_sweep_pause(request))
    return resp.status, json.loads(resp.body)


def test_hours_only_alone_leaves_pause_and_models_alone():
    ar.set_paused(False)
    cache = MagicMock()
    cache.loaded_models.return_value = ["m"]
    app_mod._model_cache = cache

    status, body = _post({"hours_only": True})

    assert status == 200
    assert body["hours_only"] is True
    assert body["paused"] is False
    assert body["models_evicted"] == []
    cache.evict_all.assert_not_called()
    assert ar.is_hours_only() is True


def test_pause_alone_leaves_hours_only_alone():
    ar.set_hours_only(True)
    app_mod._model_cache = None
    status, body = _post({"paused": True})
    assert status == 200
    assert body == {**body, "paused": True, "hours_only": True}


@pytest.mark.parametrize("body", [{}, {"other": 1}, {"hours_only": "false"}, {"paused": 0}, [True]])
def test_bad_bodies_are_rejected_and_change_nothing(body):
    ar.set_paused(False)
    ar.set_hours_only(False)
    status, _ = _post(body)
    assert status == 400
    assert ar.is_paused() is False
    assert ar.is_hours_only() is False


def test_status_reports_both_flags(monkeypatch):
    monkeypatch.setattr(app_mod, "_list_projects", lambda: {})
    app_mod._model_cache = None
    ar.set_paused(True)
    ar.set_hours_only(True)
    resp = asyncio.run(app_mod.handle_status(MagicMock()))
    data = json.loads(resp.body)
    assert data["paused"] is True
    assert data["hours_only"] is True


def test_sweep_skips_inside_work_hours(monkeypatch):
    """Drive the real loop for one tick at 10:00 and prove it never reads the registry."""
    ar.set_paused(False)
    ar.set_hours_only(True)
    monkeypatch.setattr(ar.time, "localtime", lambda *a: _at(10))

    calls = {"sleep": 0, "registry": 0}

    async def _sleep(_s):
        calls["sleep"] += 1
        if calls["sleep"] > 1:
            raise asyncio.CancelledError

    def _registry():
        calls["registry"] += 1
        return {}

    monkeypatch.setattr(ar.asyncio, "sleep", _sleep)
    monkeypatch.setattr(ar, "_read_registry", _registry)
    monkeypatch.setattr(ar, "get_model_cache", lambda: MagicMock(), raising=False)

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(ar.auto_reindex_loop(lambda: MagicMock()))
    assert calls["registry"] == 0

    calls["sleep"] = 0
    monkeypatch.setattr(ar.time, "localtime", lambda *a: _at(20))
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(ar.auto_reindex_loop(lambda: MagicMock()))
    assert calls["registry"] == 1


def test_sweep_stops_before_next_project_once_work_hours_start(monkeypatch):
    """A sweep already underway finishes its current project, then stops before the next."""
    ar.set_paused(False)
    ar.set_hours_only(True)
    monkeypatch.setattr(ar.time, "localtime", lambda *a: _at(20))

    calls = {"sleep": 0}

    async def _sleep(_s):
        calls["sleep"] += 1
        if calls["sleep"] > 1:
            raise asyncio.CancelledError

    async def _headroom(*a, **k):
        return True

    projects = [
        ar.PlannedProject(pid="p1", path="/p1", model=None, size=1),
        ar.PlannedProject(pid="p2", path="/p2", model=None, size=1),
    ]
    swept = []

    async def _sweep_project(pid, entry, model_cache):
        swept.append(pid)
        # Work hours start partway through the first project's own sweep.
        monkeypatch.setattr(ar.time, "localtime", lambda *a: _at(10))
        return True

    monkeypatch.setattr(ar.asyncio, "sleep", _sleep)
    monkeypatch.setattr(ar, "_read_registry", lambda: {"p1": {}, "p2": {}})
    monkeypatch.setattr(ar, "plan_sweep", lambda registry: projects)
    monkeypatch.setattr(ar, "wait_for_cpu_headroom", _headroom)
    monkeypatch.setattr(ar, "wait_for_system_headroom", _headroom)
    monkeypatch.setattr(ar, "_sweep_project", _sweep_project)
    monkeypatch.setattr(ar, "_release_project_resources", lambda pid: None)

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(ar.auto_reindex_loop(lambda: MagicMock()))

    assert swept == ["p1"]


textual = pytest.importorskip("textual", reason="the console is an optional extra")

from cli import console as con  # noqa: E402
from textual.widgets import Button  # noqa: E402


@pytest.fixture
def console(monkeypatch):
    posts = []
    server = {"hours_only": False}

    def _get(path, timeout=4.0):
        if path != "/status":
            return None
        return {"status": "ready", "ram_mb": 1, "loaded_models": [],
                "projects": {"count": 0, "entries": {}},
                "paused": False, "hours_only": server["hours_only"]}

    def _post_(path, payload, timeout=10.0):
        posts.append((path, payload))
        server["hours_only"] = payload["hours_only"]
        return 200, {"paused": False, "hours_only": payload["hours_only"],
                     "models_evicted": [], "indexing_project": ""}

    monkeypatch.setattr(con, "_get", _get)
    monkeypatch.setattr(con, "_post", _post_)
    monkeypatch.setattr(con, "_lock_state", lambda: ("", ""))
    return posts, server


@pytest.mark.asyncio
async def test_hours_button_posts_the_toggle_and_shows_the_answer(console):
    posts, _ = console
    app = con.ConsoleApp()
    async with app.run_test(size=(160, 40)) as pilot:
        await pilot.pause()
        button = app.query_one("#hours", Button)
        assert str(button.label) == "Off-hours only: off"

        button.press()
        await pilot.pause()
        assert posts == [("/sweep-pause", {"hours_only": True})]
        assert str(button.label) == "Off-hours only: on"
        assert button.has_class("-on")

        await pilot.press("h")
        await pilot.pause()
        assert posts[-1] == ("/sweep-pause", {"hours_only": False})
        assert str(button.label) == "Off-hours only: off"


@pytest.mark.asyncio
async def test_console_opened_later_shows_the_server_state(console):
    _, server = console
    server["hours_only"] = True
    app = con.ConsoleApp()
    async with app.run_test(size=(160, 40)) as pilot:
        await pilot.pause()
        assert str(app.query_one("#hours", Button).label) == "Off-hours only: on"
