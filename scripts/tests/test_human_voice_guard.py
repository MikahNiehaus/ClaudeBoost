"""
Tests for scripts/human-voice-guard.py (Stop hook).

Blocks when last assistant message contains banned AI vocabulary or phrases.
Exit 0 or 2.
"""
from __future__ import annotations

import hashlib
import json
import pytest
from pathlib import Path
from helpers import SCRIPTS_DIR, run_hook


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
