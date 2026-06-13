"""
Tests for scripts/auto-clear.py (Stop hook).

Injects /clear after Claude finishes if auto-clear-pending.json is set.
Always exits 0. No real tmux interaction in tests.
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import time
from unittest.mock import MagicMock, patch

import pytest
from helpers import SCRIPTS_DIR, run_hook


def _load_auto_clear():
    spec = importlib.util.spec_from_file_location("auto_clear", SCRIPTS_DIR / "auto-clear.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


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


# ---------------------------------------------------------------------------
# TMUX branch (lines 59-70) — direct import with mocked subprocess
# ---------------------------------------------------------------------------

class TestTmuxBranch:
    def _write_fresh_flag(self, boost_home, session_name: str = ""):
        flag_path = boost_home / "state" / "auto-clear-pending.json"
        flag_path.write_text(
            json.dumps({"timestamp": time.time(), "session_name": session_name}),
            encoding="utf-8",
        )

    def test_tmux_sends_clear_command(self, boost_home, monkeypatch):
        """When TMUX is set, subprocess.run is called with tmux send-keys /clear."""
        self._write_fresh_flag(boost_home)
        mod = _load_auto_clear()

        mock_run = MagicMock()
        monkeypatch.setenv("TMUX", "/tmp/tmux-1000/default,1234,0")
        monkeypatch.setenv("CLAUDEBOOST_HOME", str(boost_home))

        with patch.object(subprocess, "run", mock_run):
            mod.main()

        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]
        assert "tmux" in call_args[0]
        assert "/clear" in call_args

    def test_tmux_with_session_name_spawns_popen(self, boost_home, monkeypatch):
        """TMUX set + session_name → subprocess.Popen called for rename (lines 61-70)."""
        self._write_fresh_flag(boost_home, session_name="my-task")
        mod = _load_auto_clear()

        mock_run = MagicMock()
        mock_popen = MagicMock()
        monkeypatch.setenv("TMUX", "/tmp/tmux-1000/default,1234,0")
        monkeypatch.setenv("CLAUDEBOOST_HOME", str(boost_home))

        with patch.object(subprocess, "run", mock_run), \
             patch.object(subprocess, "Popen", mock_popen):
            mod.main()

        mock_run.assert_called_once()
        mock_popen.assert_called_once()
        popen_cmd = mock_popen.call_args[0][0]
        assert "rename" in popen_cmd[2]  # bash -c "sleep 5 && tmux send-keys '/rename ...'"

    def test_tmux_without_session_name_no_popen(self, boost_home, monkeypatch):
        """TMUX set + empty session_name → Popen NOT called (lines 61 branch False)."""
        self._write_fresh_flag(boost_home, session_name="")
        mod = _load_auto_clear()

        mock_run = MagicMock()
        mock_popen = MagicMock()
        monkeypatch.setenv("TMUX", "/tmp/tmux-1000/default,1234,0")
        monkeypatch.setenv("CLAUDEBOOST_HOME", str(boost_home))

        with patch.object(subprocess, "run", mock_run), \
             patch.object(subprocess, "Popen", mock_popen):
            mod.main()

        mock_run.assert_called_once()
        mock_popen.assert_not_called()
