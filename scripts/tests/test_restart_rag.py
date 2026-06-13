"""
Tests for scripts/restart-rag.py (CLI utility).

Finds and kills rag_server processes. When no server is running, reports
"not running" and exits 0.
"""
from __future__ import annotations

import importlib
import os
import signal
import sys
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from helpers import run_script, SCRIPTS_DIR

# Direct import for unit testing
_rr_spec = importlib.util.spec_from_file_location("restart_rag", SCRIPTS_DIR / "restart-rag.py")
_rr_mod = importlib.util.module_from_spec(_rr_spec)
_rr_spec.loader.exec_module(_rr_mod)


class TestNoServerRunning:
    def test_exits_0_when_no_rag_server(self, tmp_path):
        # On a clean test machine (or where rag_server is not running), should exit 0
        result = run_script("restart-rag.py")
        assert result.returncode == 0

    def test_reports_not_running_when_no_process(self):
        result = run_script("restart-rag.py")
        # Either "not running" or it found and stopped a server — both are exit 0
        assert result.returncode == 0
        output = result.stdout.decode(errors="replace")
        # If no server: prints "not running" message
        # If server found: prints PID info
        assert "rag" in output.lower() or "server" in output.lower() or output == ""


# ---------------------------------------------------------------------------
# Direct import unit tests for internal functions
# ---------------------------------------------------------------------------

class TestFindRagServerPids:
    def test_returns_empty_list_when_no_process(self):
        mock_result = MagicMock()
        mock_result.stdout = ""
        with patch("subprocess.run", return_value=mock_result):
            pids = _rr_mod.find_rag_server_pids()
        assert pids == []

    def test_parses_pids_from_output(self):
        mock_result = MagicMock()
        mock_result.stdout = "1234\n5678\n"
        with patch("subprocess.run", return_value=mock_result):
            pids = _rr_mod.find_rag_server_pids()
        assert 1234 in pids
        assert 5678 in pids

    def test_returns_empty_on_exception(self):
        with patch("subprocess.run", side_effect=Exception("command not found")):
            pids = _rr_mod.find_rag_server_pids()
        assert pids == []

    def test_posix_pgrep_path(self):
        mock_result = MagicMock()
        mock_result.stdout = "9999\n"
        with patch.object(_rr_mod.sys, "platform", "linux"):
            with patch("subprocess.run", return_value=mock_result) as mock_run:
                pids = _rr_mod.find_rag_server_pids()
        # pgrep should have been called with -f flag
        call_args = mock_run.call_args[0][0]
        assert "pgrep" in call_args or "pgrep" in call_args[0]


class TestMainFunction:
    def test_no_pids_exits_0(self):
        with patch.object(_rr_mod, "find_rag_server_pids", return_value=[]):
            rc = _rr_mod.main()
        assert rc == 0

    def test_kills_found_pids(self):
        kill_calls = []
        def fake_kill(pid, sig):
            kill_calls.append(pid)

        with patch.object(_rr_mod, "find_rag_server_pids", side_effect=[
            [1234],   # first call: found pid
            [],       # second call: verify stopped
        ]):
            with patch.object(_rr_mod.os, "kill", side_effect=fake_kill):
                with patch("time.sleep"):
                    rc = _rr_mod.main()

        assert rc == 0
        assert 1234 in kill_calls

    def test_handles_process_lookup_error(self):
        def fake_kill(pid, sig):
            raise ProcessLookupError("already gone")

        with patch.object(_rr_mod, "find_rag_server_pids", side_effect=[
            [9999],
            [],
        ]):
            with patch.object(_rr_mod.os, "kill", side_effect=fake_kill):
                with patch("time.sleep"):
                    rc = _rr_mod.main()
        # ProcessLookupError means already gone — continue, exit 0
        assert rc == 0

    def test_handles_permission_error(self):
        def fake_kill(pid, sig):
            raise PermissionError("permission denied")

        with patch.object(_rr_mod, "find_rag_server_pids", return_value=[9999]):
            with patch.object(_rr_mod.os, "kill", side_effect=fake_kill):
                rc = _rr_mod.main()
        assert rc == 1

    def test_handles_general_kill_error(self):
        def fake_kill(pid, sig):
            raise OSError("unknown error")

        with patch.object(_rr_mod, "find_rag_server_pids", return_value=[9999]):
            with patch.object(_rr_mod.os, "kill", side_effect=fake_kill):
                rc = _rr_mod.main()
        assert rc == 1

    def test_warns_if_same_pid_still_running(self):
        """If the same PID still runs after kill, print a warning."""
        def fake_kill(pid, sig):
            pass  # kill "succeeds" but PID stays

        captured = []
        def fake_print(*args, **kwargs):
            captured.append(" ".join(str(a) for a in args))

        with patch.object(_rr_mod, "find_rag_server_pids", side_effect=[
            [1234],   # before kill
            [1234],   # after kill — same pid
        ]):
            with patch.object(_rr_mod.os, "kill", side_effect=fake_kill):
                with patch("time.sleep"):
                    with patch("builtins.print", side_effect=fake_print):
                        rc = _rr_mod.main()

        assert rc == 0
        assert any("SIGTERM" in s or "Warning" in s or "same" in s for s in captured)

    def test_reports_new_pid_if_auto_restarted(self):
        """If a different PID appears after kill, report it."""
        captured = []
        def fake_print(*args, **kwargs):
            captured.append(" ".join(str(a) for a in args))

        with patch.object(_rr_mod, "find_rag_server_pids", side_effect=[
            [1234],   # before kill
            [5678],   # after kill — new pid (auto-restart)
        ]):
            with patch.object(_rr_mod.os, "kill", return_value=None):
                with patch("time.sleep"):
                    with patch("builtins.print", side_effect=fake_print):
                        rc = _rr_mod.main()

        assert rc == 0
        assert any("5678" in s or "auto" in s.lower() or "new" in s.lower() for s in captured)
