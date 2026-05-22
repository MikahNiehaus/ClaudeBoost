"""
rag-session-reset.py — SessionStart command hook.

Clears the $TEMP/claudeboost_rag_ok sentinel at the start of every new
session so RAG must be re-verified before agents or investigation tasks
can proceed. Without this, a stale sentinel from a previous session lets
Claude believe RAG is connected even when the MCP server is offline.

The sentinel is written by /boost after a successful rag_context call.
Clearing it here means every session starts unverified, and session-primer.py
(UserPromptSubmit) will inject the HARD STOP directive until /boost confirms
RAG is up again.

Behavior:
  - Deletes $TEMP/claudeboost_rag_ok (missing = no-op, not an error)
  - Outputs additionalContext nudge to remind user to run /boost
  - Always exits 0 (SessionStart hooks cannot block startup)
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def main() -> int:
    temp = os.environ.get("TEMP") or os.environ.get("TMPDIR") or "/tmp"
    sentinel = Path(temp) / "claudeboost_rag_ok"

    was_set = sentinel.exists()
    try:
        sentinel.unlink(missing_ok=True)
    except Exception:
        pass  # best-effort clear

    if was_set:
        # It existed from a prior session — make it clear it was cleared
        print(json.dumps({
            "additionalContext": (
                "RAG SENTINEL CLEARED: The previous session's RAG verification has expired. "
                "RAG must be re-verified before agents or investigation tasks can proceed. "
                "Run /boost to reconnect and verify RAG, then continue your work. "
                "Do NOT proceed with any codebase task until /boost confirms RAG is online."
            )
        }))

    return 0


if __name__ == "__main__":
    sys.exit(main())
