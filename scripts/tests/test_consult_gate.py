"""
Tests for scripts/consult-gate.py (PreToolUse hook).

The gate runs on Edit, MultiEdit, and Write in CONSULT mode.
It checks state/spec-sheet.json for an approved_files list and blocks any
target not in that list with permissionDecision:"ask".

Pass conditions (no output, exit 0):
  - AUTO mode
  - Bash or any non-gated tool
  - Exempt paths: workspace/, state/, .claudeboost/, plans/, docs/
  - File is listed in spec-sheet.json approved_files

Block conditions (permissionDecision:"ask", exit 0):
  - CONSULT mode, no spec-sheet.json at all
  - CONSULT mode, file not in approved_files
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import pytest
from helpers import SCRIPTS_DIR, COVERAGERC, run_hook, pretooluse


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _edit(file_path: str) -> dict:
    return pretooluse("Edit", {
        "file_path": file_path,
        "old_string": "a",
        "new_string": "b",
    })


def _write(file_path: str) -> dict:
    return pretooluse("Write", {"file_path": file_path, "content": "hello"})


def _multi(file_paths: list[str]) -> dict:
    return pretooluse("MultiEdit", {
        "edits": [{"file_path": fp, "old_string": "a", "new_string": "b"} for fp in file_paths]
    })


def _bash(command: str) -> dict:
    return pretooluse("Bash", {"command": command})


def _spec(boost_home, approved_files: list[str], task: str = "test task") -> None:
    """Write a minimal spec-sheet.json to boost_home/state/."""
    spec = {
        "task": task,
        "approved_at": "2026-06-24",
        "approved_files": approved_files,
    }
    (boost_home / "state" / "spec-sheet.json").write_text(
        json.dumps(spec), encoding="utf-8"
    )


def _consult(boost_home) -> None:
    (boost_home / "state" / "claudeboost-mode.json").write_text(
        json.dumps({"mode": "CONSULT"}), encoding="utf-8"
    )


def _auto(boost_home) -> None:
    (boost_home / "state" / "claudeboost-mode.json").write_text(
        json.dumps({"mode": "AUTO"}), encoding="utf-8"
    )


def _run(boost_home, payload: dict) -> subprocess.CompletedProcess:
    return run_hook(
        "consult-gate.py",
        payload,
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )


def _assert_ask(result: subprocess.CompletedProcess) -> dict:
    assert result.returncode == 0
    assert result.stdout.strip(), "expected JSON on stdout"
    out = json.loads(result.stdout)
    assert out.get("permissionDecision") == "ask", f"expected ask, got: {out}"
    return out


def _assert_pass(result: subprocess.CompletedProcess) -> None:
    assert result.returncode == 0
    assert result.stdout == b"", f"expected no output, got: {result.stdout!r}"


# ---------------------------------------------------------------------------
# AUTO mode: all tools pass silently
# ---------------------------------------------------------------------------

def test_auto_mode_edit_passes(boost_home):
    _auto(boost_home)
    _assert_pass(_run(boost_home, _edit("/project/src/app.py")))


def test_auto_mode_write_passes(boost_home):
    _auto(boost_home)
    _assert_pass(_run(boost_home, _write("/project/src/new_file.py")))


# ---------------------------------------------------------------------------
# Bash: always silent pass regardless of mode
# ---------------------------------------------------------------------------

def test_bash_passes_in_consult_mode(boost_home):
    _consult(boost_home)
    _assert_pass(_run(boost_home, _bash("echo hello")))


# ---------------------------------------------------------------------------
# Exempt paths: pass silently even with no spec-sheet.json
# ---------------------------------------------------------------------------

def test_exempt_workspace_path_passes(boost_home):
    _consult(boost_home)
    _assert_pass(_run(boost_home, _write("/project/workspace/task-1/context.md")))


def test_exempt_state_path_passes(boost_home):
    _consult(boost_home)
    _assert_pass(_run(boost_home, _write("/project/state/spec-sheet.json")))


def test_exempt_docs_path_passes(boost_home):
    _consult(boost_home)
    _assert_pass(_run(boost_home, _write("/project/docs/README.md")))


def test_exempt_plans_path_passes(boost_home):
    _consult(boost_home)
    _assert_pass(_run(boost_home, _write("/project/plans/plan.md")))


def test_exempt_claudeboost_path_passes(boost_home):
    _consult(boost_home)
    _assert_pass(_run(boost_home, _write("/project/.claudeboost/config.json")))


# ---------------------------------------------------------------------------
# No spec-sheet.json: Edit/Write/MultiEdit all blocked
# ---------------------------------------------------------------------------

def test_no_spec_edit_blocked(boost_home):
    _consult(boost_home)
    out = _assert_ask(_run(boost_home, _edit("/project/src/service.py")))
    assert "spec" in out["reason"].lower()


def test_no_spec_write_blocked(boost_home):
    _consult(boost_home)
    out = _assert_ask(_run(boost_home, _write("/project/src/new_service.py")))
    assert "spec" in out["reason"].lower()


def test_no_spec_multiedit_blocked(boost_home):
    _consult(boost_home)
    _assert_ask(_run(boost_home, _multi(["/project/src/a.py", "/project/src/b.py"])))


# ---------------------------------------------------------------------------
# File in spec: passes silently
# ---------------------------------------------------------------------------

def test_edit_file_in_spec_passes(boost_home):
    _consult(boost_home)
    _spec(boost_home, ["src/service.py"])
    _assert_pass(_run(boost_home, _edit("/project/src/service.py")))


def test_write_file_in_spec_passes(boost_home):
    _consult(boost_home)
    _spec(boost_home, ["src/new_module.py"])
    _assert_pass(_run(boost_home, _write("/project/src/new_module.py")))


def test_multiedit_all_files_in_spec_passes(boost_home):
    _consult(boost_home)
    _spec(boost_home, ["src/a.py", "src/b.py"])
    _assert_pass(_run(boost_home, _multi(["/project/src/a.py", "/project/src/b.py"])))


# ---------------------------------------------------------------------------
# File NOT in spec: blocked
# ---------------------------------------------------------------------------

def test_edit_file_not_in_spec_blocked(boost_home):
    _consult(boost_home)
    _spec(boost_home, ["src/other.py"])
    out = _assert_ask(_run(boost_home, _edit("/project/src/service.py")))
    assert "service.py" in out["reason"]


def test_write_file_not_in_spec_blocked(boost_home):
    _consult(boost_home)
    _spec(boost_home, ["src/other.py"])
    out = _assert_ask(_run(boost_home, _write("/project/src/new_file.py")))
    assert "new_file.py" in out["reason"]


def test_multiedit_one_file_not_in_spec_blocked(boost_home):
    """MultiEdit where one file is in spec and one isn't blocks on the unlisted one."""
    _consult(boost_home)
    _spec(boost_home, ["src/a.py"])
    _assert_ask(_run(boost_home, _multi(["/project/src/a.py", "/project/src/b.py"])))


# ---------------------------------------------------------------------------
# .claude/ path: NOT exempt (must be in spec)
# ---------------------------------------------------------------------------

def test_claude_commands_not_exempt_no_spec(boost_home):
    _consult(boost_home)
    _assert_ask(_run(boost_home, _write("/project/.claude/commands/new-skill.md")))


def test_claude_commands_in_spec_passes(boost_home):
    _consult(boost_home)
    _spec(boost_home, [".claude/commands/new-skill.md"])
    _assert_pass(_run(boost_home, _write("/project/.claude/commands/new-skill.md")))


# ---------------------------------------------------------------------------
# Missing mode file: defaults to CONSULT
# ---------------------------------------------------------------------------

def test_defaults_to_consult_when_no_mode_file(boost_home):
    # No mode file written — should default to CONSULT and block
    _assert_ask(_run(boost_home, _write("/project/src/service.py")))


# ---------------------------------------------------------------------------
# Invalid JSON on stdin: recovers gracefully, exits 0
# ---------------------------------------------------------------------------

def test_invalid_json_input_exits_0(boost_home):
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


# ---------------------------------------------------------------------------
# Edge cases: spec-sheet.json exists but approved_files is empty or malformed
# ---------------------------------------------------------------------------

def test_spec_with_empty_approved_files_blocks(boost_home):
    """Spec exists but approved_files is [] — should block any non-exempt file."""
    _consult(boost_home)
    _spec(boost_home, [])  # approved_files is empty list
    _assert_ask(_run(boost_home, _edit("/project/src/service.py")))


def test_spec_with_malformed_json_blocks(boost_home):
    """Malformed spec-sheet.json falls back to {} — approved_files defaults to [] — blocks."""
    _consult(boost_home)
    (boost_home / "state" / "spec-sheet.json").write_text("not valid json {{{{", encoding="utf-8")
    _assert_ask(_run(boost_home, _edit("/project/src/service.py")))


# ---------------------------------------------------------------------------
# Edge cases: MultiEdit with empty or all-exempt edits list
# ---------------------------------------------------------------------------

def test_multiedit_empty_edits_passes(boost_home):
    """MultiEdit with no edits at all — no file paths to check — passes silently."""
    _consult(boost_home)
    _assert_pass(_run(boost_home, pretooluse("MultiEdit", {"edits": []})))


def test_multiedit_all_files_exempt_passes(boost_home):
    """MultiEdit where every file is in an exempt path — passes silently even with no spec."""
    _consult(boost_home)
    _assert_pass(_run(boost_home, _multi([
        "/project/workspace/task-1/context.md",
        "/project/state/spec-sheet.json",
    ])))
