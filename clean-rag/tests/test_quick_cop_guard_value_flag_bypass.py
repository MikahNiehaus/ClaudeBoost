"""quick-cop-bash-guard.py's own _check_subcommand_chain() walks a git
invocation by skipping every token that starts with '-' and then reading the
subcommand off whatever token follows. That works for a flag with no value
(`git --bare status`) and for a flag whose value is fused into the same token
(`git --git-dir=/x/.git commit`), but a global git flag whose value is its own
separate token -- `-C <path>`, `-c <key>=<value>`, `--work-tree <path>` -- is
not accounted for at all. The loop's own skip-leading-dashes scan stops at the
first non-dash token, which is the flag's VALUE, not the subcommand, so that
value is read as `sub` and checked against `_GIT_BLOCKED` instead of the real
subcommand a few tokens later. The real subcommand token then falls through
the rest of `_check_subcommand_chain`'s walk as an ordinary, unrecognised
word, because only the `binary == "git"` branch would have recognised it, and
that branch only fires on a `git` token, not on the token after one.

verify-loop-git-guard.py already gets this right; it has a `_VALUE_FLAGS` set
built for exactly this reason (`git -C "path" commit -m "..."` is the example
in its own comment). quick-cop-bash-guard.py has no equivalent set at all.

This defeats quick-cop's read-only cage on real `git commit` and real
`git push`, not a parsing edge case: the command runs exactly as typed.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

HOOKS = Path(__file__).resolve().parents[1] / "hooks"
GUARD = "quick-cop-bash-guard.py"

_ENV_ALLOWLIST = frozenset({
    "PATH", "PATHEXT", "COMSPEC", "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR",
    "TEMP", "TMP", "TMPDIR",
    "PYTHONHOME", "PYTHONIOENCODING", "PYTHONUTF8", "LANG", "LC_ALL",
})


def _hermetic_env() -> dict:
    return {k: v for k, v in os.environ.items() if k.upper() in _ENV_ALLOWLIST}


def _bash(command: str) -> str:
    return json.dumps({"tool_name": "Bash", "tool_input": {"command": command}})


def _run(command: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(HOOKS / GUARD)],
        input=_bash(command),
        capture_output=True,
        text=True,
        env=_hermetic_env(),
    )


@pytest.mark.parametrize(
    "command",
    [
        "git -C /some/repo commit -m x",
        "git -c user.name=x push",
        "git -c user.email=x -c user.name=y push origin main",
        "git --work-tree /some/repo commit -m x",
        "git -C /some/repo -c user.name=x push",
    ],
)
def test_a_global_flags_own_value_token_is_not_mistaken_for_the_subcommand(command):
    """Every one of these really commits or pushes; -C, -c and --work-tree
    all take their value as a separate argv entry in real git, not fused into
    the flag's own token, so the subcommand sits one token further out than
    this guard's skip-leading-dashes scan accounts for."""
    result = _run(command)
    assert result.returncode == 2, (
        f"quick-cop-bash-guard.py allowed a git write past a value-taking "
        f"global flag (exit {result.returncode}): {command!r}\n"
        f"stderr: {result.stderr}"
    )


def test_the_fused_value_form_of_the_same_flag_is_already_caught():
    """Sanity, so a fix cannot regress this: --git-dir=/x/.git is one token,
    so the existing leading-dash skip already lands on the real subcommand
    right after it."""
    result = _run("git --git-dir=/x/.git commit -m x")
    assert result.returncode == 2


def test_a_value_flag_with_no_git_state_change_after_it_still_runs():
    """The other side of it: quick-cop still needs plain read-only git to
    work, including through a value-taking global flag."""
    result = _run("git -C /some/repo status")
    assert result.returncode == 0, (
        f"exit {result.returncode} for read-only git behind -C\n"
        f"stderr: {result.stderr}"
    )
