"""
ClaudeBoost RAG error guard — PostToolUse hook on all mcp__rag-server__* tools.

When any RAG tool returns a genuine server error, hard-blocks Claude with exit 2
so it cannot silently fall back to direct file searching. Claude must surface the
error to the user instead.

Special cases:
  - rag_index_research: blocks if ALL sources failed (sources_indexed == 0 and
    sources_failed > 0). Partial failures (some succeeded) are a warn-only signal
    already visible in the response — Claude must still report them but can continue.
  - rag_search scope=research: blocks if the error indicates the research index
    doesn't exist (can't search what was never indexed — must ask user).

Zero-result search responses (valid, just no matches) are NOT blocked.

Exit codes:
  0 = no error detected (pass through)
  2 = RAG server error detected — hard block, stderr message shown to Claude
"""
from __future__ import annotations

import json
import sys

# Phrases that indicate a genuine server/connection error vs. empty results
ERROR_SIGNALS = (
    "exception",
    "traceback",
    "connection",
    "unavailable",
    "timeout",
    "internal server",
    "mcp error",
    "tool execution failed",
)

# If the response contains any of these, it's a successful (possibly empty) result.
# Checked BEFORE error signals — a successful response with an embedded warning
# passes through so Claude can read the warning itself.
SUCCESS_SIGNALS = (
    # rag_search / rag_context
    '"results"',
    '"total_found"',
    '"context"',
    '"agent_definition"',
    '"tier_summary"',
    '"relevant_knowledge"',
    '"sources_used"',
    # rag_index / rag_index_project
    '"files_indexed"',
    '"chunks_created"',
    # rag_index_research
    '"indexed_count"',
    '"sources_indexed"',
    '"collection_path"',
    # rag_status
    '"collections"',
    # rag_scan
    '"files_to_index"',
    '"files_by_language"',
)

# Errors that appear INSIDE an otherwise-valid response structure.
# These slip past the success-signal check and must be caught explicitly.
EMBEDDED_ERRORS = (
    "research index not found",
    "run rag_index_research first",
    "project not indexed",
    "call rag_index_project first",
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


def check_total_index_failure(text_lower: str) -> str | None:
    """Return a block message if rag_index_research indexed 0 sources but had failures."""
    # Detect: "sources_indexed": 0  AND  "sources_failed": <non-zero>
    # Handle both compact JSON (no spaces) and pretty-printed (spaces after colon).
    indexed_zero = (
        '"sources_indexed": 0' in text_lower
        or '"sources_indexed":0' in text_lower
    )
    if not indexed_zero:
        return None

    failed_present = '"sources_failed"' in text_lower
    failed_zero = (
        '"sources_failed": 0' in text_lower
        or '"sources_failed":0' in text_lower
    )
    has_failures = failed_present and not failed_zero

    if has_failures:
        return (
            "rag_index_research failed: 0 sources were indexed and at least one source "
            "reported an error. Do NOT continue. Stop and report this failure to the user "
            "and ask how to proceed (different URLs, local PDF, or skip research indexing)."
        )
    return None


def main() -> int:
    raw = sys.stdin.read() if not sys.stdin.isatty() else ""
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except Exception:
        payload = {}

    text = extract_text(payload)
    text_lower = text.lower()

    if not text_lower:
        return 0

    # --- Check for total rag_index_research failure (0 indexed, N failed) ---
    block_msg = check_total_index_failure(text_lower)
    if block_msg:
        print(block_msg, file=sys.stderr)
        return 2

    # --- If any success signal is present, check for embedded errors before passing ---
    has_success = any(sig in text for sig in SUCCESS_SIGNALS)

    if has_success:
        # Check only the structured JSON "error" field — not the full response body.
        # Raw body scan caused false positives when codebase search returned source
        # code content containing these strings as Python string literals.
        try:
            parsed = json.loads(text)
        except Exception:
            parsed = {}
        top_error = (parsed.get("error") or "").lower()
        for err in EMBEDDED_ERRORS:
            if err in top_error:
                print(
                    f"RAG returned an error embedded in a valid response: \"{err}\". "
                    "Do NOT silently continue. Stop and report this to the user. "
                    "Ask whether to run the required indexing step first.",
                    file=sys.stderr,
                )
                return 2
        # Genuine success (possibly 0 results or partial warnings — Claude handles those)
        return 0

    # --- No success signal — check for bare error signals ---
    for sig in ERROR_SIGNALS:
        if sig in text_lower:
            print(
                "RAG server error detected. "
                "Do NOT fall back to file searching, grep, or proceeding without RAG context. "
                "Stop and report this error to the user: "
                f'"{text[:300].strip()}"',
                file=sys.stderr,
            )
            return 2

    # Ambiguous — no success or error signals. Let through.
    return 0


if __name__ == "__main__":
    sys.exit(main())
