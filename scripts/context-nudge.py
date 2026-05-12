"""
ClaudeBoost context nudge — PostToolUse command hook on all tool uses.

Two independent nudge channels that can both fire in the same turn:

CHANNEL A — Behavior enforcement (one per turn, elif chain):
   - After 5 consecutive file searches without RAG: RAG reminder
   - After 2 Task spawns without evaluator: evaluator reminder
   - At 100+ tool uses (every 25 past): /clear-safe suggestion
   - Every 25 tool uses: comprehensive 5-behavior checklist

CHANNEL B — Workspace checkpoint (independent, every 20 tool uses):
   - Names the specific workspace/[task-id]/context.md to update
   - Tracks compliance: if context.md mtime unchanged since last nudge → URGENT
   - If no workspace: suggests creating one at 60 tool uses

Both channels fire in the same turn when both conditions are met.
Messages are combined into a single additionalContext output.
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
CLEAR_CONSIDERATION_THRESHOLD = 100   # start suggesting /clear-safe at this tool count
CLEAR_CONSIDERATION_INTERVAL = 25     # repeat every N uses past threshold

RAG_TOOLS = {
    "mcp__rag-server__rag_search",
    "mcp__rag-server__rag_context",
    "mcp__rag-server__rag_index_project",
    "mcp__rag-server__rag_index",
    "mcp__rag-server__rag_index_research",
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

    # --- Compaction counter ---
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

    # --- Behavior tracker ---
    behavior_path = home / "state" / "behavior-tracker.json"
    try:
        behavior = json.loads(behavior_path.read_text(encoding="utf-8"))
    except Exception:
        behavior = {"reads_since_rag": 0, "tasks_since_evaluator": 0}

    # Update RAG/file counters
    if tool_name in RAG_TOOLS:
        behavior["reads_since_rag"] = 0
    elif tool_name in FILE_TOOLS:
        behavior["reads_since_rag"] = behavior.get("reads_since_rag", 0) + 1

    # Update evaluator counter
    if tool_name == "Task":
        desc = str((payload.get("tool_input") or {}).get("description", "")).lower()
        if "evaluator" in desc:
            behavior["tasks_since_evaluator"] = 0
        else:
            behavior["tasks_since_evaluator"] = behavior.get("tasks_since_evaluator", 0) + 1

    reads = behavior.get("reads_since_rag", 0)
    tasks = behavior.get("tasks_since_evaluator", 0)
    total = tracker.get("edit_count", 0)

    nudges = []

    # --- CHANNEL A: Behavior enforcement (one per turn) ---
    if reads >= RAG_THRESHOLD and reads % RAG_THRESHOLD == 0:
        nudges.append(
            f"RAG REMINDER ({reads} file searches since last RAG call): "
            "STOP reading files. Call rag_search('what you need') FIRST — "
            "it finds the relevant file faster than grep. "
            "Only read files after RAG confirms which ones are relevant."
        )
    elif tasks >= EVALUATOR_THRESHOLD and tasks % EVALUATOR_THRESHOLD == 0:
        nudges.append(
            f"EVALUATOR REMINDER ({tasks} agent spawns without evaluator): "
            "Spawn evaluator-agent on your findings before acting on them. "
            "Never self-verify — evaluator reads only the cited file:lines."
        )
    elif (
        total >= CLEAR_CONSIDERATION_THRESHOLD
        and (total - CLEAR_CONSIDERATION_THRESHOLD) % CLEAR_CONSIDERATION_INTERVAL == 0
    ):
        nudges.append(
            f"CONTEXT HEALTH CHECK ({total} tool uses this session): "
            "You are approaching context limits. Run /clear-safe — it will verify your "
            "workspace context.md is current, show you what survives, and confirm before clearing. "
            "Only suggest /clear-safe if: (1) no agent is mid-task; "
            "(2) no file edit is partially open; "
            "(3) you are at a natural stopping point. "
            "If conditions are not met, finish the current subtask first."
        )
    elif total > 0 and total % COMPREHENSIVE_INTERVAL == 0:
        nudges.append(
            "BEHAVIOR CHECKPOINT — five rules you tend to skip: "
            "(1) STUCK? -> rag_search('question') before more file reads. "
            "(2) FINDING? -> cite file:line, then spawn evaluator-agent. "
            "(3) NEW endpoint/table/dependency? -> CONSULT mode, spawn architect-agent. "
            "(4) COMPLEX task? -> workspace/[task-id]/context.md. "
            "(5) SPAWNING AGENT? -> rag_context as FIRST step in prompt."
        )

    # --- CHANNEL B: Workspace checkpoint (independent — fires even if Channel A fired) ---
    if has_workspace and total % NUDGE_INTERVAL == 0:
        ctx_files = list(workspace_dir.glob("*/context.md"))
        if ctx_files:
            most_recent = max(ctx_files, key=lambda f: f.stat().st_mtime)
            task_id = most_recent.parent.name
            current_mtime = most_recent.stat().st_mtime

            last_mtime = behavior.get("last_nudge_ctx_mtime", 0.0)
            last_path = behavior.get("last_nudge_ctx_path", "")
            last_count = behavior.get("last_nudge_count", 0)

            unchanged = (
                last_path == str(most_recent)
                and abs(current_mtime - last_mtime) < 2.0
            )

            if unchanged and last_count > 0:
                uses_since = total - last_count
                nudges.append(
                    f"URGENT CONTEXT CHECKPOINT: workspace/{task_id}/context.md "
                    f"has NOT been updated since the reminder {uses_since} tool uses ago. "
                    "Update it NOW before continuing — status, next step, decisions made. "
                    "This file is what survives /clear and compaction."
                )
            else:
                nudges.append(
                    f"CONTEXT CHECKPOINT: Update workspace/{task_id}/context.md now with: "
                    "(1) what was just implemented or decided, "
                    "(2) current status and specific next step, "
                    "(3) user requirements or constraints stated this session."
                )

            behavior["last_nudge_ctx_mtime"] = current_mtime
            behavior["last_nudge_ctx_path"] = str(most_recent)
            behavior["last_nudge_count"] = total

    elif not has_workspace and total == NO_WORKSPACE_NUDGE_THRESHOLD:
        nudges.append(
            "No active workspace detected. You've done significant work — if this is "
            "getting complex, consider creating a workspace "
            "(workspace/[task-id]/context.md) to capture code changes AND important "
            "user statements (requirements, decisions, preferences) so progress "
            "survives compaction."
        )

    try:
        behavior_path.write_text(json.dumps(behavior), encoding="utf-8")
    except Exception:
        pass

    if nudges:
        print(json.dumps({"additionalContext": "\n\n".join(nudges)}))

    return 0


if __name__ == "__main__":
    sys.exit(main())
