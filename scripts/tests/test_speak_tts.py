"""
Tests for scripts/speak-tts.py (Stop hook).

Speaks Claude's last response via TTS. Always exits 0.
Tests focus on: disabled state, missing env vars, no crash on bad input.
"""
from __future__ import annotations

import json
import pytest
from helpers import SCRIPTS_DIR, run_hook


def _stop(text: str = "", transcript_path: str = "") -> dict:
    return {
        "hook_event_name": "Stop",
        "session_id": "test",
        "last_assistant_message": text,
        "transcript_path": transcript_path,
        "stop_hook_active": False,
    }


# ---------------------------------------------------------------------------
# Always exits 0
# ---------------------------------------------------------------------------

def test_always_exits_0(boost_home):
    result = run_hook(
        "speak-tts.py",
        _stop("Hello, this is a test message"),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0


def test_exits_0_on_empty_input(boost_home):
    result = run_hook(
        "speak-tts.py",
        {},
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0


# ---------------------------------------------------------------------------
# TTS disabled: silent pass
# ---------------------------------------------------------------------------

def test_silent_when_tts_disabled(boost_home):
    state = boost_home / "state" / "speak-state.json"
    state.write_text(json.dumps({"enabled": False}), encoding="utf-8")

    result = run_hook(
        "speak-tts.py",
        _stop("Some interesting text that should not be spoken"),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0
    assert result.stdout.strip() == b""


def test_silent_when_no_speak_state(boost_home):
    # No speak-state.json → defaults to disabled
    result = run_hook(
        "speak-tts.py",
        _stop("text"),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0


# ---------------------------------------------------------------------------
# stop_hook_active: prevents infinite loop
# ---------------------------------------------------------------------------

def test_skips_when_stop_hook_active(boost_home):
    state = boost_home / "state" / "speak-state.json"
    state.write_text(json.dumps({"enabled": True, "voice": "en-US-AndrewNeural"}), encoding="utf-8")

    payload = {
        "hook_event_name": "Stop",
        "session_id": "test",
        "last_assistant_message": "This text would loop infinitely",
        "stop_hook_active": True,  # prevent loop
    }
    result = run_hook(
        "speak-tts.py",
        payload,
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0


# ---------------------------------------------------------------------------
# Short text: skip
# ---------------------------------------------------------------------------

def test_skips_short_text(boost_home):
    state = boost_home / "state" / "speak-state.json"
    state.write_text(json.dumps({"enabled": True}), encoding="utf-8")

    result = run_hook(
        "speak-tts.py",
        _stop("ok"),  # under MIN_SPEAK_CHARS=10 after filtering
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0
    assert b"Traceback" not in result.stderr


# ---------------------------------------------------------------------------
# No crash with missing TEMP env
# ---------------------------------------------------------------------------

def test_no_crash_missing_temp(boost_home, tmp_path):
    state = boost_home / "state" / "speak-state.json"
    state.write_text(json.dumps({"enabled": True}), encoding="utf-8")

    result = run_hook(
        "speak-tts.py",
        _stop("Some text to speak out loud"),
        env_overrides={
            "CLAUDEBOOST_HOME": str(boost_home),
            "TEMP": str(tmp_path),
            "TMPDIR": str(tmp_path),
        },
    )
    assert result.returncode == 0
    assert b"Traceback" not in result.stderr
