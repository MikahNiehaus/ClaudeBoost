"""
Tests for scripts/workspace-primer.py (SessionStart hook).

Injects the active workspace's identity and paths. Always exits 0.
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


def test_briefing_names_no_retired_route(boost_home, tmp_path):
    """The briefing must not send the session at /context or port 8612.

    It used to print a POST /context call and a Tier 0-4 token budget. Both
    belonged to the bundled server that was retired, so a session following
    the briefing got connection refused and carried on with no context.
    """
    ws_path = tmp_path / "workspace" / "task-routes"
    ws_path.mkdir(parents=True)
    (ws_path / "context.md").write_text("# Task\nStatus: active", encoding="utf-8")

    aws_file = boost_home / "state" / "active-workspace.json"
    aws_file.write_text(json.dumps({
        "workspace": "task-routes",
        "workspace_path": str(ws_path),
    }), encoding="utf-8")

    result = run_hook(
        "workspace-primer.py",
        _session_start(),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0
    ctx = json.loads(result.stdout).get("additionalContext", "")
    assert "task-routes" in ctx, ctx
    assert "8612" not in ctx, ctx
    assert "/context" not in ctx, ctx
    assert "Tier" not in ctx, ctx


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


def test_silent_when_workspace_id_empty(boost_home):
    """active-workspace.json with empty workspace key → silent."""
    aws_file = boost_home / "state" / "active-workspace.json"
    aws_file.write_text(json.dumps({"workspace": ""}), encoding="utf-8")

    result = run_hook(
        "workspace-primer.py",
        _session_start(),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0
    assert result.stdout.strip() == b""


def test_lookup_workspace_from_registry(boost_home, tmp_path):
    """workspace_path missing from active-workspace.json — fall back to workspaces.json registry."""
    ws_path = tmp_path / "workspace" / "reg-task"
    ws_path.mkdir(parents=True)

    aws_file = boost_home / "state" / "active-workspace.json"
    aws_file.write_text(json.dumps({"workspace": "reg-task"}), encoding="utf-8")

    reg_file = boost_home / "state" / "workspaces.json"
    reg_file.write_text(json.dumps({
        "reg-task": {"workspace_path": str(ws_path), "project_path": str(tmp_path)}
    }), encoding="utf-8")

    result = run_hook(
        "workspace-primer.py",
        _session_start(),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0
    assert result.stdout.strip()
    output = json.loads(result.stdout)
    assert "reg-task" in output.get("additionalContext", "")


def test_last_resort_workspace_directory(boost_home, tmp_path):
    """No workspace_path in json, no registry, but directory exists under CLAUDEBOOST_HOME/workspace/."""
    ws_id = "last-resort-task"
    ws_path = boost_home / "workspace" / ws_id
    ws_path.mkdir(parents=True)

    aws_file = boost_home / "state" / "active-workspace.json"
    aws_file.write_text(json.dumps({"workspace": ws_id}), encoding="utf-8")

    result = run_hook(
        "workspace-primer.py",
        _session_start(),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0
    assert result.stdout.strip()
    output = json.loads(result.stdout)
    assert ws_id in output.get("additionalContext", "")


def test_silent_when_no_workspace_path_found(boost_home):
    """workspace_path unresolvable from any source → silent."""
    aws_file = boost_home / "state" / "active-workspace.json"
    aws_file.write_text(json.dumps({"workspace": "ghost-task"}), encoding="utf-8")

    result = run_hook(
        "workspace-primer.py",
        _session_start(),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0
    assert result.stdout.strip() == b""


def test_stack_detection_go_and_python(boost_home, tmp_path):
    """Project with go.mod and pyproject.toml shows both stack labels."""
    ws_path = tmp_path / "workspace" / "stack-task"
    ws_path.mkdir(parents=True)
    (tmp_path / "go.mod").write_text("module example.com/app\n\ngo 1.21\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'app'\n", encoding="utf-8")

    aws_file = boost_home / "state" / "active-workspace.json"
    aws_file.write_text(json.dumps({
        "workspace": "stack-task",
        "workspace_path": str(ws_path),
        "project_path": str(tmp_path),
    }), encoding="utf-8")

    result = run_hook(
        "workspace-primer.py",
        _session_start(),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0
    output = json.loads(result.stdout)
    ctx = output.get("additionalContext", "")
    assert "Go" in ctx
    assert "Python" in ctx


def test_stack_detection_typescript_and_java(boost_home, tmp_path):
    """Project with tsconfig.json and pom.xml shows TypeScript and Java."""
    ws_path = tmp_path / "workspace" / "ts-java-task"
    ws_path.mkdir(parents=True)
    (tmp_path / "tsconfig.json").write_text('{"compilerOptions": {}}', encoding="utf-8")
    (tmp_path / "pom.xml").write_text("<project/>", encoding="utf-8")

    aws_file = boost_home / "state" / "active-workspace.json"
    aws_file.write_text(json.dumps({
        "workspace": "ts-java-task",
        "workspace_path": str(ws_path),
        "project_path": str(tmp_path),
    }), encoding="utf-8")

    result = run_hook(
        "workspace-primer.py",
        _session_start(),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0
    output = json.loads(result.stdout)
    ctx = output.get("additionalContext", "")
    assert "TypeScript" in ctx or "Java" in ctx


def test_stack_detection_javascript_no_tsconfig(boost_home, tmp_path):
    """package.json without tsconfig.json → JavaScript/Node label."""
    ws_path = tmp_path / "workspace" / "js-task"
    ws_path.mkdir(parents=True)
    (tmp_path / "package.json").write_text('{"name": "app"}', encoding="utf-8")

    aws_file = boost_home / "state" / "active-workspace.json"
    aws_file.write_text(json.dumps({
        "workspace": "js-task",
        "workspace_path": str(ws_path),
        "project_path": str(tmp_path),
    }), encoding="utf-8")

    result = run_hook(
        "workspace-primer.py",
        _session_start(),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0
    output = json.loads(result.stdout)
    ctx = output.get("additionalContext", "")
    assert "JavaScript" in ctx or "Node" in ctx


def test_stack_detection_nonexistent_project_path(boost_home, tmp_path):
    """project_path that doesn't exist — _detect_stack returns empty string, no crash."""
    ws_path = tmp_path / "workspace" / "no-project"
    ws_path.mkdir(parents=True)

    aws_file = boost_home / "state" / "active-workspace.json"
    aws_file.write_text(json.dumps({
        "workspace": "no-project",
        "workspace_path": str(ws_path),
        "project_path": str(tmp_path / "does-not-exist"),
    }), encoding="utf-8")

    result = run_hook(
        "workspace-primer.py",
        _session_start(),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0
    assert b"Traceback" not in result.stderr


def test_stack_detection_csproj_in_src_subdir(boost_home, tmp_path):
    """C# project with .csproj inside a src/ subdirectory (covers line 36 branch)."""
    ws_path = tmp_path / "workspace" / "csharp-task"
    ws_path.mkdir(parents=True)
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "MyApp.csproj").write_text("<Project Sdk=\"Microsoft.NET.Sdk\"/>", encoding="utf-8")

    aws_file = boost_home / "state" / "active-workspace.json"
    aws_file.write_text(json.dumps({
        "workspace": "csharp-task",
        "workspace_path": str(ws_path),
        "project_path": str(tmp_path),
    }), encoding="utf-8")

    result = run_hook(
        "workspace-primer.py",
        _session_start(),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0
    output = json.loads(result.stdout)
    ctx = output.get("additionalContext", "")
    assert "C#" in ctx or "ASP.NET" in ctx
