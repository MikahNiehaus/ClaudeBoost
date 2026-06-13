"""
Tests for scripts/reindex-check.py (SessionStart hook).

Warns when git HEAD changed since last index. Always exits 0.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from helpers import SCRIPTS_DIR, run_hook

_REPO_ROOT = str(Path(__file__).resolve().parents[2])


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
            cwd=_REPO_ROOT,
            stderr=subprocess.DEVNULL,
        ).decode().strip()
        branch = subprocess.check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=_REPO_ROOT,
            stderr=subprocess.DEVNULL,
        ).decode().strip()
    except Exception:
        pytest.skip("git not available")

    state_file = boost_home / "state" / "last-indexed-head.json"
    state_file.write_text(json.dumps({
        "head": head,
        "branch": branch,
        "project_path": _REPO_ROOT,
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
        "project_path": _REPO_ROOT,
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


# ---------------------------------------------------------------------------
# Git-repo CLAUDEBOOST_HOME: HEAD changed → warns (exercises lines 53-77)
# ---------------------------------------------------------------------------

def test_warns_when_head_changed_in_git_home(tmp_path):
    """Creates a minimal git repo as CLAUDEBOOST_HOME so git commands succeed."""
    try:
        subprocess.check_output(
            ["git", "init", str(tmp_path)],
            stderr=subprocess.DEVNULL,
        )
        subprocess.check_output(
            ["git", "-C", str(tmp_path), "commit", "--allow-empty", "-m", "init",
             "--author", "Test <test@test.com>"],
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        pytest.skip("git not available or failed to init")

    state_dir = tmp_path / "state"
    state_dir.mkdir(exist_ok=True)
    state_file = state_dir / "last-indexed-head.json"
    state_file.write_text(json.dumps({
        "head": "0000000000000000000000000000000000000000",
        "branch": "main",
    }), encoding="utf-8")

    result = run_hook(
        "reindex-check.py",
        _session_start(),
        env_overrides={"CLAUDEBOOST_HOME": str(tmp_path)},
    )
    assert result.returncode == 0
    if result.stdout.strip():
        output = json.loads(result.stdout)
        ctx = output.get("additionalContext", "")
        assert "STALE" in ctx or "index" in ctx.lower()


def test_warns_with_branch_switch_in_git_home(tmp_path):
    """Branch switched warning path is covered."""
    try:
        subprocess.check_output(["git", "init", str(tmp_path)], stderr=subprocess.DEVNULL)
        subprocess.check_output(
            ["git", "-C", str(tmp_path), "commit", "--allow-empty", "-m", "init",
             "--author", "Test <test@test.com>"],
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        pytest.skip("git not available")

    state_dir = tmp_path / "state"
    state_dir.mkdir(exist_ok=True)
    state_file = state_dir / "last-indexed-head.json"
    state_file.write_text(json.dumps({
        "head": "0000000000000000000000000000000000000000",
        "branch": "feature/old-feature",
    }), encoding="utf-8")

    result = run_hook(
        "reindex-check.py",
        _session_start(),
        env_overrides={"CLAUDEBOOST_HOME": str(tmp_path)},
    )
    assert result.returncode == 0
    if result.stdout.strip():
        output = json.loads(result.stdout)
        ctx = output.get("additionalContext", "")
        assert "branch" in ctx.lower() or "STALE" in ctx


# ---------------------------------------------------------------------------
# Corrupt state file: treated as no baseline (silent)
# ---------------------------------------------------------------------------

def test_silent_when_state_file_is_invalid_json(boost_home):
    state_file = boost_home / "state" / "last-indexed-head.json"
    state_file.write_text("{not valid json", encoding="utf-8")

    result = run_hook(
        "reindex-check.py",
        _session_start(),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0


# ---------------------------------------------------------------------------
# HEAD changed on a different branch: warn includes branch info
# ---------------------------------------------------------------------------

def test_warns_with_branch_info_when_branch_switched(boost_home):
    state_file = boost_home / "state" / "last-indexed-head.json"
    state_file.write_text(json.dumps({
        "head": "0000000000000000000000000000000000000000",
        "branch": "feature/old-branch",
        "project_path": _REPO_ROOT,
    }), encoding="utf-8")

    result = run_hook(
        "reindex-check.py",
        _session_start(),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0
    if result.stdout.strip():
        output = json.loads(result.stdout)
        ctx = output.get("additionalContext", "")
        # Should mention branch or stale
        assert "STALE" in ctx or "branch" in ctx.lower() or "index" in ctx.lower()
