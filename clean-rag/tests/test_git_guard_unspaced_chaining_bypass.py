"""verify-loop-git-guard.py finds a routed git write by shlex.split()-ing the
raw command and looking for a "git" token among the results. That only works
if shlex.split() actually breaks the command apart at the same places a real
shell would.

It does not. Python's shlex, in both posix and non-posix mode, treats ';',
'|', and '&' as ordinary word characters, not separators -- it only splits on
whitespace and quotes. A real POSIX shell needs no whitespace around any of
those three (`true;git push` is exactly as valid, and pushes exactly the same
way, as `true ; git push`). So a command with no space before the chaining
character tokenizes as one fused word ("true;git", not "true" and "git"),
`binary != "git"` is true for that fused token, and the entire denylist never
fires -- on the *successful* tokenization path, with no malformed quoting
required at all.

This is a different bug from the one the guard's docstring and
test_verify_loop_guard_fails_open_on_parse_error.py already cover (the
shlex.split() ValueError path). Those commands are ones the guard cannot
parse. These are commands the guard parses successfully and still misreads,
which is worse: nothing here looks unusual to either tokenizer.

Reproduces the exact incident verify-loop-git-guard.py's own module docstring
names: an agent running `git push` on its own, unauthorized.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

HOOKS = Path(__file__).resolve().parents[1] / "hooks"
GUARD = "verify-loop-git-guard.py"

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
        "true;git push origin main",
        "echo ok;git push origin main",
        "true|git push origin main",
        "true&git push origin main",
        "echo hi;git commit -am wip",
        "echo hi;git reset --hard HEAD~1",
    ],
)
def test_unspaced_chaining_before_git_still_reaches_a_blocked_subcommand(command):
    """No malformed quoting anywhere in these. Both shlex tokenizations
    succeed; they just fuse the chaining character onto the previous word
    instead of splitting on it, so the denylist's own token-equality check
    (`binary != "git"`) never sees a bare "git" token to compare against."""
    result = _run(command)
    assert result.returncode == 2, (
        f"verify-loop-git-guard.py allowed a routed git write through unspaced "
        f"chaining (exit {result.returncode}): {command!r}\n"
        f"stderr: {result.stderr}"
    )


def test_spaced_chaining_before_git_is_still_caught():
    """Sanity check: the same write, spelled with a space before the
    separator, is exactly what the existing suite already proves is caught.
    Pinned here too so a future fix cannot regress the case that already
    worked while only patching the unspaced one."""
    result = _run("true && git push origin main")
    assert result.returncode == 2


@pytest.mark.parametrize(
    "command",
    [
        "(git push)",
        "echo $(git push)",
        "echo `git push`",
        "pytest -q\ngit push origin main",
    ],
)
def test_other_characters_that_start_a_command_also_reach_the_denylist(command):
    """A semicolon is not the only thing a shell reads as the start of a new
    command. A subshell, a command substitution and a newline each run what
    follows them, and none of them is whitespace."""
    result = _run(command)
    assert result.returncode == 2, (
        f"exit {result.returncode} for {command!r}\nstderr: {result.stderr}"
    )


@pytest.mark.parametrize(
    "command",
    [
        "git status",
        "python -m pytest -q;git log --oneline -5",
        "python -m pytest scripts/tests -q && git diff",
        "git log --format=%(refname) -3",
        'grep -rn "git push" scripts/',
        'echo "true;git push"',
        r"find . -name '*.py' -exec grep -l foo {} \;",
        "npm test 2>&1 | tail -5",
    ],
)
def test_reading_a_separator_correctly_does_not_cost_ordinary_work(command):
    """The verify loop's whole job needs broad Bash: run the suite, read the
    diff, grep the tree. A git token quoted, escaped, or attached to a read
    only subcommand is not a write, and treating separators the way a shell
    does must not turn any of these into one."""
    result = _run(command)
    assert result.returncode == 0, (
        f"exit {result.returncode} for {command!r}\nstderr: {result.stderr}"
    )
