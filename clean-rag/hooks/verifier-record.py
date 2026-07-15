#!/usr/bin/env python
"""PostToolUse on Task and Agent. Stamps the verifier record when backpack finishes.

Mirrors research-record.py exactly, including its tool_response flattening (the
same list-of-content-blocks shape applies to any Task/Agent completion), pointed
at verifier_state instead of research_state. Never blocks; its only job is to
write down what happened.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from verifier_state import record_verifier  # noqa: E402

VERIFIER_AGENTS = {"backpack"}


def _agent_type(payload: dict) -> str:
    tool_input = payload.get("tool_input", {})
    return (
        tool_input.get("subagent_type")
        or tool_input.get("agent_type")
        or tool_input.get("agent")
        or ""
    )


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

    session_id = payload.get("session_id", "")
    report = _report(payload)
    record_verifier(session_id=session_id, report=report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
