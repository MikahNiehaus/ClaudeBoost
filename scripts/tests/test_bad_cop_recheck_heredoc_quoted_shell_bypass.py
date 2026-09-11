"""Adversarial re-check: a quoted shell name in a heredoc's operator-line tail
bypasses check_routed_git_write in scripts/bash-guard.py.

_heredoc_data_spans reads the operator line (the text before `<<` plus the
`tail` group after the tag) and blanks the heredoc body as data UNLESS a
shell is among the words on that line. The word split
(_OPERATOR_LINE_SPLIT_RE) breaks only on shell control operators and
whitespace; it does not strip quotes. _SHELL_WORD_RE then requires the whole
split word to end in `sh`/`bash`/`zsh`/`ksh`/`dash` (optionally with a path
prefix or `.exe`), so a word that still carries its surrounding quote
characters, e.g. `"bash"`, never matches.

But quoting a command name does not stop a real shell from executing it:
`cat <<EOF | "bash"` genuinely pipes the heredoc body into bash, exactly like
`cat <<EOF | bash` does (verified against a live Git Bash: `echo x | "bash"
-c 'read v; echo $v'` prints `x`, proving the quotes are inert at the command
name position). So the guard's own reasoning for keeping the body scannable
("if a shell is the thing reading it, the body really is executed") applies
here too, but the implementation misses it because of the unstripped quote.

Confirmed this is a *new* regression from this round's tail-widening fix, not
a pre-existing gap: reproduced against git HEAD's scripts/bash-guard.py using
the same test cases -- HEAD blocks all four (by accident, since HEAD's
_HEREDOC_RE required a newline immediately after the tag and therefore never
recognized `cat <<EOF | "bash"` as a heredoc at all, so the body was scanned
as raw command text and `git push` was found in command position). The
working tree's widened tail recognizes the heredoc, decides the reader is not
a shell (because of the quote), and blanks the body -- turning an accidental
BLOCK into a real ALLOW of a command that truly pushes.

Nothing in this file executes a real git push. Every case is a JSON string
handed to the hook subprocess on stdin; the hook only classifies it.
"""
from __future__ import annotations

import pytest

from helpers import run_hook, pretooluse


def _bash(command: str) -> dict:
    return pretooluse("Bash", {"command": command})


@pytest.mark.parametrize("command", [
    'cat <<EOF | "bash"\ngit push\nEOF',
    'cat <<EOF | "/usr/bin/bash"\ngit push\nEOF',
    "cat <<EOF | 'bash'\ngit push\nEOF",
    'cat <<EOF | "bash.exe"\ngit push\nEOF',
])
def test_quoted_shell_name_in_heredoc_tail_is_still_a_routed_write(command):
    """A quoted shell name in the tail still reads the heredoc body as shell
    source and really executes the git push inside it. The guard must not
    let quoting the executable name launder an otherwise-detected routed
    write."""
    result = run_hook("bash-guard.py", _bash(command))
    assert result.returncode == 2, (
        "BYPASS: quoting the shell name in a heredoc's operator-line tail "
        "makes check_routed_git_write treat a real `git push` as inert data.\n"
        f"Command: {command!r}\n"
        f"Hook exited {result.returncode} (0 = allowed) instead of 2 (block).\n"
        f"stderr: {result.stderr.decode()}"
    )
