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

from helpers import hook_env

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
LEDGER_HOOK = SCRIPTS_DIR / "session-restore-ledger.py"
RESTORE = SCRIPTS_DIR / "session-restore.py"

SID_A = "aaaaaaaa-1111-2222-3333-444444444444"
SID_B = "bbbbbbbb-1111-2222-3333-444444444444"


def _env(home: Path) -> dict:
    # The profile too, or the scripts read the real ~/.claude transcripts and live sessions.
    return hook_env({"CLAUDEBOOST_HOME": str(home), "USERPROFILE": str(home), "HOME": str(home)})


def run_ledger(home: Path, payload: dict | str) -> subprocess.CompletedProcess:
    """Run the ledger hook in text mode.

    Not helpers.run_hook: these tests feed raw strings (a malformed-JSON case)
    and read str stdout, where the shared helper json-dumps a dict and returns
    bytes. The environment still comes from helpers.hook_env, which is the part
    that must not diverge.
    """
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
        r = run_ledger(home, {"hook_event_name": "SessionStart",
                            "session_id": SID_A, "cwd": str(home / "ProjA")})
        assert r.returncode == 0
        entry = sessions(home)[SID_A]
        assert entry["cwd"] == str(home / "ProjA")
        assert entry["name"]

    def test_session_end_removes_it(self, home):
        run_ledger(home, {"hook_event_name": "SessionStart",
                        "session_id": SID_A, "cwd": str(home / "ProjA")})
        r = run_ledger(home, {"hook_event_name": "SessionEnd",
                            "session_id": SID_A, "cwd": str(home / "ProjA"),
                            "reason": "logout"})
        assert r.returncode == 0
        assert SID_A not in sessions(home)

    def test_a_crash_leaves_the_entry_behind(self, home):
        """The whole point. No SessionEnd means the session was still open."""
        run_ledger(home, {"hook_event_name": "SessionStart",
                        "session_id": SID_B, "cwd": str(home / "Proj B With Spaces")})
        assert SID_B in sessions(home)

    def test_directory_with_spaces_survives(self, home):
        run_ledger(home, {"hook_event_name": "SessionStart",
                        "session_id": SID_B, "cwd": str(home / "Proj B With Spaces")})
        assert sessions(home)[SID_B]["cwd"] == str(home / "Proj B With Spaces")

    def test_resume_keeps_the_original_started_at(self, home):
        run_ledger(home, {"hook_event_name": "SessionStart",
                        "session_id": SID_A, "cwd": str(home / "ProjA")})
        first = sessions(home)[SID_A]["startedAt"]
        time.sleep(0.05)
        run_ledger(home, {"hook_event_name": "SessionStart",
                        "session_id": SID_A, "cwd": str(home / "ProjA")})
        assert sessions(home)[SID_A]["startedAt"] == first

    def test_the_ledger_is_stamped_with_this_machine(self, home):
        run_ledger(home, {"hook_event_name": "SessionStart",
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
        assert run_ledger(home, payload).returncode == 0

    def test_nonexistent_cwd_is_not_recorded(self, home):
        run_ledger(home, {"hook_event_name": "SessionStart", "session_id": "dead",
                        "cwd": str(home / "does-not-exist")})
        assert "dead" not in sessions(home)

    def test_corrupt_ledger_is_replaced_not_fatal(self, home):
        state = home / "state"
        state.mkdir(parents=True, exist_ok=True)
        (state / "session-restore.json").write_text("{ not json", encoding="utf-8")
        r = run_ledger(home, {"hook_event_name": "SessionStart",
                            "session_id": SID_A, "cwd": str(home / "ProjA")})
        assert r.returncode == 0
        assert SID_A in sessions(home)


class TestStaleSweep:
    def test_old_and_missing_entries_are_dropped(self, home):
        run_ledger(home, {"hook_event_name": "SessionStart",
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

        run_ledger(home, {"hook_event_name": "SessionStart",
                        "session_id": SID_B, "cwd": str(home / "Proj B With Spaces")})
        s = sessions(home)
        assert "old-one" not in s, "a 40 day old entry should be swept"
        assert "gone-one" not in s, "an entry whose directory is gone should be swept"
        assert SID_A in s and SID_B in s


class TestRestorePlanning:
    def test_dry_run_opens_nothing(self, home):
        run_ledger(home, {"hook_event_name": "SessionStart",
                        "session_id": SID_B, "cwd": str(home / "Proj B With Spaces")})
        r = run_restore(home, "--dry-run", "--force")
        assert r.returncode == 0
        tabs = home / "state" / "session-restore-tabs"
        assert not tabs.exists() or not list(tabs.glob("*.bat"))

    def test_dry_run_names_the_resume_flag_and_the_directory(self, home):
        run_ledger(home, {"hook_event_name": "SessionStart",
                        "session_id": SID_B, "cwd": str(home / "Proj B With Spaces")})
        r = run_restore(home, "--dry-run", "--force")
        assert f"--resume {SID_B}" in r.stdout
        assert "Proj B With Spaces" in r.stdout

    def test_status_exits_zero_on_an_empty_ledger(self, home):
        r = run_restore(home, "--status")
        assert r.returncode == 0
        assert "session-restore.json" in r.stdout

    def test_another_machines_ledger_is_refused(self, home):
        run_ledger(home, {"hook_event_name": "SessionStart",
                        "session_id": SID_A, "cwd": str(home / "ProjA")})
        p = home / "state" / "session-restore.json"
        d = json.loads(p.read_text(encoding="utf-8"))
        d["machine"] = "SOME-OTHER-PC"
        p.write_text(json.dumps(d), encoding="utf-8")
        r = run_restore(home, "--dry-run", "--force")
        assert "SOME-OTHER-PC" in r.stdout
        assert "Nothing to restore" in r.stdout


class TestEndReasons:
    """A window close or logoff sends reason "other". That is not a deliberate exit."""

    def _start(self, home):
        run_ledger(home, {"hook_event_name": "SessionStart",
                        "session_id": SID_A, "cwd": str(home / "ProjA")})

    def test_other_keeps_the_entry(self, home):
        self._start(home)
        run_ledger(home, {"hook_event_name": "SessionEnd", "session_id": SID_A,
                        "cwd": str(home / "ProjA"), "reason": "other"})
        assert SID_A in sessions(home)

    def test_a_deliberate_exit_removes_it(self, home):
        self._start(home)
        run_ledger(home, {"hook_event_name": "SessionEnd", "session_id": SID_A,
                        "cwd": str(home / "ProjA"), "reason": "prompt_input_exit"})
        assert SID_A not in sessions(home)


@pytest.fixture
def restore_mod(home, monkeypatch):
    """session-restore.py imported against a throwaway home and profile."""
    import importlib.util
    monkeypatch.setenv("CLAUDEBOOST_HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("HOME", str(home))
    sys.path.insert(0, str(SCRIPTS_DIR))
    spec = importlib.util.spec_from_file_location("session_restore_under_test", RESTORE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    import session_restore_state
    monkeypatch.setattr(session_restore_state, "BOOST_HOME", home)
    return mod


class TestStartupHardening:
    def test_already_open_matches_session_id_not_directory(self, restore_mod, monkeypatch, home):
        monkeypatch.setattr(restore_mod, "live_sessions", lambda: [
            {"sessionId": SID_A, "cwd": str(home / "ProjA"), "name": "a"}])
        assert restore_mod._already_open(SID_A)
        assert not restore_mod._already_open(SID_B)

    def test_force_still_skips_a_live_session(self, restore_mod, monkeypatch, home):
        monkeypatch.setattr(restore_mod, "live_sessions", lambda: [
            {"sessionId": SID_A, "cwd": str(home / "ProjA"), "name": "a"}])
        for sid in (SID_A, SID_B):
            run_ledger(home, {"hook_event_name": "SessionStart",
                            "session_id": sid, "cwd": str(home / "ProjA")})
        keep, _ = restore_mod._plan(force=True)
        assert [e["sessionId"] for e in keep] == [SID_B]

    @staticmethod
    def _project_dir(restore_mod, home, cwd):
        d = home / ".claude" / "projects" / restore_mod.re.sub(r"[^A-Za-z0-9]", "-", cwd)
        d.mkdir(parents=True, exist_ok=True)
        return d

    def test_a_lost_transcript_is_not_resumable_even_with_others_present(self, restore_mod, home):
        proj = self._project_dir(restore_mod, home, str(home / "ProjA"))
        assert not restore_mod._resumable(str(home / "ProjA"), SID_A)
        (proj / "other.jsonl").write_text("{}", encoding="utf-8")
        assert not restore_mod._resumable(str(home / "ProjA"), SID_A)

    def test_a_transcript_under_a_hashed_directory_is_found(self, restore_mod, home):
        (home / "ProjA").mkdir(exist_ok=True)
        hashed = self._project_dir(restore_mod, home, "C--very-long-path-abc123")
        (hashed / f"{SID_A}.jsonl").write_text("{}", encoding="utf-8")
        assert restore_mod._transcript_exists(str(home / "ProjA"), SID_A) is True
        assert restore_mod._transcript_exists(str(home / "ProjA"), SID_B) is False

    def test_lost_transcript_beside_a_live_session_is_skipped_not_continued(
            self, restore_mod, monkeypatch, home):
        """--continue there would resume the live session's transcript as a second process."""
        cwd = str(home / "ProjA")
        (self._project_dir(restore_mod, home, cwd) / f"{SID_A}.jsonl").write_text("{}")
        monkeypatch.setattr(restore_mod, "live_sessions", lambda: [
            {"sessionId": SID_A, "cwd": cwd, "name": "a"}])
        for sid in (SID_A, SID_B):
            run_ledger(home, {"hook_event_name": "SessionStart", "session_id": sid, "cwd": cwd})
        keep, notes = restore_mod._plan(force=True)
        assert keep == []
        assert any("no transcript" in n for n in notes)
        assert "--continue" not in restore_mod._resume_args({"sessionId": SID_B, "cwd": cwd})

    def test_an_unrelated_new_session_in_the_same_dir_does_not_count_as_started(
            self, restore_mod, monkeypatch, home):
        cwd = str(home / "ProjA")
        monkeypatch.setattr(restore_mod, "live_sessions", lambda: [
            {"sessionId": "someone-else", "cwd": cwd, "name": "x"}])
        a = {"sessionId": SID_A, "cwd": cwd}
        b = {"sessionId": SID_B, "cwd": cwd}
        assert restore_mod._wait_started([a, b], 0) == [a, b]

    def test_a_semicolon_in_a_name_or_dir_cannot_split_the_wt_command(
            self, restore_mod, monkeypatch, home):
        calls = []
        monkeypatch.setattr(restore_mod.subprocess, "Popen",
                            lambda argv, **kw: calls.append(argv))
        items = [({"cwd": str(home / "a;b"), "name": "x; new-tab calc"}, Path("a.bat")),
                 ({"cwd": str(home / "ProjA"), "name": "y"}, Path("b.bat"))]
        restore_mod._launch_wt_batch("wt.exe", items)
        argv = calls[0]
        assert argv.count(";") == 1
        assert not [a for a in argv if a != ";" and ";" in a]
        assert str(home / "ProjA") in argv

    @staticmethod
    def _run_tab(restore_mod, home, name, cwd, stub_dir=None, remove_cwd=False, **extra):
        """Run the tab script under real cmd with a stub claude that records where it ran.

        where is None when the stub never ran.
        """
        stub_dir = stub_dir or home
        stub_dir.mkdir(exist_ok=True)
        stub = stub_dir / "stub-claude.cmd"
        stub.write_text('@cd > "%~dp0where.txt"\r\n@echo STUB %*\r\n', encoding="utf-8")
        cwd.mkdir(exist_ok=True)
        script = restore_mod._write_tab_script(
            0, {"cwd": str(cwd), "name": name, "sessionId": SID_A, **extra}, str(stub))
        if remove_cwd:
            cwd.rmdir()
        r = subprocess.run(["cmd", "/c", str(script)], capture_output=True, cwd=str(home))
        marker = stub_dir / "where.txt"
        where = marker.read_text(encoding="utf-8").strip() if marker.exists() else None
        return (r.stdout + r.stderr).decode("utf-8", "replace"), where

    @pytest.mark.skipif(sys.platform != "win32", reason="runs the tab script under cmd")
    def test_a_folder_gone_at_launch_stops_the_tab_instead_of_running_elsewhere(
            self, restore_mod, home):
        out, where = self._run_tab(restore_mod, home, "t", home / "gone;dir", remove_cwd=True)
        assert where is None, f"claude ran in {where}"
        assert "Folder not found" in out

    @pytest.mark.skipif(sys.platform != "win32", reason="runs the tab script under cmd")
    @pytest.mark.parametrize("flags", [
        ["--add-dir", "x&echo INJECTED"], ["--settings", "a>leak.txt"], ["--add-dir", "%COMSPEC%"],
    ])
    def test_ledger_launch_flags_never_reach_the_command_line(self, restore_mod, home, flags):
        out, _ = self._run_tab(restore_mod, home, "t", home / "ProjA", launchFlags=flags)
        assert "INJECTED" not in out
        assert not list(home.rglob("leak.txt"))
        assert f"STUB --resume {SID_A}\r\n" in out

    @pytest.mark.skipif(sys.platform != "win32", reason="runs the tab script under cmd")
    @pytest.mark.parametrize("folder", ["p%COMSPEC%q", "p^q", "a&b ^c%x%"])
    def test_a_claude_shim_in_an_awkward_folder_still_runs(self, restore_mod, home, folder):
        _, where = self._run_tab(restore_mod, home, "t", home / "ProjA", stub_dir=home / folder)
        assert where == str(home / "ProjA")

    def test_a_session_id_that_is_not_a_uuid_is_skipped(self, restore_mod, monkeypatch, home):
        monkeypatch.setattr(restore_mod, "live_sessions", lambda: [])
        for sid in ("x&echo INJECTED", SID_A):
            run_ledger(home, {"hook_event_name": "SessionStart",
                              "session_id": sid, "cwd": str(home / "ProjA")})
        keep, notes = restore_mod._plan(force=True)
        assert [e["sessionId"] for e in keep] == [SID_A]
        assert any("not a UUID" in n for n in notes)

    def test_an_uppercase_ledger_id_still_matches_a_live_session(self, restore_mod, monkeypatch, home):
        monkeypatch.setattr(restore_mod, "live_sessions",
                            lambda: [{"sessionId": SID_A.lower(), "cwd": str(home / "ProjA")}])
        assert restore_mod._already_open(SID_A.upper())

    def test_an_uppercase_live_id_still_matches_a_ledger_id(self, restore_mod, monkeypatch, home):
        monkeypatch.setattr(restore_mod, "live_sessions",
                            lambda: [{"sessionId": SID_A.upper(), "cwd": str(home / "ProjA")}])
        assert restore_mod._already_open(SID_A)

    @pytest.mark.parametrize("live_id,ledger_id", [(SID_A, SID_A.upper()), (SID_A.upper(), SID_A)])
    def test_a_started_session_counts_whatever_case_its_id_is_in(
            self, restore_mod, monkeypatch, home, live_id, ledger_id):
        monkeypatch.setattr(restore_mod, "live_sessions",
                            lambda: [{"sessionId": live_id, "cwd": str(home / "ProjA")}])
        assert restore_mod._wait_started([{"sessionId": ledger_id}], 0) == []

    def test_ids_differing_only_in_case_open_one_tab(self, restore_mod, monkeypatch, home):
        monkeypatch.setattr(restore_mod, "live_sessions", lambda: [])
        for sid in (SID_A.upper(), SID_A):
            run_ledger(home, {"hook_event_name": "SessionStart",
                              "session_id": sid, "cwd": str(home / "ProjA")})
        keep, _ = restore_mod._plan(force=True)
        assert len(keep) == 1

    def test_a_uuid_with_trailing_text_is_skipped(self, restore_mod, monkeypatch, home):
        monkeypatch.setattr(restore_mod, "live_sessions", lambda: [])
        run_ledger(home, {"hook_event_name": "SessionStart",
                          "session_id": f"{SID_A} & calc", "cwd": str(home / "ProjA")})
        keep, notes = restore_mod._plan(force=True)
        assert keep == []
        assert any("not a UUID" in n for n in notes)

    @pytest.mark.parametrize("cwd", ['C:\\a"b', "C:\\a\r\nb", "C:\\a\x1fb"])
    def test_a_directory_with_quote_or_control_characters_is_skipped(self, restore_mod, monkeypatch, cwd):
        entry = {"sessionId": SID_A, "cwd": cwd, "name": "n", "lastSeenEpoch": time.time()}
        ledger = {"sessions": {"s": entry}}
        monkeypatch.setattr(restore_mod, "read_ledger", lambda: ledger)
        monkeypatch.setattr(restore_mod, "prune_stale", lambda data: 0)
        keep, notes = restore_mod._plan(force=True)
        assert keep == []
        assert any("unsafe characters" in n for n in notes)

    @pytest.mark.skipif(sys.platform != "win32", reason="runs the tab script under cmd")
    @pytest.mark.parametrize("name", [
        "a | echo INJECTED", "a\r\necho INJECTED", "a & echo INJECTED",
        "a > leak.txt", "a < nul", "x %COMSPEC% ^", 'q" & echo INJECTED',
    ])
    def test_a_session_name_cannot_run_or_redirect_anything(self, restore_mod, home, name):
        out, where = self._run_tab(restore_mod, home, name, home / "ProjA")
        assert "INJECTED" not in out
        assert not list(home.rglob("leak.txt"))
        assert f"STUB --resume {SID_A}" in out
        assert where == str(home / "ProjA")

    @pytest.mark.skipif(sys.platform != "win32", reason="runs the tab script under cmd")
    @pytest.mark.parametrize("folder", ["café 中", "x%COMSPEC%y", "a&b ^c"])
    def test_the_tab_opens_in_its_own_folder_whatever_it_is_named(
            self, restore_mod, home, folder):
        _, where = self._run_tab(restore_mod, home, "t", home / folder)
        assert where == str(home / folder)

    def test_retry_skips_a_session_that_came_up_after_the_last_poll(
            self, restore_mod, monkeypatch, home):
        cwd = str(home / "ProjA")
        live: list[dict] = []
        monkeypatch.setattr(restore_mod, "live_sessions", lambda: list(live))
        run_ledger(home, {"hook_event_name": "SessionStart", "session_id": SID_A, "cwd": cwd})
        monkeypatch.setattr(restore_mod, "find_claude", lambda: "claude.exe")
        monkeypatch.setattr(restore_mod, "find_terminal", lambda: ("wt", "wt.exe"))
        monkeypatch.setattr(restore_mod, "boot_id", lambda: "boot-1")
        monkeypatch.setattr(restore_mod, "START_WAIT_SECONDS", 0)
        monkeypatch.setattr(restore_mod, "_launch_wt_batch", lambda *a: None)
        relaunched = []
        monkeypatch.setattr(restore_mod, "_launch", lambda e, *a, **k: relaunched.append(e))
        real_wait = restore_mod._wait_started

        def wait_then_register(entries, *rest):
            pending = real_wait(entries, *rest)
            live.append({"sessionId": SID_A, "cwd": cwd, "name": "a"})
            return pending

        monkeypatch.setattr(restore_mod, "_wait_started", wait_then_register)
        restore_mod.restore(force=True, dry_run=False)
        assert relaunched == []

    def test_wt_opens_every_tab_in_one_call(self, restore_mod, monkeypatch, home):
        calls = []
        monkeypatch.setattr(restore_mod.subprocess, "Popen",
                            lambda argv, **kw: calls.append(argv))
        items = [({"cwd": str(home / "ProjA"), "name": "a"}, Path("a.bat")),
                 ({"cwd": str(home / "Proj B With Spaces"), "name": "b"}, Path("b.bat"))]
        restore_mod._launch_wt_batch("wt.exe", items)
        assert len(calls) == 1
        assert calls[0].count("new-tab") == 2 and calls[0].count(";") == 1

    def test_wait_started_reports_the_session_that_never_came_up(self, restore_mod, monkeypatch, home):
        monkeypatch.setattr(restore_mod, "live_sessions", lambda: [
            {"sessionId": SID_A, "cwd": str(home / "ProjA"), "name": "a"}])
        up = {"sessionId": SID_A, "cwd": str(home / "ProjA")}
        down = {"sessionId": SID_B, "cwd": str(home / "ProjA")}
        assert restore_mod._wait_started([up, down], 0) == [down]


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
