"""
ClaudeBoost skill verify-gate - PreToolUse hook on Skill tool.

Companion to agent-spawn-gate.py, which on this branch is a no op stub that
exits 0. So this hook is the only half of that pair that does anything: it
fires on the Skill tool, which the Task gate never covered, closing the gap
where /qa or /workspace invoked right after /xray produced findings skipped
verification entirely.

It checks needs-verification.json and NUDGES when an action skill is invoked
with findings still unverified. It does not block.

It used to exit 2 and refuse the skill. That was wrong twice over. The refusal
told the operator to spawn `evaluator-agent`, which has never existed in this
repo, and the flag cleared only when a Task description happened to contain the
literal word "evaluator" or "verdict", so following the instruction verbatim
could not clear it. Beyond the broken wording, a verifier gate refusing work is
the enforcement shape this project has already reverted twice; see the recorded
decision in clean-rag/hooks/verifier-gate.py. Judgement calls nudge, and only
security guards refuse.

Clearing it is verify-gate-cmd.py's job, which now recognises the real agents
(quick-cop, bad-cop, good-cop) as well as an /audit batch.

Blocked skills (run code or tests against unverified findings):
  qa, workspace, explore, plan-task, create-prd, done, debug

Pass-through skills (ARE the verification step, or are read-only):
  audit, xray, security-review, graph, rag, rag-health,
  telemetry, ws, changes, visualize, speak, handoff, clear-safe

Behavior:
  - needs-verification.json absent           -> exit 0 silently
  - audit-in-progress.json present           -> exit 0 silently (batch in flight)
  - skill is pass-through                    -> exit 0 silently
  - skill is action + flag present           -> exit 0 + stderr (nudge only)
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

    # json.loads accepts any JSON value, not only an object. A payload of
    # `null`, `[]`, `"a string"` or `17` parses fine and then blows up on
    # .get(). That is an AttributeError at exit 1, and 1 is not a block under
    # the PreToolUse contract, so it failed open with a traceback on every
    # Skill call. Same defect class fixed across five clean-rag hooks; this
    # one sat outside that scope.
    if not isinstance(payload, dict):
        payload = {}

    tool_input = payload.get("tool_input", {}) or {}
    if not isinstance(tool_input, dict):
        tool_input = {}
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
        f"findings that nothing has checked yet.\n"
        f"Spawn quick-cop to confirm each finding is real against the actual "
        f"code, or run /audit, before acting on them in /{skill_name}. "
        f"Use bad-cop instead when the findings need adversarial testing rather "
        f"than a claim check.\n"
        f"This is a nudge, not a block: /{skill_name} runs either way. The flag "
        f"clears when one of those agents completes.\n"
    )
    if summary:
        msg += f"Finding preview: {summary[:150]}..."

    print(msg, file=sys.stderr)
    return 0


if __name__ == "__main__":  # pragma: no cover
    # Backstop behind the shape checks in main(). This hook only ever nudges,
    # so any unhandled failure should be silence rather than a traceback on a
    # tool call the operator did nothing wrong to make.
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)
