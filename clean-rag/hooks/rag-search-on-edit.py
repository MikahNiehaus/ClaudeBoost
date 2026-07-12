#!/usr/bin/env python3
"""RAG search on Edit: PreToolUse hook.

Triggers RAG search when user starts editing a file.
Injects search results into edit context.

Exit codes:
  0 = always (PreToolUse can suggest but not block)
"""

import json
import os
import sys
import urllib.request
from pathlib import Path

def _clean_rag_home() -> Path:
    """Resolve clean-rag root."""
    env = os.environ.get("CLEAN_RAG_HOME")
    return Path(env) if env else Path(__file__).resolve().parent.parent


def _extract_context_from_edit() -> str:
    """Extract file context from edit operation (if available)."""
    # Try to get filename from environment or context
    # This is best-effort — PreToolUse hooks have limited context
    return "code context editing patterns"


def _search_rag(query: str, port: str) -> list[dict]:
    """Search RAG for edit context."""
    try:
        req_data = json.dumps({
            "query": query,
            "sources": ["all_topics"],
            "limit": 5,
            "min_score": 0.5
        }).encode("utf-8")

        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/search",
            data=req_data,
            headers={"Content-Type": "application/json"},
            method="POST"
        )

        with urllib.request.urlopen(req, timeout=2) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("results", [])
    except Exception:
        return []


def _format_results(results: list[dict]) -> str:
    """Format search results for edit context."""
    if not results:
        return ""

    lines = ["## Edit Context (Related Research)\n"]
    for i, result in enumerate(results[:2], 1):
        topic = result.get("topic", "unknown")
        content = result.get("content", "")[:200]
        lines.append(f"**{i}. {topic}**")
        lines.append(f"{content}...\n")

    return "\n".join(lines)


def main() -> int:
    port = os.environ.get("CLEAN_RAG_PORT", "8613")

    # Search for edit-related patterns
    search_query = "code editing patterns refactoring maintainability clarity"
    results = _search_rag(search_query, port)
    context = _format_results(results)

    if context:
        print(context)

    return 0


if __name__ == "__main__":
    sys.exit(main())
