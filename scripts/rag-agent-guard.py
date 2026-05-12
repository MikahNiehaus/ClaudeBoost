"""
ClaudeBoost RAG agent guard — PreToolUse hook on Agent.

Hard-blocks agent spawning when RAG has not been verified this session.
The sentinel file ($TEMP/claudeboost_rag_ok) is created by /boost only after
RAG health checks pass, and removed at the start of each /boost run.

If the sentinel is absent, no agent may be spawned — the user must run /boost
to verify RAG before multi-agent workflows proceed.

Also checks that the ChromaDB index directory exists as a secondary signal
that the index was actually built.

Exit codes:
  0 = RAG verified — allow agent spawn
  2 = RAG not verified — hard block, stderr message shown to Claude
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def main() -> int:
    temp = os.environ.get("TEMP") or os.environ.get("TMPDIR") or "/tmp"
    sentinel = Path(temp) / "claudeboost_rag_ok"

    claudeboost_home = os.environ.get("CLAUDEBOOST_HOME", "")
    chroma_dir = Path(claudeboost_home) / "mcp-rag-server" / ".rag-index" / "chroma" if claudeboost_home else None

    sentinel_ok = sentinel.exists()
    index_ok = chroma_dir.exists() if chroma_dir else True  # if path unknown, don't block on it

    if sentinel_ok and index_ok:
        return 0

    reasons = []
    if not sentinel_ok:
        reasons.append("RAG not verified this session (sentinel missing)")
    if not index_ok:
        reasons.append("ChromaDB index not found at mcp-rag-server/.rag-index/chroma")

    print(
        "BLOCKED — cannot spawn agent: "
        + "; ".join(reasons)
        + ". "
        "Run /boost to verify RAG before spawning agents. "
        "Do NOT proceed with the current workflow. "
        "Tell the user: 'RAG is not connected — run /boost first.'",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
