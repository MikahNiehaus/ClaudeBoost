"""
Tests for scripts/human-voice-guard.py (Stop hook).

Blocks when last assistant message contains banned AI vocabulary or phrases.
Exit 0 or 2.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from helpers import SCRIPTS_DIR, run_hook


def _load_hvg():
    spec = importlib.util.spec_from_file_location(
        "human_voice_guard", SCRIPTS_DIR / "human-voice-guard.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _stop_with_transcript(transcript_path: str) -> dict:
    return {
        "hook_event_name": "Stop",
        "session_id": "test",
        "transcript_path": transcript_path,
    }


def _write_transcript(tmp_path: Path, assistant_text: str) -> str:
    transcript = tmp_path / "transcript.jsonl"
    entry = {
        "role": "assistant",
        "content": [{"type": "text", "text": assistant_text}],
    }
    transcript.write_text(json.dumps(entry) + "\n", encoding="utf-8")
    return str(transcript)


# ---------------------------------------------------------------------------
# Always exits 0 when transcript missing or no violations
# ---------------------------------------------------------------------------

def test_passes_when_no_transcript(boost_home):
    result = run_hook(
        "human-voice-guard.py",
        {"hook_event_name": "Stop", "session_id": "test", "transcript_path": ""},
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0


def test_passes_when_transcript_missing(boost_home, tmp_path):
    result = run_hook(
        "human-voice-guard.py",
        _stop_with_transcript("/nonexistent/path.jsonl"),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0


def test_passes_clean_text(boost_home, tmp_path):
    transcript = _write_transcript(tmp_path, "Here's what I found: the bug is on line 42.")
    result = run_hook(
        "human-voice-guard.py",
        _stop_with_transcript(transcript),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0


# ---------------------------------------------------------------------------
# Banned vocabulary: block
# ---------------------------------------------------------------------------

def test_blocks_banned_word_delve(boost_home, tmp_path):
    transcript = _write_transcript(
        tmp_path,
        "Let's delve into the authentication system and understand the components."
    )
    result = run_hook(
        "human-voice-guard.py",
        _stop_with_transcript(transcript),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 2
    output = json.loads(result.stdout)
    assert output.get("decision") == "block"
    assert "delve" in output.get("reason", "").lower()


def test_blocks_banned_word_pivotal(boost_home, tmp_path):
    transcript = _write_transcript(
        tmp_path,
        "This is a pivotal moment for the project, and we need to leverage our resources."
    )
    result = run_hook(
        "human-voice-guard.py",
        _stop_with_transcript(transcript),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 2


def test_blocks_banned_phrase_certainly(boost_home, tmp_path):
    transcript = _write_transcript(
        tmp_path,
        "Certainly! I'd be happy to help you with that task."
    )
    result = run_hook(
        "human-voice-guard.py",
        _stop_with_transcript(transcript),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 2


def test_blocks_banned_phrase_furthermore(boost_home, tmp_path):
    transcript = _write_transcript(
        tmp_path,
        "The test passes now. Furthermore, I've updated the docs."
    )
    result = run_hook(
        "human-voice-guard.py",
        _stop_with_transcript(transcript),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 2


# ---------------------------------------------------------------------------
# Loop prevention: second block on same hash → allow
# ---------------------------------------------------------------------------

def test_loop_prevention_allows_on_repeat_hash(boost_home, tmp_path):
    text = "We need to leverage this paradigm to empower our users."
    transcript = _write_transcript(tmp_path, text)

    msg_hash = hashlib.md5(text.encode()).hexdigest()
    state_path = boost_home / "state" / "human-voice-check.json"
    state_path.write_text(json.dumps({"last_blocked_hash": msg_hash}), encoding="utf-8")

    result = run_hook(
        "human-voice-guard.py",
        _stop_with_transcript(transcript),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    # Same hash was already blocked → allow (loop guard)
    assert result.returncode == 0


# ---------------------------------------------------------------------------
# Words in code blocks: not flagged
# ---------------------------------------------------------------------------

def test_passes_banned_word_in_code_block(boost_home, tmp_path):
    # "delve" inside a code block should not trigger
    text = "Here's an example:\n```python\ndef delve_into_data():\n    pass\n```\nThis is clean."
    transcript = _write_transcript(tmp_path, text)
    result = run_hook(
        "human-voice-guard.py",
        _stop_with_transcript(transcript),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0


# ---------------------------------------------------------------------------
# get_last_assistant_text edge cases (lines 111, 114-115, 117, 120)
# ---------------------------------------------------------------------------

class TestGetLastAssistantText:
    def test_empty_lines_skipped(self, tmp_path):
        """Empty lines in transcript are skipped (line 111 `continue`)."""
        mod = _load_hvg()
        transcript = tmp_path / "t.jsonl"
        entry = {"role": "assistant", "content": "Hello world"}
        transcript.write_text(
            "\n\n" + json.dumps(entry) + "\n\n",
            encoding="utf-8",
        )
        result = mod.get_last_assistant_text(str(transcript))
        assert result == "Hello world"

    def test_non_json_lines_skipped(self, tmp_path):
        """Non-JSON lines trigger except branch (lines 114-115) and are skipped."""
        mod = _load_hvg()
        transcript = tmp_path / "t.jsonl"
        entry = {"role": "assistant", "content": "Clean text"}
        transcript.write_text(
            "NOT JSON AT ALL\n" + json.dumps(entry) + "\n",
            encoding="utf-8",
        )
        result = mod.get_last_assistant_text(str(transcript))
        assert result == "Clean text"

    def test_non_assistant_role_skipped(self, tmp_path):
        """Entries with role != 'assistant' trigger continue (line 117)."""
        mod = _load_hvg()
        transcript = tmp_path / "t.jsonl"
        user_entry = {"role": "user", "content": "What's up?"}
        transcript.write_text(json.dumps(user_entry) + "\n", encoding="utf-8")
        result = mod.get_last_assistant_text(str(transcript))
        assert result == ""

    def test_content_as_string(self, tmp_path):
        """When content is a string, it is assigned directly (line 120)."""
        mod = _load_hvg()
        transcript = tmp_path / "t.jsonl"
        entry = {"role": "assistant", "content": "Direct string content"}
        transcript.write_text(json.dumps(entry) + "\n", encoding="utf-8")
        result = mod.get_last_assistant_text(str(transcript))
        assert result == "Direct string content"


# ---------------------------------------------------------------------------
# main() exception paths (lines 157-158, 183-184, 192-193, 199-200)
# ---------------------------------------------------------------------------

class TestMainExceptionPaths:
    def test_invalid_json_stdin_returns_0(self, boost_home):
        """Invalid JSON on stdin triggers except branch (lines 157-158), returns 0."""
        result = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "human-voice-guard.py")],
            input=b"THIS IS NOT VALID JSON",
            capture_output=True,
            env={**os.environ, "CLAUDEBOOST_HOME": str(boost_home)},
        )
        assert result.returncode == 0

    def test_invalid_json_stdin_in_process_returns_0(self, boost_home):
        """Calls main() directly with invalid JSON stdin — covers lines 157-158 for in-process coverage."""
        mod = _load_hvg()
        with patch("sys.stdin") as mock_stdin, \
             patch.dict(os.environ, {"CLAUDEBOOST_HOME": str(boost_home)}):
            mock_stdin.isatty.return_value = False
            mock_stdin.read.return_value = "THIS IS NOT VALID JSON {{{broken"
            result = mod.main()
        assert result == 0

    def test_loop_prevention_state_write_fails_silently(self, boost_home, tmp_path):
        """State write fails during loop prevention (lines 183-184); still returns 0."""
        mod = _load_hvg()
        text = "We need to leverage this paradigm to empower our users."
        transcript = tmp_path / "t.jsonl"
        entry = {"role": "assistant", "content": [{"type": "text", "text": text}]}
        transcript.write_text(json.dumps(entry) + "\n", encoding="utf-8")

        msg_hash = hashlib.md5(text.encode()).hexdigest()
        state_dir = boost_home / "state"
        state_dir.mkdir(parents=True, exist_ok=True)
        state_path = state_dir / "human-voice-check.json"
        state_path.write_text(json.dumps({"last_blocked_hash": msg_hash}), encoding="utf-8")

        original_write_text = Path.write_text

        def fail_write(self, *args, **kwargs):
            if "human-voice-check" in str(self):
                raise PermissionError("cannot write")
            return original_write_text(self, *args, **kwargs)

        payload = {"hook_event_name": "Stop", "transcript_path": str(transcript)}

        with patch.object(Path, "write_text", fail_write), \
             patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = False
            mock_stdin.read.return_value = json.dumps(payload)
            with patch.dict(os.environ, {"CLAUDEBOOST_HOME": str(boost_home)}):
                result = mod.main()

        assert result == 0

    def test_clean_text_state_write_fails_silently(self, boost_home, tmp_path):
        """State write fails when no violations (lines 192-193); still returns 0."""
        transcript = _write_transcript(tmp_path, "The fix is on line 42.")
        state_dir = boost_home / "state"
        state_dir.mkdir(parents=True, exist_ok=True)
        state_path = state_dir / "human-voice-check.json"
        state_path.mkdir()  # directory prevents write_text

        result = run_hook(
            "human-voice-guard.py",
            _stop_with_transcript(transcript),
            env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
        )
        assert result.returncode == 0

    def test_violation_state_write_fails_silently(self, boost_home, tmp_path):
        """State write fails when saving violation hash (lines 199-200); still blocks."""
        transcript = _write_transcript(tmp_path, "Let's delve into the paradigm.")
        state_dir = boost_home / "state"
        state_dir.mkdir(parents=True, exist_ok=True)
        state_path = state_dir / "human-voice-check.json"
        state_path.mkdir()  # directory prevents write_text

        result = run_hook(
            "human-voice-guard.py",
            _stop_with_transcript(transcript),
            env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
        )
        assert result.returncode == 2
