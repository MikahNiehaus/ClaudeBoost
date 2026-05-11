"""
ClaudeBoost session primer — UserPromptSubmit command hook.

Injects a compact, imperative behavior briefing into Claude's context
before every substantive user message. Acts as standing orders that
re-surface at the start of each turn before Claude decides anything.

Skips:
- Prompts shorter than 15 characters (single-word commands, greetings)
- Slash commands (start with /)

Behavior:
- Injects additionalContext JSON with 5 non-negotiable rules
- Exits 0 always (nudge, never blocks)

These rules are the five behaviors Claude most commonly forgets mid-task:
1. RAG before file searching
2. Verify Gate (file:line for every finding)
3. Evaluator for all findings (never self-verify)
4. CONSULT before new endpoints/tables/dependencies
5. rag_context as first step in every agent spawn
"""
from __future__ import annotations

import json
import sys


def main() -> int:
    raw = sys.stdin.read() if not sys.stdin.isatty() else ""
    try:
        data = json.loads(raw) if raw else {}
    except Exception:
        data = {}

    prompt = data.get("prompt", "").strip()

    # Skip slash commands and very short prompts (commands, greetings, single words)
    if len(prompt) < 15 or prompt.startswith("/"):
        return 0

    print(json.dumps({
        "additionalContext": (
            "STANDING ORDERS (non-negotiable): "
            "Search RAG before reading files. "
            "Cite file:line for every finding. "
            "Spawn evaluator-agent — never self-verify. "
            "CONSULT before new endpoints/tables/dependencies. "
            "rag_context first in every agent spawn prompt."
        )
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
