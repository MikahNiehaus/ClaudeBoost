"""A long flag spelled short is still a delete.

`_deletes_a_ref` matched `token.startswith("--delete")`, so the fully spelled
flag blocked and every abbreviation of it did not. git does not require the
full spelling: parse-options resolves any unambiguous prefix of a long option,
and `--delete` is the only long option beginning with 'd' on either subcommand
(git 2.55 `git branch -h`, `git tag -h`), so `--d` through `--delet` all
delete.

Measured against git 2.55.0.windows.5 in a throwaway repo, without deleting
anything: each prefix reaches ref lookup and reports `branch 'no-such-branch'
not found` (exit 1), while a non-prefix such as `--dx` is rejected at parse
time with `unknown option` (exit 129). Resolution, not deletion, is what the
guard has to match.

Same class as GHSA-2f96-g7mh-g2hx in GitPython, where a blocklist of exact
long options was bypassed by `--conf` for `--config`.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

GUARD = Path(__file__).resolve().parents[1] / "hooks" / "verify-loop-git-guard.py"

_ENV_ALLOWLIST = frozenset({
    "PATH", "PATHEXT", "COMSPEC", "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR",
    "TEMP", "TMP", "TMPDIR",
    "PYTHONHOME", "PYTHONIOENCODING", "PYTHONUTF8", "LANG", "LC_ALL",
})


def _hermetic_env() -> dict:
    return {k: v for k, v in os.environ.items() if k.upper() in _ENV_ALLOWLIST}


def _run(command: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(GUARD)],
        input=json.dumps({"tool_name": "Bash", "tool_input": {"command": command}}),
        capture_output=True,
        text=True,
        env=_hermetic_env(),
    )


@pytest.mark.parametrize(
    "command",
    [
        "git branch --d stale-branch",
        "git branch --de stale-branch",
        "git branch --del stale-branch",
        "git branch --dele stale-branch",
        "git branch --delet stale-branch",
        "git tag --d v1.0.0",
        "git tag --de v1.0.0",
        "git tag --del v1.0.0",
        'git branch "--del" stale-branch',
        "git status && git branch --del stale-branch",
    ],
)
def test_an_unambiguous_git_abbreviation_of_delete_is_still_a_delete(command):
    result = _run(command)
    assert result.returncode == 2, (
        f"verify-loop-git-guard.py allowed a real git delete abbreviation "
        f"(exit {result.returncode}): {command!r}\nstderr: {result.stderr}"
    )


@pytest.mark.parametrize(
    "command",
    [
        "git branch --dry-run new-branch",
        "git branch --dx new-branch",
        "git branch --no-delete new-branch",
        "git branch --merged main",
        "git tag --contains HEAD",
    ],
)
def test_a_long_option_git_cannot_resolve_to_delete_is_not_refused(command):
    """Only a prefix of `--delete` can reach the delete option, so the first
    two must stay allowed: git rejects both at parse time (`unknown option`,
    exit 129) and neither can ever become a delete. Refusing every `--d...`
    instead would block them, and would block whatever non-delete option
    beginning with 'd' a future git adds.

    `--no-delete` is git's own negated spelling and creates a branch rather
    than deleting one, measured: it parses through to `not a valid object
    name`."""
    result = _run(command)
    assert result.returncode == 0, (
        f"verify-loop-git-guard.py refused a non-delete option "
        f"(exit {result.returncode}): {command!r}\nstderr: {result.stderr}"
    )
