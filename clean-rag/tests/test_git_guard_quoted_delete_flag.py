"""The delete flags were matched against the raw command text, so a quote hid
them and a quoted argument invented them.

`git branch "-d" stale-branch` deleted the ref with no refusal. The regexes
required the flag to sit directly after whitespace in the unparsed string, and
`git_subcommand` only ever reports "branch" or "tag" for these, neither of
which is in _BLOCKED_SUBCOMMANDS, so that one raw match was the whole block.
Grouping the short options hid them the same way: `-dr` is the spelling
git-branch(1) documents as `(-d|-D) [-r]`.

It failed in the other direction too, on ordinary work these agents do all day.
`grep -rn "branch --delete" clean-rag` and `git stash push -m "drop this"` were
both refused, because a pattern and a commit message are text the raw scan
cannot tell from a flag.

Both directions are the same defect: flags read from the raw string while the
subcommand is read from shlex tokens. The tokens are quote aware, so the fix is
to read the flags from the same place. The spellings below come from
git-branch(1) and git-tag(1) rather than from guesswork.

One spelling is left open on purpose. shlex does not expand `$'...'`, so
`git branch $'-d' x` is not blocked, and neither is `git $'push' origin main`
against the older subcommand check beside it. The test near the bottom asserts
the refusal that does not happen and carries an xfail marker, so the gap is
reported as a gap instead of passing quietly. See
hooks-shell-guard-denylist-ceiling.md.
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
        'git branch "-d" stale-branch',
        "git branch '-d' stale-branch",
        'git branch "-D" stale-branch',
        'git branch "--delete" stale-branch',
        'git tag "-d" v1.0.0',
        'git tag "--delete" v1.0.0',
        'git "branch" "-d" stale-branch',
        "git branch -dr origin/gone",
        "git branch -rd origin/gone",
        'git branch --delete-merged "topic/*"',
        'git -C /some/repo branch "-d" stale-branch',
        'true;git branch "-d" stale-branch',
        'git status && git tag "-d" v1.0.0',
    ],
)
def test_a_quoted_or_grouped_delete_flag_is_still_a_delete(command):
    result = _run(command)
    assert result.returncode == 2, (
        f"verify-loop-git-guard.py allowed a ref delete "
        f"(exit {result.returncode}): {command!r}\nstderr: {result.stderr}"
    )


@pytest.mark.parametrize(
    "command",
    [
        'echo "branch -d is blocked"',
        'grep -rn "branch --delete" clean-rag',
        'python -m pytest -q -k "branch and -d"',
        'git stash push -m "drop this"',
        'git commit-graph verify',
        "git branch --list; ls -ld .",
        "git tag --list && ls -lda .",
        'git log --grep="branch -d"',
        "git branch --list",
        "git tag -l",
        "git stash list",
    ],
)
def test_the_same_words_inside_an_argument_are_not_a_flag(command):
    """A pattern, a message and a later command's flags are arguments, not
    flags to git. Refusing them costs these agents ordinary read only work,
    which is the half of the contract the refusal message itself promises."""
    result = _run(command)
    assert result.returncode == 0, (
        f"verify-loop-git-guard.py refused ordinary work "
        f"(exit {result.returncode}): {command!r}\nstderr: {result.stderr}"
    )


def test_an_unreadable_quote_still_refuses_a_git_command():
    """Reading flags from tokens means a command that will not tokenize has no
    flags to read. That path must still refuse, not fall through to allow."""
    result = _run('git branch -d "stale-branch')
    assert result.returncode == 2, (
        f"an unparseable git command was allowed: stderr {result.stderr}"
    )


@pytest.mark.xfail(
    strict=True,
    reason="open gap: shlex does not expand $'...', so the flag and the "
           "subcommand both arrive unrecognised. Recorded in "
           "spec/architecture-changes/hooks-shell-guard-denylist-ceiling.md",
)
@pytest.mark.parametrize(
    "command",
    [
        "git branch $'-d' stale-branch",
        "git $'push' origin main",
    ],
)
def test_an_ansi_c_quoted_git_write_is_still_a_git_write(command):
    """The recorded ceiling, asserted as the contract it fails rather than as
    a fact about today.

    shlex does not expand `$'...'`, so `git branch $'-d' x` arrives as the
    token `$-d`, and `git $'push' origin main` is unrecognised the same way one
    level up. Both should refuse and neither does.

    An earlier version asserted the two agreed with each other, which was true
    of a guard that blocked nothing at all, so a green suite implied coverage
    of an input nobody covers. The assertion below is the real one; `strict`
    turns it into a failure the moment either case starts blocking, which is
    what forces this marker and the spec section to move together.
    """
    assert _run(command).returncode == 2


def test_the_previously_blocked_spellings_are_unchanged():
    """Pinned so a future edit cannot fix the quoted forms while dropping the
    bare ones."""
    for command in ("git branch -d x", "git branch -D x", "git branch --delete x",
                    "git tag -d v1.0.0", "git tag --delete v1.0.0",
                    "git stash drop", "git stash clear", "git stash pop",
                    "git commit -am wip", "git push origin main"):
        assert _run(command).returncode == 2, command
