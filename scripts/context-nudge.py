"""
ClaudeBoost context nudge — PostToolUse command hook on all tool uses.

Counter-based nudges in two modes:

1. Workspace present: every 20th tool use, reminds Claude to update
   workspace context.md files with code changes AND important user
   statements (decisions, requirements, preferences). This ensures
   the compaction memo has fresh, accurate data when PreCompact fires.

2. No workspace: still tracks tool uses. If tool count reaches 60,
   suggests creating a workspace so progress survives compaction if
   the task has grown complex. Fires once, then resets tracking.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

NUDGE_INTERVAL = 20
NO_WORKSPACE_NUDGE_THRESHOLD = 60


def main() -> int:
    home = Path(os.environ.get("CLAUDEBOOST_HOME") or os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..")
    ))
    workspace_dir = home / "workspace"
    has_workspace = workspace_dir.exists() and any(workspace_dir.glob("*/context.md"))

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

    if has_workspace:
        # Nudge every Nth edit to keep context.md fresh
        if tracker["edit_count"] % NUDGE_INTERVAL != 0:
            return 0

        print(json.dumps({
            "additionalContext": (
                "CONTEXT CHECKPOINT: You have made significant progress since the last checkpoint. "
                "If you have an active workspace task, update its context.md with: "
                "(1) code changes and decisions made, "
                "(2) important user statements — requirements, preferences, constraints, corrections, "
                "and approvals the user expressed in this session. "
                "Both code changes AND user intent must be captured to survive compaction."
            ),
        }))
    else:
        # No workspace — nudge once at threshold to suggest creating one
        if tracker["edit_count"] != NO_WORKSPACE_NUDGE_THRESHOLD:
            return 0

        print(json.dumps({
            "additionalContext": (
                "No active workspace detected. You've done significant work — if this is "
                "getting complex, consider creating a workspace "
                "(workspace/[task-id]/context.md) to capture code changes AND important "
                "user statements (requirements, decisions, preferences) so progress "
                "survives compaction."
            ),
        }))

    return 0


if __name__ == "__main__":
    sys.exit(main())
