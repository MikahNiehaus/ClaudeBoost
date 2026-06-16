"""
ClaudeBoost CONSULT gate — command-type PreToolUse hook.

Replaces the prompt-type hook in scripts/setup.ps1. Prompt hooks are pure LLM
judgments without tool access, so they can't actually read the mode file or
session-approvals.json. This script reads them directly and makes a deterministic call.

Behavior:
  - AUTO mode    → exit 0 silently
  - Exempt paths → exit 0 silently (workspace/, knowledge/, plans/, docs/)
  - Edit/MultiEdit/Bash → exit 0 silently (grinding existing files is fine)
  - Write to existing file → exit 0 silently (still grinding)
  - Write to NEW file with task-plan.json present → exit 0 silently (plan approved)
  - Write to NEW file with NO task-plan.json → permissionDecision:"ask"

This is a task-level gate, not action-level. The pattern: before starting new work
that creates files, describe what you're building and wait for yes. Once approved,
write task-plan.json and grind freely through the whole task.

See research-brief in workspace/consult-mode-improvement-2026-06-16/ for why
task-level beats per-file nudges.
"""
from __future__ import annotations
import json
import os
import sys
from pathlib import Path

EXEMPT_FRAGMENTS = [
    "/workspace/", "\\workspace\\",
    "/knowledge/", "\\knowledge\\",
    "/plans/", "\\plans\\",
    "/docs/", "\\docs\\",
]


def read_json(path: str | os.PathLike, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return default


def main() -> int:
    home = os.environ.get("CLAUDEBOOST_HOME") or os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..")
    )
    mode = read_json(Path(home) / "state" / "claudeboost-mode.json", {}).get("mode", "CONSULT")

    # AUTO: always pass silently
    if mode == "AUTO":
        return 0

    # Read hook payload from stdin
    raw = sys.stdin.read() if not sys.stdin.isatty() else ""
    try:
        payload = json.loads(raw) if raw else {}
    except Exception:
        payload = {}

    tool_name = payload.get("tool_name", "") or ""
    tool_input = payload.get("tool_input", {}) or {}

    # Only gate Write tool calls. Edit/MultiEdit are on existing files (grinding).
    # Bash redirects are low-signal and over-fire — skip them.
    if tool_name != "Write":
        return 0

    file_path = (tool_input.get("file_path") or tool_input.get("path") or "").replace("\\", "/")
    if not file_path:
        return 0

    # Exempt paths: workspace, knowledge, plans, docs are low-stakes
    if any(frag.replace("\\", "/") in file_path for frag in EXEMPT_FRAGMENTS):
        return 0

    # Writing to an existing file is grinding, not starting new work
    if Path(file_path).exists():
        return 0

    # New file creation — check if a task plan has been approved
    task_plan = Path(home) / "state" / "task-plan.json"
    if task_plan.exists():
        return 0  # Plan logged — grind freely

    # No plan on record. Pause and ask the user.
    print(json.dumps({
        "permissionDecision": "ask",
        "reason": (
            f"About to create '{Path(file_path).name}' but no task plan is logged. "
            "Before writing new files, describe in 2-3 sentences what you're building "
            "(what it will look/work like from the user's perspective, plus any meaningful "
            "choices where different approaches produce different outcomes). "
            "Once the user approves, write state/task-plan.json and then grind freely."
        )
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
