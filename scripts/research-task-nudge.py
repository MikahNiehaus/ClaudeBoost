"""
ClaudeBoost research-task nudge — UserPromptSubmit hook.

Fires on every user message. Emits an additionalContext reminder to run
/research-task when an active workspace exists but has no research indexed yet.

Once /research-task has been run (workspace/.rag-index/research/ exists and
is non-empty), this script exits silently — no repeat nags.

Also emits a one-time reminder when no active workspace exists but the prompt
looks like a ticket/task start (contains keywords that suggest the user is
about to start work that would benefit from research).

Exit codes: always 0 (never blocks the prompt).
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

BOOST_HOME = Path(os.environ.get("CLAUDEBOOST_HOME") or Path(__file__).resolve().parent.parent)

TASK_KEYWORDS = (
    "workspace", "/workspace", "ticket", "implement", "build", "fix",
    "feature", "task", "research", "investigate", "pihole", "pi-hole",
    "set up", "setup", "install", "configure",
)


def _active_workspace() -> dict:
    f = BOOST_HOME / "state" / "active-workspace.json"
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _research_indexed(workspace_path: str) -> bool:
    """True if /research-task has been run for this workspace."""
    research_dir = Path(workspace_path) / ".rag-index" / "research"
    if not research_dir.exists():
        return False
    # Non-empty means at least one chunk was indexed
    return any(research_dir.iterdir())


def _prompt_suggests_task(prompt: str) -> bool:
    lower = prompt.lower()
    return any(kw in lower for kw in TASK_KEYWORDS)


def main() -> int:
    try:
        raw = sys.stdin.read() if (sys.stdin and not sys.stdin.isatty()) else ""
    except Exception:
        raw = ""
    try:
        payload = json.loads(raw) if raw else {}
    except Exception:
        payload = {}

    user_prompt = str(payload.get("prompt", "") or "")

    ws = _active_workspace()
    ws_path = ws.get("workspace_path") or ws.get("path") or ""
    ws_id = ws.get("workspace") or ws.get("workspace_id") or ""

    if ws_path and not _research_indexed(ws_path):
        # Active workspace but research not yet indexed — nudge every message
        print(json.dumps({
            "additionalContext": (
                f"RESEARCH REMINDER: Active workspace '{ws_id}' has no research index yet. "
                f"Run /research-task before delegating to agents so they get task-specific "
                f"documentation as Tier 3c context (official docs, APIs, frameworks). "
                f"Skip only for trivial/config-only tasks."
            )
        }))
        return 0

    if not ws_path and _prompt_suggests_task(user_prompt):
        # No workspace yet, but prompt looks like task work — one-time hint
        print(json.dumps({
            "additionalContext": (
                "RESEARCH REMINDER: If this is a new task, run /workspace first to create a "
                "workspace, then /research-task to index relevant docs before agents start work."
            )
        }))
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
