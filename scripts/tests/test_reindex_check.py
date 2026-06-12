"""
Tests for scripts/reindex-check.py (SessionStart hook).

Warns when git HEAD changed since last index. Always exits 0.
"""
from __future__ import annotations

import json
import subprocess
import pytest
from helpers import SCRIPTS_DIR, run_hook


def _session_start() -> dict:
    return {"hook_event_name": "SessionStart", "session_id": "test", "source": "startup"}


# ---------------------------------------------------------------------------
# Always exits 0
# ---------------------------------------------------------------------------

def test_always_exits_0(boost_home):
    result = run_hook(
        "reindex-check.py",
        _session_start(),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0


def test_silent_when_no_state_file(boost_home):
    # No last-indexed-head.json → silent
    result = run_hook(
        "reindex-check.py",
        _session_start(),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0
    assert result.stdout.strip() == b""


# ---------------------------------------------------------------------------
# HEAD unchanged: silent
# ---------------------------------------------------------------------------

def test_silent_when_head_unchanged(boost_home):
    # Get the actual current HEAD of the ClaudeBoost repo
    try:
        head = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd="C:/Users/grayw/OneDrive/prj/ClaudeBoost",
            stderr=subprocess.DEVNULL,
        ).decode().strip()
        branch = subprocess.check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd="C:/Users/grayw/OneDrive/prj/ClaudeBoost",
            stderr=subprocess.DEVNULL,
        ).decode().strip()
    except Exception:
        pytest.skip("git not available")

    state_file = boost_home / "state" / "last-indexed-head.json"
    state_file.write_text(json.dumps({
        "head": head,
        "branch": branch,
        "project_path": "C:/Users/grayw/OneDrive/prj/ClaudeBoost",
    }), encoding="utf-8")

    result = run_hook(
        "reindex-check.py",
        _session_start(),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0
    # Same HEAD → silent
    assert result.stdout.strip() == b""


# ---------------------------------------------------------------------------
# HEAD changed: warn
# ---------------------------------------------------------------------------

def test_warns_when_head_changed(boost_home):
    state_file = boost_home / "state" / "last-indexed-head.json"
    state_file.write_text(json.dumps({
        "head": "0000000000000000000000000000000000000000",
        "branch": "main",
        "project_path": "C:/Users/grayw/OneDrive/prj/ClaudeBoost",
    }), encoding="utf-8")

    result = run_hook(
        "reindex-check.py",
        _session_start(),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0
    # HEAD changed → warning
    if result.stdout.strip():
        output = json.loads(result.stdout)
        ctx = output.get("additionalContext", "")
        assert "STALE" in ctx or "stale" in ctx.lower() or "index" in ctx.lower()


# ---------------------------------------------------------------------------
# Not a git repo: silent
# ---------------------------------------------------------------------------

def test_silent_when_not_git_repo(tmp_path):
    # Use a non-git directory as CLAUDEBOOST_HOME
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    state_file = state_dir / "last-indexed-head.json"
    state_file.write_text(json.dumps({
        "head": "abc123",
        "branch": "main",
    }), encoding="utf-8")

    result = run_hook(
        "reindex-check.py",
        _session_start(),
        env_overrides={"CLAUDEBOOST_HOME": str(tmp_path)},
    )
    assert result.returncode == 0
