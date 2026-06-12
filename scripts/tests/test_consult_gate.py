"""
Tests for scripts/consult-gate.py (PreToolUse hook on Edit/Write/Bash).

The gate is a nudge (exit 0 + stderr), never a hard block. It prints a
CONSULT reminder when in CONSULT mode editing non-exempt paths.
"""
from __future__ import annotations

import json
import pytest
from helpers import SCRIPTS_DIR, run_hook, pretooluse


def _edit(file_path: str) -> dict:
    return pretooluse("Edit", {
        "file_path": file_path,
        "old_string": "a",
        "new_string": "b",
    })


def _write(file_path: str) -> dict:
    return pretooluse("Write", {
        "file_path": file_path,
        "content": "hello",
    })


def _bash_write(command: str) -> dict:
    return pretooluse("Bash", {"command": command})


# ---------------------------------------------------------------------------
# AUTO mode: always silent pass
# ---------------------------------------------------------------------------

def test_passes_silently_in_auto_mode(boost_home):
    mode_file = boost_home / "state" / "claudeboost-mode.json"
    mode_file.write_text(json.dumps({"mode": "AUTO"}), encoding="utf-8")

    result = run_hook(
        "consult-gate.py",
        _edit("/some/project/src/app.py"),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0
    assert result.stderr == b""


# ---------------------------------------------------------------------------
# CONSULT mode on non-exempt path: nudge (exit 0, but stderr has reminder)
# ---------------------------------------------------------------------------

def test_nudge_on_non_exempt_edit_in_consult_mode(boost_home):
    mode_file = boost_home / "state" / "claudeboost-mode.json"
    mode_file.write_text(json.dumps({"mode": "CONSULT"}), encoding="utf-8")

    result = run_hook(
        "consult-gate.py",
        _edit("/some/project/src/important_service.py"),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    # Still exits 0 (nudge, not block)
    assert result.returncode == 0
    # But prints a CONSULT reminder to stderr
    assert b"CONSULT" in result.stderr


# ---------------------------------------------------------------------------
# Exempt paths: always silent pass
# ---------------------------------------------------------------------------

def test_passes_silently_on_workspace_path(boost_home):
    result = run_hook(
        "consult-gate.py",
        _edit("/project/workspace/task-1/context.md"),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0
    assert result.stderr == b""


def test_passes_silently_on_claude_dir(boost_home):
    result = run_hook(
        "consult-gate.py",
        _edit("/project/.claude/settings.json"),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0
    assert result.stderr == b""


def test_passes_silently_on_knowledge_path(boost_home):
    result = run_hook(
        "consult-gate.py",
        _edit("/claudeboost/knowledge/security.md"),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0
    assert result.stderr == b""


# ---------------------------------------------------------------------------
# Read-only Bash: silent pass
# ---------------------------------------------------------------------------

def test_passes_readonly_bash(boost_home):
    result = run_hook(
        "consult-gate.py",
        _bash_write("git log --oneline"),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0
    # No CONSULT nudge for read-only bash
    assert b"CONSULT" not in result.stderr


# ---------------------------------------------------------------------------
# Pre-approved axis: skip reminder
# ---------------------------------------------------------------------------

def test_no_nudge_when_pre_approved(boost_home):
    mode_file = boost_home / "state" / "claudeboost-mode.json"
    mode_file.write_text(json.dumps({"mode": "CONSULT"}), encoding="utf-8")

    approvals_file = boost_home / "state" / "session-approvals.json"
    approvals_file.write_text(json.dumps({
        "approvals": [
            {"axis": "service", "choice": "add important_service.py endpoint"}
        ]
    }), encoding="utf-8")

    result = run_hook(
        "consult-gate.py",
        _edit("/some/project/src/important_service.py"),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0
    # Pre-approved → no nudge
    assert b"CONSULT" not in result.stderr


# ---------------------------------------------------------------------------
# Missing mode file: defaults to CONSULT
# ---------------------------------------------------------------------------

def test_defaults_to_consult_when_no_mode_file(boost_home):
    # Don't write mode file
    result = run_hook(
        "consult-gate.py",
        _edit("/some/project/src/service.py"),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0
    # Missing file → CONSULT mode → nudge fires
    assert b"CONSULT" in result.stderr
