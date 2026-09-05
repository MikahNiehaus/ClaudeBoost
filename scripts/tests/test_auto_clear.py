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
    # scripts/ on sys.path: auto-clear.py imports its sibling workspace_identity,
    # which resolves for free when the hook runs as a script but not when it is
    # loaded from a file path here.
    import sys
    if str(SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPTS_DIR))
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

    def test_signal_does_not_block_the_tmux_path_later(self, boost_home, monkeypatch):
        """A consumed signal is gone, so the next Stop reaches the /clear flag.

        The signal branch returns early. If it ever stopped consuming the file,
        the auto-clear flag would be starved forever instead of once.
        """
        self._write_fresh_flag(boost_home)
        (boost_home / "state" / "clear-safe-terminal-signal.json").write_text(
            json.dumps({"cwd": "C:/prj/x", "timestamp": time.time()}), encoding="utf-8")
        mod = _load_auto_clear()
        monkeypatch.setenv("CLAUDEBOOST_HOME", str(boost_home))
        monkeypatch.setenv("TMUX", "/tmp/tmux-1000/default,1234,0")
        monkeypatch.setattr(mod, "_find_claude_pid_windows", lambda: None)

        with patch.object(subprocess, "run", MagicMock()):
            mod.main()          # consumes the signal, returns early
            mod.main()          # second Stop: now the /clear flag is reached

        assert not (boost_home / "state" / "auto-clear-pending.json").exists()

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


# ---------------------------------------------------------------------------
# /clear-safe terminal handoff signal
#
# clear-safe-launch.py opens the replacement Windows Terminal tab and writes
# state/clear-safe-terminal-signal.json; this hook is what closes the OLD tab.
# Without a test, deleting the consumer here leaves /clear-safe silently
# half working: two tabs open, no error anywhere. That is how it broke once.
#
# os.kill is stubbed in every case below. A test that can kill the real editor
# it is running under is not a test.
# ---------------------------------------------------------------------------

class TestClearSafeTerminalSignal:
    FAKE_PID = 987654

    def _write_signal(self, boost_home, age_seconds: float = 0.0):
        """Write the signal exactly as clear-safe-launch.py writes it."""
        path = boost_home / "state" / "clear-safe-terminal-signal.json"
        path.write_text(
            json.dumps({"cwd": "C:/prj/x", "timestamp": time.time() - age_seconds},
                       indent=2),
            encoding="utf-8",
        )
        return path

    def _run(self, boost_home, monkeypatch, pid, age_seconds=0.0):
        signal = self._write_signal(boost_home, age_seconds)
        mod = _load_auto_clear()
        monkeypatch.setenv("CLAUDEBOOST_HOME", str(boost_home))
        monkeypatch.setenv("TMUX", "")
        monkeypatch.setattr(mod, "_find_claude_pid_windows", lambda: pid)

        killed = []
        monkeypatch.setattr(os, "kill", lambda p, s: killed.append((p, s)))
        rc = mod.main()
        return rc, signal, killed

    def test_fresh_signal_is_consumed_and_kills_the_tab(self, boost_home, monkeypatch):
        rc, signal, killed = self._run(boost_home, monkeypatch, self.FAKE_PID)

        assert rc == 0
        assert not signal.exists(), "signal must be one shot"
        assert killed == [(self.FAKE_PID, 9)]

    def test_stale_signal_is_consumed_without_killing(self, boost_home, monkeypatch):
        # Ten minutes old, past MAX_AGE_SECONDS. Killing on a stale signal would
        # tear down a session the user has since gone back to using.
        rc, signal, killed = self._run(
            boost_home, monkeypatch, self.FAKE_PID, age_seconds=600)

        assert rc == 0
        assert not signal.exists()
        assert killed == []

    def test_no_pid_found_is_survivable(self, boost_home, monkeypatch):
        # Not on Windows, or the process walk came up empty.
        rc, signal, killed = self._run(boost_home, monkeypatch, None)

        assert rc == 0
        assert not signal.exists()
        assert killed == []

    def test_malformed_signal_is_consumed_without_killing(self, boost_home, monkeypatch):
        # No timestamp to trust, so it is treated as infinitely old.
        signal = boost_home / "state" / "clear-safe-terminal-signal.json"
        signal.write_text("not valid json!", encoding="utf-8")
        mod = _load_auto_clear()
        monkeypatch.setenv("CLAUDEBOOST_HOME", str(boost_home))
        monkeypatch.setattr(mod, "_find_claude_pid_windows", lambda: self.FAKE_PID)
        killed = []
        monkeypatch.setattr(os, "kill", lambda p, s: killed.append((p, s)))

        assert mod.main() == 0
        assert not signal.exists()
        assert killed == []

    def test_no_signal_means_no_kill(self, boost_home, monkeypatch):
        mod = _load_auto_clear()
        monkeypatch.setenv("CLAUDEBOOST_HOME", str(boost_home))
        monkeypatch.setattr(mod, "_find_claude_pid_windows", lambda: self.FAKE_PID)
        killed = []
        monkeypatch.setattr(os, "kill", lambda p, s: killed.append((p, s)))

        assert mod.main() == 0
        assert killed == []


# ---------------------------------------------------------------------------
# /clear-safe terminal handoff signal
#
# clear-safe-launch.py opens the replacement Windows Terminal tab and writes
# state/clear-safe-terminal-signal.json; this hook is what closes the OLD tab.
# Without a test, deleting the consumer here leaves /clear-safe silently
# half-working — two tabs open, no error anywhere. That is how it broke once.
#
# os.kill is stubbed in every case below. A test that can kill the real editor
# it is running under is not a test.
# ---------------------------------------------------------------------------

class TestClearSafeTerminalSignal:
    FAKE_PID = 987654

    def _write_signal(self, boost_home, age_seconds: float = 0.0,
                      target_pid: object = "USE_FAKE_PID"):
        """Write the signal exactly as clear-safe-launch.py writes it.

        target_pid is what makes the kill safe: the signal names the session
        that asked to close, recorded at request time by the process that ran
        under it. Pass None to simulate a signal written before the field
        existed. Pass another int to simulate a signal meant for someone else.
        """
        path = boost_home / "state" / "clear-safe-terminal-signal.json"
        payload = {"cwd": "C:/prj/x", "timestamp": time.time() - age_seconds}
        if target_pid != "USE_FAKE_PID":
            if target_pid is not None:
                payload["target_pid"] = target_pid
        else:
            payload["target_pid"] = self.FAKE_PID
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return path

    def _run(self, boost_home, monkeypatch, pid, age_seconds=0.0,
             target_pid: object = "USE_FAKE_PID"):
        signal = self._write_signal(boost_home, age_seconds, target_pid)
        mod = _load_auto_clear()
        monkeypatch.setenv("CLAUDEBOOST_HOME", str(boost_home))
        monkeypatch.setenv("TMUX", "")
        monkeypatch.setattr(mod, "_find_claude_pid_windows", lambda: pid)
        # The kill path resets the terminal first. There is no console attached
        # under pytest, so stub it out rather than depend on that failing quietly.
        monkeypatch.setattr(mod, "_reset_terminal_modes", lambda: None)

        killed = []
        monkeypatch.setattr(os, "kill", lambda p, s: killed.append((p, s)))
        rc = mod.main()
        return rc, signal, killed

    def test_fresh_signal_for_this_session_kills_the_tab(self, boost_home, monkeypatch):
        """The one case that should kill: the signal names this exact session."""
        rc, signal, killed = self._run(boost_home, monkeypatch, self.FAKE_PID)

        assert rc == 0
        assert not signal.exists(), "signal must be one-shot"
        assert killed == [(self.FAKE_PID, 9)]

    def test_signal_meant_for_another_session_does_not_kill_this_one(
            self, boost_home, monkeypatch):
        """The bug this pinning exists to stop.

        The signal is fresh and this session's Stop hook is the one that reads
        it, but it was written for a different tab. Before target_pid the hook
        resolved a target by walking its own process tree, so it killed itself
        here, closing a session the user never asked to close and leaving the
        terminal's mouse reporting on.
        """
        rc, signal, killed = self._run(
            boost_home, monkeypatch, self.FAKE_PID, target_pid=self.FAKE_PID + 1)

        assert rc == 0
        assert not signal.exists(), "signal must still be one-shot"
        assert killed == [], "a signal for another session must never kill this one"

    def test_signal_without_a_target_pid_does_not_kill(self, boost_home, monkeypatch):
        """An old format signal names nobody, and guessing is what caused the
        bug. Refuse rather than fall back to killing whoever read it.

        The audit line is asserted, not just the absence of a kill. Without it
        this passes for the wrong reason: the pid comparison below also rejects
        a None target, so deleting the explicit guard would leave the test green
        while removing the check that states the intent.
        """
        rc, signal, killed = self._run(
            boost_home, monkeypatch, self.FAKE_PID, target_pid=None)

        assert rc == 0
        assert not signal.exists()
        assert killed == []

        log = (boost_home / "state" / "auto-clear.log").read_text(encoding="utf-8")
        assert "no usable target_pid" in log, (
            "the signal must be refused for naming nobody, not incidentally by "
            f"the pid comparison. Log said: {log!r}")

    def test_terminal_modes_are_reset_before_the_kill(self, boost_home, monkeypatch):
        """SIGKILL is TerminateProcess on Windows, so Claude Code never emits
        its own mouse mode disable sequences. If the reset does not go out
        before the kill, the terminal streams mouse coordinates at the shell.
        Order matters: after the kill there is no process left to send them.
        """
        signal = self._write_signal(boost_home)
        mod = _load_auto_clear()
        monkeypatch.setenv("CLAUDEBOOST_HOME", str(boost_home))
        monkeypatch.setenv("TMUX", "")
        monkeypatch.setattr(mod, "_find_claude_pid_windows", lambda: self.FAKE_PID)

        events = []
        monkeypatch.setattr(mod, "_reset_terminal_modes",
                            lambda: events.append("reset"))
        monkeypatch.setattr(os, "kill", lambda p, s: events.append("kill"))

        assert mod.main() == 0
        assert events == ["reset", "kill"], (
            f"reset must run before the kill, got {events}")

    def test_stale_signal_is_consumed_without_killing(self, boost_home, monkeypatch):
        # Ten minutes old, past MAX_AGE_SECONDS. Killing on a stale signal would
        # tear down a session the user has since gone back to using.
        rc, signal, killed = self._run(
            boost_home, monkeypatch, self.FAKE_PID, age_seconds=600)

        assert rc == 0
        assert not signal.exists()
        assert killed == []

    def test_no_pid_found_is_survivable(self, boost_home, monkeypatch):
        # Non-Windows, or the process walk came up empty.
        rc, signal, killed = self._run(boost_home, monkeypatch, None)

        assert rc == 0
        assert not signal.exists()
        assert killed == []

    def test_malformed_signal_is_consumed_without_killing(self, boost_home, monkeypatch):
        # No timestamp to trust, so it is treated as infinitely old.
        signal = boost_home / "state" / "clear-safe-terminal-signal.json"
        signal.write_text("not valid json!", encoding="utf-8")
        mod = _load_auto_clear()
        monkeypatch.setenv("CLAUDEBOOST_HOME", str(boost_home))
        monkeypatch.setattr(mod, "_find_claude_pid_windows", lambda: self.FAKE_PID)
        killed = []
        monkeypatch.setattr(os, "kill", lambda p, s: killed.append((p, s)))

        assert mod.main() == 0
        assert not signal.exists()
        assert killed == []

    def test_no_signal_means_no_kill(self, boost_home, monkeypatch):
        mod = _load_auto_clear()
        monkeypatch.setenv("CLAUDEBOOST_HOME", str(boost_home))
        monkeypatch.setattr(mod, "_find_claude_pid_windows", lambda: self.FAKE_PID)
        killed = []
        monkeypatch.setattr(os, "kill", lambda p, s: killed.append((p, s)))

        assert mod.main() == 0
        assert killed == []
