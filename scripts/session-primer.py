"""
ClaudeBoost session primer — UserPromptSubmit command hook.

Injects a compact, imperative behavior briefing into Claude's context
before every substantive user message. Acts as standing orders that
re-surface at the start of each turn before Claude decides anything.

Skips:
- Prompts shorter than 15 characters (single-word commands, greetings)

Behavior:
- Checks RAG sentinel file to detect offline/unverified RAG
- If RAG offline: injects a HARD STOP directive (no workflow may proceed)
- If RAG online: injects 6 non-negotiable standing orders
- Exits 0 always (nudge layer — PreToolUse rag-agent-guard handles hard blocks)

The 6 standing orders (RAG-online path):
1. RAG before file searching
2. Verify Gate (file:line for every finding)
3. Evaluator for all findings (never self-verify)
4. CONSULT before new endpoints/tables/dependencies
5. rag_context as first step in every agent spawn
6. If any RAG tool is unavailable or errors mid-task: STOP, report to user
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def rag_verified() -> bool:
    temp = os.environ.get("TEMP") or os.environ.get("TMPDIR") or "/tmp"
    return (Path(temp) / "claudeboost_rag_ok").exists()


def main() -> int:
    raw = sys.stdin.read() if not sys.stdin.isatty() else ""
    try:
        data = json.loads(raw) if raw else {}
    except Exception:
        data = {}

    prompt = data.get("prompt", "").strip()

    # Skip very short prompts (single-word commands, greetings)
    if len(prompt) < 15:
        return 0

    if not rag_verified():
        # RAG not verified — inject hard-stop directive for ALL prompts including slash commands
        print(json.dumps({
            "additionalContext": (
                "CRITICAL — RAG NOT VERIFIED: "
                "The RAG server has not been verified this session. "
                "You MUST NOT spawn agents, call rag_context/rag_search, "
                "or proceed with any multi-step workflow. "
                "Before doing ANYTHING else, stop and tell the user exactly: "
                "'RAG is not connected. Run /boost to verify RAG before I can continue.' "
                "Do not attempt to self-recover by reading files or grepping. Just stop."
            )
        }))
        return 0

    # RAG verified — inject normal standing orders (applies to slash commands too)
    print(json.dumps({
        "additionalContext": (
            "STANDING ORDERS (non-negotiable): "
            "Search RAG before reading files. "
            "Cite file:line for every finding. "
            "Spawn evaluator-agent — never self-verify. "
            "CONSULT before new endpoints/tables/dependencies. "
            "rag_context first in every agent spawn prompt. "
            "If any RAG MCP tool is unavailable or errors mid-task: STOP immediately, "
            "do NOT self-recover by searching files, tell the user RAG is offline."
        )
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
