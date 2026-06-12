"""
Tests for scripts/compaction-save.py (PreCompact hook).

Saves workspace context to compaction-memo.json and handoff-latest.json.
Always exits 0.
"""
from __future__ import annotations

import json
import pytest
from helpers import SCRIPTS_DIR, run_hook


def _precompact(session_id: str = "test-session", cwd: str = "/test") -> dict:
    return {
        "hook_event_name": "PreCompact",
        "session_id": session_id,
        "cwd": cwd,
        "transcript_path": "",
    }


# ---------------------------------------------------------------------------
# Always exits 0
# ---------------------------------------------------------------------------

def test_always_exits_0(boost_home):
    result = run_hook(
        "compaction-save.py",
        _precompact(),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0


def test_exits_0_no_workspaces(boost_home):
    result = run_hook(
        "compaction-save.py",
        _precompact(),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0


# ---------------------------------------------------------------------------
# Creates compaction-memo.json
# ---------------------------------------------------------------------------

def test_creates_compaction_memo(boost_home):
    memo_path = boost_home / "state" / "compaction-memo.json"
    assert not memo_path.exists()

    result = run_hook(
        "compaction-save.py",
        _precompact(),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0
    assert memo_path.exists()

    memo = json.loads(memo_path.read_text(encoding="utf-8"))
    assert "memo" in memo
    assert memo.get("compaction_number") == 1


def test_increments_compaction_number(boost_home):
    memo_path = boost_home / "state" / "compaction-memo.json"
    memo_path.write_text(json.dumps({
        "compaction_number": 5,
        "memo": "old memo",
        "session_id": "old",
        "timestamp": "2026-01-01T00:00:00Z",
    }), encoding="utf-8")

    result = run_hook(
        "compaction-save.py",
        _precompact(),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0

    memo = json.loads(memo_path.read_text(encoding="utf-8"))
    assert memo.get("compaction_number") == 6


# ---------------------------------------------------------------------------
# Creates handoff-latest.json
# ---------------------------------------------------------------------------

def test_creates_handoff_latest(boost_home):
    handoff_path = boost_home / "state" / "handoff-latest.json"

    result = run_hook(
        "compaction-save.py",
        _precompact(session_id="my-session", cwd="/myproject"),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0
    assert handoff_path.exists()

    handoff = json.loads(handoff_path.read_text(encoding="utf-8"))
    assert handoff.get("trigger") == "PreCompact"
    assert handoff.get("session_id") == "my-session"
    assert "workspace_memo" in handoff


# ---------------------------------------------------------------------------
# Includes workspace context summaries
# ---------------------------------------------------------------------------

def test_includes_workspace_context(boost_home):
    ws_dir = boost_home / "workspace" / "task-99"
    ws_dir.mkdir(parents=True)
    ctx = ws_dir / "context.md"
    ctx.write_text("# Task 99\n## Goal\nBuild the thing\n## Status\nIn progress", encoding="utf-8")

    result = run_hook(
        "compaction-save.py",
        _precompact(),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0

    memo_path = boost_home / "state" / "compaction-memo.json"
    memo = json.loads(memo_path.read_text(encoding="utf-8"))
    assert "task-99" in memo.get("memo", "")


# ---------------------------------------------------------------------------
# Outputs additionalContext
# ---------------------------------------------------------------------------

def test_outputs_additional_context(boost_home):
    result = run_hook(
        "compaction-save.py",
        _precompact(),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0
    assert result.stdout.strip()
    output = json.loads(result.stdout)
    assert "additionalContext" in output


# ---------------------------------------------------------------------------
# Archives previous memo
# ---------------------------------------------------------------------------

def test_archives_previous_memo(boost_home):
    memo_path = boost_home / "state" / "compaction-memo.json"
    memo_path.write_text(json.dumps({
        "compaction_number": 1,
        "memo": "previous memo",
        "session_id": "old-session",
        "timestamp": "2026-01-01T00:00:00Z",
    }), encoding="utf-8")

    result = run_hook(
        "compaction-save.py",
        _precompact(),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0
    history_dir = boost_home / "state" / "compaction-history"
    assert history_dir.exists()
    history_files = list(history_dir.glob("*.json"))
    assert len(history_files) == 1
