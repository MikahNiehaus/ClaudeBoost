"""
Tests for scripts/workspace-primer.py (SessionStart hook).

Injects RAG tier briefing when active workspace exists. Always exits 0.
"""
from __future__ import annotations

import json
import pytest
from helpers import SCRIPTS_DIR, run_hook


def _session_start() -> dict:
    return {"hook_event_name": "SessionStart", "session_id": "test"}


# ---------------------------------------------------------------------------
# Always exits 0
# ---------------------------------------------------------------------------

def test_always_exits_0(boost_home):
    result = run_hook(
        "workspace-primer.py",
        _session_start(),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0


def test_silent_when_no_active_workspace(boost_home):
    # No active-workspace.json → silent
    result = run_hook(
        "workspace-primer.py",
        _session_start(),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0
    assert result.stdout.strip() == b""


# ---------------------------------------------------------------------------
# Active workspace: inject briefing
# ---------------------------------------------------------------------------

def test_injects_briefing_when_active_workspace(boost_home, tmp_path):
    # Create a workspace directory
    ws_path = tmp_path / "workspace" / "task-123"
    ws_path.mkdir(parents=True)
    (ws_path / "context.md").write_text("# Task 123\nStatus: active", encoding="utf-8")

    # Write active-workspace.json
    aws_file = boost_home / "state" / "active-workspace.json"
    aws_file.write_text(json.dumps({
        "workspace": "task-123",
        "workspace_path": str(ws_path),
        "project_path": str(tmp_path),
    }), encoding="utf-8")

    result = run_hook(
        "workspace-primer.py",
        _session_start(),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0
    assert result.stdout.strip()
    output = json.loads(result.stdout)
    ctx = output.get("additionalContext", "")
    assert "task-123" in ctx
    assert "ACTIVE WORKSPACE" in ctx


def test_briefing_mentions_tier3c_when_missing(boost_home, tmp_path):
    ws_path = tmp_path / "workspace" / "task-no-research"
    ws_path.mkdir(parents=True)
    (ws_path / "context.md").write_text("# Task\nStatus: active", encoding="utf-8")

    aws_file = boost_home / "state" / "active-workspace.json"
    aws_file.write_text(json.dumps({
        "workspace": "task-no-research",
        "workspace_path": str(ws_path),
    }), encoding="utf-8")

    result = run_hook(
        "workspace-primer.py",
        _session_start(),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0
    if result.stdout.strip():
        output = json.loads(result.stdout)
        ctx = output.get("additionalContext", "")
        # Should mention research is not built
        assert "NOT BUILT" in ctx or "research" in ctx.lower()


def test_briefing_shows_tier3c_ready_when_research_exists(boost_home, tmp_path):
    ws_path = tmp_path / "workspace" / "task-with-research"
    research_dir = ws_path / ".rag-index" / "research"
    research_dir.mkdir(parents=True)
    (research_dir / "doc.json").write_text('{"chunks": []}', encoding="utf-8")
    (ws_path / "context.md").write_text("# Task\nStatus: active", encoding="utf-8")

    aws_file = boost_home / "state" / "active-workspace.json"
    aws_file.write_text(json.dumps({
        "workspace": "task-with-research",
        "workspace_path": str(ws_path),
    }), encoding="utf-8")

    result = run_hook(
        "workspace-primer.py",
        _session_start(),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0
    if result.stdout.strip():
        output = json.loads(result.stdout)
        ctx = output.get("additionalContext", "")
        assert "EXISTS" in ctx or "READY" in ctx or "research" in ctx.lower()


# ---------------------------------------------------------------------------
# Malformed active-workspace.json: silent
# ---------------------------------------------------------------------------

def test_silent_on_malformed_active_workspace(boost_home):
    aws_file = boost_home / "state" / "active-workspace.json"
    aws_file.write_text("not valid json!", encoding="utf-8")

    result = run_hook(
        "workspace-primer.py",
        _session_start(),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0
    assert b"Traceback" not in result.stderr
