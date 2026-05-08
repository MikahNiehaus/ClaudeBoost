"""
ClaudeBoost agent-spawn gate - command-type PreToolUse hook on Task.

Replaces the prompt-type "AGENT SPAWN QUALITY ROUTING" hook that was installed
by scripts/setup.ps1. Prompt-type hooks on Task tool calls were over-firing:

  1. They forced the judging LLM to "evaluate a condition" the prompt text
     asked about, but the LLM has no tool access in a hook context, so it
     couldn't actually verify prerequisites (rag_context was called, workspace
     exists, etc.). It defaulted to blocking.
  2. The hook text got re-encoded across setup.ps1 runs, producing mojibake
     that looked like garbled gibberish to the LLM judge. Multiple duplicate
     copies accumulated in settings.json because the sentinel didn't match the
     re-encoded text.
  3. It enumerated specialist agent names (ui-agent, architect-agent, etc.)
     that are ClaudeBoost knowledge-base prompts, not Claude Code subagent
     types. Spawns using "general-purpose" (the only writable subagent type
     available to the main agent) were flagged as "unrecognized."

This script reads the actual Task tool_input from stdin, checks whether the
spawn prompt instructs the agent to call `rag_context` as its first action,
and emits a non-blocking stderr nudge if it doesn't. Never blocks.

Behavior:
  - Prompt mentions `rag_context` -> exit 0 silently (pass)
  - Prompt missing `rag_context`  -> exit 0 + stderr reminder
  - architect-agent spawn without PROPOSAL_ONLY + 2 citations
                                  -> exit 0 + stderr reminder

It is a nudge, not a gate. Blocking hooks over-fire and grind the session.
A visible reminder is enough.
"""
from __future__ import annotations
import json
import re
import sys


def main() -> int:
    raw = sys.stdin.read() if not sys.stdin.isatty() else ""
    try:
        payload = json.loads(raw) if raw else {}
    except Exception:
        payload = {}

    tool_input = payload.get("tool_input", {}) or {}
    prompt = str(tool_input.get("prompt", "") or "")
    subagent_type = str(tool_input.get("subagent_type", "") or "")
    description = str(tool_input.get("description", "") or "")

    # Normalize for case-insensitive substring checks
    prompt_lower = prompt.lower()

    nudges: list[str] = []

    # Primary check: does the spawn prompt instruct the agent to call
    # rag_context? We accept any of: rag_context, mcp__rag-server__rag_context,
    # or the phrase "RAG context" as evidence.
    has_rag = (
        "rag_context" in prompt_lower
        or "mcp__rag-server__rag_context" in prompt_lower
        or "rag context" in prompt_lower
    )
    if not has_rag:
        nudges.append(
            "[agent-spawn nudge] Spawn prompt does not instruct the agent to call "
            "rag_context. For ClaudeBoost quality routing, include "
            "'mcp__rag-server__rag_context(agent=\"...\", task_description=\"...\", project_path=\"...\")' "
            "as the first action in the prompt."
        )
    elif "project_path" not in prompt_lower:
        nudges.append(
            "[agent-spawn nudge] rag_context call is missing project_path. "
            "Include project_path=\"<cwd>\" so the agent loads project-specific "
            "codebase context (Tier 4 RAG). Run `pwd` before spawning to get the path."
        )

    # Secondary check: architect-agent proposal contract.
    # Only fires if the prompt or description explicitly invokes architect-agent.
    is_architect = (
        "architect-agent" in prompt_lower
        or "architect-agent" in description.lower()
    )
    if is_architect:
        has_proposal_only = "PROPOSAL_ONLY" in prompt  # case-sensitive, as specified
        # Two file:line citations: rough regex, allow path/to/file.ext:123 or :123-456
        citation_re = re.compile(r"[\w./\\-]+\.[\w]+:\d+(?:-\d+)?")
        citations = citation_re.findall(prompt)
        if not has_proposal_only or len(citations) < 2:
            nudges.append(
                "[architect-agent nudge] Spawning architect-agent without the "
                "PROPOSAL_ONLY contract. Include the literal string PROPOSAL_ONLY "
                "and at least 2 file:line citations (format path/file.ext:line) so "
                "architect-agent can ground its proposal. Without them it will "
                "refuse and return BLOCKED."
            )

    # Emit nudges (never blocks)
    for n in nudges:
        print(n, file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
