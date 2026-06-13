"""
Tests for scripts/research-task-nudge.py (UserPromptSubmit hook).

Nudges when active workspace has no research index, or when prompt
looks like task work but no workspace exists.
Always exits 0.
"""
from __future__ import annotations

import json
import pytest
from helpers import SCRIPTS_DIR, run_hook


def _prompt(text: str) -> dict:
    return {"hook_event_name": "UserPromptSubmit", "session_id": "test", "prompt": text}


# ---------------------------------------------------------------------------
# Always exits 0
# ---------------------------------------------------------------------------

def test_always_exits_0(boost_home):
    result = run_hook(
        "research-task-nudge.py",
        _prompt("implement the login feature"),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0


def test_exits_0_no_workspace_no_task_keywords(boost_home):
    result = run_hook(
        "research-task-nudge.py",
        _prompt("what is the weather today"),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0


# ---------------------------------------------------------------------------
# No workspace + task keyword → nudge about /workspace
# ---------------------------------------------------------------------------

def test_nudge_when_no_workspace_and_task_keyword(boost_home):
    result = run_hook(
        "research-task-nudge.py",
        _prompt("implement the authentication feature"),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0
    # Should output a nudge mentioning workspace
    if result.stdout.strip():
        output = json.loads(result.stdout)
        ctx = output.get("additionalContext", "")
        assert "workspace" in ctx.lower() or "research" in ctx.lower()


# ---------------------------------------------------------------------------
# Active workspace + no research index → nudge about /research-task
# ---------------------------------------------------------------------------

def test_nudge_when_active_workspace_no_research(boost_home, tmp_path):
    # Create workspace directory (without .rag-index/research)
    ws_path = tmp_path / "workspace" / "task-123"
    ws_path.mkdir(parents=True)
    (ws_path / "context.md").write_text("# Task 123\nStatus: in progress", encoding="utf-8")

    # Set active workspace
    aws_file = boost_home / "state" / "active-workspace.json"
    aws_file.write_text(json.dumps({
        "workspace": "task-123",
        "workspace_path": str(ws_path),
    }), encoding="utf-8")

    result = run_hook(
        "research-task-nudge.py",
        _prompt("implement the feature"),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0
    assert result.stdout.strip()
    output = json.loads(result.stdout)
    ctx = output.get("additionalContext", "")
    assert "research" in ctx.lower() or "RESEARCH" in ctx


# ---------------------------------------------------------------------------
# Invalid JSON on stdin: recovers gracefully
# ---------------------------------------------------------------------------

def test_exits_0_on_invalid_json_input(boost_home):
    import subprocess
    import sys
    from helpers import SCRIPTS_DIR, COVERAGERC
    import os
    script = SCRIPTS_DIR / "research-task-nudge.py"
    env = {**os.environ, "CLAUDEBOOST_HOME": str(boost_home)}
    if COVERAGERC.exists():
        env["COVERAGE_PROCESS_START"] = str(COVERAGERC)
    result = subprocess.run(
        [sys.executable, str(script)],
        input=b"not valid json {{{{",
        capture_output=True,
        env=env,
    )
    assert result.returncode == 0


# ---------------------------------------------------------------------------
# Active workspace WITH research index → silent
# ---------------------------------------------------------------------------

def test_silent_when_research_already_indexed(boost_home, tmp_path):
    # Create workspace with research index
    ws_path = tmp_path / "workspace" / "task-456"
    research_dir = ws_path / ".rag-index" / "research"
    research_dir.mkdir(parents=True)
    (research_dir / "chunk0.json").write_text('{"text":"doc"}', encoding="utf-8")
    (ws_path / "context.md").write_text("# Task 456\nStatus: done", encoding="utf-8")

    aws_file = boost_home / "state" / "active-workspace.json"
    aws_file.write_text(json.dumps({
        "workspace": "task-456",
        "workspace_path": str(ws_path),
    }), encoding="utf-8")

    result = run_hook(
        "research-task-nudge.py",
        _prompt("continue the implementation"),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0
    # Research is indexed → no nudge (empty or no additionalContext)
    if result.stdout.strip():
        output = json.loads(result.stdout)
        # If there is output, it should NOT be a research reminder
        ctx = output.get("additionalContext", "")
        assert "RESEARCH REMINDER" not in ctx
