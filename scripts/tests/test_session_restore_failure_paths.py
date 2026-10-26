"""Session restore failure paths: tab retry, boot guard, SessionEnd with a twin process."""
from __future__ import annotations

import json
import os

from test_session_restore import (  # noqa: F401
    SID_A, home, restore_mod, run_ledger, sessions,
)


def _registry(home, *pairs):
    d = home / ".claude" / "sessions"
    d.mkdir(parents=True, exist_ok=True)
    for name, sid in pairs:
        (d / f"{name}.json").write_text(json.dumps({
            "pid": os.getpid(), "sessionId": sid, "cwd": str(home / "ProjA"),
            "kind": "interactive", "name": "n"}), encoding="utf-8")


class TestEndWhileAnotherProcessRunsTheId:
    def _start(self, home):
        run_ledger(home, {"hook_event_name": "SessionStart",
                          "session_id": SID_A, "cwd": str(home / "ProjA")})

    def _end(self, home):
        run_ledger(home, {"hook_event_name": "SessionEnd", "session_id": SID_A,
                          "cwd": str(home / "ProjA"), "reason": "prompt_input_exit"})

    def test_two_live_processes_keep_the_entry(self, home):
        self._start(home)
        _registry(home, ("1", SID_A), ("2", SID_A))
        self._end(home)
        assert SID_A in sessions(home)

    def test_a_twin_whose_id_differs_in_case_keeps_the_entry(self, home):
        self._start(home)
        _registry(home, ("1", SID_A), ("2", SID_A.upper()))
        self._end(home)
        assert SID_A in sessions(home)

    def test_one_live_process_still_removes_it(self, home):
        self._start(home)
        _registry(home, ("1", SID_A))
        self._end(home)
        assert SID_A not in sessions(home)

    def test_an_end_with_an_uppercase_id_removes_the_lowercase_entry(self, home):
        self._start(home)
        _registry(home, ("1", SID_A))
        run_ledger(home, {"hook_event_name": "SessionEnd", "session_id": SID_A.upper(),
                          "cwd": str(home / "ProjA"), "reason": "prompt_input_exit"})
        assert sessions(home) == {}

    def test_seed_replaces_a_case_twin_and_keeps_its_start_time(self, home):
        self._start(home)
        started = sessions(home)[SID_A]["startedAt"]
        _registry(home, ("1", SID_A.upper()))
        from test_session_restore import run_restore
        run_restore(home, "--seed")
        got = sessions(home)
        assert list(got) == [SID_A.upper()]
        assert got[SID_A.upper()]["startedAt"] == started

    def test_a_corrupt_entry_under_the_same_id_is_replaced(self, home):
        p = home / "state" / "session-restore.json"
        p.parent.mkdir(exist_ok=True)
        p.write_text(json.dumps({"version": 1, "sessions": {SID_A: "junk"}}), encoding="utf-8")
        self._start(home)
        assert isinstance(sessions(home)[SID_A], dict)

    def test_an_end_without_a_usable_id_removes_nothing(self, home):
        self._start(home)
        _registry(home, ("1", SID_A))
        run_ledger(home, {"hook_event_name": "SessionEnd", "session_id": ["x"],
                          "cwd": str(home / "ProjA"), "reason": "prompt_input_exit"})
        assert SID_A in sessions(home)

    def test_an_end_with_a_blank_id_removes_nothing(self, home):
        self._start(home)
        _registry(home, ("1", SID_A))
        for blank in ("   ", "\t\n"):
            run_ledger(home, {"hook_event_name": "SessionEnd", "session_id": blank,
                              "cwd": str(home / "ProjA"), "reason": "prompt_input_exit"})
            assert SID_A in sessions(home)

    def test_a_blank_session_id_does_not_hide_a_valid_camelcase_id(self, home):
        self._start(home)
        _registry(home, ("1", SID_A))
        run_ledger(home, {"hook_event_name": "SessionEnd", "session_id": "  ",
                          "sessionId": SID_A, "cwd": str(home / "ProjA"),
                          "reason": "prompt_input_exit"})
        assert sessions(home) == {}

    def test_an_end_with_only_the_camelcase_id_removes_the_entry(self, home):
        self._start(home)
        _registry(home, ("1", SID_A))
        run_ledger(home, {"hook_event_name": "SessionEnd", "sessionId": SID_A,
                          "cwd": str(home / "ProjA"), "reason": "prompt_input_exit"})
        assert sessions(home) == {}

    def test_a_start_with_an_uppercase_id_and_no_cwd_finds_the_live_cwd(self, home):
        _registry(home, ("1", SID_A))
        run_ledger(home, {"hook_event_name": "SessionStart", "session_id": SID_A.upper()})
        assert sessions(home)[SID_A.upper()]["cwd"] == str(home / "ProjA")

    def test_a_non_string_session_id_is_not_recorded(self, home):
        run_ledger(home, {"hook_event_name": "SessionStart",
                          "session_id": ["x"], "cwd": str(home / "ProjA")})
        assert sessions(home) == {}

    def test_a_start_in_another_case_replaces_instead_of_adding(self, home):
        self._start(home)
        run_ledger(home, {"hook_event_name": "SessionStart",
                          "session_id": SID_A.upper(), "cwd": str(home / "ProjA")})
        assert len(sessions(home)) == 1


class TestRetryAndBootGuard:
    @staticmethod
    def _arm(restore_mod, monkeypatch, home, live_fn, sid=SID_A):
        run_ledger(home, {"hook_event_name": "SessionStart",
                          "session_id": sid, "cwd": str(home / "ProjA")})
        monkeypatch.setattr(restore_mod, "live_sessions", live_fn)
        monkeypatch.setattr(restore_mod, "find_claude", lambda: "claude.exe")
        monkeypatch.setattr(restore_mod, "find_terminal", lambda: ("wt", "wt.exe"))
        monkeypatch.setattr(restore_mod, "boot_id", lambda: "boot-1")
        monkeypatch.setattr(restore_mod, "START_WAIT_SECONDS", 0)
        batches, relaunched = [], []
        monkeypatch.setattr(restore_mod, "_launch_wt_batch", lambda *a: batches.append(a))
        monkeypatch.setattr(restore_mod, "_launch", lambda e, *a, **k: relaunched.append(e))
        return batches, relaunched

    @staticmethod
    def _last_boot(home):
        data = json.loads((home / "state" / "session-restore.json").read_text(encoding="utf-8"))
        return (data.get("lastRestore") or {}).get("bootId")

    def test_a_tab_that_never_registers_is_retried_and_leaves_the_guard_open(
            self, restore_mod, monkeypatch, home):
        batches, relaunched = self._arm(restore_mod, monkeypatch, home, lambda: [])
        restore_mod.restore(force=False, dry_run=False)
        assert [e["sessionId"] for e in relaunched] == [SID_A]
        assert self._last_boot(home) is None
        restore_mod.restore(force=False, dry_run=False)
        assert len(batches) == 2, "a plain re-run after a failure must not be blocked"

    def test_a_clean_run_closes_the_guard(self, restore_mod, monkeypatch, home):
        live = [{"sessionId": SID_A, "cwd": str(home / "ProjA"), "name": "a"}]
        calls = []

        def lives():
            calls.append(1)
            return [] if len(calls) == 1 else live  # absent when planned, up after launch

        batches, relaunched = self._arm(restore_mod, monkeypatch, home, lives)
        restore_mod.restore(force=False, dry_run=False)
        assert relaunched == []
        assert self._last_boot(home) == "boot-1"
        restore_mod.restore(force=False, dry_run=False)
        assert len(batches) == 1

    def test_a_tab_registered_under_a_lowercase_id_counts_as_started(
            self, restore_mod, monkeypatch, home):
        calls = []

        def lives():
            calls.append(1)
            return [] if len(calls) == 1 else [{"sessionId": SID_A, "cwd": str(home / "ProjA")}]

        batches, relaunched = self._arm(restore_mod, monkeypatch, home, lives, sid=SID_A.upper())
        restore_mod.restore(force=False, dry_run=False)
        assert relaunched == []
        assert self._last_boot(home) == "boot-1"
