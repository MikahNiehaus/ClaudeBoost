"""A git write spelled so the ask rule prefix misses it is refused; reads still run."""
from __future__ import annotations

import pytest

from helpers import pretooluse, run_hook


def _exit_code(command: str) -> int:
    return run_hook("bash-guard.py", pretooluse("Bash", {"command": command})).returncode


@pytest.mark.parametrize("command", [
    "git --no-pager push origin main",
    "git -P push origin main",
    "git --bare push",
    "git --no-optional-locks push",
    "git --no-replace-objects push",
    "git --no-pager -C ../repo push",
    "git -C ../repo --no-pager push",
    "git --no-pager commit -m x",
    'git "push" origin main',
    "git pu''sh origin main",
    'git -C ../repo "push"',
    'git "-C" ../repo push',
])
def test_write_spelled_past_the_ask_rule_prefix_is_blocked(command):
    assert _exit_code(command) == 2, command


@pytest.mark.parametrize("command", [
    "git push origin main",
    "git -C ../repo push",
    'git -C "../my repo" push origin main',
    "git commit -m x",
    "git -C ../repo add x",
])
def test_write_spelled_as_the_ask_rule_matches_reaches_its_prompt(command):
    assert _exit_code(command) == 0, command


@pytest.mark.parametrize("command", [
    "git --no-pager log",
    "git -P diff",
    "git --no-pager -C ../repo status",
    "git -C ../repo --no-pager log",
])
def test_read_behind_a_global_flag_still_runs(command):
    assert _exit_code(command) == 0, command
