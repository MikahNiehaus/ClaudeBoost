"""
Tests for scripts/register-workspace.py (CLI utility).

Commands:
  register-workspace.py <task_id> <workspace_path> [project_path]
  register-workspace.py --list
  register-workspace.py --get <task_id>
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from helpers import run_script


class TestRegister:
    def test_registers_workspace_creates_entry(self, tmp_path):
        ws_path = tmp_path / "workspace" / "task-99"
        ws_path.mkdir(parents=True)
        state_dir = tmp_path / "state"
        state_dir.mkdir()

        result = run_script(
            "register-workspace.py",
            args=["task-99", str(ws_path)],
            env_overrides={"CLAUDEBOOST_HOME": str(tmp_path)},
        )
        assert result.returncode == 0
        assert b"Registered" in result.stdout
        reg_file = tmp_path / "state" / "workspaces.json"
        assert reg_file.exists()
        reg = json.loads(reg_file.read_text(encoding="utf-8"))
        assert "task-99" in reg
        assert reg["task-99"]["workspace_path"] == str(ws_path)

    def test_registers_workspace_with_project_path(self, tmp_path):
        ws_path = tmp_path / "workspace" / "task-100"
        ws_path.mkdir(parents=True)

        result = run_script(
            "register-workspace.py",
            args=["task-100", str(ws_path), str(tmp_path)],
            env_overrides={"CLAUDEBOOST_HOME": str(tmp_path)},
        )
        assert result.returncode == 0
        reg = json.loads((tmp_path / "state" / "workspaces.json").read_text(encoding="utf-8"))
        assert reg["task-100"]["project_path"] == str(tmp_path)

    def test_overwrites_existing_entry(self, tmp_path):
        state_dir = tmp_path / "state"
        state_dir.mkdir()
        reg_file = state_dir / "workspaces.json"
        reg_file.write_text(json.dumps({"task-1": {"workspace_path": "/old/path", "project_path": ""}}), encoding="utf-8")

        new_ws = tmp_path / "new_workspace"
        new_ws.mkdir()
        run_script(
            "register-workspace.py",
            args=["task-1", str(new_ws)],
            env_overrides={"CLAUDEBOOST_HOME": str(tmp_path)},
        )
        reg = json.loads(reg_file.read_text(encoding="utf-8"))
        assert reg["task-1"]["workspace_path"] == str(new_ws)


class TestNoArgs:
    def test_exits_1_when_no_args(self, tmp_path):
        result = run_script(
            "register-workspace.py",
            args=[],
            env_overrides={"CLAUDEBOOST_HOME": str(tmp_path)},
        )
        assert result.returncode == 1

    def test_exits_1_when_only_task_id(self, tmp_path):
        result = run_script(
            "register-workspace.py",
            args=["task-only"],
            env_overrides={"CLAUDEBOOST_HOME": str(tmp_path)},
        )
        assert result.returncode == 1
        assert b"Usage" in result.stderr


class TestList:
    def test_list_empty_registry(self, tmp_path):
        result = run_script(
            "register-workspace.py",
            args=["--list"],
            env_overrides={"CLAUDEBOOST_HOME": str(tmp_path)},
        )
        assert result.returncode == 0
        assert b"No project-scoped" in result.stdout

    def test_list_shows_registered_workspaces(self, tmp_path):
        ws_path = tmp_path / "workspace" / "task-42"
        ws_path.mkdir(parents=True)
        (ws_path / "context.md").write_text("# Task 42\nStatus: in progress", encoding="utf-8")

        state_dir = tmp_path / "state"
        state_dir.mkdir()
        reg = {"task-42": {"workspace_path": str(ws_path), "project_path": ""}}
        (state_dir / "workspaces.json").write_text(json.dumps(reg), encoding="utf-8")

        result = run_script(
            "register-workspace.py",
            args=["--list"],
            env_overrides={"CLAUDEBOOST_HOME": str(tmp_path)},
        )
        assert result.returncode == 0
        assert b"task-42" in result.stdout


class TestGet:
    def test_get_existing_workspace_returns_path(self, tmp_path):
        state_dir = tmp_path / "state"
        state_dir.mkdir()
        ws_path = "/some/workspace/path"
        reg = {"task-abc": {"workspace_path": ws_path, "project_path": ""}}
        (state_dir / "workspaces.json").write_text(json.dumps(reg), encoding="utf-8")

        result = run_script(
            "register-workspace.py",
            args=["--get", "task-abc"],
            env_overrides={"CLAUDEBOOST_HOME": str(tmp_path)},
        )
        assert result.returncode == 0
        assert ws_path.encode() in result.stdout

    def test_get_missing_workspace_exits_1(self, tmp_path):
        result = run_script(
            "register-workspace.py",
            args=["--get", "nonexistent-task"],
            env_overrides={"CLAUDEBOOST_HOME": str(tmp_path)},
        )
        assert result.returncode == 1
