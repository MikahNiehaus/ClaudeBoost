"""
ClaudeBoost RAG error guard — PostToolUse hook on mcp__rag-server__rag_search
and mcp__rag-server__rag_context.

When a RAG query tool returns a genuine server error (not just 0 results),
hard-blocks Claude with exit 2 so it cannot silently fall back to direct file
searching. Claude must surface the error to the user instead.

Zero-result responses (valid, just no matches) are not blocked.

Exit codes:
  0 = no error detected (pass through)
  2 = RAG server error detected — hard block, stderr message shown to Claude
"""
from __future__ import annotations

import json
import sys

# Phrases that indicate a genuine server/connection error vs. empty results
ERROR_SIGNALS = (
    "error",
    "exception",
    "traceback",
    "failed",
    "connection",
    "unavailable",
    "timeout",
    "internal server",
    "mcp error",
    "tool execution failed",
)

# If the response contains any of these, it's a successful (possibly empty) result
SUCCESS_SIGNALS = (
    '"results"',
    '"total_found"',
    '"tiers"',
    '"context"',
    '"chunks"',
)


def extract_text(payload: dict) -> str:
    raw = payload.get("tool_response") or payload.get("output") or payload.get("result")
    if isinstance(raw, list):
        for block in raw:
            if isinstance(block, dict) and block.get("type") == "text":
                return block.get("text", "")
    elif isinstance(raw, str):
        return raw
    elif isinstance(raw, dict):
        return json.dumps(raw)
    return ""


def main() -> int:
    raw = sys.stdin.read() if not sys.stdin.isatty() else ""
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except Exception:
        payload = {}

    text = extract_text(payload).lower()

    if not text:
        # No output to parse — let it through
        return 0

    # If any success signal is present, RAG responded normally (even if 0 results)
    for sig in SUCCESS_SIGNALS:
        if sig in text:
            return 0

    # No success signal — check for error signals
    for sig in ERROR_SIGNALS:
        if sig in text:
            print(
                "RAG server error detected. "
                "Do NOT fall back to file searching or grep. "
                "Stop and report this error to the user: "
                f'"{text[:200].strip()}"',
                file=sys.stderr,
            )
            return 2

    # Ambiguous — no success signals but no obvious error either. Let through.
    return 0


if __name__ == "__main__":
    sys.exit(main())
