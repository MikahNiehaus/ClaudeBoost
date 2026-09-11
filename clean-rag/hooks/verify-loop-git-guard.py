#!/usr/bin/env python
"""PreToolUse guard on Bash, scoped to bad-cop and good-cop via their own frontmatter.

Incident this exists to prevent: on 2026-08-25, good-cop applied a real,
correct fix, then ran `git commit` and `git push` on its own, reaching a
shared remote branch with nobody having asked it to. The commit's content
was fine; the act of committing and pushing was not authorized by anyone.
Telling the agent not to in prose did not stop it, because the agent still
had the capability. This removes the capability instead.

bad-cop and good-cop verify and fix code. They do not manage git state.
Committing, pushing, and every other history- or remote-altering git command
are reserved for the orchestrator, and only when the user explicitly asks
for them (see the Git Safety Protocol both agents already inherit from the
main session's own instructions). Read-only git (status, diff, log, show,
blame) stays open, since bad-cop's whole job includes checking a diff
against the ticket.

Unlike research-agent's guard, this is a denylist, not an allowlist: these
two agents legitimately need broad Bash for builds, tests, and static
analysis, so only git's mutating subcommands are blocked, everything else
passes through unchanged.

Exit codes: 0 allows, 2 blocks with the stderr message shown to the agent.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    from shell_tokens import (  # noqa: E402
        git_subcommand,
        pad_shell_operators,
        split_readings,
    )
except ImportError as _exc:
    # The helper ships in this directory, so this only fires on a broken
    # install. It still has to be handled rather than left to propagate: an
    # uncaught ImportError exits 1, and 1 is not a block under this hook
    # contract, so the guard would have allowed the command. Failing at the
    # point of use instead puts it on the refusal path at the bottom of this
    # file, which is the direction the rest of this guard already fails.
    #
    # Rebound to a module level name on purpose. Python deletes the `as` target
    # at the end of the except block (PEP 3110), so a nested function closing
    # over `_exc` raises NameError instead of the RuntimeError written below.
    # The refusal still happens either way, but the operator sees the wrong
    # cause, which is the kind of thing that costs an hour on a broken install.
    _tokenizer_import_error = _exc

    def pad_shell_operators(command: str) -> str:  # noqa: E402
        raise RuntimeError(
            "the shell tokenizer is unavailable") from _tokenizer_import_error

    def split_readings(padded: str) -> tuple:  # noqa: E402
        raise RuntimeError(
            "the shell tokenizer is unavailable") from _tokenizer_import_error

    def git_subcommand(parts: list, start: int) -> tuple:  # noqa: E402
        raise RuntimeError(
            "the shell tokenizer is unavailable") from _tokenizer_import_error

# git subcommands that change history, the working tree beyond the current
# file edit, or a remote. Anything not on this list is read only or scoped
# to the index (git add), neither of which commits or pushes anything.
_BLOCKED_SUBCOMMANDS = {
    "commit",
    "push",
    "merge",
    "rebase",
    "reset",
    "restore",
    "clean",
    "cherry-pick",
    "revert",
    "pull",
    "am",
    "apply",
}

# Any mention of git, including a path qualified or .exe one. Used only on the
# parse failure path, to tell a command this denylist could never block from
# one whose structure it needs to see and cannot.
#
# A word boundary rather than a class of separators to match on: the class had
# to list every character that can precede a command, and it did not have ';'
# or '|', so `true;git push` read as no git mention at all, which is the one
# shape this path most needs to catch. \b is the same test
# scripts/bash-guard.py already uses for the same job, and it is a superset of
# the old class, since every character that class listed is punctuation.
_GIT_TOKEN_RE = re.compile(r"\bgit(?:\.exe)?\b", re.IGNORECASE)

_BRANCH_DELETE = re.compile(r"\bbranch\b[^|;&]*\s-[dD]\b")
_TAG_DELETE = re.compile(r"\btag\b[^|;&]*\s-d\b")
_STASH_DESTRUCTIVE = re.compile(r"\bstash\b[^|;&]*\b(drop|clear|pop)\b")


def _refuse(reason: str) -> int:
    print(
        f"BLOCKED for bad-cop/good-cop: {reason}\n\n"
        "This agent verifies and fixes code; it does not manage git state. "
        "Committing, pushing, merging, rebasing, and any other history- or "
        "remote-altering git command are reserved for the orchestrator, and "
        "only when the user explicitly asks for them. Report your fix in "
        "your response and let the orchestrator handle git from there.\n\n"
        "Allowed: git status, diff, log, show, blame, add, branch (list), "
        "and any other read-only or index-only git command.",
        file=sys.stderr,
    )
    return 2


def _tokenize(command: str) -> tuple[list[list[str]], bool]:
    """Every reading of the command that parsed, and whether all of them did.

    Padding first is what makes the readings worth taking: neither mode of
    shlex splits on ';', '|' or '&' the way a shell does, so ``true;git push``
    tokenizes as ``["true;git", "push"]`` and the fused first token is not
    equal to "git". Why there are two readings rather than one, and why a
    failed reading is reported rather than dropped, is in ``split_readings``.
    """
    try:
        padded = pad_shell_operators(command)
    except ValueError:
        # The padder could not read the command's quoting to the end, so it
        # cannot say where the operators are. No tokenization of it is worth
        # anything; the caller decides what an unreadable command means.
        return [], False

    return split_readings(padded)


def _bash_command(payload) -> tuple[str, str]:
    """The Bash command out of a PreToolUse payload, as (command, problem).

    An empty command means there is nothing to judge: not a Bash call, or a
    Bash call with no command in it. A non-empty problem means the payload's
    shape could not be read at all, which is a refusal rather than an allow.

    Stdin is a system boundary and every shape handled here is valid JSON: the
    payload a bare scalar, null, or a list; tool_input null or a string; the
    command a number or a list. A naive payload.get(...).get(...) chain raises
    on each of them, and an uncaught exception exits 1 -- neither allow (0) nor
    block (2) under this hook contract, so the command would run anyway.
    """
    if not isinstance(payload, dict):
        return "", "the tool payload was not a JSON object"
    if payload.get("tool_name") != "Bash":
        return "", ""
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return "", "the Bash tool_input was not a JSON object"
    command = tool_input.get("command")
    if command is None or command == "":
        return "", ""
    if not isinstance(command, str):
        return "", "the Bash command was not a string"
    return command.strip(), ""


def _find_blocked_subcommand(tokenizations: list[list[str]]) -> str | None:
    """The first blocked git subcommand any tokenizing of the command reveals.

    Every token is checked, not just the first: these agents chain commands
    (a && b, a; b, a | b), so git can sit anywhere in the stream.
    """
    for parts in tokenizations:
        for i, token in enumerate(parts):
            binary = token.rsplit("/", 1)[-1].rsplit("\\", 1)[-1].lower()
            if binary.endswith(".exe"):
                binary = binary[:-4]
            if binary != "git":
                continue
            sub, _ = git_subcommand(parts, i)
            if sub in _BLOCKED_SUBCOMMANDS:
                return sub
    return None


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read())
    except Exception:
        # A payload this guard cannot read is a payload it cannot clear of a
        # blocked git subcommand, and "cannot tell" is not "safe" for a
        # denylist. Fail closed, the same direction research-agent-bash-guard
        # already fails. Claude Code always sends valid JSON, so this path
        # firing at all means something is wrong upstream.
        return _refuse("could not parse the tool payload")

    command, problem = _bash_command(payload)
    if problem:
        return _refuse(problem)
    if not command:
        return 0

    tokenizations, complete = _tokenize(command)

    # Whatever any reading does reveal is judged first, so a blocked write that
    # is plainly visible gets named in the refusal instead of the vaguer
    # "could not parse" below.
    blocked = _find_blocked_subcommand(tokenizations)
    if blocked:
        return _refuse(f"git {blocked!r} is not allowed for this agent: {command!r}")

    # These three read the raw command and need no tokenizer at all, so they
    # run whether or not the parse was complete.
    if _BRANCH_DELETE.search(command):
        return _refuse(f"git branch delete is not allowed for this agent: {command!r}")
    if _TAG_DELETE.search(command):
        return _refuse(f"git tag delete is not allowed for this agent: {command!r}")
    if _STASH_DESTRUCTIVE.search(command):
        return _refuse(f"destructive git stash op is not allowed for this agent: {command!r}")

    if not complete:
        # Some reading of the command failed, so "no blocked subcommand found"
        # is not a clean bill of health -- it is a partial answer, and the part
        # that is missing is exactly the part that failed to parse. An
        # unbalanced quote is ordinary rather than adversarial, so this is a
        # git-only denylist behaving like one: a command with no git token in
        # it at all is positively out of scope and still allowed, which keeps
        # the broad Bash these agents need for builds and tests working through
        # a stray quote. A command that does mention git is refused, because
        # that is exactly the string whose structure this guard needs to see
        # and cannot.
        if _GIT_TOKEN_RE.search(command):
            return _refuse(f"could not parse this git command safely: {command!r}")

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 - last line of the denylist
        # An uncaught exception exits 1, and 1 is not a block under this hook
        # contract, so a crashing guard has allowed the command. Land on 2.
        sys.exit(_refuse(f"the guard itself failed ({exc!r})"))
