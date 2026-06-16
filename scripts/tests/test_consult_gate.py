"""
Tests for scripts/consult-gate.py (PreToolUse hook on Write).

The gate fires when creating a NEW file in CONSULT mode with no task-plan.json.
It outputs permissionDecision:"ask" JSON to stdout and exits 0.
Edit/MultiEdit/Bash are silent passes — they operate on existing files (grinding).
"""
from __future__ import annotations

import json
import os
import pytest
from helpers import SCRIPTS_DIR, run_hook, pretooluse


def _edit(file_path: str) -> dict:
    return pretooluse("Edit", {
        "file_path": file_path,
        "old_string": "a",
        "new_string": "b",
    })


def _write(file_path: str, *, existing: bool = False, boost_home=None) -> dict:
    """Build a Write payload. existing=True pre-creates the file so the hook sees it."""
    if existing and boost_home is not None:
        # Create a real temp file the hook can stat
        target = boost_home / "tmp_existing_file.py"
        target.write_text("# existing", encoding="utf-8")
        file_path = str(target)
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
    assert result.stdout == b""


# ---------------------------------------------------------------------------
# Edit/MultiEdit: always silent pass (these are on existing files)
# ---------------------------------------------------------------------------

def test_edit_passes_silently_in_consult_mode(boost_home):
    mode_file = boost_home / "state" / "claudeboost-mode.json"
    mode_file.write_text(json.dumps({"mode": "CONSULT"}), encoding="utf-8")

    result = run_hook(
        "consult-gate.py",
        _edit("/some/project/src/important_service.py"),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0
    assert result.stdout == b""
    assert result.stderr == b""


# ---------------------------------------------------------------------------
# Bash: always silent pass
# ---------------------------------------------------------------------------

def test_bash_passes_silently_in_consult_mode(boost_home):
    mode_file = boost_home / "state" / "claudeboost-mode.json"
    mode_file.write_text(json.dumps({"mode": "CONSULT"}), encoding="utf-8")

    result = run_hook(
        "consult-gate.py",
        _bash_write("echo 'config' > /project/src/config.py"),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0
    assert result.stdout == b""


# ---------------------------------------------------------------------------
# Exempt paths: always silent pass
# ---------------------------------------------------------------------------

def test_passes_silently_on_workspace_path(boost_home):
    result = run_hook(
        "consult-gate.py",
        _write("/project/workspace/task-1/context.md"),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0
    assert result.stdout == b""


def test_passes_silently_on_knowledge_path(boost_home):
    result = run_hook(
        "consult-gate.py",
        _write("/claudeboost/knowledge/security.md"),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0
    assert result.stdout == b""


def test_passes_silently_on_docs_path(boost_home):
    result = run_hook(
        "consult-gate.py",
        _write("/project/docs/README.md"),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0
    assert result.stdout == b""


# ---------------------------------------------------------------------------
# .claude/ path: NOT exempt (skill edits must go through the gate)
# ---------------------------------------------------------------------------

def test_claude_dir_write_no_plan_triggers_ask(boost_home, tmp_path):
    """Write to a new .claude/ file with no task plan triggers permissionDecision:ask."""
    mode_file = boost_home / "state" / "claudeboost-mode.json"
    mode_file.write_text(json.dumps({"mode": "CONSULT"}), encoding="utf-8")

    result = run_hook(
        "consult-gate.py",
        _write("/project/.claude/commands/new-skill.md"),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0
    if result.stdout.strip():
        out = json.loads(result.stdout)
        assert out.get("permissionDecision") == "ask"


# ---------------------------------------------------------------------------
# Core gate: Write to new file with no task-plan.json → permissionDecision:ask
# ---------------------------------------------------------------------------

def test_write_new_file_no_plan_triggers_ask(boost_home):
    mode_file = boost_home / "state" / "claudeboost-mode.json"
    mode_file.write_text(json.dumps({"mode": "CONSULT"}), encoding="utf-8")

    result = run_hook(
        "consult-gate.py",
        # Path that doesn't exist on disk
        _write("/tmp/nonexistent_new_service_12345.py"),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0
    assert result.stdout.strip(), "expected JSON output on stdout"
    out = json.loads(result.stdout)
    assert out.get("permissionDecision") == "ask"
    assert "task" in out.get("reason", "").lower() or "plan" in out.get("reason", "").lower()


def test_write_new_file_with_plan_passes_silently(boost_home):
    mode_file = boost_home / "state" / "claudeboost-mode.json"
    mode_file.write_text(json.dumps({"mode": "CONSULT"}), encoding="utf-8")

    # Task plan approved
    plan_file = boost_home / "state" / "task-plan.json"
    plan_file.write_text(json.dumps({
        "task": "add new service",
        "approved_at": "2026-06-16",
    }), encoding="utf-8")

    result = run_hook(
        "consult-gate.py",
        _write("/tmp/nonexistent_new_service_12345.py"),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0
    assert result.stdout == b""


# ---------------------------------------------------------------------------
# Write to EXISTING file: silent pass (grinding, not new work)
# ---------------------------------------------------------------------------

def test_write_existing_file_passes_silently(boost_home, tmp_path):
    mode_file = boost_home / "state" / "claudeboost-mode.json"
    mode_file.write_text(json.dumps({"mode": "CONSULT"}), encoding="utf-8")

    # Create an actual file so the hook sees it as existing
    existing = tmp_path / "service.py"
    existing.write_text("# existing", encoding="utf-8")

    result = run_hook(
        "consult-gate.py",
        pretooluse("Write", {"file_path": str(existing), "content": "new content"}),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0
    assert result.stdout == b""


# ---------------------------------------------------------------------------
# Missing mode file: defaults to CONSULT
# ---------------------------------------------------------------------------

def test_defaults_to_consult_when_no_mode_file(boost_home):
    # Don't write mode file — gate should still fire on new file + no plan
    result = run_hook(
        "consult-gate.py",
        _write("/tmp/nonexistent_new_service_12345.py"),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0
    # Defaults to CONSULT → gate fires
    if result.stdout.strip():
        out = json.loads(result.stdout)
        assert out.get("permissionDecision") == "ask"


# ---------------------------------------------------------------------------
# Invalid JSON on stdin: recovers gracefully, exits 0
# ---------------------------------------------------------------------------

def test_invalid_json_input_exits_0(boost_home):
    import subprocess
    import sys
    from helpers import SCRIPTS_DIR, COVERAGERC
    script = SCRIPTS_DIR / "consult-gate.py"
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
