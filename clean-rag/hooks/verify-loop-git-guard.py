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

import json
import re
import shlex
import sys

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

# Global git flags that take a value, so the real subcommand token isn't
# mistaken for one of these values (git -C "path" commit -m "...").
_VALUE_FLAGS = {"-C", "-c", "--git-dir", "--work-tree", "--namespace"}

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


def _subcommand_after_git(parts: list, start: int) -> str | None:
    """First non-flag token after a 'git' token at parts[start], skipping
    global flags and the value of any flag that takes one."""
    i = start + 1
    while i < len(parts):
        token = parts[i]
        if token in _VALUE_FLAGS:
            i += 2
            continue
        if token.startswith("-"):
            i += 1
            continue
        return token
    return None


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read())
    except Exception:
        return 0

    if payload.get("tool_name") != "Bash":
        return 0

    command = (payload.get("tool_input", {}).get("command") or "").strip()
    if not command:
        return 0

    try:
        parts = shlex.split(command)
    except ValueError:
        return 0

    for i, token in enumerate(parts):
        binary = token.rsplit("/", 1)[-1].rsplit("\\", 1)[-1].lower()
        if binary.endswith(".exe"):
            binary = binary[:-4]
        if binary != "git":
            continue

        sub = _subcommand_after_git(parts, i)
        if sub in _BLOCKED_SUBCOMMANDS:
            return _refuse(f"git {sub!r} is not allowed for this agent: {command!r}")

    if _BRANCH_DELETE.search(command):
        return _refuse(f"git branch delete is not allowed for this agent: {command!r}")
    if _TAG_DELETE.search(command):
        return _refuse(f"git tag delete is not allowed for this agent: {command!r}")
    if _STASH_DESTRUCTIVE.search(command):
        return _refuse(f"destructive git stash op is not allowed for this agent: {command!r}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
