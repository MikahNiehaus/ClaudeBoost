"""terminal-title.py renames the terminal tab to say what Claude is doing.

Two properties matter more than the title text itself.

It must never speak. Registered on UserPromptSubmit, whose stdout is injected
into Claude's context rather than printed, so a stray byte on stdout becomes
conversation garbage. That is also why the title cannot be written to stdout at
all, which is the obvious wrong implementation.

It must never block. Registered on PreToolUse, where a non zero exit is read as
"refuse this tool call". A cosmetic hook that can refuse an Edit is worse than
no hook.

The console write itself is stubbed throughout. A test that actually set the
title would depend on having a console attached, which pytest does not
guarantee, and would leave the developer's tab renamed.
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
SCRIPT = SCRIPTS_DIR / "terminal-title.py"


@pytest.fixture()
def tt(monkeypatch):
    """The module, with the console write captured instead of performed."""
    spec = importlib.util.spec_from_file_location("terminal_title", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    written: list[str] = []
    monkeypatch.setattr(mod, "_set_title", written.append)
    mod.written = written
    return mod


def _run(payload: dict) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT)],
        input=json.dumps(payload).encode(),
        capture_output=True,
    )


# ── the two properties that could break a turn ───────────────────────────────

class TestItNeverSpeaksAndNeverBlocks:
    @pytest.mark.parametrize("payload", [
        {"hook_event_name": "UserPromptSubmit", "prompt": "fix the parser", "cwd": "/x/proj"},
        {"hook_event_name": "PreToolUse", "tool_name": "Task",
         "tool_input": {"subagent_type": "bad-cop", "description": "review diff"}},
        {"hook_event_name": "PreToolUse", "tool_name": "Edit",
         "tool_input": {"file_path": "/x/a.py"}},
        {"hook_event_name": "Stop"},
        {"hook_event_name": "SessionStart"},
        {},
    ])
    def test_exit_zero_and_silent_stdout(self, payload):
        r = _run(payload)
        assert r.returncode == 0, r.stderr
        assert r.stdout == b"", (
            "UserPromptSubmit stdout is injected into context, so anything "
            f"printed here becomes conversation garbage. Got: {r.stdout!r}"
        )

    @pytest.mark.parametrize("raw", [b"", b"   ", b"not json at all",
                                     b"[1,2,3]", b"null", b'{"hook_event_name":'])
    def test_garbage_stdin_is_survived(self, raw):
        r = subprocess.run([sys.executable, str(SCRIPT)], input=raw, capture_output=True)
        assert r.returncode == 0, r.stderr
        assert r.stdout == b""

    def test_a_console_that_raises_does_not_fail_the_hook(self, tt, monkeypatch):
        """The real reason _set_title swallows everything: a piped or detached
        process has no console, so opening CONOUT$ raises. main() must still
        return 0, because on PreToolUse a non zero exit refuses the tool call."""
        monkeypatch.setattr(sys.stdin, "isatty", lambda: False, raising=False)

        def boom(_text):
            raise OSError("no console attached")

        monkeypatch.setattr(tt, "_set_title", boom)
        monkeypatch.setattr(
            tt.sys, "stdin",
            type("S", (), {"read": staticmethod(lambda: json.dumps(
                {"hook_event_name": "Stop", "cwd": "/x/proj"})),
                "isatty": staticmethod(lambda: False)})(),
        )
        assert tt.main() == 0


# ── which events set a title at all ──────────────────────────────────────────

class TestEventRouting:
    def test_user_prompt_sets_the_task(self, tt):
        title = tt._title({"hook_event_name": "UserPromptSubmit",
                           "prompt": "fix the flaky auth test", "cwd": "/x/myrepo"})
        assert title == "myrepo | fix the flaky auth test"

    def test_task_spawn_names_the_agent(self, tt):
        title = tt._title({"hook_event_name": "PreToolUse", "tool_name": "Task",
                           "cwd": "/x/myrepo",
                           "tool_input": {"subagent_type": "bad-cop",
                                          "description": "review the diff"}})
        assert title == "myrepo | [bad-cop] review the diff"

    def test_stop_goes_idle(self, tt):
        assert tt._title({"hook_event_name": "Stop", "cwd": "/x/myrepo"}) == "myrepo | idle"

    @pytest.mark.parametrize("tool", ["Edit", "Write", "Bash", "Read", "Grep"])
    def test_ordinary_tools_leave_the_title_alone(self, tt, tool):
        """PreToolUse fires on every tool call. Retitling on each one would make
        the tab flicker and add a process spawn to every Read."""
        assert tt._title({"hook_event_name": "PreToolUse", "tool_name": tool,
                          "cwd": "/x/myrepo", "tool_input": {}}) is None

    @pytest.mark.parametrize("event", ["SessionStart", "PostToolUse", "PreCompact", ""])
    def test_unhandled_events_return_none(self, tt, event):
        assert tt._title({"hook_event_name": event, "cwd": "/x/myrepo"}) is None

    def test_an_empty_prompt_leaves_the_title_alone(self, tt):
        assert tt._title({"hook_event_name": "UserPromptSubmit",
                          "prompt": "   ", "cwd": "/x/myrepo"}) is None

    def test_a_task_spawn_without_a_subagent_type_still_titles(self, tt):
        title = tt._title({"hook_event_name": "PreToolUse", "tool_name": "Task",
                           "cwd": "/x/myrepo", "tool_input": {}})
        assert title == "myrepo | [agent]"


# ── title text rules ─────────────────────────────────────────────────────────

class TestTitleText:
    def test_a_slash_command_is_kept_as_the_summary(self, tt):
        """'/start make everything portable' reads better as the command plus
        its argument than as the first few words of prose."""
        assert tt._from_prompt("/start make everything portable") == \
            "/start make everything portable"
        assert tt._from_prompt("/ps") == "/ps"

    def test_newlines_collapse_to_one_line(self, tt):
        title = tt._title({"hook_event_name": "UserPromptSubmit", "cwd": "/x/r",
                           "prompt": "first line\n\nsecond line\tthird"})
        assert "\n" not in title and "\t" not in title
        assert title == "r | first line second line third"

    def test_non_ascii_is_dropped_not_mangled(self, tt):
        """Non ASCII in a Windows terminal title renders as mojibake, which is
        worse than losing the character."""
        title = tt._title({"hook_event_name": "UserPromptSubmit", "cwd": "/x/r",
                           "prompt": "fix the café ⚡ parser"})
        assert title.isascii(), title
        assert "parser" in title

    def test_long_titles_are_truncated_within_budget(self, tt):
        long = "make absolutely everything in this repository portable " * 6
        title = tt._title({"hook_event_name": "UserPromptSubmit",
                           "cwd": "/x/myrepo", "prompt": long})
        assert len(title) <= tt.MAX_TITLE, f"{len(title)} > {tt.MAX_TITLE}: {title}"
        assert title.endswith("...")
        assert title.startswith("myrepo | ")

    def test_truncation_does_not_cut_mid_word_when_avoidable(self, tt):
        out = tt._clean("alpha beta gamma delta epsilon", 20)
        assert out.endswith("...")
        assert " " not in out[-4:]
        assert not out.replace("...", "").endswith(" ")

    def test_a_very_long_project_name_does_not_produce_a_negative_budget(self, tt):
        """budget = MAX_TITLE - len(project) - 3 goes negative on a long path
        name. text[:negative] silently returns the wrong end of the string."""
        project = "a" * (tt.MAX_TITLE + 20)
        title = tt._title({"hook_event_name": "UserPromptSubmit",
                           "cwd": f"/x/{project}", "prompt": "do the thing"})
        assert title is not None
        assert title.startswith(project)
        assert "do the thing" not in title, "no room for it, and must not wrap around"

    def test_project_name_comes_from_cwd(self, tt):
        assert tt._project({"cwd": "/a/b/ClaudeBoost"}) == "ClaudeBoost"

    def test_missing_cwd_falls_back_without_raising(self, tt):
        assert tt._project({}) != ""
