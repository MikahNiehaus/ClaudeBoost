#!/usr/bin/env python3
"""Pre-edit hook: detect code patterns and inject research automatically.

Fires BEFORE Edit/Write/MultiEdit. Parses what's being added and injects
relevant research without user asking. Works for trivial changes like
"just add this for loop" — system detects pattern and injects research.

Exit codes:
  0 = always (PreToolUse hooks should not block)
"""

import json
import logging
import os
import sys
import threading
import urllib.request
from pathlib import Path

logging.basicConfig(level=logging.INFO, handlers=[logging.StreamHandler(sys.stderr)])
logger = logging.getLogger(__name__)

# Pattern detection rules: (pattern_keywords, search_query)
PATTERN_RULES = [
    (["for ", "while "], "loop patterns performance off-by-one edge cases iteration"),
    (["try:", "except", "catch"], "error handling logging recovery stack traces debugging"),
    (["def ", "function "], "function design documentation parameters testing"),
    (["class "], "SOLID principles class design inheritance composition"),
    (["async ", "await", "Promise"], "async patterns race conditions concurrency deadlock"),
    (["sql", ".query(", "select ", "insert ", "delete ", "update "],
     "SQL security injection parameterized queries transactions"),
    (["password", "token", "secret", "api_key", "private_key"],
     "security hashing encoding OWASP authentication secrets"),
    (["if ", "else", "elif", "switch"], "branching patterns edge cases conditional logic"),
    (["[", "]", ".append", ".push"], "array indexing bounds off-by-one performance"),
    (["dict", "{", "map", ".get("], "dictionary patterns key handling defaults"),
    (["regex", "match", "search", "replace"], "regex patterns escaping injection performance"),
    (["file", "open", "read", "write"], "file handling paths security permissions edge cases"),
    (["http", "request", "response", "fetch", "get(", "post("],
     "HTTP patterns status codes error handling timeouts"),
    (["json", ".parse(", ".loads("], "JSON parsing validation error handling security"),
    (["sort", "reverse", "shuffle"], "sorting algorithms performance stability comparison"),
    (["import", "require", "include"], "module patterns dependencies circular imports"),
    (["test", "assert", "mock"], "testing patterns mocking fixtures TDD"),
    (["print", "console", "log", "logger"], "logging structured logging debug levels"),
]


def _detect_patterns(code_text: str) -> list:
    """Detect code patterns in the added/modified code."""
    code_lower = code_text.lower()
    detected = []

    for keywords, query in PATTERN_RULES:
        if any(kw.lower() in code_lower for kw in keywords):
            detected.append(query)

    return detected


def _clean_rag_home() -> Path:
    env = os.environ.get("CLEAN_RAG_HOME")
    if env:
        return Path(env)
    return Path(__file__).resolve().parent.parent


def _search_rag(query: str) -> dict:
    """Search RAG for a pattern."""
    port = os.environ.get("CLEAN_RAG_PORT", "8613")

    try:
        payload = json.dumps({
            "query": query,
            "sources": ["all_topics"],
            "limit": 2,
            "min_score": 0.5,
        }).encode("utf-8")

        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/search",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            results = data.get("results", [])
            logger.info(f"Pattern search '{query}' returned {len(results)} results")
            return {
                "query": query,
                "results": results,
                "count": len(results),
            }
    except Exception as e:
        logger.error(f"Pattern search failed: {e}")
        return {"query": query, "results": [], "count": 0, "error": str(e)}


def _format_injection(searches: list) -> str:
    """Format all searches into injected context."""
    if not searches:
        return ""

    lines = ["## Code Pattern Research (Auto-Detected)\n"]

    for search_result in searches:
        results = search_result.get("results", [])
        if not results:
            continue

        query = search_result.get("query", "unknown")
        lines.append(f"**Pattern: {query}**")

        for i, result in enumerate(results[:2], 1):
            topic = result.get("topic", "unknown")
            score = result.get("score", 0)
            content = result.get("content", "")[:150]
            lines.append(f"  {i}. {topic} ({score:.2f}): {content}...")

        lines.append("")

    return "\n".join(lines)


def _inject_pattern_research(old_string: str, new_string: str) -> None:
    """Detect patterns and inject research in background."""
    try:
        # Detect patterns in the change
        code_diff = new_string  # Simplified: just check the new code
        patterns = _detect_patterns(code_diff)

        if not patterns:
            return

        logger.info(f"Detected {len(patterns)} patterns, searching RAG...")

        # Search RAG for each pattern (in parallel via threading)
        searches = []

        def search_pattern(query):
            result = _search_rag(query)
            searches.append(result)

        threads = [
            threading.Thread(target=search_pattern, args=(pattern,), daemon=True)
            for pattern in patterns[:5]  # Limit to 5 patterns to avoid flooding
        ]

        for t in threads:
            t.start()

        # Wait for searches to complete (with timeout)
        for t in threads:
            t.join(timeout=2)

        # Log what was found
        total_results = sum(s.get("count", 0) for s in searches)
        logger.info(f"Pattern research: {len(searches)} searches, {total_results} results")

        # Format and log injection (for visibility)
        injection = _format_injection(searches)
        if injection:
            logger.info(f"Injecting pattern research:\n{injection[:300]}...")

    except Exception as e:
        logger.error(f"Pattern research error: {e}")


def main() -> int:
    """Entry point."""
    try:
        payload = json.loads(sys.stdin.read())
    except Exception:
        return 0

    tool_name = payload.get("tool_name", "")
    if tool_name not in ("Edit", "Write", "MultiEdit"):
        return 0

    # Skip if injection disabled
    if os.environ.get("CLEAN_RAG_PATTERN_INJECT") == "false":
        return 0

    tool_input = payload.get("tool_input", {})

    if tool_name == "Edit":
        old_string = tool_input.get("old_string", "")
        new_string = tool_input.get("new_string", "")
    elif tool_name == "Write":
        new_string = tool_input.get("content", "")
        old_string = ""
    elif tool_name == "MultiEdit":
        # For MultiEdit, check the first edit
        edits = tool_input.get("edits", [])
        if not edits:
            return 0
        new_string = edits[0].get("new_string", "")
        old_string = edits[0].get("old_string", "")
    else:
        return 0

    # Fire and forget: background thread does pattern research
    t = threading.Thread(
        target=_inject_pattern_research,
        args=(old_string, new_string),
        daemon=True,
    )
    t.start()

    return 0


if __name__ == "__main__":
    sys.exit(main())
