"""
Tests for scripts/git-guard.py (PreToolUse/Bash hook).

Behavior under test:
  - Read-only git commands (status, log, diff)   -> exit 0, no output
  - Write git commands (commit, push, checkout)  -> exit 0, ask decision on stdout
  - git -C <dir> <write subcommand>              -> ask (global flags skipped)
  - Conditional subcommands (branch -D vs bare)  -> ask only with write flags
  - Non-git commands                             -> exit 0, no output
"""
from __future__ import annotations

import json

import pytest

from helpers import run_hook, pretooluse


def _bash(command: str) -> dict:
    return pretooluse("Bash", {"command": command})


def _decision(result) -> str | None:
    if not result.stdout.strip():
        return None
    out = json.loads(result.stdout)
    return out.get("hookSpecificOutput", {}).get("permissionDecision")


@pytest.mark.parametrize("command", [
    "git status",
    "git log --oneline -5",
    "git diff --stat",
    "git -C /some/repo show HEAD",
    "ls -la",
    "npm test",
])
def test_passes_read_only_and_non_git(command):
    result = run_hook("git-guard.py", _bash(command))
    assert result.returncode == 0
    assert _decision(result) is None


@pytest.mark.parametrize("command", [
    "git commit -m 'msg'",
    "git push origin main",
    "git checkout -b feature/x",
    "git -C /some/repo commit -m 'msg'",
    "git branch -D old-branch",
    "git stash",
])
def test_asks_on_write_commands(command):
    result = run_hook("git-guard.py", _bash(command))
    assert result.returncode == 0
    assert _decision(result) == "ask"


def test_bare_branch_listing_passes():
    """`git branch` with no write flags is a listing — no ask."""
    result = run_hook("git-guard.py", _bash("git branch"))
    assert result.returncode == 0
    assert _decision(result) is None


def test_stash_list_passes():
    result = run_hook("git-guard.py", _bash("git stash list"))
    assert result.returncode == 0
    assert _decision(result) is None
