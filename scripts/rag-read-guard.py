"""
ClaudeBoost rag-read-guard -- PreToolUse hook on Grep and Read.

Hard-blocks file searching when Claude has made too many file reads without
calling a RAG tool first. RAG finds the relevant file; Grep/Read reads it.
Doing it backwards (Read first, RAG never) is the pattern this guard catches.

Thresholds:
  RAG_THRESHOLD: consecutive Grep/Read calls without any RAG call before blocking
  EXEMPTED_PATHS: file paths that are always allowed (config, workspace files, etc.)

Exit codes:
  0 = allow (RAG was called recently, or below threshold, or RAG unavailable)
  2 = block (too many reads without RAG -- call rag_search first)
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

from rag_port import rag_url

# Block after this many consecutive file searches without RAG.
#
# Was 6, paired with a soft reminder at 5, so six whole-file reads landed in the
# main context before anything engaged. Measured across 322 real transcripts,
# Read is the single most expensive channel there is: 5,167 calls averaging
# 1,267 tokens, and weighted by how many later requests re-read each one it
# costs 1.66b tokens, more than every Bash discovery command combined. A RAG
# chunk is roughly 500 tokens. Engaging at 3 moves discovery to the cheap path
# sooner.
#
# It could not be tightened before now: this hook pointed at port 8612 and told
# the model to call an `rag_search` MCP tool, neither of which existed, so
# blocking earlier would only have blocked more reads while offering a broken
# alternative.
#
# Must stay ABOVE context-nudge.py's RAG_THRESHOLD, or the soft reminder becomes
# dead code. A PreToolUse block stops the tool running, so PostToolUse never
# fires and the counter never climbs past this number.
# tests/test_rag_guard_thresholds.py holds that ordering.
RAG_THRESHOLD = 3

# Always allow reads of these paths -- no RAG needed for config/workspace files
EXEMPTED_SUFFIXES = {".json", ".lock", ".env", ".gitignore", ".toml", ".yaml", ".yml"}
EXEMPTED_NAME_FRAGMENTS = {
    "context.md", "settings", "claude.md", "memory", "package", "requirements",
    "cargo.toml", "pyproject", "go.mod", "go.sum", "tsconfig",
}


def is_exempted(tool_input: dict) -> bool:
    """Return True if this file read should be allowed without a prior RAG call."""
    path_str = str(tool_input.get("file_path", "") or tool_input.get("path", "") or "").lower()
    pattern_str = str(tool_input.get("pattern", "")).lower()

    if any(frag in path_str for frag in EXEMPTED_NAME_FRAGMENTS):
        return True
    if Path(path_str).suffix in EXEMPTED_SUFFIXES:
        return True
    if Path(path_str).suffix == ".md":
        if "workspace/" in path_str or "/workspace" in path_str or "state/" in path_str:
            return True
        return False
    if "workspace" in pattern_str or "state/" in pattern_str:
        return True
    return False


def _resolve_heartbeat_path() -> Path:
    """The liveness file this guard trusts before it blocks anything.

    This pointed at mcp-rag-server/.rag-index/.heartbeat, which belonged to the
    retired 8612 server. That server was deleted, so on a fresh clone the file
    does not exist at all, and on a machine that still has the leftover
    directory it sits hours stale with model_loaded false. Either way
    _rag_is_live() returned False and the guard never blocked a single read. It
    was not mistuned, it was dead code, which is why raising or lowering
    RAG_THRESHOLD had no observable effect.

    clean-rag writes its own every 30s at clean-rag/state/.heartbeat
    (server/app.py _write_heartbeat) in a compatible shape: ts, model_loaded,
    plus a status field this does not need.

    The old RAG_INDEX_DIR override is deliberately not honored any more. It
    named the retired server's index directory, so respecting a value someone
    still has set would point the guard straight back at the dead file.
    """
    clean_rag_home = os.environ.get("CLEAN_RAG_HOME")
    if clean_rag_home:
        return Path(clean_rag_home) / "state" / ".heartbeat"
    boost_home = os.environ.get("CLAUDEBOOST_HOME") or str(
        Path(__file__).resolve().parent.parent
    )
    return Path(boost_home) / "clean-rag" / "state" / ".heartbeat"


# Resolve once per process — env vars don't change between hook invocations.
_HEARTBEAT = _resolve_heartbeat_path()


def _rag_is_live() -> bool:
    """Return True only if the RAG server heartbeat is fresh and the model is loaded.

    Reads the JSON heartbeat written by the server every 30s.
    If stale (>90s), missing, or model_loaded=False: disengages the guard so reads
    aren't blocked while the embedding model is still warming up.
    """
    if not _HEARTBEAT.name or not _HEARTBEAT.exists():
        return False

    try:
        raw = _HEARTBEAT.read_text(encoding="utf-8").strip()
        try:
            data = json.loads(raw)
            ts = float(data.get("ts", 0))
            # Allow reads while the embedding model is still loading — searches fail
            # during this window anyway, so enforcing the guard is counterproductive.
            if not data.get("model_loaded", True):
                return False
        except (ValueError, KeyError):
            ts = float(raw)
        return time.time() - ts <= 90
    except Exception:
        return False


def main() -> int:
    raw = sys.stdin.read() if not sys.stdin.isatty() else ""
    try:
        payload = json.loads(raw) if raw else {}
    except Exception:
        payload = {}

    tool_input = payload.get("tool_input") or {}

    if is_exempted(tool_input):
        return 0

    # Read counter first (cheap disk read) before the heartbeat check.
    # Most calls are below threshold — skip the heartbeat read in those cases.
    home = Path(os.environ.get("CLAUDEBOOST_HOME") or Path(__file__).resolve().parent.parent)
    tracker_path = home / "state" / "behavior-tracker.json"
    try:
        behavior = json.loads(tracker_path.read_text(encoding="utf-8"))
    except Exception:
        behavior = {"reads_since_rag": 0}

    reads_since_rag = behavior.get("reads_since_rag", 0)

    # Allow the read when a crash left dirty counters from a prior session.
    # Only fires when the tracker has a previous session_id that differs from the current
    # one — absent session_id means session-clear-save.py already reset cleanly.
    # We don't write here: writing session_id would prevent context-nudge.py (PostToolUse)
    # from detecting the change and resetting reads_since_context_update and friends.
    session_id = payload.get("session_id", "")
    _prev = behavior.get("session_id")
    if session_id and _prev and _prev != session_id:
        return 0

    if reads_since_rag < RAG_THRESHOLD:
        return 0

    # Counter at threshold — now check heartbeat (second disk read, skipped above).
    if not _rag_is_live():
        return 0

    # Every part of this message used to name something that no longer exists:
    # port 8612, an `rag_search` MCP tool, and a `scope` parameter. Blocking a
    # read and then handing back an unusable alternative is worse than not
    # blocking at all.
    print(
        f"BLOCKED -- {reads_since_rag} file searches since last RAG call. "
        f"Search first: POST {rag_url('/search')} with "
        '{"query": "<what you are looking for>", '
        f'"sources": ["project:{os.getcwd()}"], "mode": "both"}}. '
        "RAG finds the relevant file, Grep and Read then open it, not the other "
        "way around. Run both modes: vector finds semantic matches, graph finds "
        "structural neighbours. Then read only what came back. "
        "Do NOT bypass this by reading files directly.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
