"""
Regression tests for two bugs that cost eight sessions across a reboot on
2026-09-10.

Bug 1. Every hook registered with "matcher": "Always" stopped running. That was
never a valid Claude Code matcher: SessionStart takes startup|resume|clear|
compact, PreCompact takes manual|auto, and omitting the key is the documented
way to say "every source". An unrecognised literal matches nothing. The
SessionEnd registrations in the same file carry no matcher, kept working, and
so drained the session restore ledger one entry at a time while SessionStart
added none back.

The half of it that made a source-only fix useless: setup.py's _install_hook
refreshed an installed matcher only when the caller's new entry still carried a
"matcher" key. Deleting the bad line from the call sites therefore fixed a
fresh install and left every already-provisioned settings.json stuck on
"Always" forever.

Bug 2. session-restore.py launched every tab with no env=, so a restore run
from inside a live session handed each new tab CLAUDE_CODE_CHILD_SESSION=1 and
the tab refused to write its own transcript.

None of these tests touch the real ~/.claude/settings.json or open a terminal.
"""
from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS_DIR))

import setup  # noqa: E402

# Documented Claude Code matcher values, per event. Omitting the key entirely
# is also valid and means "every source"; that is represented by None.
VALID_MATCHERS = {
    "SessionStart": {None, "*", "", "startup", "resume", "clear", "compact"},
    "PreCompact": {None, "*", "", "manual", "auto"},
}


def _load_restore_module():
    """Import session-restore.py, whose hyphenated name blocks a plain import."""
    path = SCRIPTS_DIR / "session-restore.py"
    spec = importlib.util.spec_from_file_location("session_restore_under_test", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _prompt_entry(matcher, prompt, status):
    return {"matcher": matcher,
            "hooks": [{"type": "prompt", "prompt": prompt, "statusMessage": status}]}


def _command_entry(matcher, command, status=None):
    h = {"type": "command", "command": command}
    if status:
        h["statusMessage"] = status
    e = {"hooks": [h]}
    if matcher is not None:
        e["matcher"] = matcher
    return e


# ---------------------------------------------------------------------------
# Bug 1a: what setup.py registers today
# ---------------------------------------------------------------------------
class TestRegisteredMatchers:

    def test_no_registration_uses_the_always_matcher(self):
        """The literal that broke everything must not come back anywhere."""
        settings: dict = {}
        setup._install_all_hooks(settings)

        offenders = [
            (event, i, entry.get("matcher"))
            for event, entries in settings.get("hooks", {}).items()
            for i, entry in enumerate(entries or [])
            if entry.get("matcher") == "Always"
        ]
        assert offenders == [], f"'Always' is not a valid matcher: {offenders}"

    @pytest.mark.parametrize("event", sorted(VALID_MATCHERS))
    def test_matchers_are_documented_values(self, event):
        settings: dict = {}
        setup._install_all_hooks(settings)

        for i, entry in enumerate(settings.get("hooks", {}).get(event, []) or []):
            matcher = entry.get("matcher")
            assert matcher in VALID_MATCHERS[event], (
                f"{event}[{i}] matcher={matcher!r} is not a documented value; "
                f"expected one of {sorted(str(m) for m in VALID_MATCHERS[event])}"
            )

    def test_no_prompt_type_hook_is_registered_on_sessionstart(self):
        """Claude Code rejects them outright, so registering one is dead code.

        Its own error: "prompt-type hooks are not supported for SessionStart
        events (no conversation context is available)."
        """
        settings: dict = {}
        setup._install_all_hooks(settings)

        prompts = [
            h.get("statusMessage") or (h.get("prompt", "")[:40])
            for entry in settings.get("hooks", {}).get("SessionStart", []) or []
            for h in (entry.get("hooks") or [])
            if h.get("type") == "prompt"
        ]
        assert prompts == [], f"prompt-type SessionStart hooks registered: {prompts}"

    def test_sessionstart_still_registers_the_restore_ledger(self):
        """Guards against fixing the matcher by deleting the hook."""
        settings: dict = {}
        setup._install_all_hooks(settings)

        commands = [
            h.get("command", "")
            for entry in settings.get("hooks", {}).get("SessionStart", []) or []
            for h in (entry.get("hooks") or [])
        ]
        assert any("session-restore-ledger.py" in c for c in commands)


# ---------------------------------------------------------------------------
# Bug 1b: the migration. This is the branch that decides whether an existing
# machine is fixed or stays broken forever.
# ---------------------------------------------------------------------------
class TestInstallHookMatcherMigration:

    def test_stale_matcher_is_stripped_when_the_new_entry_has_none(self):
        settings = {"hooks": {"SessionStart": [
            _command_entry("Always", "python $CLAUDEBOOST_HOME/scripts/thing.py"),
        ]}}

        setup._install_hook(
            settings, "SessionStart",
            _command_entry(None, "python $CLAUDEBOOST_HOME/scripts/thing.py"),
            sentinel="thing.py", label="thing",
        )

        entry = settings["hooks"]["SessionStart"][0]
        assert "matcher" not in entry, (
            "the stale matcher survived; every already-provisioned "
            "settings.json stays broken"
        )
        assert len(settings["hooks"]["SessionStart"]) == 1, "must not duplicate"

    def test_changed_matcher_is_still_refreshed(self):
        """The original behaviour must survive the new branch."""
        settings = {"hooks": {"PreToolUse": [
            _command_entry("Edit", "python $CLAUDEBOOST_HOME/scripts/thing.py"),
        ]}}

        setup._install_hook(
            settings, "PreToolUse",
            _command_entry("Edit|Write", "python $CLAUDEBOOST_HOME/scripts/thing.py"),
            sentinel="thing.py", label="thing",
        )

        assert settings["hooks"]["PreToolUse"][0]["matcher"] == "Edit|Write"

    def test_entry_without_matcher_stays_without_one(self):
        settings = {"hooks": {"SessionEnd": [
            _command_entry(None, "python $CLAUDEBOOST_HOME/scripts/thing.py"),
        ]}}

        setup._install_hook(
            settings, "SessionEnd",
            _command_entry(None, "python $CLAUDEBOOST_HOME/scripts/thing.py"),
            sentinel="thing.py", label="thing",
        )

        assert "matcher" not in settings["hooks"]["SessionEnd"][0]

    def test_command_path_refresh_still_works_alongside_the_strip(self):
        settings = {"hooks": {"SessionStart": [
            _command_entry("Always", "python /old/path/thing.py"),
        ]}}

        setup._install_hook(
            settings, "SessionStart",
            _command_entry(None, "python /new/path/thing.py"),
            sentinel="thing.py", label="thing",
        )

        entry = settings["hooks"]["SessionStart"][0]
        assert "matcher" not in entry
        assert entry["hooks"][0]["command"] == "python /new/path/thing.py"


# ---------------------------------------------------------------------------
# Bug 1c: removing the dead prompt hooks from installs that already have them.
# Sentinels match statusMessage because the prompt TEXT already drifted: a
# plain-writing pass rewrote "Quality-first routing" to "Quality first
# routing", _install_hook's sentinel stopped matching, and the next setup run
# appended a second copy of the same hook.
# ---------------------------------------------------------------------------
class TestSupersededPromptRemoval:

    def test_both_drifted_copies_of_the_same_hook_are_removed(self):
        settings = {"hooks": {"SessionStart": [
            _prompt_entry(None, "Quality first routing: check CLAUDE.md's decision flow.",
                          "Loading ClaudeBoost workflow..."),
            _prompt_entry("Always", "Quality-first routing: Check CLAUDE.md decision flow.",
                          "Loading ClaudeBoost workflow..."),
        ]}}

        setup._remove_superseded_hooks(settings)

        assert settings.get("hooks", {}).get("SessionStart", []) == [], (
            "the duplicate pair survived; matching on prompt text alone misses "
            "whichever copy was reworded"
        )

    @pytest.mark.parametrize("status", [
        "Loading ClaudeBoost workflow...",
        "Loading CONSULT mode protocol...",
        "Loading RAG HTTP API config...",
    ])
    def test_each_dead_prompt_hook_is_removed(self, status):
        settings = {"hooks": {"SessionStart": [
            _prompt_entry("Always", "some wording that may have been rewritten", status),
        ]}}

        setup._remove_superseded_hooks(settings)

        assert settings.get("hooks", {}).get("SessionStart", []) == []

    def test_a_command_hook_sharing_a_statusmessage_is_kept(self):
        """The type guard. Sweeping by statusMessage alone would eat this."""
        settings = {"hooks": {"SessionStart": [
            _command_entry(None, "python real-work.py", "Loading ClaudeBoost workflow..."),
        ]}}

        setup._remove_superseded_hooks(settings)

        kept = settings.get("hooks", {}).get("SessionStart", [])
        assert len(kept) == 1
        assert kept[0]["hooks"][0]["command"] == "python real-work.py"

    def test_an_unrelated_prompt_hook_is_kept(self):
        settings = {"hooks": {"PreToolUse": [
            _prompt_entry("Bash", "PROCESS KILL SAFETY. Stop and check.",
                          "Process kill safety check..."),
        ]}}

        setup._remove_superseded_hooks(settings)

        assert len(settings["hooks"]["PreToolUse"]) == 1


# ---------------------------------------------------------------------------
# Bug 2: the child environment
# ---------------------------------------------------------------------------
class TestChildEnv:

    @pytest.mark.parametrize("var", [
        "CLAUDE_CODE_CHILD_SESSION",
        "CLAUDECODE",
        "CLAUDE_CODE_SESSION_ID",
        "CLAUDE_CODE_MESSAGING_SOCKET",
        "CLAUDE_CODE_MESSAGING_TOKEN",
        "CLAUDE_PID",
    ])
    def test_session_scoped_var_is_dropped(self, monkeypatch, var):
        mod = _load_restore_module()
        monkeypatch.setenv(var, "1")

        assert var not in mod._child_env()

    def test_everything_else_is_carried_across(self, monkeypatch):
        """Popen replaces the whole environment when env= is given, so an
        over-eager filter would strip PATH and the tab would not start."""
        mod = _load_restore_module()
        monkeypatch.setenv("CLAUDE_CODE_CHILD_SESSION", "1")
        monkeypatch.setenv("CLAUDEBOOST_HOME", "C:/somewhere")
        monkeypatch.setenv("PATH", "C:/bin")

        env = mod._child_env()

        assert env["CLAUDEBOOST_HOME"] == "C:/somewhere"
        assert env["PATH"] == "C:/bin"

    def test_os_environ_itself_is_not_mutated(self, monkeypatch):
        mod = _load_restore_module()
        monkeypatch.setenv("CLAUDE_CODE_CHILD_SESSION", "1")

        mod._child_env()

        assert os.environ.get("CLAUDE_CODE_CHILD_SESSION") == "1"


class TestLaunchPassesTheScrubbedEnv:
    """The end to end guard. Dropping env= from the Popen call must fail here."""

    def test_launch_passes_env_without_the_child_marker(self, monkeypatch, tmp_path):
        mod = _load_restore_module()
        monkeypatch.setenv("CLAUDE_CODE_CHILD_SESSION", "1")
        monkeypatch.setenv("CLAUDECODE", "1")

        captured: dict = {}

        class FakePopen:
            def __init__(self, argv, **kwargs):
                captured["argv"] = argv
                captured["kwargs"] = kwargs

        monkeypatch.setattr(mod.subprocess, "Popen", FakePopen)
        monkeypatch.setattr(mod.time, "sleep", lambda *_: None)

        script = tmp_path / "tab-01.bat"
        script.write_text("@echo off\r\n", encoding="utf-8")
        entry = {"cwd": str(tmp_path), "name": "probe",
                 "sessionId": "aaaaaaaa-1111-2222-3333-444444444444"}

        assert mod._launch(entry, script, "cmd", "cmd.exe", first=False) is True

        assert "env" in captured["kwargs"], (
            "Popen was called with no env=, so the tab inherits the parent's "
            "session markers and comes up with transcript saving off"
        )
        env = captured["kwargs"]["env"]
        assert "CLAUDE_CODE_CHILD_SESSION" not in env
        assert "CLAUDECODE" not in env
