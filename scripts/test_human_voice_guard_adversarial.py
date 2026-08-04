"""
Adversarial tests for human-voice-guard.py get_last_assistant_text fix.
Run: python C:/Development/ClaudeBoost/scripts/test_human_voice_guard_adversarial.py
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPT = Path("C:/Development/ClaudeBoost/scripts/human-voice-guard.py")

# --- import the module directly so we can unit-test get_last_assistant_text ---
spec = importlib.util.spec_from_file_location("hvg", SCRIPT)
hvg = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hvg)

get_last = hvg.get_last_assistant_text


def write_transcript(lines: list[dict]) -> str:
    """Write JSONL transcript to a temp file, return path."""
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False,
                                   encoding="utf-8")
    for entry in lines:
        f.write(json.dumps(entry) + "\n")
    f.flush()
    f.close()
    return f.name


def run_hook(transcript_path: str, extra_env: dict | None = None) -> tuple[int, str]:
    """Run the hook as a subprocess, return (exit_code, stdout)."""
    env = {**os.environ, "CLAUDEBOOST_HOME": str(SCRIPT.parent.parent)}
    if extra_env:
        env.update(extra_env)
    payload = json.dumps({"transcript_path": transcript_path})
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        input=payload,
        capture_output=True,
        text=True,
        env=env,
    )
    return result.returncode, result.stdout


# =============================================================================
# Unit-level tests for get_last_assistant_text
# =============================================================================

def test_new_format_text_block():
    """Property 1: new format entry is found and text extracted."""
    lines = [
        {"type": "assistant", "message": {"role": "assistant", "content": [
            {"type": "text", "text": "Hello world"}
        ]}}
    ]
    path = write_transcript(lines)
    result = get_last(path)
    os.unlink(path)
    assert result == "Hello world", f"Expected 'Hello world', got {result!r}"
    print("PASS test_new_format_text_block")


def test_old_format_string_content():
    """Property 2: old format with string content is found."""
    lines = [{"role": "assistant", "content": "Old string content"}]
    path = write_transcript(lines)
    result = get_last(path)
    os.unlink(path)
    assert result == "Old string content", f"Got {result!r}"
    print("PASS test_old_format_string_content")


def test_old_format_list_content():
    """Property 2: old format with list content is found."""
    lines = [{"role": "assistant", "content": [
        {"type": "text", "text": "Old list content"}
    ]}]
    path = write_transcript(lines)
    result = get_last(path)
    os.unlink(path)
    assert result == "Old list content", f"Got {result!r}"
    print("PASS test_old_format_list_content")


def test_thinking_block_excluded():
    """Property 3: thinking blocks must NOT bleed into text."""
    lines = [
        {"type": "assistant", "message": {"role": "assistant", "content": [
            {"type": "thinking", "thinking": "I should use delve here"},
            {"type": "text", "text": "Clean response"}
        ]}}
    ]
    path = write_transcript(lines)
    result = get_last(path)
    os.unlink(path)
    assert "thinking" not in result.lower(), f"Thinking block text leaked: {result!r}"
    assert "delve" not in result.lower(), f"Thinking content leaked into result: {result!r}"
    assert result == "Clean response", f"Got {result!r}"
    print("PASS test_thinking_block_excluded")


def test_thinking_block_with_banned_word_does_not_trigger():
    """Property 3: banned word ONLY in thinking block must not cause exit 2."""
    lines = [
        {"type": "assistant", "message": {"role": "assistant", "content": [
            {"type": "thinking", "thinking": "I should leverage this approach"},
            {"type": "text", "text": "Use this approach instead."}
        ]}}
    ]
    path = write_transcript(lines)
    code, out = run_hook(path)
    os.unlink(path)
    assert code == 0, (
        f"Exit {code}: banned word in thinking block incorrectly triggered block.\n"
        f"stdout: {out}"
    )
    print("PASS test_thinking_block_with_banned_word_does_not_trigger")


def test_banned_word_in_text_block_triggers():
    """Property 4: banned word in text block must exit 2."""
    lines = [
        {"type": "assistant", "message": {"role": "assistant", "content": [
            {"type": "text", "text": "Let me delve into this topic."}
        ]}}
    ]
    path = write_transcript(lines)
    code, out = run_hook(path)
    os.unlink(path)
    assert code == 2, f"Expected exit 2, got {code}. stdout: {out}"
    assert "block" in out.lower() or "delve" in out.lower(), f"No block in output: {out}"
    print("PASS test_banned_word_in_text_block_triggers")


def test_clean_message_exits_zero():
    """Property 5: clean message must exit 0."""
    lines = [
        {"type": "assistant", "message": {"role": "assistant", "content": [
            {"type": "text", "text": "Here is a simple answer."}
        ]}}
    ]
    path = write_transcript(lines)
    code, out = run_hook(path)
    os.unlink(path)
    assert code == 0, f"Expected exit 0, got {code}. stdout: {out}"
    print("PASS test_clean_message_exits_zero")


def test_empty_transcript_path_exits_zero():
    """Property 6: empty transcript_path must exit 0."""
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        input=json.dumps({"transcript_path": ""}),
        capture_output=True, text=True,
        env={**os.environ, "CLAUDEBOOST_HOME": str(SCRIPT.parent.parent)},
    )
    assert result.returncode == 0, f"Got {result.returncode}"
    print("PASS test_empty_transcript_path_exits_zero")


def test_missing_file_exits_zero():
    """Property 6: missing transcript file must exit 0 (not crash)."""
    code, out = run_hook("/nonexistent/path/transcript.jsonl")
    assert code == 0, f"Got {code}. stdout: {out}"
    print("PASS test_missing_file_exits_zero")


# =============================================================================
# Adversarial edge cases targeting the fix specifically
# =============================================================================

def test_message_field_is_none():
    """
    Edge case: entry has "message": null (or absent).
    entry.get("message") returns None, so `None or entry` falls back to entry.
    But entry has type=="assistant" with no content key — should return "".
    """
    lines = [
        {"type": "assistant", "message": None}
    ]
    path = write_transcript(lines)
    try:
        result = get_last(path)
    except Exception as e:
        os.unlink(path)
        raise AssertionError(f"Crashed with message=null: {e}") from e
    os.unlink(path)
    # Should not crash, and should return empty (no content key on entry itself)
    assert isinstance(result, str), f"Got non-string: {result!r}"
    print(f"PASS test_message_field_is_none (result={result!r})")


def test_message_field_is_empty_string():
    """
    Edge case: "message": "" — empty string is falsy.
    `entry.get("message") or entry` will fall back to entry.
    entry itself has no content → result should be "".
    But if entry had a "content" key this could be confusing.
    """
    lines = [
        {"type": "assistant", "message": "", "content": "Flat content on entry"}
    ]
    path = write_transcript(lines)
    result = get_last(path)
    os.unlink(path)
    # "" is falsy, so msg = entry, content = "Flat content on entry"
    # This is correct for old-format fallback, but could be surprising if someone
    # sends message="" in new format. At minimum it must not crash.
    assert isinstance(result, str), f"Non-string: {result!r}"
    print(f"PASS test_message_field_is_empty_string (result={result!r})")


def test_message_field_is_zero():
    """
    Edge case: "message": 0 — zero is falsy.
    `entry.get("message") or entry` falls back to entry.
    entry itself is a dict so msg.get("content") runs fine.
    Must not crash.
    """
    lines = [
        {"type": "assistant", "message": 0}
    ]
    path = write_transcript(lines)
    try:
        result = get_last(path)
    except Exception as e:
        os.unlink(path)
        raise AssertionError(f"Crashed with message=0: {e}") from e
    os.unlink(path)
    assert isinstance(result, str), f"Non-string: {result!r}"
    print(f"PASS test_message_field_is_zero (result={result!r})")


def test_message_field_is_false():
    """Edge case: "message": false — falsy, falls back to entry."""
    lines = [
        {"type": "assistant", "message": False}
    ]
    path = write_transcript(lines)
    try:
        result = get_last(path)
    except Exception as e:
        os.unlink(path)
        raise AssertionError(f"Crashed with message=false: {e}") from e
    os.unlink(path)
    assert isinstance(result, str)
    print(f"PASS test_message_field_is_false (result={result!r})")


def test_message_is_non_dict():
    """
    CRITICAL: entry.get("message") returns a non-dict (e.g. a list or string).
    `msg = entry.get("message") or entry` would set msg to that non-dict if truthy.
    Then `msg.get("content", "")` would raise AttributeError on a list.
    """
    lines = [
        {"type": "assistant", "message": ["not", "a", "dict"]}
    ]
    path = write_transcript(lines)
    try:
        result = get_last(path)
        crashed = False
    except AttributeError as e:
        crashed = True
        error = str(e)
    os.unlink(path)
    if crashed:
        raise AssertionError(
            f"FAIL: message=[list] caused AttributeError: {error}\n"
            "The `msg = entry.get('message') or entry` fallback does NOT guard "
            "against a truthy non-dict message value."
        )
    print(f"PASS test_message_is_non_dict (result={result!r})")


def test_message_is_non_dict_string():
    """
    CRITICAL: entry["message"] is a non-empty string (truthy, not dict).
    msg = that string, then msg.get("content") raises AttributeError.
    """
    lines = [
        {"type": "assistant", "message": "some string value"}
    ]
    path = write_transcript(lines)
    try:
        result = get_last(path)
        crashed = False
    except AttributeError as e:
        crashed = True
        error = str(e)
    os.unlink(path)
    if crashed:
        raise AssertionError(
            f"FAIL: message='string' caused AttributeError: {error}\n"
            "The `msg = entry.get('message') or entry` fallback does NOT guard "
            "against a truthy non-dict message value."
        )
    print(f"PASS test_message_is_non_dict_string (result={result!r})")


def test_last_entry_wins():
    """The last assistant entry in the transcript should be the one checked."""
    lines = [
        {"type": "assistant", "message": {"role": "assistant", "content": [
            {"type": "text", "text": "First response with delve in it"}
        ]}},
        {"type": "user", "message": {"content": "ok"}},
        {"type": "assistant", "message": {"role": "assistant", "content": [
            {"type": "text", "text": "Second clean response"}
        ]}},
    ]
    path = write_transcript(lines)
    code, out = run_hook(path)
    os.unlink(path)
    assert code == 0, (
        f"Expected exit 0 (last message is clean), got {code}.\n"
        f"stdout: {out}"
    )
    print("PASS test_last_entry_wins")


def test_both_type_and_role_assistant_not_double_counted():
    """
    Entry with BOTH type=assistant AND role=assistant (new format often has this
    on the inner message, but outer entry could too). Should count once.
    """
    lines = [
        {"type": "assistant", "role": "assistant", "message": {
            "role": "assistant",
            "content": [{"type": "text", "text": "Answer here"}]
        }}
    ]
    path = write_transcript(lines)
    result = get_last(path)
    os.unlink(path)
    assert result == "Answer here", f"Got {result!r}"
    print("PASS test_both_type_and_role_assistant_not_double_counted")


def test_content_list_with_only_thinking_blocks_gives_empty():
    """
    If content is a list with ONLY thinking blocks (no text blocks),
    parts will be empty, so last should not update. Result stays "".
    """
    lines = [
        {"type": "assistant", "message": {"role": "assistant", "content": [
            {"type": "thinking", "thinking": "internal monologue"}
        ]}}
    ]
    path = write_transcript(lines)
    result = get_last(path)
    os.unlink(path)
    # parts is empty, so `if parts: last = ...` doesn't execute. last stays "".
    assert result == "", f"Expected empty string, got {result!r}"
    print(f"PASS test_content_list_with_only_thinking_blocks_gives_empty (result={result!r})")


def test_banned_word_in_thinking_only_exits_zero_via_hook():
    """
    When a thinking block has a banned word but text block is clean,
    the full hook must exit 0. This is the end-to-end version of
    test_thinking_block_with_banned_word_does_not_trigger.
    """
    lines = [
        {"type": "assistant", "message": {"role": "assistant", "content": [
            {"type": "thinking", "thinking": "I will leverage synergy here"},
            {"type": "text", "text": "Here is a direct answer."}
        ]}}
    ]
    path = write_transcript(lines)
    code, out = run_hook(path)
    os.unlink(path)
    assert code == 0, (
        f"Exit {code}: thinking-only banned words incorrectly triggered block.\n"
        f"stdout: {out}"
    )
    print("PASS test_banned_word_in_thinking_only_exits_zero_via_hook")


# =============================================================================
# Run all tests
# =============================================================================

TESTS = [
    test_new_format_text_block,
    test_old_format_string_content,
    test_old_format_list_content,
    test_thinking_block_excluded,
    test_thinking_block_with_banned_word_does_not_trigger,
    test_banned_word_in_text_block_triggers,
    test_clean_message_exits_zero,
    test_empty_transcript_path_exits_zero,
    test_missing_file_exits_zero,
    test_message_field_is_none,
    test_message_field_is_empty_string,
    test_message_field_is_zero,
    test_message_field_is_false,
    test_message_is_non_dict,
    test_message_is_non_dict_string,
    test_last_entry_wins,
    test_both_type_and_role_assistant_not_double_counted,
    test_content_list_with_only_thinking_blocks_gives_empty,
    test_banned_word_in_thinking_only_exits_zero_via_hook,
]

if __name__ == "__main__":
    passed = 0
    failed = 0
    failures = []
    for t in TESTS:
        try:
            t()
            passed += 1
        except AssertionError as e:
            failed += 1
            failures.append((t.__name__, str(e)))
            print(f"FAIL {t.__name__}: {e}")
        except Exception as e:
            failed += 1
            failures.append((t.__name__, f"Unexpected exception: {e}"))
            print(f"ERROR {t.__name__}: {e}")

    print(f"\n{'='*60}")
    print(f"Results: {passed} passed, {failed} failed out of {len(TESTS)} tests")
    if failures:
        print("\nFailures:")
        for name, msg in failures:
            print(f"  {name}: {msg}")
    sys.exit(1 if failed else 0)
