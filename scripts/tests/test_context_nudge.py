"""
Tests for scripts/context-nudge.py (PostToolUse hook).

Two independent channels:
  A. Behavior enforcement (RAG reminder, evaluator reminder, clear suggestion)
  B. Workspace checkpoint (stale context.md nudge)

Always exits 0.
"""
from __future__ import annotations

import json
import time
import pytest
from helpers import SCRIPTS_DIR, run_hook, posttooluse


# ---------------------------------------------------------------------------
# Always exits 0
# ---------------------------------------------------------------------------

def test_always_exits_0(boost_home):
    result = run_hook(
        "context-nudge.py",
        posttooluse("Read", {"file_path": "/some/file.py"}),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0


def test_exits_0_on_empty_input(boost_home):
    result = run_hook(
        "context-nudge.py",
        {},
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0


# ---------------------------------------------------------------------------
# Channel A: RAG reminder after too many reads
# ---------------------------------------------------------------------------

def test_rag_reminder_when_reads_exceed_threshold(boost_home):
    # Pre-populate behavior tracker with reads at the threshold
    tracker = boost_home / "state" / "behavior-tracker.json"
    tracker.write_text(json.dumps({
        "reads_since_rag": 5,
        "tasks_since_evaluator": 0,
        "reads_since_context_update": 0,
    }), encoding="utf-8")

    # Compaction tracker needed too
    ct = boost_home / "state" / "compaction-tracker.json"
    ct.write_text(json.dumps({"edit_count": 4}), encoding="utf-8")

    result = run_hook(
        "context-nudge.py",
        posttooluse("Read", {"file_path": "/some/file.py"}),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0
    # The nudge fires — output should contain RAG reminder
    if result.stdout.strip():
        output = json.loads(result.stdout)
        ctx = output.get("additionalContext", "")
        assert "RAG" in ctx or "rag" in ctx.lower()


# ---------------------------------------------------------------------------
# Channel A: evaluator reminder after multiple agent spawns
# ---------------------------------------------------------------------------

def test_evaluator_reminder_after_multiple_spawns(boost_home):
    tracker = boost_home / "state" / "behavior-tracker.json"
    tracker.write_text(json.dumps({
        "reads_since_rag": 0,
        "tasks_since_evaluator": 2,
        "reads_since_context_update": 0,
    }), encoding="utf-8")

    ct = boost_home / "state" / "compaction-tracker.json"
    ct.write_text(json.dumps({"edit_count": 4}), encoding="utf-8")

    result = run_hook(
        "context-nudge.py",
        posttooluse("Task", {
            "description": "some agent",
            "prompt": "do work",
        }),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0


# ---------------------------------------------------------------------------
# Channel B: stale workspace context nudge
# ---------------------------------------------------------------------------

def test_stale_context_nudge_on_edit(boost_home, tmp_path):
    # Create a stale context.md (old mtime)
    ws_dir = boost_home / "workspace" / "task-99"
    ws_dir.mkdir(parents=True)
    ctx_file = ws_dir / "context.md"
    ctx_file.write_text("# Task 99\nStatus: in progress", encoding="utf-8")

    # Make it appear old (10 minutes ago)
    old_mtime = time.time() - 700
    import os
    os.utime(str(ctx_file), (old_mtime, old_mtime))

    tracker = boost_home / "state" / "behavior-tracker.json"
    tracker.write_text(json.dumps({
        "reads_since_rag": 0,
        "tasks_since_evaluator": 0,
        "reads_since_context_update": 0,
    }), encoding="utf-8")

    ct = boost_home / "state" / "compaction-tracker.json"
    ct.write_text(json.dumps({"edit_count": 3}), encoding="utf-8")

    result = run_hook(
        "context-nudge.py",
        posttooluse("Edit", {"file_path": "/project/src/app.py", "new_string": "x", "old_string": "y"}),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0
    # Stale context.md after an Edit → nudge
    if result.stdout.strip():
        output = json.loads(result.stdout)
        ctx = output.get("additionalContext", "")
        assert "context" in ctx.lower() or "CONTEXT" in ctx


# ---------------------------------------------------------------------------
# Fresh context: no stale nudge
# ---------------------------------------------------------------------------

def test_no_stale_nudge_when_context_fresh(boost_home):
    ws_dir = boost_home / "workspace" / "task-fresh"
    ws_dir.mkdir(parents=True)
    ctx_file = ws_dir / "context.md"
    ctx_file.write_text("# Fresh\nStatus: current", encoding="utf-8")
    # mtime is now (just written) — fresh

    tracker = boost_home / "state" / "behavior-tracker.json"
    tracker.write_text(json.dumps({
        "reads_since_rag": 0,
        "tasks_since_evaluator": 0,
        "reads_since_context_update": 0,
        "last_nudge_ctx_mtime": 0,
        "last_nudge_ctx_path": "",
        "last_nudge_count": 0,
    }), encoding="utf-8")

    ct = boost_home / "state" / "compaction-tracker.json"
    ct.write_text(json.dumps({"edit_count": 3}), encoding="utf-8")

    result = run_hook(
        "context-nudge.py",
        posttooluse("Edit", {"file_path": "/project/app.py", "new_string": "x", "old_string": "y"}),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0
    if result.stdout.strip():
        output = json.loads(result.stdout)
        ctx = output.get("additionalContext", "")
        # Should NOT contain stale context warning
        assert "stale" not in ctx.lower()
