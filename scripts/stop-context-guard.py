"""
ClaudeBoost stop-context-guard — Stop command hook.

Fires when Claude is about to stop responding. At high tool-use count,
checks if any active workspace context.md is stale. If so, blocks with
a reminder to update context before stopping.

Threshold: fires when edit_count > THRESHOLD and
           (edit_count - THRESHOLD) % FIRE_EVERY == 0
Stale definition: context.md not modified in the last STALE_MINUTES minutes

Exit codes:
  0 = allow stop (below threshold, or context.md is fresh)
  2 = block stop (high tool count + stale context.md)
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

THRESHOLD = 40       # tool uses before guard activates
FIRE_EVERY = 20      # only check every N uses past threshold
STALE_MINUTES = 20   # context.md older than this is considered stale


def main() -> int:
    home = Path(os.environ.get("CLAUDEBOOST_HOME") or os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..")
    ))
    state_dir = home / "state"
    workspace_dir = home / "workspace"

    # Read tool use count
    tracker_path = state_dir / "compaction-tracker.json"
    try:
        tracker = json.loads(tracker_path.read_text(encoding="utf-8"))
    except Exception:
        tracker = {"edit_count": 0}

    edit_count = tracker.get("edit_count", 0)

    # Check threshold and rate limiter
    if edit_count <= THRESHOLD:
        return 0
    if (edit_count - THRESHOLD) % FIRE_EVERY != 0:
        return 0

    # Find all active workspace context.md files
    if not workspace_dir.exists():
        return 0

    context_files = list(workspace_dir.glob("*/context.md"))
    if not context_files:
        return 0

    # Check the most recently modified context.md
    most_recent = max(context_files, key=lambda f: f.stat().st_mtime)
    age_seconds = time.time() - most_recent.stat().st_mtime
    age_minutes = age_seconds / 60

    if age_minutes <= STALE_MINUTES:
        return 0  # context is fresh, allow stop

    # Block: context is stale at high tool count
    age_display = f"{int(age_minutes)} minutes"
    reason = (
        f"CONTEXT CHECKPOINT — update workspace context.md before stopping.\n"
        f"You have made {edit_count} tool calls. The most recently updated "
        f"context.md ({most_recent.parent.name}/context.md) has not been "
        f"updated in over {age_display}.\n\n"
        "Update it now with:\n"
        "  - Current task status (what's done, what's next)\n"
        "  - Key decisions made this session and WHY\n"
        "  - Any user constraints or preferences stated\n"
        "  - Next concrete step (specific enough for a fresh session to resume)\n"
        "  - Failed approaches (what was tried and didn't work)\n\n"
        "If you are at a natural stopping point and context is getting full,\n"
        "run /clear-safe — it will verify context.md, show what survives,\n"
        "and confirm before clearing. The SessionEnd hook saves state automatically."
    )

    print(json.dumps({"decision": "block", "reason": reason}))
    return 2


if __name__ == "__main__":
    sys.exit(main())
