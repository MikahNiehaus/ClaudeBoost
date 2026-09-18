"""The console's Delete button, driven for real through Textual's pilot.

The dangerous part of a delete button is not the request. It is sending the
wrong project, or sending anything at all without a confirmation. Both are
driven here rather than reasoned about.

Nothing talks to a real server: _get and _post are replaced, so a failure here
is the console's fault and a pass does not depend on anything being up.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

textual = pytest.importorskip("textual", reason="the console is an optional extra")

from cli import console as con  # noqa: E402
from textual.widgets import Button, DataTable  # noqa: E402

TWO_PROJECTS = {
    "status": "ready",
    "ram_mb": 1000,
    "loaded_models": ["nomic-ai/CodeRankEmbed"],
    "projects": {
        "count": 2,
        "entries": {
            "alpha-1111": {
                "project_path": r"C:\Development\Alpha",
                "files_indexed": 5, "chunks_created": 9,
                "indexed_at": "2026-09-17T00:00:00+00:00",
            },
            "beta-2222": {
                "project_path": r"C:\Development\Beta",
                "files_indexed": 7, "chunks_created": 11,
                "indexed_at": "2026-09-17T00:00:00+00:00",
            },
        },
    },
}


@pytest.fixture
def wired(monkeypatch):
    """Console with a fake server. Returns the list of POSTs it made."""
    posts = []

    def _fake_get(path, timeout=4.0):
        return TWO_PROJECTS if path == "/status" else None

    def _fake_post(path, payload, timeout=10.0):
        posts.append((path, payload))
        return 200, {"dirs_removed": [r"C:\fake\dir"], "dirs_failed": [],
                     "registry_removed": ["alpha-1111"]}

    monkeypatch.setattr(con, "_get", _fake_get)
    monkeypatch.setattr(con, "_post", _fake_post)
    monkeypatch.setattr(con, "_lock_state", lambda: ("", ""))
    # The real tailer would read the live server log.
    monkeypatch.setattr(con.LogTail, "poll", lambda self: [])
    return posts


@pytest.mark.asyncio
async def test_pressing_delete_asks_before_it_does_anything(wired):
    app = con.ConsoleApp()
    async with app.run_test(size=(140, 40)) as pilot:
        await pilot.pause()
        app.query_one("#projects-table", DataTable).focus()
        await pilot.press("d")
        await pilot.pause()

        assert isinstance(app.screen, con.ConfirmScreen), (
            "Delete opened no confirmation, so one keypress would destroy an index"
        )
        assert wired == [], "a request went out before the user confirmed"


@pytest.mark.asyncio
async def test_cancelling_sends_nothing(wired):
    app = con.ConsoleApp()
    async with app.run_test(size=(140, 40)) as pilot:
        await pilot.pause()
        app.query_one("#projects-table", DataTable).focus()
        await pilot.press("d")
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()

        assert not isinstance(app.screen, con.ConfirmScreen)
        assert wired == [], "cancel still sent a delete"


@pytest.mark.asyncio
async def test_confirming_sends_the_real_path_of_the_highlighted_row(wired):
    """The Directory column is truncated from the left to fit. Sending what is
    on screen would delete nothing, or the wrong thing."""
    app = con.ConsoleApp()
    async with app.run_test(size=(140, 40)) as pilot:
        await pilot.pause()
        table = app.query_one("#projects-table", DataTable)
        table.focus()
        pid = table.coordinate_to_cell_key(table.cursor_coordinate).row_key.value

        await pilot.press("d")
        await pilot.pause()
        app.screen.query_one("#confirm", Button).press()
        await pilot.pause()

        assert len(wired) == 1
        path, payload = wired[0]
        assert path == "/delete-project"
        assert payload["confirm"] is True
        assert payload["project_path"] == TWO_PROJECTS["projects"]["entries"][pid]["project_path"]
        assert "..." not in payload["project_path"]


@pytest.mark.asyncio
async def test_the_pause_button_does_not_fire_a_delete(wired):
    """on_button_pressed used to ignore which button was pressed, so adding a
    second one made every click pause."""
    app = con.ConsoleApp()
    async with app.run_test(size=(140, 40)) as pilot:
        await pilot.pause()
        app.query_one("#pause", Button).press()
        await pilot.pause()

        assert [p for p, _ in wired] == ["/sweep-pause"]


@pytest.mark.asyncio
async def test_the_delete_button_does_not_fire_a_pause(wired):
    app = con.ConsoleApp()
    async with app.run_test(size=(140, 40)) as pilot:
        await pilot.pause()
        app.query_one("#delete", Button).press()
        await pilot.pause()

        assert isinstance(app.screen, con.ConfirmScreen)
        assert wired == []


@pytest.mark.asyncio
async def test_no_age_column_is_rendered(wired):
    """Age is not a state here: reindexing is incremental and content hash
    keyed, so an old index is not a stale one."""
    app = con.ConsoleApp()
    async with app.run_test(size=(140, 40)) as pilot:
        await pilot.pause()
        labels = [
            str(c.label) for c in app.query_one("#projects-table", DataTable).columns.values()
        ]

        assert "Indexed" not in labels
        assert not hasattr(con, "_age")
        assert not hasattr(con, "_age_style")


@pytest.mark.asyncio
async def test_the_per_run_counters_are_not_labelled_as_totals(wired):
    """files_indexed counts one run's work, not the index size."""
    app = con.ConsoleApp()
    async with app.run_test(size=(140, 40)) as pilot:
        await pilot.pause()
        labels = [
            str(c.label) for c in app.query_one("#projects-table", DataTable).columns.values()
        ]

        assert "Files" not in labels
        assert "Run files" in labels
        assert "Run chunks" in labels
