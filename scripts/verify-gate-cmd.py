"""
ClaudeBoost verify-gate command hook - PostToolUse on Task.

Replaces the prompt-type "VERIFY GATE" hook that fired after every agent
spawn and forced Claude to respond before continuing the next batch step.

Problem with prompt-type:
  - Fires after EVERY Task tool call and injects as a user turn
  - Claude must respond before it can issue the next tool call
  - Code-review batching (passes 1-14) grinds to a halt because
    Claude stops to "respond to the verify gate" after each pass agent
  - context-nudge.py already has REVIEW_PASS_MARKERS suppression, but
    the prompt-type hook fired independently and overrode it

This script emits a non-blocking stderr nudge (system-reminder) instead.
Claude can read it and act on it — but is NOT forced to respond before
continuing batch work.

Behavior:
  - Code-review pass (description contains review pass markers) -> silent
  - Agent response contains BLOCKER/HIGH/MEDIUM findings -> stderr reminder
  - No findings detected -> silent
  - Always exits 0 (never blocks)
"""
from __future__ import annotations
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

BOOST_HOME = Path(os.environ.get("CLAUDEBOOST_HOME") or Path(__file__).resolve().parent.parent)
_FLAG = BOOST_HOME / "state" / "needs-verification.json"


REVIEW_PASS_MARKERS = (
    "review pass", "pass 1 —", "pass 2 —", "pass 3 —",
    "pass 4 —", "pass 5 —", "pass 6 —", "pass 7 —",
    "pass 8 —", "pass 9 —", "pass 10 —", "pass 11 —",
    "pass 12 —", "pass 13 —", "pass 14 —",
    "simplicity review", "dead code review",
    "ticket alignment review", "migration/schema review",
    "banned dependencies review", "test coverage",
    "smoke test review",
)

FINDING_KEYWORDS = (
    '"severity": "blocker"',
    '"severity": "high"',
    '"severity": "medium"',
    '"severity": "warning"',
    "blocker:", "high:", "medium:",
)


def main() -> int:
    raw = sys.stdin.read() if not sys.stdin.isatty() else ""
    try:
        payload = json.loads(raw) if raw else {}
    except Exception:
        payload = {}

    tool_input = payload.get("tool_input", {}) or {}
    tool_response = str(payload.get("tool_response", "") or "")
    desc = str(tool_input.get("description", "") or "").lower()
    response_lower = tool_response.lower()

    # Suppress during active parallel batch runs (/audit, etc.).
    # audit-in-progress.json is set by /audit Phase 0 and cleared at Phase 5.
    # Writing NEEDS_VERIFICATION during a batch flow would block the next agent batch.
    if (BOOST_HOME / "state" / "audit-in-progress.json").exists():
        return 0

    # Suppress during code-review batch runs — they have their own evaluator (Pass 15)
    if any(marker in desc for marker in REVIEW_PASS_MARKERS):
        return 0

    # Suppress after evaluator-agent runs — it IS the verification step
    if "evaluator" in desc:
        return 0

    # Only nudge if the response actually contains severity findings
    has_findings = any(kw in response_lower for kw in FINDING_KEYWORDS)
    if not has_findings:
        # Clear any stale flag — the latest agent run had no findings
        try:
            _FLAG.unlink(missing_ok=True)
        except Exception:
            pass
        return 0

    # Write the flag so agent-spawn-gate.py can block the next spawn
    try:
        _FLAG.write_text(
            json.dumps({
                "flagged_at": datetime.now(timezone.utc).isoformat(),
                "tool_name": tool_input.get("description", "Task"),
                "finding_summary": tool_response[:500],
            }),
            encoding="utf-8",
        )
    except Exception:
        pass  # never block on flag-write failure

    print(
        "[verify-gate nudge] Agent output contains BLOCKER/WARNING findings.\n"
        "Spawn evaluator-agent to verify — never self-verify (confirmation bias).\n"
        "Evaluator checks: does each finding cite file:line? Does code show the issue?\n"
        "Drop false positives. No findings after verify? Present results directly.",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
