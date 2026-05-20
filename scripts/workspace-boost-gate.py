"""
ClaudeBoost workspace-boost gate — PreToolUse hook on Bash(mkdir*workspace*).

Hard-blocks workspace creation when /boost has not been run this session.
The sentinel file ($TEMP/claudeboost_rag_ok) is created by /boost only after
RAG health checks pass.

Without /boost, the RAG index is unverified and rag_context won't load
correctly into the workspace — so blocking here is the right call rather
than letting the workspace get created with a broken RAG underneath it.

Exit codes:
  0 = /boost verified — allow workspace creation
  2 = /boost not run — hard block, message shown to Claude
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def main() -> int:
    temp = os.environ.get("TEMP") or os.environ.get("TMPDIR") or "/tmp"
    sentinel = Path(temp) / "claudeboost_rag_ok"

    if sentinel.exists():
        return 0

    print(
        "BLOCKED — cannot create workspace: /boost has not been run this session. "
        "RAG is unverified. Run /boost first to verify RAG, then retry workspace creation. "
        "Do NOT proceed with mkdir or workspace setup until /boost confirms RAG is healthy.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
