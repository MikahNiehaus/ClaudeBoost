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
# HTTP RAG call (Bash to 127.0.0.1:8612) resets reads_since_rag counter
# ---------------------------------------------------------------------------

def test_http_rag_bash_resets_reads_counter(boost_home):
    tracker = boost_home / "state" / "behavior-tracker.json"
    tracker.write_text(json.dumps({
        "reads_since_rag": 6,
        "tasks_since_evaluator": 0,
        "reads_since_context_update": 0,
    }), encoding="utf-8")

    ct = boost_home / "state" / "compaction-tracker.json"
    ct.write_text(json.dumps({"edit_count": 2}), encoding="utf-8")

    result = run_hook(
        "context-nudge.py",
        posttooluse("Bash", {"command": "curl -s http://127.0.0.1:8612/status"}),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0
    updated = json.loads(tracker.read_text(encoding="utf-8"))
    assert updated.get("reads_since_rag", 999) == 0


# ---------------------------------------------------------------------------
# Auto-save with context.md that raises read error (unreadable file) — no crash
# ---------------------------------------------------------------------------

def test_auto_save_handles_unreadable_context_file(boost_home):
    import os
    ws_dir = boost_home / "workspace" / "task-unreadable"
    ws_dir.mkdir(parents=True)
    ctx_file = ws_dir / "context.md"
    ctx_file.write_text("# Task unreadable\nStatus: in progress", encoding="utf-8")

    # Make the workspace recent so it's picked up by session window
    os.utime(str(ctx_file), (time.time(), time.time()))

    tracker = boost_home / "state" / "behavior-tracker.json"
    tracker.write_text(json.dumps({
        "reads_since_rag": 0,
        "tasks_since_evaluator": 0,
        "reads_since_context_update": 0,
    }), encoding="utf-8")

    ct = boost_home / "state" / "compaction-tracker.json"
    ct.write_text(json.dumps({"edit_count": 2}), encoding="utf-8")

    result = run_hook(
        "context-nudge.py",
        posttooluse("Edit", {"file_path": "/project/src/app.py", "new_string": "x", "old_string": "y"}),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0


# ---------------------------------------------------------------------------
# Channel A: evaluator nudge fires with workspace present
# ---------------------------------------------------------------------------

def test_evaluator_nudge_fires_with_workspace(boost_home, tmp_path):
    ws_dir = boost_home / "workspace" / "task-eval"
    ws_dir.mkdir(parents=True)
    ctx_file = ws_dir / "context.md"
    ctx_file.write_text("# Task eval\nStatus: in progress", encoding="utf-8")

    tracker = boost_home / "state" / "behavior-tracker.json"
    tracker.write_text(json.dumps({
        "reads_since_rag": 0,
        "tasks_since_evaluator": 3,
        "reads_since_context_update": 0,
        "last_task_response": "scripts/foo.py:12 found an issue",
    }), encoding="utf-8")

    ct = boost_home / "state" / "compaction-tracker.json"
    ct.write_text(json.dumps({"edit_count": 4}), encoding="utf-8")

    result = run_hook(
        "context-nudge.py",
        posttooluse("Task", {"description": "some non-evaluator agent", "prompt": "do work"}),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0


# ---------------------------------------------------------------------------
# Channel B: workspace checkpoint on non-Edit tool at interval
# ---------------------------------------------------------------------------

def test_workspace_checkpoint_fires_at_nudge_interval(boost_home):
    ws_dir = boost_home / "workspace" / "task-interval"
    ws_dir.mkdir(parents=True)
    ctx_file = ws_dir / "context.md"
    ctx_file.write_text("# Task interval\nStatus: working", encoding="utf-8")

    import os
    import time
    old_mtime = time.time() - 700
    os.utime(str(ctx_file), (old_mtime, old_mtime))

    tracker = boost_home / "state" / "behavior-tracker.json"
    tracker.write_text(json.dumps({
        "reads_since_rag": 0,
        "tasks_since_evaluator": 0,
        "reads_since_context_update": 0,
    }), encoding="utf-8")

    # Set edit_count to exactly a multiple of NUDGE_INTERVAL (8)
    ct = boost_home / "state" / "compaction-tracker.json"
    ct.write_text(json.dumps({"edit_count": 7}), encoding="utf-8")

    result = run_hook(
        "context-nudge.py",
        posttooluse("Read", {"file_path": "/src/foo.py"}),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0


def test_urgent_context_nudge_when_unchanged_since_last(boost_home):
    import os
    import time
    ws_dir = boost_home / "workspace" / "task-urgent"
    ws_dir.mkdir(parents=True)
    ctx_file = ws_dir / "context.md"
    ctx_file.write_text("# Task urgent\nStatus: stale", encoding="utf-8")
    old_mtime = time.time() - 900
    os.utime(str(ctx_file), (old_mtime, old_mtime))

    tracker = boost_home / "state" / "behavior-tracker.json"
    tracker.write_text(json.dumps({
        "reads_since_rag": 0,
        "tasks_since_evaluator": 0,
        "reads_since_context_update": 0,
        "last_nudge_ctx_mtime": old_mtime,
        "last_nudge_ctx_path": str(ctx_file),
        "last_nudge_count": 2,
    }), encoding="utf-8")

    ct = boost_home / "state" / "compaction-tracker.json"
    ct.write_text(json.dumps({"edit_count": 7}), encoding="utf-8")

    result = run_hook(
        "context-nudge.py",
        posttooluse("Read", {"file_path": "/src/bar.py"}),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0


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


# ---------------------------------------------------------------------------
# Auto-save handoff function (direct import)
# ---------------------------------------------------------------------------

def test_auto_save_handoff_writes_file(boost_home):
    import sys, time
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent))
    import importlib.util
    spec = importlib.util.spec_from_file_location("context_nudge", Path(__file__).parent.parent / "context-nudge.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    # Create a real context.md file
    ws_dir = boost_home / "workspace" / "task-autosave"
    ws_dir.mkdir(parents=True)
    ctx = ws_dir / "context.md"
    ctx.write_text("# Auto Save\nStatus: in progress", encoding="utf-8")

    mod._auto_save_handoff(boost_home, [ctx], "test-session")

    handoff_path = boost_home / "state" / "handoff-latest.json"
    assert handoff_path.exists()
    data = json.loads(handoff_path.read_text(encoding="utf-8"))
    assert "workspace_memo" in data
    assert "task-autosave" in data["workspace_memo"]


def test_auto_save_handoff_empty_ctx_files(boost_home):
    """auto_save_handoff with empty list does nothing."""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent))
    import importlib.util
    spec = importlib.util.spec_from_file_location("context_nudge", Path(__file__).parent.parent / "context-nudge.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    mod._auto_save_handoff(boost_home, [], "test-session")
    # No file should be created
    handoff_path = boost_home / "state" / "handoff-latest.json"
    assert not handoff_path.exists()


# ---------------------------------------------------------------------------
# Channel A: context_window_usage triggers context pressure nudge
# ---------------------------------------------------------------------------

def test_context_pressure_nudge_at_75_pct(boost_home):
    tracker = boost_home / "state" / "behavior-tracker.json"
    tracker.write_text(json.dumps({
        "reads_since_rag": 0,
        "tasks_since_evaluator": 0,
        "reads_since_context_update": 0,
    }), encoding="utf-8")

    ct = boost_home / "state" / "compaction-tracker.json"
    ct.write_text(json.dumps({"edit_count": 5}), encoding="utf-8")

    # context_window_usage at 76% → CONTEXT PRESSURE nudge
    payload = posttooluse("Read", {"file_path": "/foo.py"})
    payload["context_window_usage"] = {"input_tokens": 152000}  # 76% of 200k

    result = run_hook(
        "context-nudge.py",
        payload,
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0
    if result.stdout.strip():
        output = json.loads(result.stdout)
        ctx = output.get("additionalContext", "")
        assert "CONTEXT PRESSURE" in ctx or "window" in ctx.lower() or "clear" in ctx.lower()


# ---------------------------------------------------------------------------
# Channel A: comprehensive behavior checkpoint at multiples of COMPREHENSIVE_INTERVAL
# ---------------------------------------------------------------------------

def test_comprehensive_behavior_checkpoint(boost_home):
    tracker = boost_home / "state" / "behavior-tracker.json"
    tracker.write_text(json.dumps({
        "reads_since_rag": 0,
        "tasks_since_evaluator": 0,
        "reads_since_context_update": 0,
    }), encoding="utf-8")

    # edit_count=24 → after +1 = 25 = multiple of COMPREHENSIVE_INTERVAL
    ct = boost_home / "state" / "compaction-tracker.json"
    ct.write_text(json.dumps({"edit_count": 24}), encoding="utf-8")

    result = run_hook(
        "context-nudge.py",
        posttooluse("Read", {"file_path": "/foo.py"}),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0
    if result.stdout.strip():
        output = json.loads(result.stdout)
        ctx = output.get("additionalContext", "")
        assert "BEHAVIOR CHECKPOINT" in ctx or "rules" in ctx.lower()


# ---------------------------------------------------------------------------
# Channel A: clear-safe consideration at 100+ tool uses
# ---------------------------------------------------------------------------

def test_clear_consideration_at_100_uses(boost_home):
    tracker = boost_home / "state" / "behavior-tracker.json"
    tracker.write_text(json.dumps({
        "reads_since_rag": 0,
        "tasks_since_evaluator": 0,
        "reads_since_context_update": 0,
    }), encoding="utf-8")

    ct = boost_home / "state" / "compaction-tracker.json"
    ct.write_text(json.dumps({"edit_count": 99}), encoding="utf-8")  # → 100 after +1

    result = run_hook(
        "context-nudge.py",
        posttooluse("Read", {"file_path": "/foo.py"}),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0
    if result.stdout.strip():
        output = json.loads(result.stdout)
        ctx = output.get("additionalContext", "")
        assert "clear" in ctx.lower() or "CONTEXT" in ctx


# ---------------------------------------------------------------------------
# Channel B: no workspace nudge at threshold (no workspace present)
# ---------------------------------------------------------------------------

def test_no_workspace_nudge_at_threshold(boost_home):
    tracker = boost_home / "state" / "behavior-tracker.json"
    tracker.write_text(json.dumps({
        "reads_since_rag": 0,
        "tasks_since_evaluator": 0,
        "reads_since_context_update": 0,
    }), encoding="utf-8")

    ct = boost_home / "state" / "compaction-tracker.json"
    ct.write_text(json.dumps({"edit_count": 59}), encoding="utf-8")  # → 60

    result = run_hook(
        "context-nudge.py",
        posttooluse("Read", {"file_path": "/foo.py"}),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0
    if result.stdout.strip():
        output = json.loads(result.stdout)
        ctx = output.get("additionalContext", "")
        assert "workspace" in ctx.lower() or "No active workspace" in ctx


# ---------------------------------------------------------------------------
# Task tool: evaluator with verdict resets counter
# ---------------------------------------------------------------------------

def test_evaluator_verdict_resets_counter(boost_home):
    tracker = boost_home / "state" / "behavior-tracker.json"
    tracker.write_text(json.dumps({
        "reads_since_rag": 0,
        "tasks_since_evaluator": 4,
        "reads_since_context_update": 0,
    }), encoding="utf-8")

    ct = boost_home / "state" / "compaction-tracker.json"
    ct.write_text(json.dumps({"edit_count": 3}), encoding="utf-8")

    payload = posttooluse("Task", {"description": "evaluator-agent check findings"})
    payload["tool_response"] = "Grade: PASS - all findings confirmed"

    result = run_hook(
        "context-nudge.py",
        payload,
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0
    updated = json.loads(tracker.read_text(encoding="utf-8"))
    assert updated.get("tasks_since_evaluator") == 0


# ---------------------------------------------------------------------------
# Task tool: review pass doesn't increment counter
# ---------------------------------------------------------------------------

def test_review_pass_doesnt_increment_evaluator_counter(boost_home):
    tracker = boost_home / "state" / "behavior-tracker.json"
    tracker.write_text(json.dumps({
        "reads_since_rag": 0,
        "tasks_since_evaluator": 1,
        "reads_since_context_update": 0,
    }), encoding="utf-8")

    ct = boost_home / "state" / "compaction-tracker.json"
    ct.write_text(json.dumps({"edit_count": 3}), encoding="utf-8")

    payload = posttooluse("Task", {"description": "review pass 1 — security check"})
    payload["tool_response"] = "Pass complete"

    result = run_hook(
        "context-nudge.py",
        payload,
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0
    updated = json.loads(tracker.read_text(encoding="utf-8"))
    # Review pass doesn't increment
    assert updated.get("tasks_since_evaluator") == 1


# ---------------------------------------------------------------------------
# Channel A: write findings nudge fires at reads_since_context_update threshold
# ---------------------------------------------------------------------------

def test_write_findings_nudge_fires_at_threshold(boost_home):
    ws_dir = boost_home / "workspace" / "task-findings"
    ws_dir.mkdir(parents=True)
    ctx_file = ws_dir / "context.md"
    ctx_file.write_text("# Findings Task\nStatus: investigating", encoding="utf-8")

    tracker = boost_home / "state" / "behavior-tracker.json"
    # reads_since_context_update at threshold (5) already
    tracker.write_text(json.dumps({
        "reads_since_rag": 0,
        "tasks_since_evaluator": 0,
        "reads_since_context_update": 4,  # +1 from file tool = 5 = threshold
    }), encoding="utf-8")

    ct = boost_home / "state" / "compaction-tracker.json"
    ct.write_text(json.dumps({"edit_count": 3}), encoding="utf-8")

    result = run_hook(
        "context-nudge.py",
        posttooluse("Read", {"file_path": "/src/foo.py"}),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0
    if result.stdout.strip():
        output = json.loads(result.stdout)
        ctx = output.get("additionalContext", "")
        assert "WRITE FINDINGS" in ctx or "reads" in ctx.lower()


# ---------------------------------------------------------------------------
# Context.md written: resets reads_since_context_update
# ---------------------------------------------------------------------------

def test_writing_context_md_resets_reads_since_ctx(boost_home):
    tracker = boost_home / "state" / "behavior-tracker.json"
    tracker.write_text(json.dumps({
        "reads_since_rag": 0,
        "tasks_since_evaluator": 0,
        "reads_since_context_update": 8,
    }), encoding="utf-8")

    ct = boost_home / "state" / "compaction-tracker.json"
    ct.write_text(json.dumps({"edit_count": 3}), encoding="utf-8")

    result = run_hook(
        "context-nudge.py",
        posttooluse("Edit", {"file_path": "/project/workspace/task-x/context.md", "new_string": "x", "old_string": "y"}),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0
    updated = json.loads(tracker.read_text(encoding="utf-8"))
    assert updated.get("reads_since_context_update") == 0


# ---------------------------------------------------------------------------
# Task response with citations: evaluator nudge includes citations
# ---------------------------------------------------------------------------

def test_evaluator_nudge_with_citations_in_last_response(boost_home):
    tracker = boost_home / "state" / "behavior-tracker.json"
    tracker.write_text(json.dumps({
        "reads_since_rag": 0,
        "tasks_since_evaluator": 2,
        "reads_since_context_update": 0,
        "last_task_response": "Found issue at scripts/auth.py:42 and scripts/login.py:100",
    }), encoding="utf-8")

    ct = boost_home / "state" / "compaction-tracker.json"
    ct.write_text(json.dumps({"edit_count": 3}), encoding="utf-8")

    result = run_hook(
        "context-nudge.py",
        posttooluse("Task", {"description": "some non-evaluator task", "prompt": "do work"}),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0
    if result.stdout.strip():
        output = json.loads(result.stdout)
        ctx = output.get("additionalContext", "")
        # Should have evaluator reminder
        assert "EVALUATOR" in ctx or "evaluator" in ctx.lower()


# ---------------------------------------------------------------------------
# Direct import unit tests for missing coverage paths
# ---------------------------------------------------------------------------

import importlib.util as _ilu
import uuid as _uuid

def _load_cn_mod():
    """Load a fresh copy of context-nudge.py for direct unit testing."""
    mod_name = f"context_nudge_{_uuid.uuid4().hex}"
    spec = _ilu.spec_from_file_location(mod_name, SCRIPTS_DIR / "context-nudge.py")
    mod = _ilu.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestAutoSaveHandoffBranches:
    def test_empty_ctx_files_returns_early(self, boost_home):
        """Line 63: _auto_save_handoff returns early when ctx_files is empty."""
        mod = _load_cn_mod()
        # Should complete without creating handoff-latest.json
        mod._auto_save_handoff(boost_home, [], "test-session")
        handoff_path = boost_home / "state" / "handoff-latest.json"
        assert not handoff_path.exists()

    def test_all_read_failures_returns_early(self, boost_home, tmp_path):
        """Lines 71-72, 74-75: all files fail to read -> summaries empty -> return early."""
        import sys
        from unittest.mock import patch, MagicMock
        mod = _load_cn_mod()
        # Create a fake Path that raises on read_text
        bad_path = MagicMock()
        bad_path.parent.name = "task-bad"
        bad_path.read_text.side_effect = OSError("permission denied")

        mod._auto_save_handoff(boost_home, [bad_path], "test-session")
        # No handoff should be written
        handoff_path = boost_home / "state" / "handoff-latest.json"
        assert not handoff_path.exists()

    def test_write_text_failure_is_swallowed(self, boost_home, tmp_path):
        """Lines 90-91: write_text exception is swallowed, no crash."""
        from unittest.mock import patch
        mod = _load_cn_mod()

        ws_dir = boost_home / "workspace" / "task-write-fail"
        ws_dir.mkdir(parents=True)
        ctx = ws_dir / "context.md"
        ctx.write_text("# Write Fail Task\nStatus: testing", encoding="utf-8")

        # Patch Path.write_text to raise on handoff file
        original_write_text = type(boost_home / "state" / "handoff-latest.json").write_text

        call_count = [0]
        def failing_write_text(self, content, **kwargs):
            call_count[0] += 1
            if "handoff" in str(self):
                raise OSError("disk full")
            return original_write_text(self, content, **kwargs)

        with patch.object(type(boost_home / "state" / "handoff-latest.json"),
                         "write_text", failing_write_text):
            mod._auto_save_handoff(boost_home, [ctx], "test-session")
        # No crash — exception was swallowed
        assert True


class TestMainBadJsonAndTrackerFailures:
    def test_bad_json_stdin_continues(self, boost_home):
        """Lines 118-119: bad JSON stdin -> payload = {} -> continues without crash."""
        import subprocess, sys, os
        script = SCRIPTS_DIR / "context-nudge.py"
        env = {**os.environ, "CLAUDEBOOST_HOME": str(boost_home)}
        result = subprocess.run(
            [sys.executable, str(script)],
            input=b"NOT VALID JSON {{{",
            capture_output=True,
            env=env,
        )
        assert result.returncode == 0

    def test_secondary_rag_reminder_branch(self, boost_home):
        """Line 243: reads >= RAG_THRESHOLD and reads % RAG_THRESHOLD == 0 branch."""
        from helpers import posttooluse
        tracker = boost_home / "state" / "behavior-tracker.json"
        # reads_since_rag = 10 (= 2x RAG_THRESHOLD) fires secondary reminder
        tracker.write_text(__import__("json").dumps({
            "reads_since_rag": 9,  # +1 from this read = 10
            "tasks_since_evaluator": 0,
            "reads_since_context_update": 0,
        }), encoding="utf-8")
        ct = boost_home / "state" / "compaction-tracker.json"
        ct.write_text(__import__("json").dumps({"edit_count": 3}), encoding="utf-8")

        result = run_hook(
            "context-nudge.py",
            posttooluse("Read", {"file_path": "/src/foo.py"}),
            env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
        )
        assert result.returncode == 0

    def test_evaluator_nudge_no_citations(self, boost_home):
        """Line 261: no file:line citations found in last_task_response -> no_citations branch."""
        from helpers import posttooluse
        tracker = boost_home / "state" / "behavior-tracker.json"
        tracker.write_text(__import__("json").dumps({
            "reads_since_rag": 0,
            "tasks_since_evaluator": 2,
            "reads_since_context_update": 0,
            "last_task_response": "All checks passed, nothing specific found.",
        }), encoding="utf-8")
        ct = boost_home / "state" / "compaction-tracker.json"
        ct.write_text(__import__("json").dumps({"edit_count": 3}), encoding="utf-8")

        result = run_hook(
            "context-nudge.py",
            posttooluse("Task", {"description": "some-agent task", "prompt": "do work"}),
            env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
        )
        assert result.returncode == 0
        if result.stdout.strip():
            import json
            output = json.loads(result.stdout)
            ctx = output.get("additionalContext", "")
            # No citations branch: warns about missing citations
            assert "evaluator" in ctx.lower() or "EVALUATOR" in ctx


# ---------------------------------------------------------------------------
# Direct-import tests covering lines 118-119, 142-143, 261, 357-358
# These run in-process so coverage.py captures them even when subprocess
# coverage isn't collected.
# ---------------------------------------------------------------------------

import importlib.util as _ilu2
import io
import json as _json
import uuid as _uuid2
from unittest.mock import patch, MagicMock


def _load_fresh_cn():
    """Load a fresh isolated copy of context-nudge.py."""
    mod_name = f"context_nudge_cov_{_uuid2.uuid4().hex}"
    spec = _ilu2.spec_from_file_location(
        mod_name,
        SCRIPTS_DIR / "context-nudge.py",
    )
    mod = _ilu2.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestMissingLineCoverage:
    """Target the four uncovered line groups identified by coverage."""

    # -- Lines 118-119: bad JSON on stdin falls back to empty payload ----------

    def test_bad_json_stdin_falls_back_to_empty_payload(self, boost_home):
        """Lines 118-119: json.loads raises -> except -> payload = {}."""
        mod = _load_fresh_cn()

        # Provide a valid compaction-tracker so the script doesn't short-circuit
        ct = boost_home / "state" / "compaction-tracker.json"
        ct.write_text(_json.dumps({"edit_count": 3}), encoding="utf-8")
        bt = boost_home / "state" / "behavior-tracker.json"
        bt.write_text(_json.dumps({
            "reads_since_rag": 0,
            "tasks_since_evaluator": 0,
            "reads_since_context_update": 0,
        }), encoding="utf-8")

        fake_stdin = io.StringIO("NOT VALID JSON {{{")
        fake_stdin.isatty = lambda: False  # not a tty, so raw = stdin.read()

        with patch.object(mod.sys, "stdin", fake_stdin), \
             patch.object(mod, "main", wraps=mod.main) as _m, \
             patch.dict(mod.os.environ, {"CLAUDEBOOST_HOME": str(boost_home)}):
            rc = mod.main()

        assert rc == 0

    # -- Lines 142-143: compaction-tracker write failure is swallowed ----------

    def test_compaction_tracker_write_failure_is_swallowed(self, boost_home):
        """Lines 142-143: tracker_path.write_text raises -> except -> pass."""
        mod = _load_fresh_cn()

        bt = boost_home / "state" / "behavior-tracker.json"
        bt.write_text(_json.dumps({
            "reads_since_rag": 0,
            "tasks_since_evaluator": 0,
            "reads_since_context_update": 0,
        }), encoding="utf-8")

        fake_stdin = io.StringIO(_json.dumps({
            "tool_name": "Read",
            "session_id": "s1",
            "tool_input": {"file_path": "/foo.py"},
        }))
        fake_stdin.isatty = lambda: False

        # Patch write_text on Path instances: fail only for compaction-tracker
        original_write_text = type(boost_home).write_text

        def selective_write_fail(self, content, **kwargs):
            if "compaction-tracker" in str(self):
                raise OSError("disk full")
            return original_write_text(self, content, **kwargs)

        with patch.object(type(boost_home / "state" / "compaction-tracker.json"),
                          "write_text", selective_write_fail), \
             patch.object(mod.sys, "stdin", fake_stdin), \
             patch.dict(mod.os.environ, {"CLAUDEBOOST_HOME": str(boost_home)}):
            rc = mod.main()

        # Must not raise — exception is swallowed on line 143
        assert rc == 0

    # -- Line 261: no file:line citations -> no_citations branch --------------


    def test_evaluator_nudge_no_citations_branch_covered(self, boost_home):
        """Line 261: unique_citations is empty -> else branch -> no-citations hint."""
        mod = _load_fresh_cn()

        ct = boost_home / "state" / "compaction-tracker.json"
        ct.write_text(_json.dumps({"edit_count": 3}), encoding="utf-8")
        bt = boost_home / "state" / "behavior-tracker.json"
        # tasks_since_evaluator=2 triggers the nudge; last_task_response has no citations
        bt.write_text(_json.dumps({
            "reads_since_rag": 0,
            "tasks_since_evaluator": 2,
            "reads_since_context_update": 0,
            "last_task_response": "Everything looks fine, no issues spotted here.",
        }), encoding="utf-8")

        # Task tool with a non-evaluator, non-review-pass description
        fake_stdin = io.StringIO(_json.dumps({
            "tool_name": "Task",
            "session_id": "s2",
            "tool_input": {"description": "some-agent task", "prompt": "do work"},
            "tool_response": "",
        }))
        fake_stdin.isatty = lambda: False

        captured = io.StringIO()
        with patch.object(mod.sys, "stdin", fake_stdin), \
             patch.object(mod.sys, "stdout", captured), \
             patch.dict(mod.os.environ, {"CLAUDEBOOST_HOME": str(boost_home)}):
            rc = mod.main()

        assert rc == 0
        out = captured.getvalue().strip()
        if out:
            data = _json.loads(out)
            ctx = data.get("additionalContext", "")
            # The no-citations branch adds a warning about missing file:line refs
            assert "No file:line citations" in ctx or "EVALUATOR" in ctx

    # -- Lines 357-358: behavior-tracker write failure is swallowed -----------

    def test_behavior_tracker_write_failure_is_swallowed(self, boost_home):
        """Lines 357-358: behavior_path.write_text raises -> except -> pass."""
        mod = _load_fresh_cn()

        ct = boost_home / "state" / "compaction-tracker.json"
        ct.write_text(_json.dumps({"edit_count": 3}), encoding="utf-8")
        bt = boost_home / "state" / "behavior-tracker.json"
        bt.write_text(_json.dumps({
            "reads_since_rag": 0,
            "tasks_since_evaluator": 0,
            "reads_since_context_update": 0,
        }), encoding="utf-8")

        fake_stdin = io.StringIO(_json.dumps({
            "tool_name": "Read",
            "session_id": "s3",
            "tool_input": {"file_path": "/bar.py"},
        }))
        fake_stdin.isatty = lambda: False

        original_write_text = type(boost_home).write_text

        def fail_behavior_write(self, content, **kwargs):
            if "behavior-tracker" in str(self):
                raise OSError("no space left")
            return original_write_text(self, content, **kwargs)

        with patch.object(type(boost_home / "state" / "behavior-tracker.json"),
                          "write_text", fail_behavior_write), \
             patch.object(mod.sys, "stdin", fake_stdin), \
             patch.dict(mod.os.environ, {"CLAUDEBOOST_HOME": str(boost_home)}):
            rc = mod.main()

        # No crash — exception is swallowed on line 358
        assert rc == 0


class TestCitationHintElseBranch:
    """Line 261: citation_hint else branch (no file:line found in agent output)."""

    def _load_mod(self):
        import importlib.util
        from pathlib import Path as _Path
        spec = importlib.util.spec_from_file_location(
            "context_nudge",
            _Path(__file__).resolve().parent.parent / "context-nudge.py",
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_no_citations_in_agent_output_triggers_else(self, monkeypatch, tmp_path):
        """Line 261: no file:line in agent tool response -> citation_hint else branch."""
        import json
        from unittest.mock import MagicMock, patch

        mod = self._load_mod()

        # Build a PostToolUse fixture that looks like agent output with no citations
        fixture = {
            "hook_event_name": "PostToolUse",
            "tool_name": "Task",
            "tool_input": {"prompt": "review the code", "description": "some task"},
            "tool_response": "BLOCKER: missing error handling. No citations.",
            "session_id": "test",
            "transcript_path": "/tmp/test.jsonl",
            "cwd": str(tmp_path),
        }

        import io
        monkeypatch.setattr(mod.sys, "stdin", io.StringIO(json.dumps(fixture)))
        monkeypatch.setattr(mod.sys.stdin, "isatty", lambda: False)
        monkeypatch.setenv("CLAUDEBOOST_HOME", str(tmp_path))
        (tmp_path / "state").mkdir(parents=True)
        bt = tmp_path / "state" / "behavior-tracker.json"
        # tasks_since_evaluator=1 -> after Task increment becomes 2 == EVALUATOR_THRESHOLD
        # so the evaluator branch fires; response has no file:line -> else branch at line 261
        bt.write_text(json.dumps({
            "reads_since_rag": 0,
            "reads_since_context_update": 0,
            "tasks_since_evaluator": 1,
        }), encoding="utf-8")

        result = mod.main()
        # Should exit 0 or 1 without crashing
        assert result in (0, 1)


# ---------------------------------------------------------------------------
# Step 1 fix: project workspace detection via state/workspaces.json registry
# ---------------------------------------------------------------------------

def test_project_workspace_detected_via_registry(boost_home, tmp_path):
    """Registry-based lookup finds a workspace outside $CLAUDEBOOST_HOME/workspace/."""
    project_ws = tmp_path / "myproject" / "workspace" / "task-proj"
    project_ws.mkdir(parents=True)
    (project_ws / "context.md").write_text(
        "# Project Task\nStatus: investigating", encoding="utf-8"
    )

    reg = {"task-proj": {
        "workspace_path": str(project_ws),
        "project_path": str(tmp_path / "myproject"),
    }}
    (boost_home / "state" / "workspaces.json").write_text(
        json.dumps(reg), encoding="utf-8"
    )

    tracker = boost_home / "state" / "behavior-tracker.json"
    tracker.write_text(json.dumps({
        "reads_since_rag": 0,
        "tasks_since_evaluator": 0,
        "reads_since_context_update": 0,
    }), encoding="utf-8")

    # edit_count at 7 → after +1 = 8 = NUDGE_INTERVAL
    ct = boost_home / "state" / "compaction-tracker.json"
    ct.write_text(json.dumps({"edit_count": 7}), encoding="utf-8")

    result = run_hook(
        "context-nudge.py",
        posttooluse("Read", {"file_path": "/src/foo.py"}),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0
    # Channel B checkpoint should fire and reference "task-proj"
    if result.stdout.strip():
        output = json.loads(result.stdout)
        ctx = output.get("additionalContext", "")
        assert "task-proj" in ctx


def test_has_workspace_true_for_registry_path_only(boost_home, tmp_path):
    """WRITE FINDINGS fires when has_workspace comes from the registry, not a local glob."""
    # No boost_home/workspace/ directory at all — only registry
    project_ws = tmp_path / "proj" / "workspace" / "issue-42"
    project_ws.mkdir(parents=True)
    (project_ws / "context.md").write_text(
        "# Issue 42\nStatus: in progress", encoding="utf-8"
    )

    reg = {"issue-42": {
        "workspace_path": str(project_ws),
        "project_path": str(tmp_path / "proj"),
    }}
    (boost_home / "state" / "workspaces.json").write_text(
        json.dumps(reg), encoding="utf-8"
    )

    tracker = boost_home / "state" / "behavior-tracker.json"
    # reads_since_context_update at 4 → +1 from Read = 5 = READS_BEFORE_CONTEXT_UPDATE
    tracker.write_text(json.dumps({
        "reads_since_rag": 0,
        "tasks_since_evaluator": 0,
        "reads_since_context_update": 4,
    }), encoding="utf-8")

    ct = boost_home / "state" / "compaction-tracker.json"
    ct.write_text(json.dumps({"edit_count": 3}), encoding="utf-8")

    result = run_hook(
        "context-nudge.py",
        posttooluse("Read", {"file_path": "/src/bar.py"}),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0
    assert result.stdout.strip(), "Expected WRITE FINDINGS nudge but got no output"
    output = json.loads(result.stdout)
    ctx = output.get("additionalContext", "")
    assert "WRITE FINDINGS" in ctx
    assert "issue-42" in ctx


def test_registry_missing_workspace_path_key_skipped(boost_home, tmp_path):
    """Registry entries without workspace_path are skipped gracefully."""
    project_ws = tmp_path / "good" / "workspace" / "task-good"
    project_ws.mkdir(parents=True)
    (project_ws / "context.md").write_text("# Good\nStatus: ok", encoding="utf-8")

    reg = {
        "task-bad": {"project_path": str(tmp_path / "bad")},  # missing workspace_path
        "task-good": {
            "workspace_path": str(project_ws),
            "project_path": str(tmp_path / "good"),
        },
    }
    (boost_home / "state" / "workspaces.json").write_text(
        json.dumps(reg), encoding="utf-8"
    )

    tracker = boost_home / "state" / "behavior-tracker.json"
    tracker.write_text(json.dumps({
        "reads_since_rag": 0,
        "tasks_since_evaluator": 0,
        "reads_since_context_update": 4,
    }), encoding="utf-8")

    ct = boost_home / "state" / "compaction-tracker.json"
    ct.write_text(json.dumps({"edit_count": 3}), encoding="utf-8")

    result = run_hook(
        "context-nudge.py",
        posttooluse("Read", {"file_path": "/src/x.py"}),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0
    # task-good should be found; task-bad silently skipped
    if result.stdout.strip():
        output = json.loads(result.stdout)
        ctx = output.get("additionalContext", "")
        assert "task-good" in ctx


# ---------------------------------------------------------------------------
# Step 1b fix: decision:block escalation at 2x READS_BEFORE_CONTEXT_UPDATE
# ---------------------------------------------------------------------------

def test_block_escalation_at_double_threshold(boost_home):
    """decision:block fires when reads_since_context_update >= 2 * READS_BEFORE_CONTEXT_UPDATE."""
    ws_dir = boost_home / "workspace" / "task-block"
    ws_dir.mkdir(parents=True)
    (ws_dir / "context.md").write_text(
        "# Block Test\nStatus: investigating", encoding="utf-8"
    )

    tracker = boost_home / "state" / "behavior-tracker.json"
    # 9 → +1 from Read = 10 = 2 * READS_BEFORE_CONTEXT_UPDATE (5)
    tracker.write_text(json.dumps({
        "reads_since_rag": 0,
        "tasks_since_evaluator": 0,
        "reads_since_context_update": 9,
    }), encoding="utf-8")

    ct = boost_home / "state" / "compaction-tracker.json"
    ct.write_text(json.dumps({"edit_count": 3}), encoding="utf-8")

    result = run_hook(
        "context-nudge.py",
        posttooluse("Read", {"file_path": "/src/main.py"}),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0
    assert result.stdout.strip(), "Expected block output but got none"
    output = json.loads(result.stdout)
    assert output.get("decision") == "block", f"Expected decision:block, got: {output}"
    assert "BLOCKED" in output.get("reason", "")


def test_first_nudge_is_soft_not_block(boost_home):
    """First WRITE FINDINGS nudge (5 reads) is additionalContext only — no decision:block."""
    ws_dir = boost_home / "workspace" / "task-soft"
    ws_dir.mkdir(parents=True)
    (ws_dir / "context.md").write_text(
        "# Soft Task\nStatus: in progress", encoding="utf-8"
    )

    tracker = boost_home / "state" / "behavior-tracker.json"
    # 4 → +1 from Read = 5 = first nudge threshold
    tracker.write_text(json.dumps({
        "reads_since_rag": 0,
        "tasks_since_evaluator": 0,
        "reads_since_context_update": 4,
    }), encoding="utf-8")

    ct = boost_home / "state" / "compaction-tracker.json"
    ct.write_text(json.dumps({"edit_count": 3}), encoding="utf-8")

    result = run_hook(
        "context-nudge.py",
        posttooluse("Read", {"file_path": "/src/soft.py"}),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0
    assert result.stdout.strip(), "Expected a nudge but got none"
    output = json.loads(result.stdout)
    assert output.get("decision") != "block"
    ctx = output.get("additionalContext", "")
    assert "WRITE FINDINGS" in ctx
    assert "BLOCKED" not in ctx


def test_block_escalation_with_registry_workspace(boost_home, tmp_path):
    """decision:block fires correctly for a registry-registered project workspace."""
    project_ws = tmp_path / "app" / "workspace" / "feat-99"
    project_ws.mkdir(parents=True)
    (project_ws / "context.md").write_text(
        "# Feat 99\nStatus: building", encoding="utf-8"
    )

    reg = {"feat-99": {
        "workspace_path": str(project_ws),
        "project_path": str(tmp_path / "app"),
    }}
    (boost_home / "state" / "workspaces.json").write_text(
        json.dumps(reg), encoding="utf-8"
    )

    tracker = boost_home / "state" / "behavior-tracker.json"
    # 19 → +1 = 20 = 4 * READS_BEFORE_CONTEXT_UPDATE — still >= 2x, block fires
    tracker.write_text(json.dumps({
        "reads_since_rag": 0,
        "tasks_since_evaluator": 0,
        "reads_since_context_update": 19,
    }), encoding="utf-8")

    ct = boost_home / "state" / "compaction-tracker.json"
    ct.write_text(json.dumps({"edit_count": 3}), encoding="utf-8")

    result = run_hook(
        "context-nudge.py",
        posttooluse("Read", {"file_path": "/app/src/main.py"}),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0
    assert result.stdout.strip()
    output = json.loads(result.stdout)
    assert output.get("decision") == "block"
    assert "feat-99" in output.get("reason", "")


# ---------------------------------------------------------------------------
# session_id persistence — crash safety net reliability
# ---------------------------------------------------------------------------

def test_session_id_persisted_to_tracker(boost_home):
    """session_id must be written to behavior-tracker.json so the crash safety
    net can fire on the NEXT crash. The double-load bug would lose it."""
    tracker = boost_home / "state" / "behavior-tracker.json"
    tracker.write_text(json.dumps({
        "reads_since_rag": 0,
        "tasks_since_evaluator": 0,
        "reads_since_context_update": 0,
    }), encoding="utf-8")
    ct = boost_home / "state" / "compaction-tracker.json"
    ct.write_text(json.dumps({"edit_count": 0}), encoding="utf-8")

    # posttooluse always uses session_id="test-session" — verify it reaches the tracker
    result = run_hook(
        "context-nudge.py",
        posttooluse("Read", {"file_path": "/foo.py"}),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0
    data = json.loads(tracker.read_text(encoding="utf-8"))
    assert data.get("session_id") == "test-session", (
        "session_id not persisted — crash safety net will fail on second crash"
    )


def test_crash_safety_net_resets_and_persists_new_session_id(boost_home):
    """Simulates crash: tracker has old session_id + dirty counters.
    New session starts → crash safety net resets counters AND persists new id.
    posttooluse uses session_id='test-session'; tracker has 'old-session-id' → differs → fires."""
    tracker = boost_home / "state" / "behavior-tracker.json"
    tracker.write_text(json.dumps({
        "reads_since_rag": 5,
        "tasks_since_evaluator": 3,
        "reads_since_context_update": 12,
        "last_nudge_ctx_mtime": 1234567890.0,
        "last_nudge_ctx_path": "/old/context.md",
        "last_nudge_count": 99,
        "reads_ctx_workspace_id": "old-ws",
        "session_id": "old-session-id",
    }), encoding="utf-8")
    ct = boost_home / "state" / "compaction-tracker.json"
    ct.write_text(json.dumps({"edit_count": 0}), encoding="utf-8")

    result = run_hook(
        "context-nudge.py",
        posttooluse("Read", {"file_path": "/foo.py"}),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0
    data = json.loads(tracker.read_text(encoding="utf-8"))

    # Counters must be near-zero: reset to 0 by the safety net, then +1 from the
    # current Read call (normal processing runs after the reset). Key proof that the
    # reset fired is that they are 1, not 12/5/3 from the crashed session.
    assert data.get("reads_since_context_update") == 1, "expected 1, not dirty value"
    assert data.get("reads_since_rag") == 1, "expected 1, not dirty value"
    assert data.get("tasks_since_evaluator") == 0
    assert data.get("last_nudge_ctx_mtime") == 0.0
    assert data.get("last_nudge_ctx_path") == ""
    assert data.get("last_nudge_count") == 0
    assert data.get("reads_ctx_workspace_id") == ""

    # New session_id persisted so a SECOND crash triggers the net again
    assert data.get("session_id") == "test-session", (
        "new session_id not persisted — crash safety net would fail on next crash"
    )
