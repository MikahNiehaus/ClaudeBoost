"""
Tests for scripts/speak-tts.py (Stop hook).

Speaks Claude's last response via TTS. Always exits 0.
Tests focus on: disabled state, missing env vars, no crash on bad input.
"""
from __future__ import annotations

import json
import pytest
from helpers import SCRIPTS_DIR, run_hook


def _stop(text: str = "", transcript_path: str = "") -> dict:
    return {
        "hook_event_name": "Stop",
        "session_id": "test",
        "last_assistant_message": text,
        "transcript_path": transcript_path,
        "stop_hook_active": False,
    }


# ---------------------------------------------------------------------------
# Always exits 0
# ---------------------------------------------------------------------------

def test_always_exits_0(boost_home):
    result = run_hook(
        "speak-tts.py",
        _stop("Hello, this is a test message"),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0


def test_exits_0_on_empty_input(boost_home):
    result = run_hook(
        "speak-tts.py",
        {},
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0


# ---------------------------------------------------------------------------
# TTS disabled: silent pass
# ---------------------------------------------------------------------------

def test_silent_when_tts_disabled(boost_home):
    state = boost_home / "state" / "speak-state.json"
    state.write_text(json.dumps({"enabled": False}), encoding="utf-8")

    result = run_hook(
        "speak-tts.py",
        _stop("Some interesting text that should not be spoken"),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0
    assert result.stdout.strip() == b""


def test_silent_when_no_speak_state(boost_home):
    # No speak-state.json → defaults to disabled
    result = run_hook(
        "speak-tts.py",
        _stop("text"),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0


# ---------------------------------------------------------------------------
# stop_hook_active: prevents infinite loop
# ---------------------------------------------------------------------------

def test_skips_when_stop_hook_active(boost_home):
    state = boost_home / "state" / "speak-state.json"
    state.write_text(json.dumps({"enabled": True, "voice": "en-US-AndrewNeural"}), encoding="utf-8")

    payload = {
        "hook_event_name": "Stop",
        "session_id": "test",
        "last_assistant_message": "This text would loop infinitely",
        "stop_hook_active": True,  # prevent loop
    }
    result = run_hook(
        "speak-tts.py",
        payload,
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0


# ---------------------------------------------------------------------------
# Short text: skip
# ---------------------------------------------------------------------------

def test_skips_short_text(boost_home):
    state = boost_home / "state" / "speak-state.json"
    state.write_text(json.dumps({"enabled": True}), encoding="utf-8")

    result = run_hook(
        "speak-tts.py",
        _stop("ok"),  # under MIN_SPEAK_CHARS=10 after filtering
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0
    assert b"Traceback" not in result.stderr


# ---------------------------------------------------------------------------
# No crash with missing TEMP env
# ---------------------------------------------------------------------------

def test_no_crash_missing_temp(boost_home, tmp_path):
    state = boost_home / "state" / "speak-state.json"
    state.write_text(json.dumps({"enabled": True}), encoding="utf-8")

    result = run_hook(
        "speak-tts.py",
        _stop("Some text to speak out loud"),
        env_overrides={
            "CLAUDEBOOST_HOME": str(boost_home),
            "TEMP": str(tmp_path),
            "TMPDIR": str(tmp_path),
        },
    )
    assert result.returncode == 0
    assert b"Traceback" not in result.stderr


# ---------------------------------------------------------------------------
# Unit tests: module-level functions (imported directly)
# ---------------------------------------------------------------------------

import importlib.util
import sys as _sys
from pathlib import Path as _Path


def _load_mod():
    spec = importlib.util.spec_from_file_location(
        "speak_tts", SCRIPTS_DIR / "speak-tts.py"
    )
    mod = importlib.util.module_from_spec(spec)
    _sys.path.insert(0, str(SCRIPTS_DIR))
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# kill_existing_player: lines 43-44, 50, 55-56
# ---------------------------------------------------------------------------

def test_kill_existing_player_writes_stop_file(tmp_path):
    """Lines 43-44: write stop file succeeds."""
    mod = _load_mod()
    mod.kill_existing_player(str(tmp_path))
    stop_file = tmp_path / "claudeboost_tts.stop"
    assert stop_file.exists()
    assert stop_file.read_text(encoding="utf-8") == "stop"


def test_kill_existing_player_kills_pid(tmp_path, monkeypatch):
    """Line 50: os.kill is called when a valid PID file exists."""
    mod = _load_mod()
    import os, signal
    killed = []

    def fake_kill(pid, sig):
        killed.append((pid, sig))

    monkeypatch.setattr(mod.os, "kill", fake_kill)

    # Write a PID file with the current process's PID (safe — SIGTERM to self
    # is a no-op on Windows; we've patched it away anyway).
    pid_file = tmp_path / "claudeboost_tts.pid"
    pid_file.write_text(str(os.getpid()), encoding="utf-8")

    mod.kill_existing_player(str(tmp_path))

    assert len(killed) == 1
    assert killed[0][1] == signal.SIGTERM


def test_kill_existing_player_unlinks_pid_file(tmp_path, monkeypatch):
    """Lines 55-56: PID file is removed after the kill attempt."""
    mod = _load_mod()
    import os

    # Suppress the actual kill so the test doesn't SIGTERM the test runner.
    monkeypatch.setattr(mod.os, "kill", lambda pid, sig: None)

    pid_file = tmp_path / "claudeboost_tts.pid"
    pid_file.write_text(str(os.getpid()), encoding="utf-8")

    mod.kill_existing_player(str(tmp_path))

    assert not pid_file.exists()


def test_kill_existing_player_no_pid_file_no_crash(tmp_path):
    """Lines 47-56: No crash when PID file is absent (exception path swallowed)."""
    mod = _load_mod()
    # No pid file exists — should silently pass
    mod.kill_existing_player(str(tmp_path))


# ---------------------------------------------------------------------------
# extract_from_transcript: lines 68-94
# ---------------------------------------------------------------------------

def test_extract_from_transcript_returns_last_assistant_text(tmp_path):
    """Lines 68-94: happy path — last assistant text block returned."""
    mod = _load_mod()
    transcript = tmp_path / "transcript.jsonl"
    entry = {
        "message": {
            "role": "assistant",
            "content": [{"type": "text", "text": "Hello from assistant"}],
        }
    }
    transcript.write_text(json.dumps(entry) + "\n", encoding="utf-8")

    result = mod.extract_from_transcript(str(transcript))
    assert result == "Hello from assistant"


def test_extract_from_transcript_skips_non_assistant(tmp_path):
    """Lines 83-84: non-assistant messages are skipped."""
    mod = _load_mod()
    transcript = tmp_path / "transcript.jsonl"
    user_entry = {
        "message": {
            "role": "user",
            "content": [{"type": "text", "text": "User said something"}],
        }
    }
    transcript.write_text(json.dumps(user_entry) + "\n", encoding="utf-8")

    result = mod.extract_from_transcript(str(transcript))
    assert result == ""


def test_extract_from_transcript_skips_empty_lines(tmp_path):
    """Line 76: empty lines in JSONL are skipped."""
    mod = _load_mod()
    transcript = tmp_path / "transcript.jsonl"
    entry = {
        "message": {
            "role": "assistant",
            "content": [{"type": "text", "text": "Found it"}],
        }
    }
    # Prepend blank lines
    transcript.write_text("\n\n" + json.dumps(entry) + "\n", encoding="utf-8")

    result = mod.extract_from_transcript(str(transcript))
    assert result == "Found it"


def test_extract_from_transcript_skips_invalid_json_lines(tmp_path):
    """Line 81: invalid JSON lines don't crash — they're skipped."""
    mod = _load_mod()
    transcript = tmp_path / "transcript.jsonl"
    valid_entry = {
        "message": {
            "role": "assistant",
            "content": [{"type": "text", "text": "Valid"}],
        }
    }
    transcript.write_text(
        "not-json\n" + json.dumps(valid_entry) + "\n", encoding="utf-8"
    )

    result = mod.extract_from_transcript(str(transcript))
    assert result == "Valid"


def test_extract_from_transcript_missing_file():
    """Lines 69-72: missing file returns empty string."""
    mod = _load_mod()
    result = mod.extract_from_transcript("/nonexistent/path/transcript.jsonl")
    assert result == ""


def test_extract_from_transcript_multiple_text_blocks(tmp_path):
    """Lines 87-92: multiple text blocks joined with newline."""
    mod = _load_mod()
    transcript = tmp_path / "transcript.jsonl"
    entry = {
        "message": {
            "role": "assistant",
            "content": [
                {"type": "text", "text": "First block"},
                {"type": "tool_use", "name": "Read"},
                {"type": "text", "text": "Second block"},
            ],
        }
    }
    transcript.write_text(json.dumps(entry) + "\n", encoding="utf-8")

    result = mod.extract_from_transcript(str(transcript))
    assert result == "First block\nSecond block"


def test_extract_from_transcript_no_text_blocks(tmp_path):
    """Lines 88-92: assistant with no text-type blocks returns empty."""
    mod = _load_mod()
    transcript = tmp_path / "transcript.jsonl"
    entry = {
        "message": {
            "role": "assistant",
            "content": [{"type": "tool_use", "name": "Bash"}],
        }
    }
    transcript.write_text(json.dumps(entry) + "\n", encoding="utf-8")

    result = mod.extract_from_transcript(str(transcript))
    assert result == ""


# ---------------------------------------------------------------------------
# condense_for_speech: line 166 (empty line skipped with continue)
# ---------------------------------------------------------------------------

def test_condense_for_speech_skips_empty_lines():
    """Line 166: empty lines inside the text are skipped with continue."""
    mod = _load_mod()
    text = "First real sentence.\n\n\nAnother real sentence here."
    result = mod.condense_for_speech(text)
    # Empty lines are dropped; content survives
    assert "First real sentence" in result
    assert "Another real sentence" in result


# ---------------------------------------------------------------------------
# main(): stdin isatty branch (lines 199-202), JSON parse error (206-207),
#         Linux early return (222), transcript fallback (233-235),
#         no text after transcript (238), write_text failure (251-252),
#         stale stop unlink (261-262), POSIX start_new_session (275),
#         Popen exception (281-282)
# ---------------------------------------------------------------------------

def test_main_stdin_is_tty_reads_empty(tmp_path, monkeypatch):
    """Lines 199-202: when stdin.isatty() is True, raw stays empty → no crash."""
    mod = _load_mod()
    import io

    monkeypatch.setattr(mod.sys, "stdin", io.StringIO("ignored"))
    # StringIO.isatty() returns False by default; patch it to True
    monkeypatch.setattr(mod.sys.stdin, "isatty", lambda: True)
    monkeypatch.setenv("CLAUDEBOOST_HOME", str(tmp_path))
    (tmp_path / "state").mkdir(parents=True)
    # No speak-state.json → disabled → returns 0 without reading stdin content
    result = mod.main()
    assert result == 0


def test_main_invalid_json_stdin(tmp_path, monkeypatch):
    """Lines 206-207: invalid JSON on stdin falls back to empty payload."""
    mod = _load_mod()
    import io

    monkeypatch.setattr(mod.sys, "stdin", io.StringIO("{not valid json}"))
    monkeypatch.setattr(mod.sys.stdin, "isatty", lambda: False)
    monkeypatch.setenv("CLAUDEBOOST_HOME", str(tmp_path))
    (tmp_path / "state").mkdir(parents=True)
    # Disabled state → returns 0; key thing is no crash from bad JSON
    result = mod.main()
    assert result == 0


def test_main_returns_0_on_non_windows_non_macos(tmp_path, monkeypatch):
    """Line 222: non-Windows/non-macOS platform exits early with 0."""
    mod = _load_mod()
    import io

    payload = json.dumps({"last_assistant_message": "Hello", "stop_hook_active": False})
    monkeypatch.setattr(mod.sys, "stdin", io.StringIO(payload))
    monkeypatch.setattr(mod.sys.stdin, "isatty", lambda: False)
    monkeypatch.setenv("CLAUDEBOOST_HOME", str(tmp_path))
    (tmp_path / "state").mkdir(parents=True)
    (tmp_path / "state" / "speak-state.json").write_text(
        json.dumps({"enabled": True}), encoding="utf-8"
    )
    # Force non-Windows, non-macOS
    monkeypatch.setattr(mod, "IS_WINDOWS", False)
    monkeypatch.setattr(mod, "IS_MACOS", False)

    result = mod.main()
    assert result == 0


def test_main_transcript_fallback(tmp_path, monkeypatch):
    """Lines 233-235: no last_assistant_message → reads from transcript_path."""
    mod = _load_mod()
    import io

    transcript = tmp_path / "transcript.jsonl"
    entry = {
        "message": {
            "role": "assistant",
            "content": [{"type": "text", "text": "Hello from transcript fallback text"}],
        }
    }
    transcript.write_text(json.dumps(entry) + "\n", encoding="utf-8")

    payload = json.dumps({
        "last_assistant_message": "",
        "transcript_path": str(transcript),
        "stop_hook_active": False,
    })
    monkeypatch.setattr(mod.sys, "stdin", io.StringIO(payload))
    monkeypatch.setattr(mod.sys.stdin, "isatty", lambda: False)
    monkeypatch.setenv("CLAUDEBOOST_HOME", str(tmp_path))
    (tmp_path / "state").mkdir(parents=True)
    (tmp_path / "state" / "speak-state.json").write_text(
        json.dumps({"enabled": True}), encoding="utf-8"
    )
    # Force platform to avoid actual Popen
    monkeypatch.setattr(mod, "IS_WINDOWS", False)
    monkeypatch.setattr(mod, "IS_MACOS", False)

    result = mod.main()
    assert result == 0


def test_main_no_text_after_transcript_returns_0(tmp_path, monkeypatch):
    """Line 238: transcript exists but has no assistant text → returns 0."""
    mod = _load_mod()
    import io

    transcript = tmp_path / "transcript.jsonl"
    # Only user messages — no assistant text
    entry = {
        "message": {
            "role": "user",
            "content": [{"type": "text", "text": "User said hi"}],
        }
    }
    transcript.write_text(json.dumps(entry) + "\n", encoding="utf-8")

    payload = json.dumps({
        "last_assistant_message": "",
        "transcript_path": str(transcript),
        "stop_hook_active": False,
    })
    monkeypatch.setattr(mod.sys, "stdin", io.StringIO(payload))
    monkeypatch.setattr(mod.sys.stdin, "isatty", lambda: False)
    monkeypatch.setenv("CLAUDEBOOST_HOME", str(tmp_path))
    (tmp_path / "state").mkdir(parents=True)
    (tmp_path / "state" / "speak-state.json").write_text(
        json.dumps({"enabled": True}), encoding="utf-8"
    )
    monkeypatch.setattr(mod, "IS_WINDOWS", False)
    monkeypatch.setattr(mod, "IS_MACOS", False)

    result = mod.main()
    assert result == 0


def test_main_write_text_failure_returns_0(tmp_path, monkeypatch):
    """Lines 251-252: if writing the temp text file fails, returns 0 gracefully."""
    mod = _load_mod()
    import io

    payload = json.dumps({
        "last_assistant_message": "Hello this is a long enough message to speak aloud today",
        "stop_hook_active": False,
    })
    monkeypatch.setattr(mod.sys, "stdin", io.StringIO(payload))
    monkeypatch.setattr(mod.sys.stdin, "isatty", lambda: False)
    monkeypatch.setenv("CLAUDEBOOST_HOME", str(tmp_path))
    monkeypatch.setenv("TEMP", str(tmp_path))
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    (tmp_path / "state").mkdir(parents=True)
    (tmp_path / "state" / "speak-state.json").write_text(
        json.dumps({"enabled": True}), encoding="utf-8"
    )
    monkeypatch.setattr(mod, "IS_WINDOWS", True)

    # Make Path.write_text raise so the except branch is hit
    original_write_text = _Path.write_text

    def failing_write_text(self, *args, **kwargs):
        if "claudeboost_tts_text.txt" in str(self):
            raise OSError("disk full")
        return original_write_text(self, *args, **kwargs)

    monkeypatch.setattr(_Path, "write_text", failing_write_text)

    result = mod.main()
    assert result == 0


def test_main_unlinks_stale_stop_file(tmp_path, monkeypatch):
    """Lines 261-262: stale stop file is removed before spawning player."""
    mod = _load_mod()
    import io

    # Pre-create a stale stop file
    stale_stop = tmp_path / "claudeboost_tts.stop"
    stale_stop.write_text("stop", encoding="utf-8")

    payload = json.dumps({
        "last_assistant_message": "Hello this is a long enough message to speak aloud today",
        "stop_hook_active": False,
    })
    monkeypatch.setattr(mod.sys, "stdin", io.StringIO(payload))
    monkeypatch.setattr(mod.sys.stdin, "isatty", lambda: False)
    monkeypatch.setenv("CLAUDEBOOST_HOME", str(tmp_path))
    monkeypatch.setenv("TEMP", str(tmp_path))
    (tmp_path / "state").mkdir(parents=True)
    (tmp_path / "state" / "speak-state.json").write_text(
        json.dumps({"enabled": True}), encoding="utf-8"
    )
    monkeypatch.setattr(mod, "IS_WINDOWS", True)

    # Mock Popen so no real process spawns
    import subprocess as _subprocess
    monkeypatch.setattr(mod.subprocess, "Popen", lambda *a, **kw: None)

    result = mod.main()
    assert result == 0
    assert not stale_stop.exists()


def test_main_posix_start_new_session(tmp_path, monkeypatch):
    """Line 275: on POSIX (non-Windows), start_new_session=True is passed to Popen."""
    mod = _load_mod()
    import io

    captured_kwargs = {}

    def fake_popen(args, **kwargs):
        captured_kwargs.update(kwargs)

    payload = json.dumps({
        "last_assistant_message": "Hello this is a long enough message to speak aloud today",
        "stop_hook_active": False,
    })
    monkeypatch.setattr(mod.sys, "stdin", io.StringIO(payload))
    monkeypatch.setattr(mod.sys.stdin, "isatty", lambda: False)
    monkeypatch.setenv("CLAUDEBOOST_HOME", str(tmp_path))
    monkeypatch.setenv("TEMP", str(tmp_path))
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    (tmp_path / "state").mkdir(parents=True)
    (tmp_path / "state" / "speak-state.json").write_text(
        json.dumps({"enabled": True}), encoding="utf-8"
    )
    # Force POSIX path
    monkeypatch.setattr(mod, "IS_WINDOWS", False)
    monkeypatch.setattr(mod, "IS_MACOS", True)
    monkeypatch.setattr(mod.subprocess, "Popen", fake_popen)

    result = mod.main()
    assert result == 0
    assert captured_kwargs.get("start_new_session") is True
    assert "creationflags" not in captured_kwargs


def test_main_popen_exception_returns_0(tmp_path, monkeypatch):
    """Lines 281-282: Popen raising an exception doesn't crash — returns 0."""
    mod = _load_mod()
    import io

    def exploding_popen(*args, **kwargs):
        raise OSError("cannot spawn")

    payload = json.dumps({
        "last_assistant_message": "Hello this is a long enough message to speak aloud today",
        "stop_hook_active": False,
    })
    monkeypatch.setattr(mod.sys, "stdin", io.StringIO(payload))
    monkeypatch.setattr(mod.sys.stdin, "isatty", lambda: False)
    monkeypatch.setenv("CLAUDEBOOST_HOME", str(tmp_path))
    monkeypatch.setenv("TEMP", str(tmp_path))
    (tmp_path / "state").mkdir(parents=True)
    (tmp_path / "state" / "speak-state.json").write_text(
        json.dumps({"enabled": True}), encoding="utf-8"
    )
    monkeypatch.setattr(mod, "IS_WINDOWS", True)
    monkeypatch.setattr(mod.subprocess, "Popen", exploding_popen)

    result = mod.main()
    assert result == 0


# ---------------------------------------------------------------------------
# kill_existing_player exception branches
# ---------------------------------------------------------------------------

def test_kill_existing_player_write_fails(tmp_path):
    """Lines 43-44: stop-file write raises -> silently ignored."""
    mod = _load_mod()
    from unittest.mock import patch
    from pathlib import Path as _P
    orig = _P.write_text
    def fail_write(self, *a, **kw):
        if "claudeboost_tts.stop" in str(self):
            raise OSError("read-only")
        return orig(self, *a, **kw)
    with patch.object(_P, "write_text", fail_write):
        mod.kill_existing_player(str(tmp_path))  # must not raise


def test_kill_existing_player_sigterm_sent(tmp_path):
    """Line 50: os.kill(pid, SIGTERM) fires when pid file has a valid PID."""
    mod = _load_mod()
    import os, signal
    from unittest.mock import patch
    pid_file = tmp_path / "claudeboost_tts.pid"
    pid_file.write_text(str(os.getpid()), encoding="utf-8")
    kills = []
    with patch.object(os, "kill", side_effect=lambda p, s: kills.append((p, s))):
        mod.kill_existing_player(str(tmp_path))
    assert kills and kills[0][1] == signal.SIGTERM


def test_kill_existing_player_unlink_fails(tmp_path):
    """Lines 55-56: pid-file unlink raises -> silently ignored."""
    mod = _load_mod()
    from unittest.mock import patch
    from pathlib import Path as _P
    pid_file = tmp_path / "claudeboost_tts.pid"
    pid_dir = tmp_path / "claudeboost_tts.pid_dir"
    pid_dir.mkdir()
    orig_unlink = _P.unlink
    def fail_unlink(self, *a, **kw):
        if "claudeboost_tts.pid" in str(self):
            raise OSError("busy")
        return orig_unlink(self, *a, **kw)
    pid_file.write_text("99999999", encoding="utf-8")
    with patch.object(_P, "unlink", fail_unlink):
        mod.kill_existing_player(str(tmp_path))  # must not raise


# ---------------------------------------------------------------------------
# extract_from_transcript coverage (lines 68-94)
# ---------------------------------------------------------------------------

def test_extract_from_transcript_returns_assistant_text(tmp_path):
    """Lines 68-94: reads transcript JSONL and returns last assistant text."""
    import json
    mod = _load_mod()
    transcript = tmp_path / "t.jsonl"
    entry = {"message": {"role": "assistant", "content": [{"type": "text", "text": "hello world"}]}}
    transcript.write_text(json.dumps(entry) + "\n", encoding="utf-8")
    result = mod.extract_from_transcript(str(transcript))
    assert result == "hello world"


def test_extract_from_transcript_skips_empty_lines(tmp_path):
    """Line 77: empty lines in transcript are skipped (continue)."""
    import json
    mod = _load_mod()
    transcript = tmp_path / "t.jsonl"
    entry = {"message": {"role": "assistant", "content": [{"type": "text", "text": "hi"}]}}
    # Put valid entry FIRST so reversed() sees empty lines first, then finds valid entry
    transcript.write_text(json.dumps(entry) + "\n\n\n", encoding="utf-8")
    result = mod.extract_from_transcript(str(transcript))
    assert result == "hi"


def test_extract_from_transcript_skips_invalid_json(tmp_path):
    """Lines 80-81: invalid JSON lines are skipped (except Exception: continue)."""
    import json
    mod = _load_mod()
    transcript = tmp_path / "t.jsonl"
    entry = {"message": {"role": "assistant", "content": [{"type": "text", "text": "ok"}]}}
    # Put valid entry FIRST so reversed() sees invalid line first, then finds valid entry
    transcript.write_text(json.dumps(entry) + "\n" + "NOT JSON\n", encoding="utf-8")
    result = mod.extract_from_transcript(str(transcript))
    assert result == "ok"


def test_extract_from_transcript_file_missing_returns_empty():
    """Line 71-72: missing file -> except Exception -> return ""."""
    mod = _load_mod()
    result = mod.extract_from_transcript("/nonexistent/path/transcript.jsonl")
    assert result == ""


# ---------------------------------------------------------------------------
# filter_for_speech: empty line skip (line 166)
# ---------------------------------------------------------------------------

def test_filter_for_speech_skips_blank_lines():
    """Line 166: blank lines are skipped (continue)."""
    mod = _load_mod()
    result = mod.filter_for_speech("hello world\n\nthis is content")
    assert "hello world" in result or "content" in result


# ---------------------------------------------------------------------------
# main() edge cases
# ---------------------------------------------------------------------------

def test_main_stdin_read_raises_returns_0(monkeypatch):
    """Lines 201-202: sys.stdin.read() raises -> except Exception: pass, raw stays ''."""
    mod = _load_mod()
    from unittest.mock import MagicMock
    fake_stdin = MagicMock()
    fake_stdin.isatty.return_value = False
    fake_stdin.read.side_effect = OSError("broken pipe")
    monkeypatch.setattr(mod.sys, "stdin", fake_stdin)
    result = mod.main()
    assert result == 0  # payload = {}, state disabled -> returns 0 early


def test_main_invalid_json_stdin_uses_empty_payload(tmp_path, monkeypatch):
    """Lines 206-207: invalid JSON -> except Exception -> payload = {}."""
    mod = _load_mod()
    import io
    monkeypatch.setattr(mod.sys, "stdin", io.StringIO("NOT JSON!!!"))
    monkeypatch.setattr(mod.sys.stdin, "isatty", lambda: False)
    monkeypatch.setenv("CLAUDEBOOST_HOME", str(tmp_path))
    (tmp_path / "state").mkdir(parents=True)
    (tmp_path / "state" / "speak-state.json").write_text(
        '{"enabled": false}', encoding="utf-8"
    )
    result = mod.main()
    assert result == 0  # payload={} -> state not enabled -> return 0


def test_main_non_windows_non_macos_returns_0(tmp_path, monkeypatch):
    """Line 222: Linux platform -> return 0 immediately."""
    mod = _load_mod()
    import io
    payload = '{"last_assistant_message": "something", "stop_hook_active": false}'
    monkeypatch.setattr(mod.sys, "stdin", io.StringIO(payload))
    monkeypatch.setattr(mod.sys.stdin, "isatty", lambda: False)
    monkeypatch.setenv("CLAUDEBOOST_HOME", str(tmp_path))
    (tmp_path / "state").mkdir(parents=True)
    (tmp_path / "state" / "speak-state.json").write_text(
        '{"enabled": true}', encoding="utf-8"
    )
    monkeypatch.setattr(mod, "IS_WINDOWS", False)
    monkeypatch.setattr(mod, "IS_MACOS", False)
    result = mod.main()
    assert result == 0


def test_main_transcript_fallback_used(tmp_path, monkeypatch):
    """Lines 233-235: no last_assistant_message -> transcript_path fallback."""
    import json
    mod = _load_mod()
    import io
    transcript = tmp_path / "t.jsonl"
    entry = {"message": {"role": "assistant", "content": [{"type": "text", "text": "hello world test content"}]}}
    transcript.write_text(json.dumps(entry) + "\n", encoding="utf-8")
    payload_str = json.dumps({"transcript_path": str(transcript), "stop_hook_active": False})
    monkeypatch.setattr(mod.sys, "stdin", io.StringIO(payload_str))
    monkeypatch.setattr(mod.sys.stdin, "isatty", lambda: False)
    monkeypatch.setenv("CLAUDEBOOST_HOME", str(tmp_path))
    monkeypatch.setenv("TEMP", str(tmp_path))
    (tmp_path / "state").mkdir(parents=True)
    (tmp_path / "state" / "speak-state.json").write_text('{"enabled": true}', encoding="utf-8")
    monkeypatch.setattr(mod, "IS_WINDOWS", False)
    monkeypatch.setattr(mod, "IS_MACOS", False)
    result = mod.main()
    assert result == 0  # non-mac/non-win -> return 0 after text is found


def test_main_no_text_after_transcript_fallback(tmp_path, monkeypatch):
    """Line 238: transcript has no assistant text -> return 0."""
    import json
    mod = _load_mod()
    import io
    transcript = tmp_path / "t.jsonl"
    transcript.write_text(json.dumps({"message": {"role": "user", "content": []}}) + "\n", encoding="utf-8")
    payload_str = json.dumps({"transcript_path": str(transcript), "stop_hook_active": False})
    monkeypatch.setattr(mod.sys, "stdin", io.StringIO(payload_str))
    monkeypatch.setattr(mod.sys.stdin, "isatty", lambda: False)
    monkeypatch.setenv("CLAUDEBOOST_HOME", str(tmp_path))
    (tmp_path / "state").mkdir(parents=True)
    (tmp_path / "state" / "speak-state.json").write_text('{"enabled": true}', encoding="utf-8")
    monkeypatch.setattr(mod, "IS_WINDOWS", True)
    result = mod.main()
    assert result == 0


def test_main_write_text_file_fails_returns_0(tmp_path, monkeypatch):
    """Lines 251-252: Path.write_text for text_file raises -> return 0."""
    import json
    mod = _load_mod()
    import io
    from unittest.mock import patch
    from pathlib import Path as _P
    payload_str = json.dumps({
        "last_assistant_message": "hello world this is definitely long enough text",
        "stop_hook_active": False,
    })
    monkeypatch.setattr(mod.sys, "stdin", io.StringIO(payload_str))
    monkeypatch.setattr(mod.sys.stdin, "isatty", lambda: False)
    monkeypatch.setenv("CLAUDEBOOST_HOME", str(tmp_path))
    monkeypatch.setenv("TEMP", str(tmp_path))
    (tmp_path / "state").mkdir(parents=True)
    (tmp_path / "state" / "speak-state.json").write_text('{"enabled": true}', encoding="utf-8")
    monkeypatch.setattr(mod, "IS_WINDOWS", True)
    orig_write = _P.write_text
    def fail_write(self, *a, **kw):
        if "claudeboost_tts_text.txt" in str(self):
            raise OSError("no space")
        return orig_write(self, *a, **kw)
    with patch.object(_P, "write_text", fail_write):
        result = mod.main()
    assert result == 0


def test_main_stale_stop_unlink_fails_silently(tmp_path, monkeypatch):
    """Lines 261-262: stale_stop unlink raises -> except Exception: pass (not fatal)."""
    import json
    mod = _load_mod()
    import io
    from unittest.mock import patch, MagicMock
    from pathlib import Path as _P
    payload_str = json.dumps({
        "last_assistant_message": "hello world this is definitely long enough text",
        "stop_hook_active": False,
    })
    monkeypatch.setattr(mod.sys, "stdin", io.StringIO(payload_str))
    monkeypatch.setattr(mod.sys.stdin, "isatty", lambda: False)
    monkeypatch.setenv("CLAUDEBOOST_HOME", str(tmp_path))
    monkeypatch.setenv("TEMP", str(tmp_path))
    (tmp_path / "state").mkdir(parents=True)
    (tmp_path / "state" / "speak-state.json").write_text('{"enabled": true}', encoding="utf-8")
    # Use IS_MACOS=True so code reaches lines 261-262 (not-linux path)
    monkeypatch.setattr(mod, "IS_WINDOWS", False)
    monkeypatch.setattr(mod, "IS_MACOS", True)
    orig_unlink = _P.unlink
    def fail_unlink(self, *a, **kw):
        if "claudeboost_tts.stop" in str(self):
            raise OSError("busy")
        return orig_unlink(self, *a, **kw)
    fake_popen = MagicMock(return_value=MagicMock())
    monkeypatch.setattr(mod.subprocess, "Popen", fake_popen)
    with patch.object(_P, "unlink", fail_unlink):
        result = mod.main()
    assert result == 0


def test_main_posix_start_new_session_flag_set(tmp_path, monkeypatch):
    """Line 275: non-Windows Popen gets start_new_session=True."""
    import json
    mod = _load_mod()
    import io
    from unittest.mock import MagicMock
    payload_str = json.dumps({
        "last_assistant_message": "hello world this is definitely long enough",
        "stop_hook_active": False,
    })
    monkeypatch.setattr(mod.sys, "stdin", io.StringIO(payload_str))
    monkeypatch.setattr(mod.sys.stdin, "isatty", lambda: False)
    monkeypatch.setenv("CLAUDEBOOST_HOME", str(tmp_path))
    monkeypatch.setenv("TEMP", str(tmp_path))
    (tmp_path / "state").mkdir(parents=True)
    (tmp_path / "state" / "speak-state.json").write_text('{"enabled": true}', encoding="utf-8")
    monkeypatch.setattr(mod, "IS_WINDOWS", False)
    monkeypatch.setattr(mod, "IS_MACOS", True)
    captured = {}
    def fake_popen(args, **kwargs):
        captured.update(kwargs)
        return MagicMock()
    monkeypatch.setattr(mod.subprocess, "Popen", fake_popen)
    result = mod.main()
    assert result == 0
    assert captured.get("start_new_session") is True


def test_main_popen_raises_returns_0(tmp_path, monkeypatch):
    """Lines 281-282: Popen raises -> except Exception: pass -> return 0."""
    import json
    mod = _load_mod()
    import io
    payload_str = json.dumps({
        "last_assistant_message": "hello world this is definitely long enough",
        "stop_hook_active": False,
    })
    monkeypatch.setattr(mod.sys, "stdin", io.StringIO(payload_str))
    monkeypatch.setattr(mod.sys.stdin, "isatty", lambda: False)
    monkeypatch.setenv("CLAUDEBOOST_HOME", str(tmp_path))
    monkeypatch.setenv("TEMP", str(tmp_path))
    (tmp_path / "state").mkdir(parents=True)
    (tmp_path / "state" / "speak-state.json").write_text('{"enabled": true}', encoding="utf-8")
    monkeypatch.setattr(mod, "IS_WINDOWS", False)
    monkeypatch.setattr(mod, "IS_MACOS", True)
    monkeypatch.setattr(mod.subprocess, "Popen", lambda *a, **kw: (_ for _ in ()).throw(OSError("no exec")))
    result = mod.main()
    assert result == 0
