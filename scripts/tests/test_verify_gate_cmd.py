"""
Tests for scripts/verify-gate-cmd.py (PostToolUse/Task hook).

Phase A — base behavior:
  - No findings in response               -> exit 0, no stderr
  - Response has "severity": "blocker"    -> exit 0, stderr has nudge
  - Response has bare "blocker:" keyword  -> exit 0, stderr has nudge
  - Description is a code-review pass     -> exit 0, silent (suppressed)
  - Description contains "evaluator"      -> exit 0, silent (suppressed)

Phase B — flag file:
  - Findings detected                     -> needs-verification.json written
  - No findings                           -> needs-verification.json removed if present
"""
from __future__ import annotations

import json

import pytest

from helpers import SCRIPTS_DIR, run_hook, posttooluse


def _task_response(response: str, description: str = "some agent task") -> dict:
    return posttooluse("Task", {"description": description}, tool_response=response)


# ---------------------------------------------------------------------------
# Happy paths
# ---------------------------------------------------------------------------

def test_silent_on_clean_response(boost_home):
    """No findings in response — hook should be completely silent."""
    result = run_hook(
        "verify-gate-cmd.py",
        _task_response("All checks passed. No issues found."),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0
    assert result.stderr == b""


# ---------------------------------------------------------------------------
# Finding detection
# ---------------------------------------------------------------------------

def test_nudges_on_severity_blocker(boost_home):
    """Response with JSON severity blocker should emit the verify-gate nudge."""
    response = '{"severity": "blocker", "message": "SQL injection at line 42"}'
    result = run_hook(
        "verify-gate-cmd.py",
        _task_response(response),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0
    assert b"verify-gate nudge" in result.stderr.lower() or b"VERIFY" in result.stderr or b"evaluator" in result.stderr.lower()


def test_nudges_on_bare_blocker_keyword(boost_home):
    """Response with bare 'blocker:' keyword should also trigger the nudge."""
    response = "blocker: Missing auth check on /admin endpoint"
    result = run_hook(
        "verify-gate-cmd.py",
        _task_response(response),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0
    assert result.stderr != b""


def test_nudges_on_severity_high(boost_home):
    """HIGH severity also triggers the nudge."""
    response = '"severity": "high" — unvalidated redirect in auth flow'
    result = run_hook(
        "verify-gate-cmd.py",
        _task_response(response),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0
    assert result.stderr != b""


# ---------------------------------------------------------------------------
# Suppression
# ---------------------------------------------------------------------------

def test_silent_on_review_pass_description():
    """Code-review pass descriptions suppress the nudge even with findings."""
    response = '"severity": "blocker" — missing auth'
    result = run_hook(
        "verify-gate-cmd.py",
        _task_response(response, description="pass 3 — security review"),
    )
    assert result.returncode == 0
    assert result.stderr == b""


def test_silent_when_evaluator_ran():
    """Evaluator-agent runs are suppressed — they ARE the verification step."""
    response = '"severity": "high" — potential issue'
    result = run_hook(
        "verify-gate-cmd.py",
        _task_response(response, description="evaluator-agent verification pass"),
    )
    assert result.returncode == 0
    assert result.stderr == b""


# ---------------------------------------------------------------------------
# Phase B: flag file behaviour
# ---------------------------------------------------------------------------

def test_writes_flag_on_findings(boost_home):
    """When findings are detected the needs-verification.json flag is written."""
    flag = boost_home / "state" / "needs-verification.json"
    assert not flag.exists()

    response = '"severity": "blocker" — missing auth check'
    run_hook(
        "verify-gate-cmd.py",
        _task_response(response),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )

    assert flag.exists(), "flag file should be written when findings are detected"
    data = json.loads(flag.read_text(encoding="utf-8"))
    assert "flagged_at" in data
    assert "finding_summary" in data


def test_clears_flag_when_no_findings(boost_home):
    """When no findings are present any existing flag is removed."""
    flag = boost_home / "state" / "needs-verification.json"
    flag.write_text('{"flagged_at": "old"}', encoding="utf-8")

    run_hook(
        "verify-gate-cmd.py",
        _task_response("All checks passed. Nothing found."),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )

    assert not flag.exists(), "flag file should be cleared when no findings"
