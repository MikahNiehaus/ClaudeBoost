#!/usr/bin/env python
"""PreToolUse on Task/Agent. Increments the swiper-active counter when swiper starts.

Swiper runs as a subagent with its own session_id. The research gate checks that
session_id, finds no turn record for it, and would block every Write swiper tries
to make. This hook increments a counter before the subagent starts so the gate
can allow those writes without requiring a turn record for the subagent's session.

swiper-finished() in research-record.py decrements the counter when the task
completes, so the bypass is scoped exactly to swiper's lifetime.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from research_state import swiper_started


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read())
    except Exception:
        return 0

    if payload.get("tool_name") not in ("Task", "Agent"):
        return 0

    tool_input = payload.get("tool_input", {})
    agent_type = (
        tool_input.get("subagent_type")
        or tool_input.get("agent_type")
        or tool_input.get("agent")
        or ""
    ).lower()

    if agent_type == "swiper":
        swiper_started()

    return 0


if __name__ == "__main__":
    sys.exit(main())
