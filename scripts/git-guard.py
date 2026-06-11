#!/usr/bin/env python3
"""
git-guard.py

PreToolUse hook that intercepts write git operations and forces the
permission ask-dialog, so every state-changing git command requires
explicit user approval.

Read-only operations (status, log, diff, show, blame, ls-files, etc.)
pass through silently. Write operations route through the permission
prompt regardless of any allow-list rules.

Exit 0 always — uses permissionDecision:ask rather than a hard block,
so the ask-dialog appears and the user can approve or deny.
"""

import json
import re
import sys

# These subcommands never modify state — always pass through.
READ_ONLY = frozenset({
    "status", "log", "diff", "show", "blame", "ls-files", "ls-tree",
    "rev-parse", "cat-file", "shortlog", "describe", "grep",
    "name-rev", "for-each-ref", "count-objects", "verify-pack",
    "fsck", "check-ignore", "check-attr", "check-mailmap",
})

# These subcommands always modify state — always ask.
ALWAYS_WRITE = frozenset({
    "add", "commit", "push", "pull", "fetch", "checkout", "switch",
    "merge", "rebase", "reset", "restore", "cherry-pick", "revert",
    "rm", "mv", "apply", "am", "init", "clone", "clean",
    "filter-branch", "filter-repo",
})

# These subcommands are write ops only when specific flags/sub-subcommands appear.
CONDITIONAL_WRITE: dict[str, re.Pattern] = {
    "tag":             re.compile(r"(-a|--annotate|-d|--delete|-s|--sign|-f|--force)"),
    "branch":          re.compile(r"(-d|--delete|-D|-m|--move|-M|-c|--copy|-C|--set-upstream)"),
    "remote":          re.compile(r"\b(add|remove|rm|set-url|set-head|set-branches|rename|prune)\b"),
    "config":          re.compile(r"(--global|--system|--local|--worktree|--unset|--remove-section|--add|--replace-all)"),
    "submodule":       re.compile(r"\b(add|deinit|update|sync|absorbgitdirs)\b"),
    "worktree":        re.compile(r"\b(add|remove|move|prune|repair|lock|unlock)\b"),
    "notes":           re.compile(r"\b(add|append|edit|remove|copy|merge|prune)\b"),
    "sparse-checkout": re.compile(r"\b(init|set|add|disable|reapply)\b"),
    "reflog":          re.compile(r"\b(expire|delete)\b"),
    "lfs":             re.compile(r"\b(track|untrack|install|uninstall|push|fetch|prune|migrate)\b"),
    # stash with no args = push (write); only list/show are read-only
    "stash":           re.compile(r"^(?!(list|show)(\s|$))"),
    "bisect":          re.compile(r"\b(start|good|bad|old|new|skip|reset|run)\b"),
}


def parse_git_subcommand(cmd: str):
    """
    Tokenize cmd and extract the git subcommand, skipping global flags.
    Returns (subcommand, rest_of_args) or (None, None) if not a git command.
    Handles: git [opts] sub, git -C <dir> [opts] sub, "path/to/git" sub, etc.
    """
    tokens = cmd.split()
    if not tokens:
        return None, None

    first = tokens[0].strip("\"'")
    if not (first == "git" or first.endswith("/git") or first.endswith("\\git")):
        return None, None

    i = 1
    while i < len(tokens):
        t = tokens[i]
        if t in ("-C", "--git-dir", "--work-tree", "--namespace"):
            i += 2  # flag + its value
        elif t.startswith(("--git-dir=", "--work-tree=", "--namespace=")):
            i += 1
        elif t.startswith("-"):
            i += 1  # single-char flag without an argument
        else:
            break

    if i >= len(tokens):
        return None, None

    sub = tokens[i]
    rest = " ".join(tokens[i + 1:])
    return sub, rest


def is_write_op(sub: str, rest: str) -> bool:
    if sub in ALWAYS_WRITE:
        return True
    if sub in READ_ONLY:
        return False
    pat = CONDITIONAL_WRITE.get(sub)
    return bool(pat.search(rest)) if pat is not None else False


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    cmd = (data.get("tool_input") or {}).get("command", "")
    if not cmd:
        sys.exit(0)

    sub, rest = parse_git_subcommand(cmd)
    if sub is None or not is_write_op(sub, rest):
        sys.exit(0)

    # Write op detected: route through the permission ask-dialog.
    out = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "ask",
            "permissionDecisionReason": (
                f"'git {sub}' modifies repository state. "
                "User confirmation required before this runs."
            ),
        }
    }
    print(json.dumps(out))
    sys.exit(0)


if __name__ == "__main__":
    main()
