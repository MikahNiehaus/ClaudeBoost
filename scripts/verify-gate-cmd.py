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

# Agents whose completion IS the verification step, so their own output must
# not re-arm the flag. Kept as a set of real agent names; there is no
# `evaluator-agent` and there never was.
VERIFIER_AGENTS = frozenset({"quick-cop", "bad-cop", "good-cop"})

# Fallback for a payload that carries no agent type. Substring match on the
# caller's own description, so it is loose by nature.
_DESC_MARKERS = ("quick-cop", "quick cop", "bad-cop", "bad cop",
                 "good-cop", "good cop", "evaluator", "verdict")


def _agent_type(tool_input: dict) -> str:
    """Which agent the Task payload says ran.

    Same resolution order as clean-rag/hooks/research-record.py and
    verifier-record.py. Kept identical on purpose: three hooks disagreeing
    about what counts as an agent name is its own class of bug.

    Takes the tool_input rather than the whole payload because main() has
    already checked that it is a dict, and re-reading it here would be a
    second place for that check to be missing.
    """
    return str(
        tool_input.get("subagent_type")
        or tool_input.get("agent_type")
        or tool_input.get("agent")
        or ""
    )


def _ran_a_verification(tool_input: dict, desc: str) -> bool:
    """Whether this Task completion IS the verification step.

    Two ways to recognise one, because the description alone was never enough.
    This used to match only "evaluator" or "verdict" in the caller's
    description. Both words were written for `evaluator-agent`, which has never
    existed in this repo. So the only way to clear the flag was to happen to
    use one of those two words: a real quick-cop spawn described as "Check the
    finding" left it set forever.

    The reliable signal is the agent type itself, which the Task payload
    carries. `_agent_type` is the same resolution order already used by
    clean-rag/hooks/research-record.py and verifier-record.py, so all three
    hooks agree on what a payload says the agent was.

    The description match stays as a fallback, but ONLY when the payload
    carries no agent type at all, which is the single case it was written for.
    As a free standing disjunct it also matched a payload naming an agent that
    is not a verifier, so a researcher spawn described as "Research the
    evaluator pattern used elsewhere" deleted a real pending finding: the
    description is the caller's own prose and says nothing about which agent
    ran. Reading it only in the absence of the reliable signal keeps the
    fallback doing its job and stops it overruling the answer.

    "verdict" is kept in the marker list because a verification pass is often
    named for its output, e.g. "Opus verdict synthesis"; without it a verifier
    payload carrying no type re-flags its own findings and loops.
    """
    agent_type = _agent_type(tool_input).lower()
    if agent_type:
        return agent_type in VERIFIER_AGENTS
    return any(marker in desc for marker in _DESC_MARKERS)


def main() -> int:
    try:
        raw = sys.stdin.read() if (sys.stdin and not sys.stdin.isatty()) else ""
    except Exception:
        raw = ""
    try:
        payload = json.loads(raw) if raw else {}
    except Exception:
        payload = {}

    # json.loads accepts any JSON value, not only an object, so `null`, `[]`,
    # `"a string"` and `17` all parse and then blow up on .get(). That is an
    # AttributeError at exit 1, and 1 is not a recognized PostToolUse verdict,
    # so the hook crashed rather than answering. Same defect class already
    # fixed across five clean-rag hooks and in skill-verify-gate.py, whose
    # guards this matches; this hook sat outside that scope.
    if not isinstance(payload, dict):
        payload = {}

    tool_input = payload.get("tool_input", {}) or {}
    if not isinstance(tool_input, dict):
        tool_input = {}

    tool_response = str(payload.get("tool_response", "") or "")
    desc = str(tool_input.get("description", "") or "").lower()
    response_lower = tool_response.lower()

    # Suppress during active parallel batch runs (/audit, etc.).
    # audit-in-progress.json is set by /audit Phase 0 and cleared at Phase 5.
    # Writing NEEDS_VERIFICATION during a batch flow would block the next agent batch.
    if (BOOST_HOME / "state" / "audit-in-progress.json").exists():
        return 0

    # Suppress during /review --deep batch runs — they have their own evaluator (Pass 15)
    if any(marker in desc for marker in REVIEW_PASS_MARKERS):
        return 0

    # Suppress after a verification agent runs — its own findings must not
    # re-arm the flag against itself. See _ran_a_verification for which signal
    # settles it and why the description is only a fallback.
    if _ran_a_verification(tool_input, desc):
        try:
            _FLAG.unlink(missing_ok=True)
        except Exception:
            pass
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
                "cwd": os.getcwd(),
                "tool_name": tool_input.get("description", "Task"),
                "finding_summary": tool_response[:500],
            }),
            encoding="utf-8",
        )
    except Exception:
        pass  # never block on flag-write failure

    print(
        "[verify-gate nudge] Agent output contains BLOCKER/WARNING findings.\n"
        "Spawn quick-cop to check them — never self-verify (confirmation bias).\n"
        "It checks: does each finding cite file:line? Does the code show the issue?\n"
        "Drop false positives. No findings after the check? Present results directly.\n"
        "Use bad-cop instead when the findings need adversarial tests run against\n"
        "real code rather than a read-and-confirm pass.",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception:
        # The shape checks in main() are the real fix; this is the backstop the
        # five clean-rag hooks in this same class already carry and this one
        # did not. An uncaught exception exits 1, which is not a recognized
        # PostToolUse verdict, so a crash here reads as a broken hook rather
        # than as "nothing to say". This hook only ever nudges, so exit 0 is
        # the honest answer when it cannot form an opinion.
        sys.exit(0)
