"""
ClaudeBoost project-RAG flag — PostToolUse command hook on rag_index_project.

When rag_index_project completes successfully (files_indexed key present in
output), writes $TEMP/claudeboost_project_rag_ok so the status line can show
a "Project RAG" indicator independently from the "Boost RAG" indicator.

Clears the flag if the tool returned an error (no files_indexed key).

Exit codes:
  0 = pass (always — this hook never blocks)
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

FLAG_FILENAME = "claudeboost_project_rag_ok"


def main() -> int:
    flag_path = Path(tempfile.gettempdir()) / FLAG_FILENAME

    # Read hook output from stdin
    raw = sys.stdin.read() if not sys.stdin.isatty() else ""
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except Exception:
        payload = {}

    # PostToolUse stdin contains tool output under various keys depending on
    # Claude Code version. Try the most common wrappers first, then the raw payload.
    tool_output = (
        payload.get("tool_response")
        or payload.get("output")
        or payload.get("result")
        or payload
    )

    # Detect successful indexing: output must contain files_indexed
    if isinstance(tool_output, dict) and "files_indexed" in tool_output:
        try:
            flag_path.write_text("ok", encoding="utf-8")
        except Exception:
            pass
    elif isinstance(tool_output, str) and "files_indexed" in tool_output:
        try:
            flag_path.write_text("ok", encoding="utf-8")
        except Exception:
            pass
    else:
        # Tool errored or returned unexpected output — clear stale flag
        try:
            flag_path.unlink(missing_ok=True)
        except Exception:
            pass

    return 0


if __name__ == "__main__":
    sys.exit(main())
