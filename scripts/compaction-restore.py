"""
ClaudeBoost compaction restore — SessionStart command hook.

After compaction, reads the saved compaction memo and injects it as
additionalContext so Claude knows where it left off and what to do next.

Only fires when the session start source is "compact" (post-compaction).
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def main() -> int:
    home = Path(os.environ.get("CLAUDEBOOST_HOME") or os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..")
    ))
    memo_path = home / "state" / "compaction-memo.json"

    # Read hook input
    raw = sys.stdin.read() if not sys.stdin.isatty() else ""
    try:
        hook_input = json.loads(raw) if raw else {}
    except Exception:
        hook_input = {}

    # Only inject after compaction
    if hook_input.get("source") != "compact":
        return 0

    # Read memo
    if not memo_path.exists():
        return 0

    try:
        memo_data = json.loads(memo_path.read_text(encoding="utf-8"))
    except Exception:
        return 0

    memo_text = memo_data.get("memo", "")
    if not memo_text:
        return 0

    # Build restoration context
    context = (
        "POST-COMPACTION CONTEXT RESTORATION\n"
        "====================================\n\n"
        "You just went through compaction. Below is your saved working state.\n\n"
        f"{memo_text}\n\n"
        "RESUME INSTRUCTIONS:\n"
        "- Read the workspace context.md files listed above for full detail\n"
        "- Continue from the last documented next step\n"
        "- Keep workspace context.md files updated as you work\n"
        "- If the user gave you a task before compaction, pick it back up"
    )

    print(json.dumps({"additionalContext": context}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
