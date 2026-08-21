"""
Tests for the session restore pair:
  scripts/session-restore-ledger.py   SessionStart / SessionEnd hook
  scripts/session-restore.py          reopens the tabs
  scripts/session_restore_state.py    shared ledger and probes

Every test points CLAUDEBOOST_HOME at a tmp_path, so none of them read or write
the real state/ directory or open a terminal window.

The headless class is the regression guard for a bug that shipped once: the
scheduled task runs under pythonw.exe, which has no stdout, and reading
sys.stdout.isatty() there raised at import. The script died before it could log
anything, so the login restore silently did nothing and the only trace was a
Last Result of 1 in Task Scheduler.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
LEDGER_HOOK = SCRIPTS_DIR / "session-restore-ledger.py"
RESTORE = SCRIPTS_DIR / "session-restore.py"

SID_A = "aaaaaaaa-1111-2222-3333-444444444444"
SID_B = "bbbbbbbb-1111-2222-3333-444444444444"


def _env(home: Path) -> dict:
    return {**os.environ, "CLAUDEBOOST_HOME": str(home)}


def run_hook(home: Path, payload: dict | str) -> subprocess.CompletedProcess:
    raw = payload if isinstance(payload, str) else json.dumps(payload)
    return subprocess.run([sys.executable, str(LEDGER_HOOK)], input=raw, text=True,
                          capture_output=True, env=_env(home), timeout=120)


def run_restore(home: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(RESTORE), *args], text=True,
                          capture_output=True, env=_env(home), timeout=180)


def ledger(home: Path) -> dict:
    p = home / "state" / "session-restore.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def sessions(home: Path) -> dict:
    return ledger(home).get("sessions") or {}


@pytest.fixture
def home(tmp_path):
    """A throwaway CLAUDEBOOST_HOME with the scripts and two project dirs."""
    (tmp_path / "scripts").mkdir()
    (tmp_path / "ProjA").mkdir()
    (tmp_path / "Proj B With Spaces").mkdir()
    return tmp_path


class TestLedgerRoundTrip:
    def test_session_start_records_the_session(self, home):
        r = run_hook(home, {"hook_event_name": "SessionStart",
                            "session_id": SID_A, "cwd": str(home / "ProjA")})
        assert r.returncode == 0
        entry = sessions(home)[SID_A]
        assert entry["cwd"] == str(home / "ProjA")
        assert entry["name"]

    def test_session_end_removes_it(self, home):
        run_hook(home, {"hook_event_name": "SessionStart",
                        "session_id": SID_A, "cwd": str(home / "ProjA")})
        r = run_hook(home, {"hook_event_name": "SessionEnd",
                            "session_id": SID_A, "cwd": str(home / "ProjA"),
                            "reason": "logout"})
        assert r.returncode == 0
        assert SID_A not in sessions(home)

    def test_a_crash_leaves_the_entry_behind(self, home):
        """The whole point. No SessionEnd means the session was still open."""
        run_hook(home, {"hook_event_name": "SessionStart",
                        "session_id": SID_B, "cwd": str(home / "Proj B With Spaces")})
        assert SID_B in sessions(home)

    def test_directory_with_spaces_survives(self, home):
        run_hook(home, {"hook_event_name": "SessionStart",
                        "session_id": SID_B, "cwd": str(home / "Proj B With Spaces")})
        assert sessions(home)[SID_B]["cwd"] == str(home / "Proj B With Spaces")

    def test_resume_keeps_the_original_started_at(self, home):
        run_hook(home, {"hook_event_name": "SessionStart",
                        "session_id": SID_A, "cwd": str(home / "ProjA")})
        first = sessions(home)[SID_A]["startedAt"]
        time.sleep(0.05)
        run_hook(home, {"hook_event_name": "SessionStart",
                        "session_id": SID_A, "cwd": str(home / "ProjA")})
        assert sessions(home)[SID_A]["startedAt"] == first

    def test_the_ledger_is_stamped_with_this_machine(self, home):
        run_hook(home, {"hook_event_name": "SessionStart",
                        "session_id": SID_A, "cwd": str(home / "ProjA")})
        assert ledger(home)["machine"]


class TestConcurrency:
    def test_six_simultaneous_starts_all_land(self, home):
        """The advisory lock exists for this. Six sessions opening at once must
        not lose entries to a read then write race."""
        procs = []
        for i in range(6):
            p = subprocess.Popen([sys.executable, str(LEDGER_HOOK)],
                                 stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL, text=True, env=_env(home))
            p.stdin.write(json.dumps({
                "hook_event_name": "SessionStart",
                "session_id": f"cccccccc-{i:04d}-2222-3333-444444444444",
                "cwd": str(home / "ProjA"),
            }))
            p.stdin.close()
            procs.append(p)
        for p in procs:
            p.wait(timeout=180)
        assert len([s for s in sessions(home) if s.startswith("cccccccc-")]) == 6


class TestBadInputNeverBreaksASession:
    """A restore ledger is a convenience. It must never interfere with the
    session the user is actually in, so every path exits 0."""

    @pytest.mark.parametrize("payload", [
        {},
        {"hook_event_name": "SessionStart"},
        {"hook_event_name": "SessionStart", "cwd": "/nope"},
        {"hook_event_name": "Nonsense", "session_id": "x", "cwd": "/tmp"},
        {"hook_event_name": "SessionEnd"},
        "this is not json",
        "",
    ])
    def test_exits_zero(self, home, payload):
        assert run_hook(home, payload).returncode == 0

    def test_nonexistent_cwd_is_not_recorded(self, home):
        run_hook(home, {"hook_event_name": "SessionStart", "session_id": "dead",
                        "cwd": str(home / "does-not-exist")})
        assert "dead" not in sessions(home)

    def test_corrupt_ledger_is_replaced_not_fatal(self, home):
        state = home / "state"
        state.mkdir(parents=True, exist_ok=True)
        (state / "session-restore.json").write_text("{ not json", encoding="utf-8")
        r = run_hook(home, {"hook_event_name": "SessionStart",
                            "session_id": SID_A, "cwd": str(home / "ProjA")})
        assert r.returncode == 0
        assert SID_A in sessions(home)


class TestStaleSweep:
    def test_old_and_missing_entries_are_dropped(self, home):
        run_hook(home, {"hook_event_name": "SessionStart",
                        "session_id": SID_A, "cwd": str(home / "ProjA")})
        p = home / "state" / "session-restore.json"
        d = json.loads(p.read_text(encoding="utf-8"))
        d["sessions"]["old-one"] = {
            "sessionId": "old-one", "cwd": str(home / "ProjA"), "name": "ancient",
            "lastSeenEpoch": time.time() - (40 * 86400),
        }
        d["sessions"]["gone-one"] = {
            "sessionId": "gone-one", "cwd": str(home / "deleted"), "name": "deleted",
            "lastSeenEpoch": time.time(),
        }
        p.write_text(json.dumps(d), encoding="utf-8")

        run_hook(home, {"hook_event_name": "SessionStart",
                        "session_id": SID_B, "cwd": str(home / "Proj B With Spaces")})
        s = sessions(home)
        assert "old-one" not in s, "a 40 day old entry should be swept"
        assert "gone-one" not in s, "an entry whose directory is gone should be swept"
        assert SID_A in s and SID_B in s


class TestRestorePlanning:
    def test_dry_run_opens_nothing(self, home):
        run_hook(home, {"hook_event_name": "SessionStart",
                        "session_id": SID_B, "cwd": str(home / "Proj B With Spaces")})
        r = run_restore(home, "--dry-run", "--force")
        assert r.returncode == 0
        tabs = home / "state" / "session-restore-tabs"
        assert not tabs.exists() or not list(tabs.glob("*.bat"))

    def test_dry_run_names_the_resume_flag_and_the_directory(self, home):
        run_hook(home, {"hook_event_name": "SessionStart",
                        "session_id": SID_B, "cwd": str(home / "Proj B With Spaces")})
        r = run_restore(home, "--dry-run", "--force")
        assert "--resume" in r.stdout or "--continue" in r.stdout
        assert "Proj B With Spaces" in r.stdout

    def test_status_exits_zero_on_an_empty_ledger(self, home):
        r = run_restore(home, "--status")
        assert r.returncode == 0
        assert "session-restore.json" in r.stdout

    def test_another_machines_ledger_is_refused(self, home):
        run_hook(home, {"hook_event_name": "SessionStart",
                        "session_id": SID_A, "cwd": str(home / "ProjA")})
        p = home / "state" / "session-restore.json"
        d = json.loads(p.read_text(encoding="utf-8"))
        d["machine"] = "SOME-OTHER-PC"
        p.write_text(json.dumps(d), encoding="utf-8")
        r = run_restore(home, "--dry-run", "--force")
        assert "SOME-OTHER-PC" in r.stdout
        assert "Nothing to restore" in r.stdout


@pytest.mark.skipif(os.name != "nt", reason="pythonw.exe is Windows only")
class TestHeadless:
    """Regression guard for the pythonw.exe bug. See the module docstring."""

    @staticmethod
    def _pythonw() -> Path:
        return Path(sys.executable).with_name("pythonw.exe")

    @pytest.mark.parametrize("args", [["--status"], ["--dry-run"], ["--from-task"]])
    def test_runs_with_no_console(self, home, args):
        pythonw = self._pythonw()
        if not pythonw.is_file():
            pytest.skip("pythonw.exe not present in this interpreter's directory")
        r = subprocess.run([str(pythonw), str(RESTORE), *args],
                           capture_output=True, text=True, env=_env(home), timeout=180)
        assert r.returncode == 0, f"exited {r.returncode} with no console"

    def test_from_task_still_writes_the_log_with_no_stdout(self, home):
        pythonw = self._pythonw()
        if not pythonw.is_file():
            pytest.skip("pythonw.exe not present in this interpreter's directory")
        subprocess.run([str(pythonw), str(RESTORE), "--from-task"],
                       capture_output=True, text=True, env=_env(home), timeout=180)
        log = home / "state" / "session-restore.log"
        assert log.exists(), "a headless run must still leave a trace in the log"
        assert "scheduled task fired" in log.read_text(encoding="utf-8")

    def test_hook_runs_with_no_console_and_no_stdin(self, home):
        pythonw = self._pythonw()
        if not pythonw.is_file():
            pytest.skip("pythonw.exe not present in this interpreter's directory")
        r = subprocess.run([str(pythonw), str(LEDGER_HOOK)], stdin=subprocess.DEVNULL,
                           capture_output=True, text=True, env=_env(home), timeout=120)
        assert r.returncode == 0


class TestStateHelpers:
    @pytest.fixture(autouse=True)
    def _import(self):
        sys.path.insert(0, str(SCRIPTS_DIR))
        import session_restore_state as srs
        self.srs = srs

    def test_pid_alive_on_this_process(self):
        assert self.srs.pid_alive(os.getpid()) is True

    @pytest.mark.parametrize("pid", [0, -1, 4294967])
    def test_pid_alive_false_for_bogus_pids(self, pid):
        assert self.srs.pid_alive(pid) is False

    def test_boot_id_is_stable_within_a_run(self):
        assert self.srs.boot_id() == self.srs.boot_id()

    def test_machine_key_is_not_empty(self):
        assert self.srs.machine_key()

    def test_needs_call_only_for_batch_shims(self):
        assert self.srs.needs_call(r"C:\x\claude.CMD") is True
        assert self.srs.needs_call(r"C:\x\claude.bat") is True
        assert self.srs.needs_call(r"C:\x\claude.exe") is False
        assert self.srs.needs_call("/usr/bin/claude") is False

    def test_live_sessions_never_raises(self):
        """It reads an internal, undocumented Claude Code directory, so it has
        to degrade to an empty list rather than throw."""
        assert isinstance(self.srs.live_sessions(), list)


@pytest.mark.skipif(os.name != "nt", reason="process start times are read via Win32 here")
class TestProcessIdentity:
    """A live pid is not proof it is the same process.

    Windows reuses pids, and reassigns them from scratch after a reboot. A
    stale ~/.claude/sessions file naming a recycled pid would otherwise look
    like a live session, and restore would skip that directory and silently
    lose it. procStart is what pins a pid to one process.
    """

    @pytest.fixture(autouse=True)
    def _import(self):
        sys.path.insert(0, str(SCRIPTS_DIR))
        import session_restore_state as srs
        self.srs = srs
        self.pid = os.getpid()
        self.start = srs.proc_start_filetime(self.pid)

    def test_own_start_time_is_readable(self):
        assert self.start is not None and self.start > 0

    def test_own_pid_with_its_real_start_is_accepted(self):
        assert self.srs._same_process(self.pid, self.start) is True

    @pytest.mark.parametrize("offset,label", [
        (36_000_000_000, "an hour"),
        (100_000_000, "ten seconds"),
        (30_000_000, "three seconds"),
    ])
    def test_a_recycled_pid_is_rejected(self, offset, label):
        assert self.srs._same_process(self.pid, self.start - offset) is False, \
            f"a start time {label} off should not pass as the same process"

    def test_small_drift_is_tolerated(self):
        """One second of rounding must not reject a genuinely live session,
        because that would make restore open a duplicate tab."""
        assert self.srs._same_process(self.pid, self.start - 10_000_000) is True

    @pytest.mark.parametrize("recorded", [None, "", "not-a-number", []])
    def test_unverifiable_degrades_to_assuming_same(self, recorded):
        """Cannot tell means assume it is live. A wrong 'dead' costs a duplicate
        tab, a wrong 'live' loses a session, so this errs toward the cheaper
        mistake."""
        assert self.srs._same_process(self.pid, recorded) is True

    def test_start_time_of_a_dead_pid_is_none(self):
        assert self.srs.proc_start_filetime(4294967) is None

    def test_recorded_procstart_matches_the_kernel_for_real_sessions(self):
        """Guards the assumption the whole check rests on: that Claude Code's
        procStart is the same Win32 FILETIME this code reads back."""
        registry = Path.home() / ".claude" / "sessions"
        if not registry.is_dir():
            pytest.skip("no Claude Code session registry on this machine")

        compared = 0
        for f in registry.glob("*.json"):
            try:
                s = json.loads(f.read_text(encoding="utf-8-sig"))
            except Exception:
                continue
            pid, recorded = int(s.get("pid") or 0), s.get("procStart")
            if not pid or not recorded or not self.srs.pid_alive(pid):
                continue
            actual = self.srs.proc_start_filetime(pid)
            if actual is None:
                continue
            assert abs(actual - int(recorded)) <= 20_000_000, (
                f"pid {pid}: recorded {recorded} vs kernel {actual}. If this drifts, "
                "restore starts rejecting live sessions and opening duplicates."
            )
            compared += 1

        if compared == 0:
            pytest.skip("no live Claude session with a procStart to compare")
