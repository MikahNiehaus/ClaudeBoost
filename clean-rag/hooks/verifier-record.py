#!/usr/bin/env python
"""PostToolUse on Task and Agent. Stamps the verifier record when good-cop
finishes, or when bad-cop finishes having found nothing (a genuinely clean
adversarial pass needs no separate good-cop run to confirm it).

Mirrors research-record.py exactly, including its tool_response flattening (the
same list-of-content-blocks shape applies to any Task/Agent completion), pointed
at verifier_state instead of research_state. Never blocks; its only job is to
write down what happened.

One completion it deliberately does not write down: bad-cop in Mode B, the /qa
evidence judge. That pass reads a finished QA session's artifacts and never looks
at a diff, so a stamp for it would tell verifier-gate.py that bad-cop reviewed
the code and found real bugs. See is_evidence_judge_pass in verifier_state.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from verifier_state import is_evidence_judge_pass, record_verifier  # noqa: E402

VERIFIER_AGENTS = {"good-cop", "bad-cop"}


def _agent_type(payload: dict) -> str:
    tool_input = payload.get("tool_input", {})
    return (
        tool_input.get("subagent_type")
        or tool_input.get("agent_type")
        or tool_input.get("agent")
        or ""
    )


def _spawn_prompt(payload: dict) -> str:
    """The prompt the agent was spawned with, which is where the mode marker is."""
    return payload.get("tool_input", {}).get("prompt") or ""


def _report(payload: dict) -> str:
    """The agent's report, flattened to plain text. See research-record.py's
    _report() for why this can't just be str(tool_response)."""
    response = payload.get("tool_response", "")

    if isinstance(response, str):
        return response

    if isinstance(response, list):
        parts = []
        for block in response:
            if isinstance(block, dict):
                parts.append(block.get("text") or block.get("content") or "")
            elif isinstance(block, str):
                parts.append(block)
        return "\n".join(p for p in parts if p)

    if isinstance(response, dict):
        inner = response.get("content") or response.get("output") or response.get("text")
        if inner is None:
            return ""
        if isinstance(inner, (str, list, dict)):
            return _report({"tool_response": inner})
        return str(inner)

    return str(response)


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read())
    except Exception:
        return 0

    if payload.get("tool_name") not in ("Task", "Agent"):
        return 0

    agent_type = _agent_type(payload)
    if agent_type not in VERIFIER_AGENTS:
        return 0

    report = _report(payload)
    if is_evidence_judge_pass(_spawn_prompt(payload), report):
        return 0

    session_id = payload.get("session_id", "")
    record_verifier(session_id=session_id, report=report, agent_type=agent_type)
    return 0


if __name__ == "__main__":
    sys.exit(main())
