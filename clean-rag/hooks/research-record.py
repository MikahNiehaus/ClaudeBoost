#!/usr/bin/env python
"""PostToolUse on Task and Agent. Stamps the turn record when research finishes.

This is the half of the gate the model cannot forge. research-gate.py refuses an
edit unless this hook has fired, and this hook only fires after Claude Code has
actually run a research or triage agent to completion. There is no path from
"claim you researched" to a stamped record.

Never blocks. Its only job is to write the record down.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from research_state import RESEARCH_AGENTS, record_agent  # noqa: E402


def _agent_type(payload: dict) -> str:
    tool_input = payload.get("tool_input", {})
    return (
        tool_input.get("subagent_type")
        or tool_input.get("agent_type")
        or tool_input.get("agent")
        or ""
    )


def _verdict(payload: dict) -> str:
    """Pull the agent's verdict out of its response, for the record.

    Only used for the log. The gate cares that an agent ran, not what it said,
    because a triage NONE and a full research report both mean the work got
    looked at.
    """
    response = payload.get("tool_response", "")
    if isinstance(response, dict):
        response = response.get("content") or response.get("output") or str(response)
    if not isinstance(response, str):
        response = str(response)

    for line in response.splitlines():
        stripped = line.strip()
        if stripped.upper().startswith("VERDICT:"):
            return stripped
    return response[:200]


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read())
    except Exception:
        return 0

    if payload.get("tool_name") not in ("Task", "Agent"):
        return 0

    agent_type = _agent_type(payload)
    if agent_type not in RESEARCH_AGENTS:
        return 0

    record_agent(
        session_id=payload.get("session_id", ""),
        agent_type=agent_type,
        verdict=_verdict(payload),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
