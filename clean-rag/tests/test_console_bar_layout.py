"""The console's top bar keeps every button on screen and clickable at common widths."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

textual = pytest.importorskip("textual", reason="the console is an optional extra")

from cli import console as con  # noqa: E402
from textual.widgets import Button  # noqa: E402

# Long model names and a busy lock make the status labels as wide as they get.
BUSY = {
    "status": "ready",
    "ram_mb": 12345,
    "loaded_models": ["nomic-ai/CodeRankEmbed", "example/a-much-longer-embedding-model-name"],
    "projects": {"count": 1, "entries": {"a-1": {"project_path": r"C:\Dev\Alpha"}}},
}
BUTTONS = ("delete", "hours", "pause")


@pytest.fixture
def posts(monkeypatch):
    sent = []
    monkeypatch.setattr(con, "_get", lambda path, timeout=4.0: BUSY if path == "/status" else None)
    monkeypatch.setattr(
        con, "_post", lambda path, body, timeout=10.0: (sent.append(path) or (200, {"paused": True}))
    )
    monkeypatch.setattr(con, "_lock_state", lambda: ("index-project", r"C:\Dev\Pantry"))
    monkeypatch.setattr(con.LogTail, "poll", lambda self: [])
    return sent


@pytest.mark.asyncio
@pytest.mark.parametrize("width", [80, 100, 120, 160])
async def test_bar_buttons_fit_without_overlapping(posts, width):
    app = con.ConsoleApp()
    async with app.run_test(size=(width, 30)) as pilot:
        await pilot.pause()
        regions = [app.query_one(f"#{b}", Button).region for b in BUTTONS]
        for left, right in zip(regions, regions[1:]):
            assert left.right <= right.x, (width, regions)
        for region in regions:
            assert region.width > 0 and region.right <= width, (width, regions)

        await pilot.click("#pause")
        await pilot.pause()
        assert posts == ["/sweep-pause"]
