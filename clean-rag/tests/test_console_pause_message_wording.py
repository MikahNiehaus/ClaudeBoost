"""Adversarial bad-cop re-check on the pause notification wording.

A prior bad-cop pass nit-fixed verifier-record.py's read-failure message. As
part of that same round the orchestrator also renamed the pause notification's
"released" to "evicted" in cli/console.py. This drives the real Pause button
through Textual's pilot, the same way test_console_delete_button.py does, and
asserts on the actual notify() call rather than reading the source.

Nothing talks to a real server; _get and _post are replaced.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

textual = pytest.importorskip("textual", reason="the console is an optional extra")

from cli import console as con  # noqa: E402
from textual.widgets import Button  # noqa: E402

ONE_PROJECT_STATUS = {
    "status": "ready",
    "ram_mb": 1000,
    "loaded_models": ["nomic-ai/CodeRankEmbed"],
    "projects": {
        "count": 1,
        "entries": {
            "alpha-1111": {
                "project_path": r"C:\Development\Alpha",
                "files_indexed": 5, "chunks_created": 9,
                "indexed_at": "2026-09-17T00:00:00+00:00",
            },
        },
    },
}


@pytest.fixture
def wired(monkeypatch):
    posts = []

    def _fake_get(path, timeout=4.0):
        return ONE_PROJECT_STATUS if path == "/status" else None

    monkeypatch.setattr(con, "_get", _fake_get)
    monkeypatch.setattr(con, "_lock_state", lambda: ("", ""))
    return posts


async def _drive_pause(monkeypatch, wired, post_body):
    said = []

    def _fake_post(path, payload, timeout=10.0):
        wired.append((path, payload))
        return 200, post_body

    monkeypatch.setattr(con, "_post", _fake_post)
    monkeypatch.setattr(
        con.ConsoleApp, "notify",
        lambda self, message, **kw: said.append((message, kw.get("timeout"))),
    )

    app = con.ConsoleApp()
    async with app.run_test(size=(140, 40)) as pilot:
        await pilot.pause()
        app.query_one("#pause", Button).press()
        await pilot.pause()
    return said


@pytest.mark.asyncio
async def test_pause_message_says_evicted_not_released_or_freed(wired, monkeypatch):
    """Neither "released" nor "freed" may appear: the nit fixed exactly this
    word ("released" reads as "freed", both claim memory was returned to the
    OS, which torch does not do)."""
    said = await _drive_pause(
        monkeypatch, wired, {
            "paused": True, "models_evicted": ["nomic-ai/CodeRankEmbed"],
            "indexing_still_finishing": False, "indexing_project": None,
        },
    )
    assert len(said) == 1
    message, timeout = said[0]
    assert "evicted" in message
    assert "released" not in message
    assert "freed" not in message
    assert "1 model(s) evicted" in message


@pytest.mark.asyncio
async def test_pause_message_has_no_dash_of_any_kind(wired, monkeypatch):
    """comment-humanness-check.py hard-blocks any dash in a comment; the same
    project rule applies to user facing prose per this review's correctness
    property 6."""
    said = await _drive_pause(
        monkeypatch, wired, {
            "paused": True, "models_evicted": ["nomic-ai/CodeRankEmbed"],
            "indexing_still_finishing": False, "indexing_project": None,
        },
    )
    message, _ = said[0]
    for dash in ("\u2013", "\u2014", "\u2012", "\u2015", " - ", "--"):
        assert dash not in message, f"found {dash!r} in {message!r}"


@pytest.mark.asyncio
async def test_pause_message_names_a_still_finishing_project_and_stays_readable(
    wired, monkeypatch,
):
    """The longest real shape of this message: eviction count, the capped
    growth clause, the RAM clause, and the still finishing clause. Textual's
    notify() truncates nothing itself, but a message this long is worth
    proving is not silently cut by the widget at render time."""
    said = await _drive_pause(
        monkeypatch, wired, {
            "paused": True,
            "models_evicted": ["nomic-ai/CodeRankEmbed", "Salesforce/SFR-Embedding-Code-400M_R"],
            "indexing_still_finishing": True,
            "indexing_project": r"C:\Development\SomeReallyLongProjectNameHere",
        },
    )
    message, timeout = said[0]
    assert message == (
        "Indexing paused. 2 model(s) evicted, which caps growth. "
        "RAM already in use will not drop much. "
        "SomeReallyLongProjectNameHere finishes first."
    )
    assert timeout == 7


@pytest.mark.asyncio
async def test_pause_message_zero_models_evicted_still_reads_correctly(wired, monkeypatch):
    """Nothing was resident (a pause with no prior search), so the count is
    literally zero. The sentence must still parse as English, not "0
    model(s) evicted"."""
    said = await _drive_pause(
        monkeypatch, wired, {
            "paused": True, "models_evicted": [],
            "indexing_still_finishing": False, "indexing_project": None,
        },
    )
    message, _ = said[0]
    assert message == (
        "Indexing paused. 0 model(s) evicted, which caps growth. "
        "RAM already in use will not drop much."
    )
