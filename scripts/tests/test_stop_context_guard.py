"""
Tests for scripts/stop-context-guard.py (Stop hook).

Blocks Claude from stopping when context.md is stale after many tool uses.
Exit 0 (allow) or 2 (block).
"""
from __future__ import annotations

import json
import time
import pytest
from helpers import SCRIPTS_DIR, run_hook


def _stop() -> dict:
    return {"hook_event_name": "Stop", "session_id": "test"}


# ---------------------------------------------------------------------------
# Below threshold: always allow
# ---------------------------------------------------------------------------

def test_passes_when_below_threshold(boost_home):
    ct = boost_home / "state" / "compaction-tracker.json"
    ct.write_text(json.dumps({"edit_count": 3}), encoding="utf-8")

    result = run_hook(
        "stop-context-guard.py",
        _stop(),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0


def test_passes_when_no_workspace(boost_home):
    ct = boost_home / "state" / "compaction-tracker.json"
    ct.write_text(json.dumps({"edit_count": 50}), encoding="utf-8")
    # No workspace directory

    result = run_hook(
        "stop-context-guard.py",
        _stop(),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0


# ---------------------------------------------------------------------------
# Above threshold + fresh context: allow
# ---------------------------------------------------------------------------

def test_passes_when_context_fresh(boost_home):
    ct = boost_home / "state" / "compaction-tracker.json"
    ct.write_text(json.dumps({"edit_count": 10}), encoding="utf-8")

    ws_dir = boost_home / "workspace" / "task-1"
    ws_dir.mkdir(parents=True)
    ctx = ws_dir / "context.md"
    ctx.write_text("# Task\nStatus: current", encoding="utf-8")
    # mtime is just now — fresh

    result = run_hook(
        "stop-context-guard.py",
        _stop(),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0


# ---------------------------------------------------------------------------
# Above threshold + stale context: block
# ---------------------------------------------------------------------------

def test_blocks_when_context_stale(boost_home):
    ct = boost_home / "state" / "compaction-tracker.json"
    # edit_count=10, THRESHOLD=5, FIRE_EVERY=5 → (10-5)%5 == 0 → fires
    ct.write_text(json.dumps({"edit_count": 10}), encoding="utf-8")

    ws_dir = boost_home / "workspace" / "task-stale"
    ws_dir.mkdir(parents=True)
    ctx = ws_dir / "context.md"
    ctx.write_text("# Task\nStatus: old", encoding="utf-8")

    # Make it appear 15 minutes old (past 10-minute stale threshold)
    old_time = time.time() - 900
    import os
    os.utime(str(ctx), (old_time, old_time))

    result = run_hook(
        "stop-context-guard.py",
        _stop(),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 2
    assert result.stdout.strip()
    output = json.loads(result.stdout)
    assert output.get("decision") == "block"
    assert "context.md" in output.get("reason", "").lower()


# ---------------------------------------------------------------------------
# NEEDS_VERIFICATION flag: mentioned in block message
# ---------------------------------------------------------------------------

def test_block_message_mentions_verification_when_flag_set(boost_home):
    ct = boost_home / "state" / "compaction-tracker.json"
    ct.write_text(json.dumps({"edit_count": 10}), encoding="utf-8")

    ws_dir = boost_home / "workspace" / "task-verify"
    ws_dir.mkdir(parents=True)
    ctx = ws_dir / "context.md"
    ctx.write_text("# Task\nStatus: check needed", encoding="utf-8")

    old_time = time.time() - 900
    import os
    os.utime(str(ctx), (old_time, old_time))

    # Set the needs-verification flag
    flag = boost_home / "state" / "needs-verification.json"
    flag.write_text(json.dumps({
        "flagged_at": "2026-01-01T00:00:00Z",
        "finding_summary": "SQL injection in query.py:42",
    }), encoding="utf-8")

    result = run_hook(
        "stop-context-guard.py",
        _stop(),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 2
    reason = json.loads(result.stdout).get("reason", "")
    assert "NEEDS_VERIFICATION" in reason or "evaluator" in reason.lower()
