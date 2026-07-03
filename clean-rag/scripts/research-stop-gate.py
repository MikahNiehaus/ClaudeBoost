#!/usr/bin/env python3
"""research-stop-gate.py: Stop hook that blocks unresearched responses.

Citation: C:/prj/ClaudeBoost/docs/CLAUDEBOOST-REFERENCE.md lines 349-362
Stop hooks must be Type: Command hook to block with exit code 2.

This hook reads the response text and checks for research citations.

Exit codes:
  0 = allow (response is researched or passes exemption)
  2 = block (response makes unsourced technical claims)
"""

import json
import sys
import re

RESEARCH_PASS_PATTERNS = [
    r"file:line",
    r"file:\d+",
    r"\(score\s+[\d.]+\)",
    r"topic:\w+",
    r"Grep",
    r"WebSearch",
    r"C:/prj/",
    r"Read:",
    r"CLAUDEBOOST-REFERENCE.md",
]

UNSOURCED_CLAIM_PATTERNS = [
    r"best practice",
    r"you should",
    r"typically",
    r"generally",
    r"usually",
    r"React patterns",
    r"game development practices",
]


def has_research_citations(text):
    """Check if response contains research citations."""
    for pattern in RESEARCH_PASS_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return True
    return False


def has_unsourced_claims(text):
    """Check if response makes unsourced technical claims."""
    for pattern in UNSOURCED_CLAIM_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return True
    return False


def main() -> int:
    raw = sys.stdin.read() if not sys.stdin.isatty() else ""

    # Parse hook input: {"response_text": "..."}
    try:
        hook_input = json.loads(raw) if raw else {}
    except Exception:
        hook_input = {}

    response_text = hook_input.get("response_text", "") or ""

    # Check for research citations
    has_citations = has_research_citations(response_text)
    has_claims = has_unsourced_claims(response_text)

    # PASS if: has citations OR no unsourced claims
    if has_citations or not has_claims:
        return 0

    # FAIL if: unsourced claims detected
    reason = (
        "You made technical claims without citing a source. "
        "Search first: POST http://127.0.0.1:8613/search "
        "then cite topic:score before responding."
    )

    block_msg = {"decision": "block", "reason": reason}
    print(json.dumps(block_msg))
    return 2


if __name__ == "__main__":
    sys.exit(main())
