"""
ClaudeBoost context nudge — PostToolUse command hook on all tool uses.

Counter-based nudges in three modes:

1. Behavior enforcement: tracks RAG usage and evaluator usage patterns.
   - After 5 consecutive file searches (Read/Grep/Glob/Bash) without any RAG call:
     injects a RAG reminder into additionalContext.
   - After 2 Task spawns without an evaluator-agent spawn:
     injects an evaluator reminder.
   - Every 25 tool uses: injects a comprehensive 5-behavior checklist.

2. Workspace present: every 20th tool use, reminds Claude to update
   workspace context.md files with code changes AND important user
   statements (decisions, requirements, preferences, corrections,
   approvals). This ensures the compaction memo has fresh, accurate
   data when PreCompact fires.

3. No workspace: still tracks tool uses. If tool count reaches 60,
   suggests creating a workspace so progress survives compaction if
   the task has grown complex. Fires once, then resets tracking.

Behavior enforcement fires first and short-circuits the workspace nudge
in the same turn (only one additionalContext injection per call).
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

NUDGE_INTERVAL = 20
NO_WORKSPACE_NUDGE_THRESHOLD = 60
RAG_THRESHOLD = 5          # reads without RAG before reminding
EVALUATOR_THRESHOLD = 2    # agent spawns without evaluator before reminding
COMPREHENSIVE_INTERVAL = 25  # full behavior checklist every N tool uses

RAG_TOOLS = {
    "mcp__rag-server__rag_search",
    "mcp__rag-server__rag_context",
    "mcp__rag-server__rag_index_project",
    "mcp__rag-server__rag_index",
    "mcp__rag-server__rag_status",
    "mcp__rag-server__rag_scan",
}
FILE_TOOLS = {"Read", "Grep", "Glob", "Bash"}


def main() -> int:
    home = Path(os.environ.get("CLAUDEBOOST_HOME") or os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..")
    ))
    workspace_dir = home / "workspace"
    has_workspace = workspace_dir.exists() and any(workspace_dir.glob("*/context.md"))

    # --- Read hook payload ---
    raw = sys.stdin.read() if not sys.stdin.isatty() else ""
    try:
        payload = json.loads(raw) if raw else {}
    except Exception:
        payload = {}

    tool_name = payload.get("tool_name", "")

    # --- Compaction counter (existing) ---
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

    # --- Behavior tracker (new) ---
    behavior_path = home / "state" / "behavior-tracker.json"
    try:
        behavior = json.loads(behavior_path.read_text(encoding="utf-8"))
    except Exception:
        behavior = {"reads_since_rag": 0, "tasks_since_evaluator": 0}

    # Update RAG/file counters
    if tool_name in RAG_TOOLS:
        behavior["reads_since_rag"] = 0   # good behavior — reset
    elif tool_name in FILE_TOOLS:
        behavior["reads_since_rag"] = behavior.get("reads_since_rag", 0) + 1

    # Update evaluator counter
    if tool_name == "Task":
        desc = str((payload.get("tool_input") or {}).get("description", "")).lower()
        if "evaluator" in desc:
            behavior["tasks_since_evaluator"] = 0   # good behavior — reset
        else:
            behavior["tasks_since_evaluator"] = behavior.get("tasks_since_evaluator", 0) + 1

    try:
        behavior_path.write_text(json.dumps(behavior), encoding="utf-8")
    except Exception:
        pass

    # --- Behavior enforcement nudges (fire before workspace nudge) ---
    reads = behavior.get("reads_since_rag", 0)
    tasks = behavior.get("tasks_since_evaluator", 0)
    total = tracker.get("edit_count", 0)

    nudge = None

    if reads >= RAG_THRESHOLD and reads % RAG_THRESHOLD == 0:
        nudge = (
            f"RAG REMINDER ({reads} file searches since last RAG call): "
            "STOP reading files. Call rag_search('what you need') FIRST — "
            "it finds the relevant file faster than grep. "
            "Only read files after RAG confirms which ones are relevant."
        )
    elif tasks >= EVALUATOR_THRESHOLD and tasks % EVALUATOR_THRESHOLD == 0:
        nudge = (
            f"EVALUATOR REMINDER ({tasks} agent spawns without evaluator): "
            "Spawn evaluator-agent on your findings before acting on them. "
            "Never self-verify — evaluator reads only the cited file:lines."
        )
    elif total > 0 and total % COMPREHENSIVE_INTERVAL == 0:
        nudge = (
            "BEHAVIOR CHECKPOINT — five rules you tend to skip: "
            "(1) STUCK? -> rag_search('question') before more file reads. "
            "(2) FINDING? -> cite file:line, then spawn evaluator-agent. "
            "(3) NEW endpoint/table/dependency? -> CONSULT mode, spawn architect-agent. "
            "(4) COMPLEX task? -> workspace/[task-id]/context.md. "
            "(5) SPAWNING AGENT? -> rag_context as FIRST step in prompt."
        )

    if nudge:
        print(json.dumps({"additionalContext": nudge}))
        return 0   # don't double-fire workspace nudge in same turn

    # --- Workspace nudge (existing logic, unchanged) ---
    if has_workspace:
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
