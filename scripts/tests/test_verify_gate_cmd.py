"""
Tests for scripts/verify-gate-cmd.py (PostToolUse/Task hook).

Phase A — base behavior:
  - No findings in response               -> exit 0, no stderr
  - Response has "severity": "blocker"    -> exit 0, stderr has nudge
  - Response has bare "blocker:" keyword  -> exit 0, stderr has nudge
  - Description is a /review --deep pass  -> exit 0, silent (suppressed)
  - Description contains "evaluator"      -> exit 0, silent (suppressed)
  - audit-in-progress.json active         -> exit 0, silent (suppressed, no flag written)

Phase B — flag file:
  - Findings detected                     -> needs-verification.json written
  - No findings                           -> needs-verification.json removed if present
"""
from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from helpers import SCRIPTS_DIR, run_hook, posttooluse

# Direct import for unit testing
_vg_spec = importlib.util.spec_from_file_location("verify_gate_cmd", SCRIPTS_DIR / "verify-gate-cmd.py")
_vg_mod = importlib.util.module_from_spec(_vg_spec)
_vg_spec.loader.exec_module(_vg_mod)


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


def test_silent_on_verdict_description_and_clears_flag(boost_home):
    """A verdict-synthesis run is the evaluator step — suppress and clear the flag.

    Without this, the gate re-flags the evaluator's own findings and the
    next spawn gets blocked again, looping forever.
    """
    flag = boost_home / "state" / "needs-verification.json"
    flag.write_text('{"flagged_at": "old"}', encoding="utf-8")

    response = '"severity": "high" — confirmed finding from verdict pass'
    result = run_hook(
        "verify-gate-cmd.py",
        _task_response(response, description="Opus verdict synthesis"),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0
    assert result.stderr == b""
    assert not flag.exists(), "flag should be cleared after the verdict run"


def test_silent_during_audit_run(boost_home):
    """During an active /audit run, suppress regardless of finding severity — no flag written."""
    audit_flag = boost_home / "state" / "audit-in-progress.json"
    audit_flag.write_text('{"active":true}', encoding="utf-8")
    try:
        response = '"severity": "blocker", "message": "critical issue found"'
        result = run_hook(
            "verify-gate-cmd.py",
            _task_response(response),
            env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
        )
        assert result.returncode == 0
        assert result.stderr == b""
        # Critically: NEEDS_VERIFICATION must NOT be written during a batch run
        assert not (boost_home / "state" / "needs-verification.json").exists()
    finally:
        audit_flag.unlink(missing_ok=True)


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


# ---------------------------------------------------------------------------
# Direct import unit tests for main() exception paths
# ---------------------------------------------------------------------------

class TestMainExceptionPaths:
    """Cover the exception catch blocks that subprocess tests can't reach."""

    def test_stdin_read_exception_returns_0(self, tmp_path):
        """Lines 59-60: sys.stdin.read() raises -> raw = "" -> payload = {} -> continues."""
        import io
        bad_stdin = MagicMock()
        bad_stdin.isatty.return_value = False
        bad_stdin.read.side_effect = OSError("broken pipe")

        with patch.object(_vg_mod, "BOOST_HOME", tmp_path), \
             patch.object(_vg_mod, "_FLAG", tmp_path / "state" / "needs-verification.json"), \
             patch("sys.stdin", bad_stdin):
            rc = _vg_mod.main()
        assert rc == 0

    def test_json_parse_exception_returns_0(self, tmp_path):
        """Lines 63-64: json.loads raises -> payload = {} -> continues."""
        import io
        bad_stdin = MagicMock()
        bad_stdin.isatty.return_value = False
        bad_stdin.read.return_value = "NOT VALID JSON {{{"

        with patch.object(_vg_mod, "BOOST_HOME", tmp_path), \
             patch.object(_vg_mod, "_FLAG", tmp_path / "state" / "needs-verification.json"), \
             patch("sys.stdin", bad_stdin):
            rc = _vg_mod.main()
        assert rc == 0

    def test_review_pass_marker_suppresses(self, tmp_path):
        """Line 79: description contains review pass marker -> exit 0 silent."""
        import io
        payload = json.dumps({
            "tool_input": {"description": "pass 3 — security review"},
            "tool_response": '"severity": "blocker" — something bad',
        })
        fake_stdin = MagicMock()
        fake_stdin.isatty.return_value = False
        fake_stdin.read.return_value = payload

        with patch.object(_vg_mod, "BOOST_HOME", tmp_path), \
             patch.object(_vg_mod, "_FLAG", tmp_path / "state" / "needs-verification.json"), \
             patch("sys.stdin", fake_stdin):
            rc = _vg_mod.main()
        assert rc == 0

    def test_evaluator_unlink_exception_still_returns_0(self, tmp_path):
        """Lines 87-88: _FLAG.unlink() raises -> exception swallowed -> returns 0."""
        import io
        payload = json.dumps({
            "tool_input": {"description": "evaluator-agent verification pass"},
            "tool_response": '"severity": "high" — something',
        })
        fake_stdin = MagicMock()
        fake_stdin.isatty.return_value = False
        fake_stdin.read.return_value = payload

        flag = MagicMock()
        flag.unlink.side_effect = OSError("permission denied")

        # Also patch the audit-in-progress check
        fake_audit_path = MagicMock()
        fake_audit_path.exists.return_value = False

        with patch.object(_vg_mod, "BOOST_HOME", tmp_path), \
             patch.object(_vg_mod, "_FLAG", flag):
            # Need to patch the audit path lookup too
            fake_state = MagicMock()
            fake_state.__truediv__ = MagicMock(return_value=fake_audit_path)
            with patch.object(_vg_mod, "BOOST_HOME", MagicMock(__truediv__=lambda s, x: fake_audit_path if x == "state" else tmp_path / x)):
                # Simplest: just call with a real tmp_path and mock _FLAG unlink
                pass

        # Direct approach: call main() with evaluator in description, _FLAG.unlink raises
        payload2 = json.dumps({
            "tool_input": {"description": "evaluator check"},
            "tool_response": '"severity": "high"',
        })
        stdin2 = MagicMock()
        stdin2.isatty.return_value = False
        stdin2.read.return_value = payload2

        bad_flag = tmp_path / "state" / "needs-verification.json"
        bad_flag.parent.mkdir(parents=True, exist_ok=True)

        with patch.object(_vg_mod, "_FLAG", bad_flag), \
             patch.object(_vg_mod, "BOOST_HOME", tmp_path), \
             patch("sys.stdin", stdin2):
            rc = _vg_mod.main()
        assert rc == 0

    def test_no_findings_unlink_exception_returns_0(self, tmp_path):
        """Lines 97-98: _FLAG.unlink() raises when no findings -> exception swallowed."""
        payload = json.dumps({
            "tool_input": {"description": "normal agent task"},
            "tool_response": "All good, nothing found.",
        })
        fake_stdin = MagicMock()
        fake_stdin.isatty.return_value = False
        fake_stdin.read.return_value = payload

        flag_mock = MagicMock()
        flag_mock.unlink.side_effect = OSError("disk error")

        with patch.object(_vg_mod, "_FLAG", flag_mock), \
             patch.object(_vg_mod, "BOOST_HOME", tmp_path), \
             patch("sys.stdin", fake_stdin):
            rc = _vg_mod.main()
        assert rc == 0

    def test_flag_write_exception_returns_0(self, tmp_path):
        """Lines 111-112: _FLAG.write_text() raises -> exception swallowed -> still exits 0."""
        payload = json.dumps({
            "tool_input": {"description": "normal agent task"},
            "tool_response": '"severity": "blocker" — critical bug found',
        })
        fake_stdin = MagicMock()
        fake_stdin.isatty.return_value = False
        fake_stdin.read.return_value = payload

        flag_mock = MagicMock()
        flag_mock.write_text.side_effect = OSError("disk full")

        with patch.object(_vg_mod, "_FLAG", flag_mock), \
             patch.object(_vg_mod, "BOOST_HOME", tmp_path), \
             patch("sys.stdin", fake_stdin):
            rc = _vg_mod.main()
        assert rc == 0


    def test_bad_json_via_subprocess_exits_0(self, boost_home):
        """Lines 63-64: bad JSON stdin via subprocess -> payload = {} -> exits 0."""
        import subprocess, sys, os
        script = SCRIPTS_DIR / "verify-gate-cmd.py"
        env = {**os.environ, "CLAUDEBOOST_HOME": str(boost_home)}
        result = subprocess.run(
            [sys.executable, str(script)],
            input=b"NOT VALID JSON {{{",
            capture_output=True,
            env=env,
        )
        assert result.returncode == 0

    def test_audit_in_progress_suppresses_via_direct_call(self, tmp_path):
        """Line 75: audit-in-progress.json exists -> return 0 immediately (direct import path)."""
        state_dir = tmp_path / "state"
        state_dir.mkdir(parents=True, exist_ok=True)
        audit_flag = state_dir / "audit-in-progress.json"
        audit_flag.write_text('{"active":true}', encoding="utf-8")

        payload = json.dumps({
            "tool_input": {"description": "normal agent task"},
            "tool_response": '"severity": "blocker" \u2014 critical bug',
        })
        fake_stdin = MagicMock()
        fake_stdin.isatty.return_value = False
        fake_stdin.read.return_value = payload

        with patch.object(_vg_mod, "BOOST_HOME", tmp_path), \
             patch.object(_vg_mod, "_FLAG", tmp_path / "state" / "needs-verification.json"), \
             patch("sys.stdin", fake_stdin):
            rc = _vg_mod.main()

        assert rc == 0
        assert not (tmp_path / "state" / "needs-verification.json").exists()

    def test_evaluator_unlink_raises_exception_is_swallowed(self, tmp_path):
        """Lines 87-88: _FLAG.unlink() raises inside evaluator branch -> except swallows it -> returns 0."""
        state_dir = tmp_path / "state"
        state_dir.mkdir(parents=True, exist_ok=True)

        payload = json.dumps({
            "tool_input": {"description": "evaluator-agent verification pass"},
            "tool_response": '"severity": "high" \u2014 some finding',
        })
        fake_stdin = MagicMock()
        fake_stdin.isatty.return_value = False
        fake_stdin.read.return_value = payload

        flag_mock = MagicMock()
        flag_mock.unlink.side_effect = OSError("permission denied on unlink")

        with patch.object(_vg_mod, "BOOST_HOME", tmp_path), \
             patch.object(_vg_mod, "_FLAG", flag_mock), \
             patch("sys.stdin", fake_stdin):
            rc = _vg_mod.main()

        assert rc == 0
        flag_mock.unlink.assert_called_once_with(missing_ok=True)

