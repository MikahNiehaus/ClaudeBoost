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

# HIGH urgency: these topics almost always need external research before implementation
HIGH_URGENCY_KEYWORDS = (
    "integration", "api", "migrate", "migration", "upgrade", "authentication",
    "authorization", "oauth", "jwt", "database schema", "third-party",
    "webhook", "payment", "stripe", "twilio", "sendgrid", "external service",
    "compliance", "gdpr", "hipaa", "security audit", "vulnerability",
)

# LOW urgency: research may help but isn't critical
LOW_URGENCY_KEYWORDS = (
    "workspace", "/workspace", "ticket", "implement", "build",
    "feature", "task", "research", "investigate", "pihole", "pi-hole",
    "set up", "setup", "install", "configure",
    "endpoint", "component", "page", "model", "service", "handler",
    "controller", "workflow", "add", "create",
)

# These never need external research — skip the nudge entirely
SKIP_KEYWORDS = (
    "fix typo", "rename", "refactor", "cleanup", "format", "lint",
    "update comment", "fix test", "bump version",
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


def _prompt_suggests_task(prompt: str) -> str:
    """Return 'high', 'low', or '' based on keyword tier match.

    Checks skip keywords first — if matched, returns '' so the nudge is suppressed.
    Then checks high urgency, then low urgency.
    """
    lower = prompt.lower()
    if any(kw in lower for kw in SKIP_KEYWORDS):
        return ""
    if any(kw in lower for kw in HIGH_URGENCY_KEYWORDS):
        return "high"
    if any(kw in lower for kw in LOW_URGENCY_KEYWORDS):
        return "low"
    return ""


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

    if not ws_path:
        tier = _prompt_suggests_task(user_prompt)
        if tier == "high":
            print(json.dumps({
                "additionalContext": (
                    "⚡ research-task recommended: This task involves external integrations or "
                    "security-sensitive work — external docs are almost always needed. Run "
                    "/workspace first, then `/research-task [workspace-id]` before delegating "
                    "to implementation agents."
                )
            }))
        elif tier == "low":
            print(json.dumps({
                "additionalContext": (
                    "💡 Consider running /workspace first, then `/research-task [workspace-id]` "
                    "— it'll automatically find relevant docs for this task and give agents "
                    "better context."
                )
            }))
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
