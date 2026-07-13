"""Shared state for the research gate.

The gate has to answer one question: did research actually happen this turn?

The honest way to answer it is to record something the model cannot fabricate.
A self written "yes I researched" file proves nothing, the model writes that file.
An agent spawn is different: only Claude Code can start one, and only after it
finishes does the PostToolUse hook fire. So the gate keys off real agent runs.

One record per turn. UserPromptSubmit opens a new one, a completed research or
triage agent stamps it, and the pre edit gate reads it.
"""

import hashlib
import json
import os
import time
from pathlib import Path

# Agents whose completion counts as research having happened.
RESEARCH_AGENTS = {"research-agent", "triage-agent"}

# A turn record older than this is treated as gone. Covers the case where a turn
# is abandoned and a new edit arrives much later without a fresh prompt.
TURN_MAX_AGE_S = 3600


def clean_rag_home() -> Path:
    env = os.environ.get("CLEAN_RAG_HOME")
    if env:
        return Path(env)
    return Path(__file__).resolve().parent.parent


def _state_dir() -> Path:
    d = clean_rag_home() / "state" / "research"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _record_path(session_id: str) -> Path:
    # Session ids come from Claude Code and can contain anything, so hash rather
    # than trusting it as a filename.
    key = hashlib.sha256((session_id or "no-session").encode("utf-8")).hexdigest()[:16]
    return _state_dir() / f"turn-{key}.json"


def open_turn(session_id: str, prompt: str) -> None:
    """Called on UserPromptSubmit. Starts a fresh turn with no research in it."""
    record = {
        "session_id": session_id,
        "started_at": time.time(),
        "prompt_preview": (prompt or "")[:200],
        "agents_run": [],
    }
    try:
        _record_path(session_id).write_text(json.dumps(record, indent=2), encoding="utf-8")
    except OSError:
        # A gate that can't record is a gate that blocks everything. Staying
        # silent here is the lesser evil, the pre edit hook fails open on a
        # missing record and says why.
        pass


def record_agent(session_id: str, agent_type: str, verdict: str = "") -> None:
    """Called on PostToolUse after an agent finishes."""
    if agent_type not in RESEARCH_AGENTS:
        return

    path = _record_path(session_id)
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        record = {"session_id": session_id, "started_at": time.time(), "agents_run": []}

    record.setdefault("agents_run", []).append({
        "agent": agent_type,
        "at": time.time(),
        "verdict": verdict[:400],
    })

    try:
        path.write_text(json.dumps(record, indent=2), encoding="utf-8")
    except OSError:
        pass


def turn_has_research(session_id: str) -> tuple[bool, str]:
    """Did a research or triage agent complete during this turn?

    Returns (ok, reason). Reason explains a False so the gate can say something
    useful instead of just refusing.
    """
    path = _record_path(session_id)
    if not path.exists():
        return False, "no turn record, so no research agent has run"

    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False, "turn record is unreadable"

    age = time.time() - record.get("started_at", 0)
    if age > TURN_MAX_AGE_S:
        return False, f"turn record is stale ({age / 60:.0f} minutes old)"

    agents = record.get("agents_run", [])
    if not agents:
        return False, "no research agent has run this turn"

    names = ", ".join(a.get("agent", "?") for a in agents)
    return True, f"research ran this turn ({names})"
