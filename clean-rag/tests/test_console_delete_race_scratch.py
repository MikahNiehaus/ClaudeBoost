"""Scratch adversarial test for property 8 (bad-cop QA pass, not part of the
diff under review). Proves what a table refresh between dialog-open and
dialog-confirm actually does to which project gets deleted."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

textual = pytest.importorskip("textual", reason="the console is an optional extra")

from cli import console as con  # noqa: E402
from textual.widgets import Button, DataTable  # noqa: E402

TWO_PROJECTS = {
    "status": "ready", "ram_mb": 1000, "loaded_models": [],
    "projects": {"count": 2, "entries": {
        "alpha-1111": {"project_path": r"C:\Development\Alpha",
                        "files_indexed": 5, "chunks_created": 9},
        "beta-2222": {"project_path": r"C:\Development\Beta",
                       "files_indexed": 7, "chunks_created": 11},
    }},
}

# A refresh that arrives mid-dialog: alpha has moved/renamed on disk, so its
# project_path is now different, SAME pid.
REFRESH_MID_DIALOG = {
    "status": "ready", "ram_mb": 1000, "loaded_models": [],
    "projects": {"count": 2, "entries": {
        "alpha-1111": {"project_path": r"C:\Development\Alpha-RENAMED",
                        "files_indexed": 5, "chunks_created": 9},
        "beta-2222": {"project_path": r"C:\Development\Beta",
                       "files_indexed": 7, "chunks_created": 11},
    }},
}


@pytest.mark.asyncio
async def test_refresh_mid_dialog_does_not_change_the_delete_target(monkeypatch):
    posts = []
    status_holder = {"data": TWO_PROJECTS}

    def _fake_get(path, timeout=4.0):
        return status_holder["data"] if path == "/status" else None

    def _fake_post(path, payload, timeout=10.0):
        posts.append((path, payload))
        return 200, {"dirs_removed": [], "dirs_failed": [], "registry_removed": ["alpha-1111"]}

    monkeypatch.setattr(con, "_get", _fake_get)
    monkeypatch.setattr(con, "_post", _fake_post)
    monkeypatch.setattr(con, "_lock_state", lambda: ("", ""))
    monkeypatch.setattr(con.LogTail, "poll", lambda self: [])

    app = con.ConsoleApp()
    async with app.run_test(size=(140, 40)) as pilot:
        await pilot.pause()
        table = app.query_one("#projects-table", DataTable)
        table.focus()
        pid_at_open = table.coordinate_to_cell_key(table.cursor_coordinate).row_key.value
        path_captured_at_open = app._paths.get(pid_at_open)
        print(f"selected pid at dialog-open time: {pid_at_open!r}, path captured: {path_captured_at_open!r}")

        await pilot.press("d")
        await pilot.pause()
        assert isinstance(app.screen, con.ConfirmScreen)

        # The 3s refresh timer fires while the dialog is open, and the server
        # now reports a DIFFERENT path for the same project id.
        status_holder["data"] = REFRESH_MID_DIALOG
        app.refresh_status()
        await pilot.pause()
        print(f"self._paths after the mid-dialog refresh: {app._paths}")

        app.screen.query_one("#confirm", Button).press()
        await pilot.pause()

        assert len(posts) == 1
        path_sent, payload = posts[0]
        print(f"path actually sent to /delete-project: {payload['project_path']!r}")

        assert payload["project_path"] == path_captured_at_open, (
            "the delete used the path AFTER a mid-dialog refresh instead of "
            "the one shown to the user when they confirmed the dialog text"
        )
