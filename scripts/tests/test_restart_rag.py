"""
Tests for scripts/restart-rag.py (CLI utility).

Finds and kills rag_server processes. When no server is running, reports
"not running" and exits 0.
"""
from __future__ import annotations

import ast
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
    """These used to run restart-rag.py for real. They must not.

    The two removed tests called `run_script("restart-rag.py")` with no mocking
    at all. That runs the real script, which runs a real WMI query and then
    `os.kill(pid, SIGTERM)` on every match. On Windows os.kill with SIGTERM is
    TerminateProcess: immediate, no cleanup, no way to decline.

    The match is a substring test against the whole command line:

        $_.CommandLine -like '*rag_server*' -and $_.Name -like 'python*'

    Nothing matches that today, because the server runs
    clean-rag/server/__main__.py. The old comment, "On a clean test machine (or
    where rag_server is not running), should exit 0", is the whole problem: the
    test's safety was an assumption about the machine, checked nowhere, and any
    python process that ever gets `rag_server` into its command line turns a
    test run into a kill.

    Every branch of main() is already covered in TestMainFunction with
    find_rag_server_pids and os.kill patched, so running the real thing was
    buying no coverage in exchange for that.
    """

    def test_exits_0_when_nothing_matches(self):
        """What the removed end to end tests were actually asserting."""
        with patch.object(_rr_mod, "find_rag_server_pids", return_value=[]):
            assert _rr_mod.main() == 0

    def test_says_the_server_is_not_running(self):
        captured = []
        with patch.object(_rr_mod, "find_rag_server_pids", return_value=[]):
            with patch("builtins.print", side_effect=lambda *a, **k: captured.append(" ".join(str(x) for x in a))):
                assert _rr_mod.main() == 0
        joined = " ".join(captured).lower()
        assert "not running" in joined or "no rag_server" in joined, captured

    def test_the_suite_never_executes_the_real_killer(self):
        """Self policing, so the removed pattern cannot come back quietly.

        Parses this file and fails if anything calls run_script on
        restart-rag.py again. A comment saying "do not do this" does not
        survive a future edit; a failing test does.

        AST rather than a text scan, because a text scan matches its own
        docstring and its own detection line. It did, first time.
        """
        tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
        offenders = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
            if name not in ("run_script", "run_hook"):
                continue
            for arg in node.args:
                if isinstance(arg, ast.Constant) and "restart-rag.py" in str(arg.value):
                    offenders.append(f"line {node.lineno}: {name}({arg.value!r})")

        assert not offenders, (
            "restart-rag.py sends SIGTERM to every process matching "
            "'*rag_server*'. Patch find_rag_server_pids and call main() "
            f"directly instead. Offending calls: {offenders}"
        )


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
