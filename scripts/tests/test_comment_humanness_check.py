"""
Tests for scripts/comment-humanness-check.py (PostToolUse on Edit/Write).

Nudges when comments look AI-generated. Always exits 0.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest
from helpers import SCRIPTS_DIR, run_hook, posttooluse


def _load_module():
    """Load comment-humanness-check.py as a Python module."""
    mod_name = "comment_humanness_check"
    if mod_name in sys.modules:
        return sys.modules[mod_name]
    spec = importlib.util.spec_from_file_location(
        mod_name,
        SCRIPTS_DIR / "comment-humanness-check.py",
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod  # register so coverage can track it
    sys.path.insert(0, str(SCRIPTS_DIR))
    spec.loader.exec_module(mod)
    return mod


def _write_with(content: str) -> dict:
    return posttooluse("Write", {"file_path": "/src/app.py", "content": content})


def _edit_with(new_string: str) -> dict:
    return posttooluse("Edit", {
        "file_path": "/src/app.py",
        "old_string": "old",
        "new_string": new_string,
    })


# ---------------------------------------------------------------------------
# Always exits 0
# ---------------------------------------------------------------------------

def test_always_exits_0():
    result = run_hook("comment-humanness-check.py", _write_with("x = 1"))
    assert result.returncode == 0


def test_exits_0_on_empty_input():
    result = run_hook("comment-humanness-check.py", {})
    assert result.returncode == 0


# ---------------------------------------------------------------------------
# Clean code: no nudge
# ---------------------------------------------------------------------------

def test_no_nudge_on_human_comments():
    content = """
# why we sort here: the API returns unsorted IDs
data.sort()

# cheap check before hitting the DB
if not user_id:
    return None

result = db.get(user_id)
"""
    result = run_hook("comment-humanness-check.py", _write_with(content))
    assert result.returncode == 0
    assert result.stderr == b""


def test_no_nudge_when_fewer_than_3_comments():
    content = """
# short comment
x = 1
# another comment
"""
    result = run_hook("comment-humanness-check.py", _write_with(content))
    assert result.returncode == 0
    assert result.stderr == b""


# ---------------------------------------------------------------------------
# Formal opener: nudge
# ---------------------------------------------------------------------------

def test_nudge_on_formal_opener():
    content = """
// This function facilitates the authentication flow.
// This method validates user credentials.
// This class manages the session state.
// This variable holds the current token.
x = auth()
"""
    result = run_hook("comment-humanness-check.py", _write_with(content))
    assert result.returncode == 0
    assert b"comment-humanness" in result.stderr


# ---------------------------------------------------------------------------
# Complete sentence uniformity: nudge
# ---------------------------------------------------------------------------

def test_nudge_on_sentence_uniformity():
    content = """
// Initializes the database connection.
// Sets up the authentication middleware.
// Configures the logging system.
// Registers all route handlers.
// Starts the HTTP server.
x = setup()
"""
    result = run_hook("comment-humanness-check.py", _write_with(content))
    assert result.returncode == 0
    assert b"comment-humanness" in result.stderr


# ---------------------------------------------------------------------------
# Banned vocabulary: nudge
# ---------------------------------------------------------------------------

def test_nudge_on_banned_vocab():
    content = """
// This function facilitates the seamless user login.
// It leverages the JWT token.
// Please note the robust error handling.
// The purpose of this is to authenticate.
x = login()
"""
    result = run_hook("comment-humanness-check.py", _write_with(content))
    assert result.returncode == 0
    assert b"comment-humanness" in result.stderr


# ---------------------------------------------------------------------------
# Dash separator: hard block
# ---------------------------------------------------------------------------

def test_nudge_on_dash_separator():
    content = """
// auth - validates the token
// session - manages state
// db - handles queries
// cache - stores results
x = init()
"""
    result = run_hook("comment-humanness-check.py", _write_with(content))
    # Spaced hyphen separators are a hard block per CLAUDE.md dash rule
    assert result.returncode == 2
    assert b"BLOCKED" in result.stderr


# ---------------------------------------------------------------------------
# Edit tool path
# ---------------------------------------------------------------------------

def test_works_with_edit_tool():
    new_string = """
// This function facilitates the data processing.
// This method transforms the input.
// This class manages the pipeline state.
x = process()
"""
    result = run_hook("comment-humanness-check.py", _edit_with(new_string))
    assert result.returncode == 0
    assert b"comment-humanness" in result.stderr


# ---------------------------------------------------------------------------
# Unit-level tests for individual check functions (cover missed branches)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def mod():
    return _load_module()


# Line 85 — check_complete_sentence_uniformity returns None when < 3 comments
def test_complete_sentence_uniformity_fewer_than_3(mod):
    result = mod.check_complete_sentence_uniformity(["// One line."])
    assert result is None


def test_complete_sentence_uniformity_exactly_2(mod):
    result = mod.check_complete_sentence_uniformity(["// First line.", "// Second line."])
    assert result is None


# Line 109 — check_spacing_uniformity returns None when < 5 comments
def test_spacing_uniformity_fewer_than_5(mod):
    comments = ["// a", "// b", "// c", "// d"]
    result = mod.check_spacing_uniformity(comments)
    assert result is None


def test_spacing_uniformity_exactly_4(mod):
    result = mod.check_spacing_uniformity(["// one"] * 4)
    assert result is None


# Line 109 — check_spacing_uniformity returns None when >= 5 comments but spacing varies
def test_spacing_uniformity_no_trigger_when_spacing_varies(mod):
    # Mix of single-space and no-space comments — not uniform, should not flag
    comments = [
        "// single space",
        "//no space",
        "// single space",
        "//no space",
        "// single space",
    ]
    result = mod.check_spacing_uniformity(comments)
    assert result is None


# check_structural_uniformity returns a string when 4 consecutive comments
# are within 5 chars of each other in length (not a Finding object)
def test_structural_uniformity_triggers(mod):
    # All 16 chars long — definitely within 5-char window
    comments = ["// twelve chars."] * 4
    result = mod.check_structural_uniformity(comments)
    assert result is not None
    assert isinstance(result, str)


def test_structural_uniformity_no_trigger_when_lengths_vary(mod):
    comments = [
        "// short",                        # 8
        "// a much longer comment here",   # 30
        "// mid",                          # 6
        "// another long one over here",   # 30
    ]
    result = mod.check_structural_uniformity(comments)
    assert result is None


# Lines 174-175 — main() except branch: invalid JSON exits 0
def test_main_returns_0_on_invalid_json():
    import os
    import subprocess
    script = SCRIPTS_DIR / "comment-humanness-check.py"
    env = {**os.environ}
    result = subprocess.run(
        [sys.executable, str(script)],
        input=b"not valid json{{{{",
        capture_output=True,
        env=env,
    )
    assert result.returncode == 0


# Lines 174-175 — test main() directly by patching sys.stdin (in-process coverage)
def test_main_returns_0_on_invalid_json_in_process(mod):
    import io
    import unittest.mock as mock
    fake_stdin = io.StringIO("{{not valid json}}")
    with mock.patch.object(mod.sys, "stdin", fake_stdin):
        result = mod.main()
    assert result == 0


# ---------------------------------------------------------------------------
# Dash detection (check_dashes) — replaces check_hyphenated_compounds
# ---------------------------------------------------------------------------

def test_flags_non_blocking(mod):
    results = mod.check_dashes(["// non-blocking call", "// skip", "// ok"])
    assert results  # non-empty list means flagged


def test_flags_hard_coded(mod):
    results = mod.check_dashes(["// hard-coded for now", "// revisit", "// skip"])
    assert results


def test_flags_new_prefixes(mod):
    # Prefixes covered by the compound pattern
    cases = [
        "// pre-computed lookup, skip recalc",
        "// auto-generated by schema builder",
        "// type-safe wrapper avoids casts",
        "// thread-safe via lock around map",
        "// lazy-loaded on first access",
        "// self-contained module, no deps",
    ]
    for comment in cases:
        results = mod.check_dashes([comment, "// ok", "// skip"])
        assert results, f"Expected flagging for: {comment!r}"


def test_no_flag_filename_with_dashes(mod):
    # human-voice-guard.py has dashes but is a filename — no compound prefix match
    results = mod.check_dashes([
        "// see human-voice-guard.py for the full list",
        "// runs after every edit",
        "// exit 0 always",
    ])
    assert not results


def test_no_flag_backtick_wrapped(mod):
    # backtick-wrapped identifiers are stripped before checking
    results = mod.check_dashes([
        "// use `non-blocking` pattern instead",
        "// see docs",
        "// no await needed",
    ])
    assert not results


def test_no_flag_cli_flag_dry_run(mod):
    # --dry-run: double-dash flag, suffix 'run' is not a compound prefix
    results = mod.check_dashes([
        "// calls --dry-run mode, no writes happen",
        "// safe to test",
        "// no side effects",
    ])
    assert not results


def test_nudge_on_hyphenated_compound_integration():
    # Full integration: a compound word (dash in comment) triggers a hard block at exit 2
    content = """
// non-blocking call to the cache layer
// returns null if the key is missing
// caller handles the miss
x = cache.get(key)
"""
    result = run_hook("comment-humanness-check.py", _write_with(content))
    assert result.returncode == 2
    assert b"BLOCKED" in result.stderr


# Line 200 — main() returns 0 when no findings (clean code with 3+ comments)
def test_main_returns_0_when_no_findings():
    # Human-style comments: fragments, no dots, not uniform, no banned words
    content = """
# why we do this: avoids a DB round-trip on cold start
x = cached_value()

# skip empty inputs fast
if not items:
    return []

# keeps the list ordered by insert time
items.sort(key=lambda i: i.created_at)
result = process(items)
"""
    result = run_hook("comment-humanness-check.py", _write_with(content))
    assert result.returncode == 0
    assert result.stderr == b""
