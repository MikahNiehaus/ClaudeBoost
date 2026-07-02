#!/usr/bin/env python3
"""clean-rag RAG enforcement: UserPromptSubmit hook.

Fires on every user message. Injects a mandate to search RAG before
responding or editing. This is the strongest enforcement point for
ensuring all responses and decisions are research-grounded.

This hook cannot block responses (UserPromptSubmit has no exit-code gate),
but it injects instructions into every turn so Claude is reminded to
search RAG before doing anything.

Exit codes:
  0 = always (UserPromptSubmit hooks cannot block)
"""

import json
import os
import sys
from pathlib import Path


def _clean_rag_home() -> Path:
    """Resolve the clean-rag root directory."""
    env = os.environ.get("CLEAN_RAG_HOME")
    if env:
        return Path(env)
    return Path(__file__).resolve().parent.parent


def _read_mode() -> str:
    """Check if ClaudeBoost AUTO mode is active."""
    cb_home = os.environ.get("CLAUDEBOOST_HOME", "")
    if not cb_home:
        return "CONSULT"
    mode_file = Path(cb_home) / "state" / "claudeboost-mode.json"
    if mode_file.exists():
        try:
            data = json.loads(mode_file.read_text(encoding="utf-8"))
            return data.get("mode", "CONSULT")
        except Exception:
            pass
    return "CONSULT"


def _load_topic_tree() -> str:
    """Build a compact topic tree from topics.json for routing."""
    home = _clean_rag_home()
    registry_path = home / "state" / "topics.json"
    if not registry_path.exists():
        return "  (no topics indexed yet)"

    try:
        topics = json.loads(registry_path.read_text(encoding="utf-8"))
    except Exception:
        return "  (failed to read topic registry)"

    if not topics:
        return "  (no topics indexed yet)"

    # Group by category
    by_cat: dict[str, list[str]] = {}
    for name, info in topics.items():
        cat = info.get("category", "uncategorized")
        chunks = info.get("chunks", 0)
        by_cat.setdefault(cat, []).append(f"{name}({chunks})")

    lines = []
    for cat in sorted(by_cat):
        items = ", ".join(sorted(by_cat[cat]))
        lines.append(f"  {cat}/: {items}")

    return "\n".join(lines)


def main() -> int:
    port = os.environ.get("CLEAN_RAG_PORT", "8613")
    topic_tree = _load_topic_tree()

    # The mandate injected into every user message turn
    mandate = (
        "\n\n--- CLEAN-RAG: RESEARCH-FIRST MANDATE ---\n"
        "Before responding, editing, or making any decision:\n\n"
        "1. IDENTIFY which topic(s) your response touches.\n"
        "   Indexed topics by category:\n"
        f"{topic_tree}\n\n"
        "2. SEARCH for each topic before responding:\n"
        f"   POST http://127.0.0.1:{port}/search\n"
        '   {{"query": "<specific question>", "sources": ["topic:<name>", "all_topics"]}}\n\n'
        "3. If NO matching topic exists or results don't answer your question,\n"
        "   do BOTH of these (not one or the other, BOTH):\n"
        "   a. DIRECT RESEARCH NOW (Fast Path): Research the specific question\n"
        "      yourself (Grep codebase, read a doc, WebSearch). This unblocks you.\n"
        "   b. ALSO SPAWN PARALLEL AGENT (REQUIRED, not optional):\n"
        "      Spawn a background agent with this workflow:\n"
        f"      1) POST http://127.0.0.1:{port}/acquire-topic\n"
        '         {{"topic": "<slug>", "category": "<category>"}}\n'
        "      2) If files_acquired > 0: done. Report what was indexed.\n"
        "      3) If files_acquired == 0 or needs_websearch == true:\n"
        "         a) WebSearch for '<topic> official documentation'\n"
        "         b) Fetch top 3-5 results with WebFetch\n"
        "         c) Save content to clean-rag/knowledge/<category>/<topic>/\n"
        f"         d) POST http://127.0.0.1:{port}/index-topic\n"
        '            {{"topic": "<slug>", "category": "<category>"}}\n'
        "         e) Report files saved and chunks indexed\n"
        "      Categories: ai, api, cloud, databases, dotnet, frontend,\n"
        "      infrastructure, languages, node-frameworks, php-frameworks,\n"
        "      python-frameworks, ruby-frameworks, security, testing,\n"
        "      tools, ui. New category if none fit.\n"
        "      Do NOT wait for this agent. Do NOT spawn a second for same topic.\n"
        "      Skipping this step means the same gap next time.\n\n"
        "4. BASE your response on RAG results, not training data.\n"
        "   Cite which topic and score backed each claim.\n\n"
        "5. For EDITS: the proof-gate hook will mechanically block any edit\n"
        "   without a proof file. Search first, write proof, then edit.\n\n"
        "6. RESEARCH SUFFICIENCY: Before writing proof, search from at least\n"
        "   2 different angles (proof-gate rejects proofs with < 2 angles):\n"
        "   - technology : How does this tech work? Search the topic docs\n"
        "   - codebase   : What patterns exist in this project already?\n"
        "   - pitfalls   : What commonly goes wrong with this approach?\n"
        "   - security   : Any security implications? (when applicable)\n"
        "   - best_practices : What is the recommended pattern?\n"
        "   Include angles in proof: research_angles=[{angle, query, score}, ...]\n"
        "--- END CLEAN-RAG MANDATE ---\n"
    )

    # Output the mandate so it gets injected into the conversation
    print(mandate)
    return 0


if __name__ == "__main__":
    sys.exit(main())
