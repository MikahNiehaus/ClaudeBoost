"""
Tests for scripts/session-clear-save.py (SessionEnd hook).

Saves workspace context to handoff-latest.json on /clear. Always exits 0.
"""
from __future__ import annotations

import json
import pytest
from helpers import SCRIPTS_DIR, run_hook


def _session_end(source: str = "clear", session_id: str = "test", cwd: str = "/test") -> dict:
    return {
        "hook_event_name": "SessionEnd",
        "session_id": session_id,
        "source": source,
        "cwd": cwd,
        "transcript_path": "",
    }


# ---------------------------------------------------------------------------
# Always exits 0
# ---------------------------------------------------------------------------

def test_always_exits_0(boost_home):
    result = run_hook(
        "session-clear-save.py",
        _session_end(),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0


def test_exits_0_on_compact_source(boost_home):
    # "compact" source should be skipped (not our trigger)
    result = run_hook(
        "session-clear-save.py",
        _session_end(source="compact"),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0


# ---------------------------------------------------------------------------
# Creates handoff-latest.json on clear
# ---------------------------------------------------------------------------

def test_creates_handoff_on_clear(boost_home):
    handoff_path = boost_home / "state" / "handoff-latest.json"
    assert not handoff_path.exists()

    result = run_hook(
        "session-clear-save.py",
        _session_end(source="clear", session_id="test-sess", cwd="/myproject"),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0
    assert handoff_path.exists()

    handoff = json.loads(handoff_path.read_text(encoding="utf-8"))
    assert handoff.get("trigger") == "SessionEnd(clear)"
    assert handoff.get("session_id") == "test-sess"


# ---------------------------------------------------------------------------
# Includes workspace context
# ---------------------------------------------------------------------------

def test_includes_workspace_memo(boost_home):
    ws_dir = boost_home / "workspace" / "task-abc"
    ws_dir.mkdir(parents=True)
    (ws_dir / "context.md").write_text(
        "# Task ABC\n## Goal\nImplement thing\n## Status\nIn progress",
        encoding="utf-8",
    )

    result = run_hook(
        "session-clear-save.py",
        _session_end(),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0

    handoff_path = boost_home / "state" / "handoff-latest.json"
    handoff = json.loads(handoff_path.read_text(encoding="utf-8"))
    memo = handoff.get("workspace_memo", "")
    assert "task-abc" in memo


# ---------------------------------------------------------------------------
# Resets behavior and compaction trackers
# ---------------------------------------------------------------------------

def test_resets_behavior_tracker(boost_home):
    bt = boost_home / "state" / "behavior-tracker.json"
    bt.write_text(json.dumps({
        "reads_since_rag": 99,
        "tasks_since_evaluator": 5,
    }), encoding="utf-8")

    result = run_hook(
        "session-clear-save.py",
        _session_end(),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0

    tracker = json.loads(bt.read_text(encoding="utf-8"))
    assert tracker.get("reads_since_rag", 99) == 0


# ---------------------------------------------------------------------------
# Outputs additionalContext
# ---------------------------------------------------------------------------

def test_outputs_additional_context(boost_home):
    result = run_hook(
        "session-clear-save.py",
        _session_end(),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0
    if result.stdout.strip():
        output = json.loads(result.stdout)
        assert "additionalContext" in output


# ---------------------------------------------------------------------------
# Skips non-clear sources
# ---------------------------------------------------------------------------

def test_skips_unknown_source(boost_home):
    result = run_hook(
        "session-clear-save.py",
        _session_end(source="startup"),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0
    assert result.stdout.strip() == b""
