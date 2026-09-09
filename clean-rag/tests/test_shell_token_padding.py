"""pad_shell_operators() is the shared primitive both Bash guards use to find
the boundary a shell would find. shlex splits only on whitespace and quotes, so
without this a command chained with no space around ';', '|' or '&' tokenizes
as one fused word and the guards' binary checks never fire.

Tested at the function level as well as through the guards, because two of its
branches are correct in a direction the guards cannot currently observe: a
padded operator inside a quoted span stays one shlex token either way, and an
escaped operator is not a separator in a real shell either. Both are load
bearing the moment anything reads the padded string with a regex rather than
shlex, and neither should be removed as dead weight.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

HOOKS = Path(__file__).resolve().parents[1] / "hooks"
sys.path.insert(0, str(HOOKS))

from shell_tokens import UnbalancedQuote, pad_shell_operators  # noqa: E402

_ENV_ALLOWLIST = frozenset({
    "PATH", "PATHEXT", "COMSPEC", "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR",
    "TEMP", "TMP", "TMPDIR",
    "PYTHONHOME", "PYTHONIOENCODING", "PYTHONUTF8", "LANG", "LC_ALL",
})


@pytest.mark.parametrize(
    "command, expected",
    [
        ("true;git push", "true ; git push"),
        ("true|git push", "true | git push"),
        ("true&git push", "true & git push"),
        ("true&&git push", "true &  & git push"),
        ("(git push)", " ( git push ) "),
        ("echo `git push`", "echo  ` git push ` "),
        ("a\nb", "a \n b"),
    ],
)
def test_an_operator_gets_a_boundary_on_both_sides(command, expected):
    assert pad_shell_operators(command) == expected


@pytest.mark.parametrize(
    "command",
    [
        'echo "true;git push"',
        "echo 'true;git push'",
        'grep -rn "rm -rf" src/',
        "pytest -k 'test_a or test_b'",
    ],
)
def test_a_quoted_span_is_left_exactly_as_written(command):
    """A shell does not read an operator inside quotes as one, so neither does
    this. Padding there would rewrite the argument's own data."""
    assert pad_shell_operators(command) == command


@pytest.mark.parametrize(
    "command",
    [
        r"find . -name '*.py' -exec grep -l foo {} \;",
        r"true\;git push",
        r"echo a\&b",
    ],
)
def test_an_escaped_operator_is_not_a_boundary(command):
    r"""`true\;git push` passes a literal ';git' to true and pushes nothing.
    Padding it would invent a second command that the shell never runs, and
    the guards would block honest work on the strength of it."""
    assert pad_shell_operators(command) == command


@pytest.mark.parametrize(
    "command, expected",
    [
        # Inside "...", a backslash escapes " (POSIX 2.2.3), so the span runs
        # to the second real quote and the ';' after it is a separator.
        (r'''echo "a\"b";git push''', r'''echo "a\"b" ; git push'''),
        # \\ is an escaped backslash, so the very next quote does close.
        (r'''echo "a\\";git push''', r'''echo "a\\" ; git push'''),
        # A backslash before anything else inside "..." is literal, and must
        # not swallow the character after it.
        (r'''echo "a\zb";git push''', r'''echo "a\zb" ; git push'''),
        # $'...' escapes whatever follows, so \' does not close the span.
        (r"""echo $'it\'s';git push""", r"""echo $'it\'s' ; git push"""),
        (r"""echo $'a\\';git push""", r"""echo $'a\\' ; git push"""),
        # $"..." is a double-quoted span with a locale lookup, delimited the
        # ordinary way.
        (r'''echo $"a;b";git push''', r'''echo $"a;b" ; git push'''),
    ],
)
def test_an_escape_inside_a_span_does_not_end_it_early(command, expected):
    """Closing a span at an escaped quote leaves the real closing quote
    opening a second span that never ends, so every operator after it reads as
    quoted and gets no boundary. That is a separator the guards then cannot
    see, which is the direction that costs a bypass rather than a false
    refusal."""
    assert pad_shell_operators(command) == expected


@pytest.mark.parametrize(
    "command",
    [
        "git commit -m 'fix: don't break the build'",
        'echo "unterminated ;git push',
        r"""echo $'unterminated ;git push""",
        "echo 'a\";git push",
    ],
)
def test_quoting_that_never_closes_is_refused_rather_than_guessed(command):
    """The boundaries after an unterminated quote are not knowable from the
    text. Returning the string anyway reports "no operators out here", which a
    caller reads as "nothing to block", so this says so instead and both
    guards refuse on it."""
    with pytest.raises(UnbalancedQuote):
        pad_shell_operators(command)


@pytest.mark.parametrize(
    "command, expected",
    [
        # The literal run is closed, the substitution is padded as the command
        # it is, and the literal run reopens after it.
        ('echo "$(git push)"', 'echo "" $ ( git push )  ""'),
        ('echo "a $(git push) b"', 'echo "a " $ ( git push )  " b"'),
        ('echo "`git push`"', 'echo "" ` git push ` ""'),
        # A ')' only closes the substitution at nesting depth zero.
        ('echo "$(echo $(git push))"', 'echo "" $ ( echo $ ( git push )  )  ""'),
        # Quoting inside the substitution body is read with the ordinary rules,
        # so a ';' that is literal data there stays literal.
        ("""echo "$(grep 'a;b' f)\"""", """echo "" $ ( grep 'a;b' f )  \"\""""),
    ],
)
def test_a_substitution_inside_double_quotes_is_padded_as_a_command(command, expected):
    """Double quotes suppress word splitting and globbing of a substitution's
    output. They never suppress the substitution (POSIX 2.2.3 exempts '$' and
    '`'; 2.6.3 says the shell executes the command in a subshell). Copying the
    span through verbatim hid `echo "$(git push origin main)"` from both
    guards, so the executable part is lifted out of the quotes here."""
    assert pad_shell_operators(command) == expected


@pytest.mark.parametrize(
    "command",
    [
        # Single quotes really do suppress it, so refusing this is a false block.
        "echo '$(git push)'",
        "echo '`git push`'",
        # A backslash before '$' or '`' inside "..." makes it literal text.
        r'echo "\$(git push)"',
        r'echo "\`git push\`"',
        # ${...} is parameter expansion, not a command.
        'echo "${GIT_PUSH}"',
    ],
)
def test_text_a_shell_does_not_execute_is_left_exactly_as_written(command):
    """The other direction of the same rule. Lifting these out of their quotes
    would invent an invocation the shell never makes and cost a false refusal
    on ordinary work."""
    assert pad_shell_operators(command) == command


@pytest.mark.parametrize(
    "command",
    [
        'echo "$(git push"',
        'echo "`git push"',
        'echo "$(echo $(git push)"',
        # These two reach the substitution's own refusal rather than the
        # quoted span's: every quote balances, and it is the ')' or the closing
        # backtick that is missing. Without a case like this the branch is
        # covered only incidentally by the unterminated-quote refusal, and a
        # substitution that silently ran to the end of the string would go
        # unnoticed.
        'echo "$(git push""',
        'echo "`git push""',
    ],
)
def test_a_substitution_that_never_closes_is_refused_rather_than_guessed(command):
    """Where the command inside an unterminated substitution ends is not
    knowable from the text, and the same reasoning as an unterminated quote
    applies: reporting no boundary is what a caller reads as nothing to
    block.

    The substitution's own refusal is redundant on purpose and no test can
    distinguish it, so do not delete it as untested. A substitution that ran
    to the end of the string also swallowed the closing quote of the span
    around it, so that span refuses too; deleting either one leaves the same
    exception type on every input (checked over 16093 generated fragments of
    quotes, substitutions and operators). Two independent refusals on the one
    path where this scanner has historically guessed wrong is the point."""
    with pytest.raises(UnbalancedQuote):
        pad_shell_operators(command)


def test_lifting_a_substitution_out_of_quotes_only_ever_splits_a_token():
    """The safety direction for the rewrite. Every character of the input
    survives in order; the only additions are spaces and the quotes that
    re-delimit the literal runs around the executable region. So a token can
    be split into several but never merged, and any span this touches held a
    '$(' or a '`', neither of which appears in a binary name, so no token that
    used to match can stop matching."""
    command = 'echo "a;b $(git push) c" && ls'
    padded = pad_shell_operators(command)
    assert "".join(padded.split()).replace('"', "") == "".join(command.split()).replace('"', "")
    assert padded.count('"') == command.count('"') + 2


def test_the_refusal_is_a_valueerror_for_the_callers_that_already_catch_one():
    """Both guards route a tokenizer ValueError to their considered refusal
    path. A type outside that hierarchy would land on their last-ditch handler
    instead, so the relationship is pinned rather than left to inspection."""
    assert issubclass(UnbalancedQuote, ValueError)


def test_padding_only_ever_adds_boundaries():
    """The safety direction. Padding must not be able to hide a binary the
    caller would otherwise have found, so every non-space character survives
    in order."""
    command = 'git -C "C:\\repo dir" commit -m "wip;ok" && echo `date`'
    assert pad_shell_operators(command).split() != command.split()
    assert "".join(pad_shell_operators(command).split()) == "".join(command.split())


@pytest.mark.parametrize(
    "guard, command",
    [
        ("verify-loop-git-guard.py", "git push origin main"),
        ("quick-cop-bash-guard.py", "rm -rf important_dir"),
    ],
)
def test_a_guard_refuses_when_this_helper_is_unavailable(tmp_path, guard, command):
    """Both guards fail closed by their own stated contract, and importing this
    helper must not open a way around that. An uncaught ImportError exits 1,
    which is not a block under the hook contract, so the command would have run.
    Proven on a scratch copy; the real hooks directory is never modified.
    """
    scratch = Path(tempfile.mkdtemp(dir=tmp_path)) / "hooks"
    shutil.copytree(HOOKS, scratch, ignore=shutil.ignore_patterns("__pycache__"))
    (scratch / "shell_tokens.py").unlink()

    result = subprocess.run(
        [sys.executable, str(scratch / guard)],
        input=json.dumps({"tool_name": "Bash", "tool_input": {"command": command}}),
        capture_output=True,
        text=True,
        env={k: v for k, v in os.environ.items() if k.upper() in _ENV_ALLOWLIST},
    )
    assert result.returncode == 2, (
        f"{guard} exited {result.returncode} without the helper, which allows "
        f"{command!r} to run\nstderr: {result.stderr}"
    )
