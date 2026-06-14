"""
Tests for scripts/speak-stop.py (UserPromptSubmit / manual stop hook).

Stops any playing TTS by writing a stop file and killing by PID.
Always exits 0.
"""
from __future__ import annotations

import json
import pytest
from helpers import SCRIPTS_DIR, run_hook


def _prompt() -> dict:
    return {"hook_event_name": "UserPromptSubmit", "session_id": "test", "prompt": "continue"}


# ---------------------------------------------------------------------------
# Always exits 0
# ---------------------------------------------------------------------------

def test_always_exits_0(tmp_path):
    result = run_hook(
        "speak-stop.py",
        _prompt(),
        env_overrides={"TEMP": str(tmp_path)},
    )
    assert result.returncode == 0


def test_exits_0_on_empty_input(tmp_path):
    result = run_hook(
        "speak-stop.py",
        {},
        env_overrides={"TEMP": str(tmp_path)},
    )
    assert result.returncode == 0


# ---------------------------------------------------------------------------
# Creates stop file
# ---------------------------------------------------------------------------

def test_creates_stop_file(tmp_path):
    stop_file = tmp_path / "claudeboost_tts.stop"
    assert not stop_file.exists()

    result = run_hook(
        "speak-stop.py",
        _prompt(),
        env_overrides={"TEMP": str(tmp_path)},
    )
    assert result.returncode == 0
    assert stop_file.exists()
    assert stop_file.read_text(encoding="utf-8") == "stop"


# ---------------------------------------------------------------------------
# No crash when PID file missing
# ---------------------------------------------------------------------------

def test_no_crash_when_no_pid_file(tmp_path):
    result = run_hook(
        "speak-stop.py",
        _prompt(),
        env_overrides={"TEMP": str(tmp_path)},
    )
    assert result.returncode == 0
    assert b"Traceback" not in result.stderr


# ---------------------------------------------------------------------------
# No crash when PID file has invalid PID
# ---------------------------------------------------------------------------

def test_no_crash_on_invalid_pid(tmp_path):
    pid_file = tmp_path / "claudeboost_tts.pid"
    pid_file.write_text("not-a-pid", encoding="utf-8")

    result = run_hook(
        "speak-stop.py",
        _prompt(),
        env_overrides={"TEMP": str(tmp_path)},
    )
    assert result.returncode == 0
    assert b"Traceback" not in result.stderr


# ---------------------------------------------------------------------------
# No crash when PID does not exist
# ---------------------------------------------------------------------------

def test_no_crash_on_nonexistent_pid(tmp_path):
    pid_file = tmp_path / "claudeboost_tts.pid"
    pid_file.write_text("99999999", encoding="utf-8")  # very unlikely to exist

    result = run_hook(
        "speak-stop.py",
        _prompt(),
        env_overrides={"TEMP": str(tmp_path)},
    )
    assert result.returncode == 0
    assert b"Traceback" not in result.stderr


# ---------------------------------------------------------------------------
# No stdout output
# ---------------------------------------------------------------------------

def test_no_stdout_output(tmp_path):
    result = run_hook(
        "speak-stop.py",
        _prompt(),
        env_overrides={"TEMP": str(tmp_path)},
    )
    assert result.returncode == 0
    assert result.stdout.strip() == b""


# ---------------------------------------------------------------------------
# Lines 27-28: stop_file.write_text raises (except Exception: pass)
# ---------------------------------------------------------------------------

def test_write_stop_file_exception_is_swallowed(tmp_path):
    # Make claudeboost_tts.stop a directory so write_text raises PermissionError.
    # The except block on lines 27-28 must swallow it and still exit 0.
    stop_dir = tmp_path / "claudeboost_tts.stop"
    stop_dir.mkdir()

    result = run_hook(
        "speak-stop.py",
        _prompt(),
        env_overrides={"TEMP": str(tmp_path)},
    )
    assert result.returncode == 0
    assert b"Traceback" not in result.stderr


# ---------------------------------------------------------------------------
# Lines 39-40: pid_file.unlink raises (except Exception: pass)
# ---------------------------------------------------------------------------

def test_unlink_pid_file_exception_is_swallowed(tmp_path):
    # Make claudeboost_tts.pid a directory so unlink raises PermissionError.
    # The except block on lines 39-40 must swallow it and still exit 0.
    pid_dir = tmp_path / "claudeboost_tts.pid"
    pid_dir.mkdir()

    result = run_hook(
        "speak-stop.py",
        _prompt(),
        env_overrides={"TEMP": str(tmp_path)},
    )
    assert result.returncode == 0
    assert b"Traceback" not in result.stderr
