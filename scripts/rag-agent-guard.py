"""
ClaudeBoost RAG agent guard — PreToolUse hook on Agent.

Checks that the RAG server heartbeat is fresh before allowing agent spawns.
With HTTP transport, Claude Code auto-reconnects — no session sentinel needed.

Exit codes:
  0 = RAG server is live — allow agent spawn
  0 = RAG server not detected — allow anyway (fail-open so debugging works)
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path


def _heartbeat_age() -> float | None:
    """Return heartbeat age in seconds, or None if missing/unreadable."""
    rag_index_dir = os.environ.get("RAG_INDEX_DIR", "")
    if not rag_index_dir:
        local_appdata = os.environ.get("LOCALAPPDATA", "")
        if local_appdata:
            rag_index_dir = str(Path(local_appdata) / "rag-server-index")
        else:
            # macOS / Linux: server writes to BOOST_HOME/mcp-rag-server/.rag-index
            rag_index_dir = str(Path(__file__).resolve().parent.parent / "mcp-rag-server" / ".rag-index")
    if not rag_index_dir:
        return None
    hb = Path(rag_index_dir) / ".heartbeat"
    if not hb.exists():
        return None
    try:
        raw = hb.read_text(encoding="utf-8").strip()
        try:
            data = json.loads(raw)
            ts = float(data.get("ts", 0))
        except (ValueError, KeyError):
            ts = float(raw)
        return time.time() - ts
    except Exception:
        return None


def main() -> int:
    age = _heartbeat_age()

    if age is None:
        # Can't detect server state — allow spawn (fail-open)
        return 0

    if age <= 90:
        # Server is alive and ticking
        return 0

    # Heartbeat stale — server may be down, but we still allow spawn.
    # The agent will get a clear MCP error if RAG is actually unavailable.
    # We warn but don't block — blocking creates a circular dependency where
    # you can't spawn a debug agent to investigate a dead RAG server.
    print(
        f"WARNING: RAG server heartbeat is {age:.0f}s old — server may be down. "
        "If RAG tools fail inside the agent, run: python \"$CLAUDEBOOST_HOME/scripts/rag-server-start.py\"",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
