"""
Tests for scripts/comment-humanness-check.py (PostToolUse on Edit/Write).

Nudges when comments look AI-generated. Always exits 0.
"""
from __future__ import annotations

import json
import pytest
from helpers import SCRIPTS_DIR, run_hook, posttooluse


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
# Dash separator: nudge
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
    assert result.returncode == 0
    # " - " as separator should trigger nudge
    assert b"comment-humanness" in result.stderr


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
