"""
ClaudeBoost context nudge — PostToolUse command hook on Edit|Write.

Counter-based: every 15th edit/write, reminds Claude to update workspace
context.md files. This ensures the compaction memo has fresh data to save
when PreCompact fires.

Skips entirely if no active workspace exists (no overhead for simple tasks).
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

NUDGE_INTERVAL = 15


def main() -> int:
    home = Path(os.environ.get("CLAUDEBOOST_HOME") or os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..")
    ))
    workspace_dir = home / "workspace"

    # No workspace = no nudge needed
    if not workspace_dir.exists() or not any(workspace_dir.glob("*/context.md")):
        return 0

    # Read/increment counter
    tracker_path = home / "state" / "compaction-tracker.json"
    try:
        tracker = json.loads(tracker_path.read_text(encoding="utf-8"))
    except Exception:
        tracker = {"edit_count": 0}

    tracker["edit_count"] = tracker.get("edit_count", 0) + 1

    try:
        tracker_path.write_text(json.dumps(tracker), encoding="utf-8")
    except Exception:
        pass

    # Only nudge every Nth edit
    if tracker["edit_count"] % NUDGE_INTERVAL != 0:
        return 0

    print(json.dumps({
        "additionalContext": (
            "CONTEXT CHECKPOINT: You have made several edits since the last checkpoint. "
            "If you have an active workspace task, update its context.md with current "
            "progress, decisions made, and next steps. This ensures context is preserved "
            "if compaction fires."
        ),
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
