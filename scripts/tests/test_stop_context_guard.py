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


# ---------------------------------------------------------------------------
# Line 41-42: tracker file unreadable — falls back to edit_count=0 (allow)
# ---------------------------------------------------------------------------

def test_passes_when_tracker_file_missing(boost_home):
    # No compaction-tracker.json at all — except branch sets edit_count=0
    result = run_hook(
        "stop-context-guard.py",
        _stop(),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0


def test_passes_when_tracker_file_corrupt(boost_home):
    # Corrupt JSON — except branch sets edit_count=0, below threshold → allow
    ct = boost_home / "state" / "compaction-tracker.json"
    ct.write_text("NOT VALID JSON {{{{", encoding="utf-8")

    result = run_hook(
        "stop-context-guard.py",
        _stop(),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0


# ---------------------------------------------------------------------------
# Line 50: rate limiter — edit_count above threshold but not on a FIRE_EVERY
# boundary, so guard stays quiet
# ---------------------------------------------------------------------------

def test_passes_when_above_threshold_but_not_on_fire_boundary(boost_home):
    # THRESHOLD=5, FIRE_EVERY=5 → (edit_count - 5) % 5 != 0 for edit_count=11
    ct = boost_home / "state" / "compaction-tracker.json"
    ct.write_text(json.dumps({"edit_count": 11}), encoding="utf-8")

    # Even with a stale context, the rate limiter fires first and returns 0
    ws_dir = boost_home / "workspace" / "task-rate"
    ws_dir.mkdir(parents=True)
    ctx = ws_dir / "context.md"
    ctx.write_text("# Task", encoding="utf-8")
    import os
    old_time = time.time() - 900
    os.utime(str(ctx), (old_time, old_time))

    result = run_hook(
        "stop-context-guard.py",
        _stop(),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0


# ---------------------------------------------------------------------------
# Line 64: workspace exists but no context.md touched in this session window
# (all context.md files are older than SESSION_WINDOW_HOURS)
# ---------------------------------------------------------------------------

def test_passes_when_no_context_files_in_session_window(boost_home):
    ct = boost_home / "state" / "compaction-tracker.json"
    # edit_count fires: (10-5)%5==0
    ct.write_text(json.dumps({"edit_count": 10}), encoding="utf-8")

    ws_dir = boost_home / "workspace" / "task-old"
    ws_dir.mkdir(parents=True)
    ctx = ws_dir / "context.md"
    ctx.write_text("# Task\nFrom last week", encoding="utf-8")

    # Backdate to 5 hours ago — beyond SESSION_WINDOW_HOURS=4
    import os
    ancient = time.time() - (5 * 3600)
    os.utime(str(ctx), (ancient, ancient))

    result = run_hook(
        "stop-context-guard.py",
        _stop(),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0


# ---------------------------------------------------------------------------
# Lines 84-85: needs-verification.json exists but is corrupt JSON
# — except branch sets flag_data={}, no warning emitted (flagged_at absent)
# ---------------------------------------------------------------------------

def test_block_message_no_verification_warning_when_flag_file_corrupt(boost_home):
    ct = boost_home / "state" / "compaction-tracker.json"
    ct.write_text(json.dumps({"edit_count": 10}), encoding="utf-8")

    ws_dir = boost_home / "workspace" / "task-corrupt-flag"
    ws_dir.mkdir(parents=True)
    ctx = ws_dir / "context.md"
    ctx.write_text("# Task", encoding="utf-8")
    import os
    old_time = time.time() - 900
    os.utime(str(ctx), (old_time, old_time))

    # Write a corrupt needs-verification.json
    flag = boost_home / "state" / "needs-verification.json"
    flag.write_text("NOT VALID JSON {{{{", encoding="utf-8")

    result = run_hook(
        "stop-context-guard.py",
        _stop(),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    # Still blocks (stale context), but no NEEDS_VERIFICATION warning
    assert result.returncode == 2
    reason = json.loads(result.stdout).get("reason", "")
    assert "NEEDS_VERIFICATION" not in reason
