#!/usr/bin/env python3
"""Strip Claude co-author lines from git commit commands before they run.

Handles two forms:
  - Escaped \n inside -m "..." args: \nCo-authored-by: Claude ...
  - Real newlines in heredocs or multiline strings
"""
import json
import re
import sys


def main():
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        sys.exit(0)

    command = data.get("tool_input", {}).get("command", "")

    # Quick exit if not a git commit command
    if not re.search(r"\bgit\b.*\bcommit\b", command):
        sys.exit(0)

    original = command

    # Remove escaped \n + co-author line (inside quoted -m args)
    command = re.sub(
        r"\\nCo-authored-by:\s*Claude[^\\n'\"]*",
        "",
        command,
        flags=re.IGNORECASE,
    )
    # Remove real newline + co-author line (heredocs, multiline)
    command = re.sub(
        r"\nCo-authored-by:\s*Claude[^\n]*",
        "",
        command,
        flags=re.IGNORECASE,
    )

    if command == original:
        sys.exit(0)

    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "updatedInput": {"command": command},
        }
    }))
    sys.exit(0)


if __name__ == "__main__":
    main()
