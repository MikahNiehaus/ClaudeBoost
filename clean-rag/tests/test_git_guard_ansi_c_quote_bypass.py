"""A quoted span whose escaping is read wrong swallows the separator after it.

pad_shell_operators() used to track quote state by matching a single
character against the quote it opened with, with no escape handling at all.
That is right for '...', where a backslash means nothing and the span ends at
the very next quote. It is wrong for the other two forms a shell has:

* $'...' is ANSI-C quoting, where a backslash escapes what follows, so \\' is
  a literal quote that does NOT close the span (Shell Command Language 2.2.3).
* "..." escapes a backslash before $, `, ", \\ or a newline, so \\" is a
  literal quote that does not close the span either. This one needs no '$'
  and no shell extension, only an escaped quote in an ordinary argument.

Reading either as the end of the span closes it one character early. The real
closing quote is then misread as OPENING a fresh span, and everything after
it, including a real unquoted ';' followed by a blocked write, is walked as
"inside a quote" and never padded. It stays fused to "git" in shlex's output
and verify-loop-git-guard.py's token equality check (`binary != "git"`) never
fires.

This is the exact incident verify-loop-git-guard.py's own module docstring
names, good-cop reaching a remote with `git push` and nobody having asked it
to, reachable again through a form of quoting neither
test_shell_token_padding.py nor test_git_guard_unspaced_chaining_bypass.py
exercises.

quick-cop-bash-guard.py shares the same scan. Its single posix=True
shlex.split() covers it whenever the mis-read leaves a quote unbalanced, but
not when it does not: the double-quoted cases below parse cleanly and reached
an `rm -rf` behind the ';'. Both guards are exercised here for that reason.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

HOOKS = Path(__file__).resolve().parents[1] / "hooks"
sys.path.insert(0, str(HOOKS))

from shell_tokens import pad_shell_operators  # noqa: E402

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


def test_the_separator_after_an_ansi_c_quote_gets_a_boundary():
    """Root cause, isolated from either guard: the ';' after a $'...' literal
    is a real separator and has to come back padded.

    Asserted as the exact output rather than as "a padded ';' appears
    somewhere", because the span before it must survive untouched too: padding
    inside the literal would rewrite the argument's own data.
    """
    command = r"""echo $'it\'s fine';git push origin main"""
    assert pad_shell_operators(command) == r"""echo $'it\'s fine' ; git push origin main"""


def test_the_separator_after_an_escaped_double_quote_gets_a_boundary():
    r"""The same confusion with no $'...' anywhere: inside "..." a backslash
    escapes the quote (POSIX 2.2.3), so `\"` does not end the span. Reading it
    as the end leaves the following ';' looking quoted and un-padded."""
    command = r'''echo "a\"b";git push origin main'''
    assert pad_shell_operators(command) == r'''echo "a\"b" ; git push origin main'''


@pytest.mark.parametrize(
    "command",
    [
        r"""echo $'it\'s fine';git push origin main""",
        r"""x=$'\'a';git push origin main""",
        r"""echo $'\'x';git commit -am wip""",
        # Two $'...' literals leave the escape-confused scan balanced at the
        # end of the string, so an "unterminated quote" check alone does not
        # notice that the separators between them were swallowed.
        r"""echo $'\'a';echo hi;git push origin main;echo $'\'b'""",
        # No $'...' at all: an escaped quote inside "..." is the same
        # confusion in the quoting form every shell has.
        r'''echo "a\"b";git push origin main''',
        r'''grep -rn "x\"y" src/;git commit -am wip''',
    ],
)
def test_a_misread_quoted_span_cannot_hide_a_routed_git_write(command):
    """A quoted literal whose escaping the scan gets wrong, followed with no
    space by a real ';git push', must not reach an ordinary git push with the
    guard reporting allow (exit 0) instead of block (exit 2)."""
    result = _run("verify-loop-git-guard.py", command)
    assert result.returncode == 2, (
        f"verify-loop-git-guard.py allowed a routed git write through quoted "
        f"span confusion (exit {result.returncode}): {command!r}\n"
        f"stderr: {result.stderr}"
    )


@pytest.mark.parametrize(
    "command",
    [
        r"""x=$'\'a';git push origin main""",
        # This one is not covered by the ValueError path: the padded string
        # parses cleanly in posix mode, so a mis-read span is the only thing
        # standing between quick-cop and the mutation behind the ';'.
        r'''echo "a\"b";rm -rf important_dir''',
        r'''echo "a\"b";npm install evil''',
    ],
)
def test_the_read_only_cage_holds_against_the_same_confusion(command):
    """quick-cop-bash-guard.py shares this scan and is refused by the same
    correction. Its own ValueError path saves it only when the mis-read
    happens to leave a quote unbalanced, which the double-quoted cases here
    do not, so the padding itself has to be right."""
    result = _run("quick-cop-bash-guard.py", command)
    assert result.returncode == 2, (
        f"quick-cop-bash-guard.py allowed a mutation behind a mis-read quoted "
        f"span (exit {result.returncode}): {command!r}\nstderr: {result.stderr}"
    )


@pytest.mark.parametrize(
    "command",
    [
        r"""git log --grep=$'don\'t'""",
        # git reached through a separator with no space in front of it, which
        # is the shape the mention check has to recognise on this path.
        r"""true;git log --grep=$'don\'t'""",
        r"""pytest -q;git show $'a\'b'""",
    ],
)
def test_half_a_reading_is_not_a_clean_bill_of_health(command):
    """These pad correctly and then split cleanly in one shlex mode and raise
    in the other, and the mode that works reports a read only subcommand.

    Taking that as the answer is choosing the more permissive of two readings
    on the strength of the other one having failed, which is what let a padder
    bug through as an allow. The guard has seen only part of the command, so
    a command that mentions git at all is refused instead.
    """
    result = _run("verify-loop-git-guard.py", command)
    assert result.returncode == 2, (
        f"verify-loop-git-guard.py accepted a partial reading of a git command "
        f"(exit {result.returncode}): {command!r}\nstderr: {result.stderr}"
    )


def test_a_partial_reading_of_ordinary_work_still_runs():
    """The other side of it. This is a git-only denylist, so a command with no
    git in it is out of scope even when its quoting cannot be read, and the
    broad Bash these agents need for builds and tests keeps working."""
    result = _run("verify-loop-git-guard.py", r"""pytest -k $'a\'b' -q""")
    assert result.returncode == 0, (
        f"exit {result.returncode} for an unparseable command with no git in "
        f"it\nstderr: {result.stderr}"
    )


def test_the_spaced_equivalent_is_still_caught():
    """Sanity: the identical write, spelled with a space before the
    semicolon, is exactly what the existing suite already proves is caught."""
    result = _run(
        "verify-loop-git-guard.py",
        r"""echo $'it\'s fine'; git push origin main""",
    )
    assert result.returncode == 2
