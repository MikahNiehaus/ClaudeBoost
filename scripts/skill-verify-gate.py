"""
ClaudeBoost skill verify-gate - PreToolUse hook on Skill tool.

Companion to agent-spawn-gate.py. That gate fires on Task (agent spawns) and
blocks them when needs-verification.json is pending. But it does NOT fire on
the Skill tool — so if the user invokes /qa or /workspace via Skill right after
/xray produces findings, the gate is bypassed entirely.

This hook closes that gap. It checks the same needs-verification.json flag and
blocks action skills until the flag is cleared (by running /audit or spawning
an evaluator-agent via Task, both of which clear the flag).

Blocked skills (run code or tests against unverified findings):
  qa, workspace, explore, plan-task, create-prd, done, debug

Pass-through skills (ARE the verification step, or are read-only):
  audit, xray, security-review, graph, rag, rag-health,
  telemetry, ws, changes, visualize, speak, handoff, clear-safe

Behavior:
  - needs-verification.json absent           -> exit 0 silently
  - audit-in-progress.json present           -> exit 0 silently (batch in flight)
  - skill is pass-through                    -> exit 0 silently
  - skill is action + flag present           -> exit 2 + stderr (blocked)
"""
from __future__ import annotations
import json
import os
import sys
from pathlib import Path

BOOST_HOME = Path(os.environ.get("CLAUDEBOOST_HOME") or Path(__file__).resolve().parent.parent)
_FLAG = BOOST_HOME / "state" / "needs-verification.json"
_AUDIT_ACTIVE = BOOST_HOME / "state" / "audit-in-progress.json"

# Skills that start new work against code that has unverified findings pending.
# Blocked when needs-verification.json exists.
ACTION_SKILLS = {
    "qa",
    "workspace",
    "explore",
    "plan-task",
    "create-prd",
    "done",
    "debug",
}

# Skills that are verification-layer tools, read-only research, or housekeeping.
# These are always allowed regardless of the flag.
PASSTHROUGH_SKILLS = {
    "audit",
    "grill-me",
    "grilling",
    "quick-cop",
    "xray",
    "security-review",
    "graph",
    "rag",
    "rag-health",
    "telemetry",
    "ws",
    "changes",
    "visualize",
    "speak",
    "handoff",
    "clear-safe",
    "index-project",
    "index-boost",
    "boost",
    "status",
}


def main() -> int:
    try:
        raw = sys.stdin.read() if (sys.stdin and not sys.stdin.isatty()) else ""
    except Exception:
        raw = ""
    try:
        payload = json.loads(raw) if raw else {}
    except Exception:
        payload = {}

    tool_input = payload.get("tool_input", {}) or {}
    skill_name = str(tool_input.get("skill", "") or "").strip().lower()

    # No flag — nothing to enforce
    if not _FLAG.exists():
        return 0

    # Audit batch in flight — suppress (audit-in-progress.json set by /audit Phase 0)
    if _AUDIT_ACTIVE.exists():
        return 0

    # Pass-through skills are never blocked
    if skill_name in PASSTHROUGH_SKILLS:
        return 0

    # Unknown skills default to pass-through (don't break unknown skills)
    if skill_name not in ACTION_SKILLS:
        return 0

    # Read flag for context in the message
    try:
        flag_data = json.loads(_FLAG.read_text(encoding="utf-8"))
        flagged_by = flag_data.get("tool_name", "a prior agent")
        summary = flag_data.get("finding_summary", "")[:200]
    except Exception:
        flagged_by = "a prior agent"
        summary = ""

    msg = (
        f"[skill-verify-gate] NEEDS_VERIFICATION pending — {flagged_by} produced "
        f"findings that have not been verified by evaluator-agent yet.\n"
        f"Run /audit or spawn evaluator-agent to verify the findings before "
        f"running /{skill_name}. The gate clears automatically when the evaluator runs.\n"
    )
    if summary:
        msg += f"Finding preview: {summary[:150]}..."

    print(msg, file=sys.stderr)
    return 2


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
