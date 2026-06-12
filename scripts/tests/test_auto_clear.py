"""
Tests for scripts/auto-clear.py (Stop hook).

Injects /clear after Claude finishes if auto-clear-pending.json is set.
Always exits 0. No real tmux interaction in tests.
"""
from __future__ import annotations

import json
import time
import pytest
from helpers import SCRIPTS_DIR, run_hook


def _stop() -> dict:
    return {"hook_event_name": "Stop", "session_id": "test"}


# ---------------------------------------------------------------------------
# Always exits 0
# ---------------------------------------------------------------------------

def test_always_exits_0(boost_home):
    result = run_hook(
        "auto-clear.py",
        _stop(),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0


def test_exits_0_no_flag(boost_home):
    result = run_hook(
        "auto-clear.py",
        _stop(),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0


def test_exits_0_when_no_claudeboost_home():
    # CLAUDEBOOST_HOME not set → return 0 immediately
    result = run_hook(
        "auto-clear.py",
        _stop(),
        env_overrides={"CLAUDEBOOST_HOME": ""},
    )
    assert result.returncode == 0


# ---------------------------------------------------------------------------
# Flag present and fresh: consumed (one-shot)
# ---------------------------------------------------------------------------

def test_consumes_flag_when_present(boost_home):
    flag_path = boost_home / "state" / "auto-clear-pending.json"
    flag_path.write_text(json.dumps({
        "timestamp": time.time(),
        "session_name": "test-session",
    }), encoding="utf-8")

    assert flag_path.exists()

    result = run_hook(
        "auto-clear.py",
        _stop(),
        env_overrides={
            "CLAUDEBOOST_HOME": str(boost_home),
            "TMUX": "",  # non-tmux env so no actual tmux call
        },
    )
    assert result.returncode == 0
    # Flag should be deleted (one-shot)
    assert not flag_path.exists()


# ---------------------------------------------------------------------------
# Flag present but stale: consumed and ignored
# ---------------------------------------------------------------------------

def test_ignores_stale_flag(boost_home):
    flag_path = boost_home / "state" / "auto-clear-pending.json"
    # Stale: 10 minutes ago (past 5-minute MAX_AGE_SECONDS)
    flag_path.write_text(json.dumps({
        "timestamp": time.time() - 600,
        "session_name": "old-session",
    }), encoding="utf-8")

    result = run_hook(
        "auto-clear.py",
        _stop(),
        env_overrides={
            "CLAUDEBOOST_HOME": str(boost_home),
            "TMUX": "",
        },
    )
    assert result.returncode == 0
    # Flag still consumed even if stale
    assert not flag_path.exists()


# ---------------------------------------------------------------------------
# Malformed flag: no crash
# ---------------------------------------------------------------------------

def test_no_crash_on_malformed_flag(boost_home):
    flag_path = boost_home / "state" / "auto-clear-pending.json"
    flag_path.write_text("not valid json!", encoding="utf-8")

    result = run_hook(
        "auto-clear.py",
        _stop(),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0
    assert b"Traceback" not in result.stderr
