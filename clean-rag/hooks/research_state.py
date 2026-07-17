"""Shared state for the research gate.

The gate answers one question: was the file I'm about to edit actually covered by
research this turn?

Note the shape of that question. It is not "did some agent run", which is what
this used to ask, and the difference matters. Under the old rule one triage run
at the top of a turn unlocked every edit that followed: in practice a single
agent stamped the record and then ten unrelated code edits sailed through
unresearched. The gate had stopped complaining, so nobody noticed.

That failure is task drift, not omission. The model did research. It then edited
something else. A boolean cannot catch that, because its memory is "an agent ran"
rather than "an agent looked at this file".

So a stamp carries a scope: the files its research covered. The gate checks
membership. One research run covers a coherent multi file change, and an edit to
a file nobody researched still blocks. That's the guarantee of per edit gating at
roughly the cost of per turn gating.

Per edit gating (one agent spawn per file) was considered and rejected. There is
no evidence that re-researching ten times for one coherent refactor beats
researching once, and this codebase already learned what blind forced retrieval
costs when it deleted the topic knowledge base.

The scope-then-check pattern is not new here. scripts/consult-gate.py already
does it for the approval gate, and file_in_spec below is deliberately the same
matching logic.
"""

import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path

# Agents whose completion counts as research having happened. Both run the full
# pass every time: researcher maps the codebase and grounds the change in real
# engineering standards; swiper checks existence and finds what to clone. Either
# stamps the file scope it covered. The gate checks per-file membership in any
# stamp's scope, not whether a specific agent ran. /ps is the human's exit for
# a turn they already know is trivial — skips both research and the verifier gate.
RESEARCH_AGENTS = {"swiper", "researcher"}

# A record older than this is treated as gone, covering an abandoned turn whose
# edits arrive much later without a fresh prompt.
TURN_MAX_AGE_S = 3600


def clean_rag_home() -> Path:
    env = os.environ.get("CLEAN_RAG_HOME")
    if env:
        return Path(env)
    return Path(__file__).resolve().parent.parent


def _boost_home() -> Path:
    env = os.environ.get("CLAUDEBOOST_HOME")
    if env:
        return Path(env)
    return clean_rag_home().parent


def _write_lock(path: Path):
    """The real cross process lock, not the PID file convention.

    These hooks are separate short lived processes, and CLAUDE.md explicitly
    allows up to 3 agents in parallel, so two of them can finish milliseconds
    apart and both read-modify-write this same JSON. Without a lock the later
    write silently drops the earlier stamp: a lost update inside the very
    mechanism built to stop things going unnoticed.

    mcp-rag-server's locking.py is an OS level lock (msvcrt.locking on Windows).
    indexing.py's acquire_index_lock is NOT: it's a PID file with a TOCTOU gap
    between the check and the write, which is fine for serializing rare multi
    minute reindexes and wrong for a frequent short one like this.

    Degrades to no lock if the module can't be imported, since a hook that can't
    take a lock should still work, just without the race protection.
    """
    try:
        lock_src = _boost_home() / "mcp-rag-server" / "src"
        if str(lock_src) not in sys.path:
            sys.path.insert(0, str(lock_src))
        from rag_server.core.locking import index_write_lock

        return index_write_lock(path.with_suffix(".json.lock"))
    except Exception:
        import contextlib

        return contextlib.nullcontext()


def _state_dir() -> Path:
    d = clean_rag_home() / "state" / "research"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _record_path(session_id: str) -> Path:
    # Session ids come from Claude Code and could contain anything, so hash
    # rather than trusting one as a filename.
    key = hashlib.sha256((session_id or "no-session").encode("utf-8")).hexdigest()[:16]
    return _state_dir() / f"turn-{key}.json"


def _normalize(path: str) -> str:
    return path.replace("\\", "/").lower()


def file_in_scope(file_path: str, covered: list[str]) -> bool:
    """Is this file within what the research actually covered?

    Same matching as consult-gate.py's file_in_spec (scripts/consult-gate.py:51),
    plus glob support so research can declare a module rather than listing every
    file in it.

    Entries may be:
      - an absolute or relative path: clean-rag/server/app.py
      - a glob: clean-rag/hooks/*.py, or src/auth/**
    """
    norm = _normalize(file_path)

    for entry in covered:
        entry = _normalize(entry.strip().strip("/\\"))
        if not entry:
            continue

        if "*" in entry:
            # ** crosses directory separators, * does not.
            pattern = re.escape(entry).replace(r"\*\*", "\x00").replace(r"\*", "[^/]*")
            pattern = pattern.replace("\x00", ".*")
            if re.search(pattern + "$", norm):
                return True
            continue

        if norm == entry or norm.endswith("/" + entry):
            return True

    return False


def extract_covered_files(text: str, prefix: str = "COVERS:") -> list[str]:
    """Pull the file scope out of an agent's report.

    An agent declares scope with a line like:
        COVERS: clean-rag/server/app.py, clean-rag/hooks/*.py

    `prefix` lets a sibling gate reuse this same parser for its own marker line
    (verifier-gate's stamps use "VERIFIED:") instead of forking the logic.

    If it declares nothing, it covers nothing, and the gate will block. That's
    deliberate. An agent that can't say what it looked at hasn't given the gate
    anything to check, and silently treating that as "covers everything" is
    exactly the blanket clearance this design exists to remove.

    Claude Code's Agent tool appends an "agentId: ... (use SendMessage with
    to: ..., summary: ...)" wrapper suffix to a spawned agent's final report
    text, and it can land glued onto this exact line with no newline in
    between. Left alone, that suffix gets swept into the file list and
    corrupts the last entry, so it's cut off before the comma split.
    """
    if not text:
        return []

    marker = prefix.upper()
    for line in text.splitlines():
        stripped = line.strip().lstrip("*# ").strip()
        if stripped.upper().startswith(marker):
            raw = stripped.split(":", 1)[1]
            raw = raw.split("agentId:", 1)[0]
            return [p.strip().strip("`") for p in raw.split(",") if p.strip()]

    return []


def open_turn(session_id: str, prompt: str, quick: bool = False) -> None:
    """Called on UserPromptSubmit. Updates turn metadata; preserves existing stamps.

    Research coverage earned this session persists across messages until it expires
    (TURN_MAX_AGE_S) or new research lands. This is the prerequisite for the research
    gate being a hard block: under the old reset-on-every-message design, coverage
    from swiper was wiped by the next follow-up message before anything was edited,
    causing constant false blocks. Preserving stamps fixes that. Coverage now expires
    only via the TTL or when new research runs (which adds its own stamps on top).

    `quick` marks a /ps turn: the human's explicit "skip the ceremony". Set
    deterministically from the raw prompt text, never by the model.
    """
    path = _record_path(session_id)
    try:
        with _write_lock(path):
            try:
                record = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                record = {"session_id": session_id, "started_at": time.time(), "stamps": []}

            # Update metadata but preserve existing stamps. Coverage persists across
            # follow-up messages; it expires only via TTL or when new research runs.
            record["session_id"] = session_id
            record["started_at"] = time.time()
            record["prompt_preview"] = (prompt or "")[:200]
            record["quick"] = bool(quick)
            record.setdefault("stamps", [])

            path.write_text(json.dumps(record, indent=2), encoding="utf-8")
    except OSError:
        # A gate that can't write its record blocks every edit. Staying quiet is
        # the lesser evil; the pre edit hook explains a missing record itself.
        pass


def is_quick_turn(session_id: str) -> bool:
    """Did this turn start with /ps? Then the gates and the verifier stand down.

    Fail closed: a missing, malformed, or stale record returns False, so a broken
    record means "still require research and verification", never a silent skip. The
    age guard (same TURN_MAX_AGE_S the research check uses) also stops a quick flag
    leaking into a later turn if a following open_turn write failed and left the old
    record in place.
    """
    path = _record_path(session_id)
    if not path.exists():
        return False
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(record, dict) or not record.get("quick", False):
            return False
        return (time.time() - record.get("started_at", 0)) <= TURN_MAX_AGE_S
    except Exception:  # noqa: BLE001 -- any failure means "not quick", enforce the gate
        return False


def record_agent(session_id: str, agent_type: str, report: str = "") -> None:
    """Called on PostToolUse after researcher or swiper finishes."""
    if agent_type not in RESEARCH_AGENTS:
        return

    path = _record_path(session_id)

    with _write_lock(path):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            record = {"session_id": session_id, "started_at": time.time(), "stamps": []}

        record.setdefault("stamps", []).append({
            "agent": agent_type,
            "at": time.time(),
            "covers": extract_covered_files(report),
            "verdict": _first_verdict_line(report),
        })

        try:
            path.write_text(json.dumps(record, indent=2), encoding="utf-8")
        except OSError:
            pass


def _first_verdict_line(text: str) -> str:
    for line in (text or "").splitlines():
        stripped = line.strip()
        if stripped.upper().startswith("VERDICT:"):
            return stripped[:200]
    return (text or "")[:200]


def has_any_research_this_turn(session_id: str) -> tuple[bool, str]:
    """Did swiper run at all this turn? For actions with no single file to
    scope against, a destructive package manager command, not an edit to a file.
    Same freshness rule as check_file_researched, just without the per file scope
    check, since "which file does this cover" does not apply to a shell command.
    """
    path = _record_path(session_id)
    if not path.exists():
        return False, "no research agent has run this turn"

    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False, "the research record is unreadable"

    stamps = record.get("stamps", [])
    last_activity = max([record.get("started_at", 0)] + [s.get("at", 0) for s in stamps])
    age = time.time() - last_activity
    if age > TURN_MAX_AGE_S:
        return False, f"the research record is stale ({age / 60:.0f} minutes old)"

    if not stamps:
        return False, "no research agent has run this turn"

    return True, f"research ran this turn ({stamps[-1].get('agent')})"


# ---------------------------------------------------------------------------
# Session-scoped /ps persistence.
#
# /ps marks one message's turn record as quick. The next user message opens
# a fresh turn record with quick=False, so the gate blocks again on the very
# next edit. User sends /ps, then the actual task as a separate message. The
# task message gets blocked.
#
# Fix: a session-keyed file with a 10-minute TTL. set_session_quick() is
# called when /ps is detected. rag-enforce.py checks is_session_quick() on
# new turns and carries the flag forward. clear_session_quick() is called by
# research-record.py once real research lands, ending the sticky /ps.
# ---------------------------------------------------------------------------

SESSION_QUICK_MAX_AGE_S = 600  # 10 minutes


def _session_quick_path(session_id: str) -> Path:
    key = hashlib.sha256((session_id or "no-session").encode()).hexdigest()[:16]
    return _state_dir() / f"session-quick-{key}.json"


def set_session_quick(session_id: str) -> None:
    path = _session_quick_path(session_id)
    path.write_text(json.dumps({"set_at": time.time()}), encoding="utf-8")


def clear_session_quick(session_id: str) -> None:
    path = _session_quick_path(session_id)
    try:
        path.unlink(missing_ok=True)
    except Exception:
        pass


def is_session_quick(session_id: str) -> bool:
    """True if /ps was issued recently for this session and no research has landed since."""
    path = _session_quick_path(session_id)
    if not path.exists():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return (time.time() - data.get("set_at", 0)) <= SESSION_QUICK_MAX_AGE_S
    except Exception:
        return False


def check_file_researched(session_id: str, file_path: str) -> tuple[bool, str]:
    """Was this specific file covered by research this turn?

    Returns (ok, reason). The reason explains a refusal, so the gate can say
    something useful instead of just saying no.
    """
    path = _record_path(session_id)
    if not path.exists():
        return False, "no research agent has run this turn"

    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False, "the research record is unreadable"

    stamps = record.get("stamps", [])

    # Freshness keys off the most recent research activity, not the turn open time.
    # A long turn that keeps researching is not stale; only a genuinely abandoned
    # record is (its newest stamp, or its start if nothing stamped, has aged out).
    # Keying staleness to started_at alone bricked every edit in a session that ran
    # past TURN_MAX_AGE_S, even right after a valid research stamp landed for this file.
    last_activity = max([record.get("started_at", 0)] + [s.get("at", 0) for s in stamps])
    age = time.time() - last_activity
    if age > TURN_MAX_AGE_S:
        return False, f"the research record is stale ({age / 60:.0f} minutes old)"

    if not stamps:
        return False, "no research agent has run this turn"

    for stamp in stamps:
        if file_in_scope(file_path, stamp.get("covers", [])):
            return True, f"covered by {stamp.get('agent')}"

    # Research ran, but not on this file. This is the case the old boolean gate
    # waved through, and it's the one that actually bit.
    covered = sorted({c for s in stamps for c in s.get("covers", [])})
    if covered:
        shown = ", ".join(covered[:4]) + (" ..." if len(covered) > 4 else "")
        return False, f"research this turn covered {shown}, not this file"

    agents = ", ".join(s.get("agent", "?") for s in stamps)
    return False, f"{agents} ran but declared no file scope (no COVERS: line)"
