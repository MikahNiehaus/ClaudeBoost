"""Command substitution inside a double-quoted string is still live in a real
shell. Quoting suppresses word-splitting and globbing of its OUTPUT; it does
not suppress the substitution itself, only a single-quoted span does that
(POSIX 2.2.3, and 2.6.3 Command Substitution: "the shell shall expand [it] by
executing command in a subshell environment"). Confirmed against a real bash
in this repo's own environment:

    $ echo "prefix $(echo INNER_RAN) suffix"
    prefix INNER_RAN suffix
    $ x="$(echo INNER_RAN)"; echo "captured: $x"
    captured: INNER_RAN

pad_shell_operators()'s double-quoted span scan does not know this. It reads
`"..."` looking only for the next unescaped `"`, so a `$(...)` or `` `...` ``
nested inside the span is copied through as inert data, exactly like the text
of a commit message would be. shlex then sees the whole span, git subcommand
and all, as one quoted token, and the guards' token-equality check for "git"
(or a blocked binary) never fires -- not because the quote confused it, but
because nothing inside a `"..."` span is ever looked at for a nested `$(` or
backtick at all.

This is not the escaped-quote bug the previous two rounds fixed. That bug
made the scanner misjudge where a span ENDS. This one is a span that ends
exactly where a shell would end it, and is otherwise read correctly -- the
gap is that a real shell still executes something inside it, and the scanner
has no model of that at all. No unbalanced quote, no incomplete parse: this
reaches `_find_blocked_subcommand` / `_check_subcommand_chain` with a clean,
complete tokenization that just never contains a "git" or "rm" token, because
that token was hidden inside a quoted string the shell doesn't actually treat
as inert.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

HOOKS = Path(__file__).resolve().parents[1] / "hooks"

_ENV_ALLOWLIST = frozenset({
    "PATH", "PATHEXT", "COMSPEC", "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR",
    "TEMP", "TMP", "TMPDIR",
    "PYTHONHOME", "PYTHONIOENCODING", "PYTHONUTF8", "LANG", "LC_ALL",
})


def _hermetic_env() -> dict:
    return {k: v for k, v in os.environ.items() if k.upper() in _ENV_ALLOWLIST}


def _bash(command: str) -> str:
    return json.dumps({"tool_name": "Bash", "tool_input": {"command": command}})


def _run(guard: str, command: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(HOOKS / guard)],
        input=_bash(command),
        capture_output=True,
        text=True,
        env=_hermetic_env(),
    )


@pytest.mark.parametrize(
    "command",
    [
        'echo "$(git push origin main)"',
        'echo "prefix $(git push origin main) suffix"',
        'x="$(git push origin main)"; echo $x',
        'echo "`git push origin main`"',
        'echo "`git commit -am wip`"',
        'echo "$(git commit -am wip)"',
    ],
)
def test_git_write_nested_in_a_double_quoted_substitution_is_not_allowed(command):
    """Every one of these really runs `git push` or `git commit` in a
    subshell the moment a real shell parses the line, regardless of the
    surrounding double quotes. verify-loop-git-guard.py exists specifically
    to stop bad-cop/good-cop from reaching a remote on their own."""
    result = _run("verify-loop-git-guard.py", command)
    assert result.returncode == 2, (
        f"verify-loop-git-guard.py allowed a git write hidden inside a "
        f"double-quoted command substitution (exit {result.returncode}): "
        f"{command!r}\nstderr: {result.stderr}"
    )


@pytest.mark.parametrize(
    "command",
    [
        'echo "$(rm -rf important_dir)"',
        'echo "$(npm install evil-package)"',
        'x="$(rm -rf important_dir)"',
        'echo "`rm -rf important_dir`"',
    ],
)
def test_the_read_only_cage_is_not_defeated_by_the_same_construct(command):
    """quick-cop-bash-guard.py shares pad_shell_operators() and the same gap:
    a blocked binary hidden inside a nested, double-quoted $(...) or
    backtick substitution still executes, and the guard has to see that."""
    result = _run("quick-cop-bash-guard.py", command)
    assert result.returncode == 2, (
        f"quick-cop-bash-guard.py allowed a mutation hidden inside a "
        f"double-quoted command substitution (exit {result.returncode}): "
        f"{command!r}\nstderr: {result.stderr}"
    )


@pytest.mark.parametrize(
    "command",
    [
        'echo "$(printf hi > secrets.txt)"',
        'echo "$(cat a > b)"',
        'echo "$(grep -r x . >> log.txt)"',
    ],
)
def test_a_redirect_inside_the_substitution_is_a_real_write(command):
    """The same root cause reaches quick-cop's write-redirection check, which
    reads the command with quoted spans removed. A '>' inside a double-quoted
    substitution really does create a file, so removing it as quoted data hid
    the write even when the binary running it was on the allowlist."""
    result = _run("quick-cop-bash-guard.py", command)
    assert result.returncode == 2, (
        f"quick-cop-bash-guard.py allowed a write redirection hidden inside a "
        f"double-quoted command substitution (exit {result.returncode}): "
        f"{command!r}\nstderr: {result.stderr}"
    )


def test_a_literal_angle_bracket_in_a_quoted_argument_still_runs():
    """The other side of that: a '>' inside plain double quotes is data, not a
    redirection, and refusing it would block ordinary grep and echo work."""
    result = _run("quick-cop-bash-guard.py", 'echo "a > b"')
    assert result.returncode == 0, (
        f"exit {result.returncode} for a literal '>' in a quoted argument\n"
        f"stderr: {result.stderr}"
    )


@pytest.mark.parametrize(
    "command",
    [
        r'echo "\$(git push origin main)"',
        r'echo "\`git push origin main\`"',
    ],
)
def test_an_escaped_dollar_or_backtick_is_literal_text(command):
    r"""Inside "...", a backslash before '$' or '`' suppresses the expansion
    (POSIX 2.2.3), so these print the text and push nothing. Confirmed against
    a real bash: `echo "escaped: \$(echo SHOULD_NOT_RUN)"` prints
    `escaped: $(echo SHOULD_NOT_RUN)`. Refusing them would be a false block."""
    result = _run("verify-loop-git-guard.py", command)
    assert result.returncode == 0, (
        f"exit {result.returncode} for text a shell never executes: {command!r}\n"
        f"stderr: {result.stderr}"
    )


def test_the_same_construct_at_top_level_unquoted_is_already_caught():
    """Sanity, so a fix cannot regress this: `(` and `)` are padded as
    operators outside any quoted span, so an unquoted $(...) or bare
    backtick invocation already exposes "git" as its own token."""
    result = _run("verify-loop-git-guard.py", "echo $(git push origin main)")
    assert result.returncode == 2
    result = _run("verify-loop-git-guard.py", r"echo `git push origin main`")
    assert result.returncode == 2


def test_single_quoting_the_same_text_is_correctly_left_alone():
    """The other side of it: inside '...', $ is a literal character and no
    substitution happens at all in a real shell, so this is not a case the
    guard needs to catch and refusing it would be a false block."""
    result = _run("verify-loop-git-guard.py", "echo '$(git push origin main)'")
    assert result.returncode == 0, (
        "a single-quoted literal is not a live command substitution in any "
        f"real shell; refusing it is a false block (exit {result.returncode})"
    )
