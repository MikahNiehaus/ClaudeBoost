"""
ClaudeBoost Bash guard — command-type PreToolUse hook.

Intercepts Bash tool calls and BLOCKS patterns that trigger Claude Code's
built-in safety prompts (which waste the user's time). Claude is told what
to do instead so it can retry correctly.

Blocked patterns:
  1. cd "/path" && command  — triggers "bare repository attack" prompt
  2. Backslash-escaped spaces — triggers "backslash-escaped whitespace" prompt

Exit codes:
  0 = allow (pass)
  2 = block (Claude sees stderr message and retries)
"""
from __future__ import annotations

import json
import re
import sys


def check_cd_compound(command: str) -> str | None:
    """Detect cd + && compound commands."""
    # Match: cd <path> && <command> or cd <path> ; <command>
    if re.search(r"\bcd\s+.+\s*&&\s*", command):
        # Extract what command follows &&
        match = re.search(r"&&\s*(\w+)", command)
        following = match.group(1) if match else "command"
        if following == "git":
            return (
                "BLOCKED: Do not use `cd && git`. "
                "Use `git -C \"/path\" ...` instead. "
                "Compound cd+git triggers a permission prompt."
            )
        return (
            "BLOCKED: Do not use `cd && command`. "
            "Use absolute paths directly instead. "
            "Compound cd commands trigger a permission prompt."
        )
    return None


def check_backslash_spaces(command: str) -> str | None:
    """Detect backslash-escaped spaces in paths."""
    # Match backslash-space that looks like path escaping, not inside quotes
    # Common pattern: /some/path/F\ and\ B\ PWA/
    if re.search(r"(?<![\"'])\b\S+\\ \S+", command):
        return (
            "BLOCKED: Do not backslash-escape spaces in paths. "
            "Use double-quoted paths instead: \"/path/F and B PWA/Nectar\". "
            "Backslash-escaped whitespace triggers a permission prompt."
        )
    return None


def main() -> int:
    raw = ""
    try:
        if not sys.stdin.isatty():
            raw = sys.stdin.read()
    except Exception:
        return 0

    try:
        payload = json.loads(raw) if raw.strip() else {}
    except Exception:
        return 0

    command = payload.get("tool_input", {}).get("command", "")
    if not command:
        return 0

    # Run checks in order
    for check in [check_cd_compound, check_backslash_spaces]:
        msg = check(command)
        if msg:
            print(msg, file=sys.stderr)
            return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
