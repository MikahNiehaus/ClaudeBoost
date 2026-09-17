"""The guard blocked `git restore` and `git branch -d`, and allowed the other
spellings of both.

Its docstring defines the job as blocking git commands that change history, the
working tree beyond the current file edit, or a remote, and says everything
unlisted is read only or index scoped. Three commands broke that:

  git checkout -- <path>      discards uncommitted work, same as `restore`
  git checkout <ref>          replaces the working tree, and can detach HEAD
  git branch --delete <name>  the long form of the blocked -d

Git 2.23 split checkout's two jobs into `switch` and `restore` (git-switch(1),
git-restore(1)), so the three names spell one operation between them. Blocking
one of them enforced a third of a rule.

These are ordinary commands an agent reaches for by mistake, not constructed
bypasses. spec/architecture-changes/hooks-shell-guard-denylist-ceiling.md
stopped the rounds of exotic-spelling patching on this family and named that
distinction as the line: record the exotic ones, fix the ones reachable by an
ordinary mistake. It also decided this guard stays a denylist, so these are
added to the list rather than the guard being reshaped.
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
        "git checkout -- src/app.py",
        "git checkout .",
        "git checkout main -- other_file.py",
        "git checkout feature/other-branch",
        "git checkout -b scratch",
        "git switch main",
        "git switch -c scratch",
        "git branch --delete stale-branch",
        "git branch --delete --force stale-branch",
        "git tag --delete v1.0.0",
        "true;git checkout -- src/app.py",
        "git -C /some/repo checkout main",
    ],
)
def test_the_working_tree_writes_are_blocked(command):
    result = _run(command)
    assert result.returncode == 2, (
        f"verify-loop-git-guard.py allowed a working-tree write "
        f"(exit {result.returncode}): {command!r}\nstderr: {result.stderr}"
    )


@pytest.mark.parametrize(
    "command",
    [
        "git status",
        "git status --porcelain",
        "git diff HEAD",
        "git log --oneline -5",
        "git show HEAD:clean-rag/hooks/verifier_state.py",
        "git blame clean-rag/hooks/verifier_state.py",
        "git branch",
        "git branch --list",
        "git tag",
        "git add clean-rag/hooks/verifier_state.py",
        "python -m pytest -q",
    ],
)
def test_the_read_only_work_these_agents_need_still_runs(command):
    """The guard exists to stop unauthorized git writes, not to stop bad-cop
    reading a diff. Every one of these is in its own refusal message's list of
    what stays allowed."""
    result = _run(command)
    assert result.returncode == 0, (
        f"verify-loop-git-guard.py refused ordinary read-only work "
        f"(exit {result.returncode}): {command!r}\nstderr: {result.stderr}"
    )


def test_the_previously_blocked_spellings_are_unchanged():
    """Pinned so a future edit cannot fix the long forms while dropping the
    short ones."""
    for command in ("git restore src/app.py", "git branch -d x", "git branch -D x",
                    "git tag -d v1.0.0", "git commit -am wip", "git push origin main"):
        assert _run(command).returncode == 2, command
