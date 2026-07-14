#!/usr/bin/env python
"""PostToolUse on Task and Agent. Stamps the turn record when research finishes.

This is the half of the gate the model cannot simply skip. research-gate.py
refuses an edit unless this hook has fired, and this hook only fires after Claude
Code has actually run a research or triage agent to completion.

To be clear about what that is and isn't: it stops the model forgetting or
drifting, which is the real failure. It is not a security boundary. A model with
Write access can author a stamp file directly if it sets out to. The only actual
security control here is the bash guard on the research agents themselves.

Never blocks. Its only job is to write down what happened.
"""

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from research_state import (  # noqa: E402
    RESEARCH_AGENTS,
    clean_rag_home,
    extract_covered_files,
    record_agent,
)


def _agent_type(payload: dict) -> str:
    tool_input = payload.get("tool_input", {})
    return (
        tool_input.get("subagent_type")
        or tool_input.get("agent_type")
        or tool_input.get("agent")
        or ""
    )


def _report(payload: dict) -> str:
    """The agent's report, flattened to plain text.

    tool_response is not a string. It arrives as a list of content blocks,
    [{"type": "text", "text": "..."}], and str() on that gives a Python repr
    where newlines are escaped as literal backslash-n. Anything downstream doing
    splitlines() then sees one enormous line and matches nothing, which would
    make the COVERS scope undiscoverable and leave the gate blocking every edit
    forever. Found by reading a real stamped record rather than trusting the
    shape the docs implied.

    Passed through whole rather than reduced to a verdict line, because the gate
    needs COVERS, and that's what names the files the research actually looked at.
    """
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


def _log_triage_decision(session_id: str, report: str) -> None:
    """Append the triage verdict to a persistent log, for a future skip classifier.

    The plan is a classifier fine tuned on real NONE vs RESEARCH decisions, which
    beats a zero shot one, and that needs labeled data. So record every triage
    verdict with its context here. Append only, and it never raises: logging must
    not break the gate.
    """
    verdict = ""
    for line in report.splitlines():
        s = line.strip().upper()
        if s.startswith("VERDICT:"):
            if "NONE" in s:
                verdict = "NONE"
            elif "RESEARCH" in s:
                verdict = "RESEARCH"
            break
    if not verdict:
        return

    entry = {
        "at": time.time(),
        "session_id": session_id,
        "verdict": verdict,
        "covers": extract_covered_files(report),
        "report": report[:2000],
    }
    try:
        path = clean_rag_home() / "state" / "triage-decisions.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except OSError:
        pass


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

    session_id = payload.get("session_id", "")
    report = _report(payload)
    record_agent(session_id=session_id, agent_type=agent_type, report=report)
    if agent_type == "triage-agent":
        _log_triage_decision(session_id, report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
