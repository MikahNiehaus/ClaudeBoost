"""Recover a finished subagent's type when SubagentStop leaves it blank.

SubagentStop usually carries `agent_type`. It does not always. Two payloads
captured by a live probe on this machine arrived with `agent_type: ""` and a
populated `last_assistant_message`, and anthropics/claude-code#27755 reports
the same shape: "when SubagentStop does fire, it often lacks the
last_assistant_message field or arrives with an empty agent_type".

A blank type falls straight through the record hooks' membership test against
VERIFIER_AGENTS / RESEARCH_AGENTS, so a real good-cop pass writes no stamp at
all and every file it reviewed still reads as unverified.

WHERE THE TYPE IS RECOVERED FROM, AND WHY IT IS THIS AND NOT THE REPORT

Claude Code writes a sidecar next to every subagent transcript:

    <session>/subagents/agent-<agent_id>.meta.json
    {"agentType": "good-cop", "description": "Fix bad-cop High findings",
     "toolUseId": "...", "spawnDepth": 1, "requestShape": "background", ...}

That file is written by the harness, not by the agent, which is the entire
reason it is the fallback. The obvious alternative -- when the type is blank,
look at whether the report contains a "VERIFIED:" line -- would open the exact
hole the stamped-record design exists to close. clean-rag/CLAUDE.md puts it
plainly: "Only Claude Code can start an agent, and the stamp only lands after
one completes. There is no path from 'say you researched' to a stamped record."
Trusting report text would create that path, and any agent could then mint a
coverage stamp by printing one line.

So this resolves identity from harness-written state or not at all. An agent
with no readable sidecar stays unidentified and records nothing, which is what
already happens today and is the safe direction to fail.
"""

from __future__ import annotations

import json
from pathlib import Path


def _candidate_meta_paths(payload: dict):
    """Where the sidecar for this completion could be, best source first."""
    transcript = payload.get("agent_transcript_path")
    if isinstance(transcript, str) and transcript:
        # .../subagents/agent-<id>.jsonl -> .../subagents/agent-<id>.meta.json
        try:
            yield Path(transcript).with_suffix(".meta.json")
        except ValueError:
            pass

    agent_id = payload.get("agent_id")
    session_transcript = payload.get("transcript_path")
    if (isinstance(agent_id, str) and agent_id
            and isinstance(session_transcript, str) and session_transcript):
        # .../<session>.jsonl -> .../<session>/subagents/agent-<id>.meta.json
        try:
            session_dir = Path(session_transcript).with_suffix("")
        except ValueError:
            return
        yield session_dir / "subagents" / f"agent-{agent_id}.meta.json"


def _read_agent_type(meta_path: Path) -> str:
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ""
    if not isinstance(meta, dict):
        return ""
    value = meta.get("agentType") or meta.get("agent_type") or ""
    return value.strip() if isinstance(value, str) else ""


def agent_type_from_meta(payload: dict) -> str:
    """The agent's type per the harness's own sidecar, or "" if unresolvable.

    Never raises and never blocks: these hooks only write a record, so an
    unreadable sidecar has to degrade to "we don't know", not to an exception.
    """
    if not isinstance(payload, dict):
        return ""
    try:
        for meta_path in _candidate_meta_paths(payload):
            agent_type = _read_agent_type(meta_path)
            if agent_type:
                return agent_type
    except Exception:
        return ""
    return ""
