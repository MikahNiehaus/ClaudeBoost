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
and exits 2 (blocking) if it doesn't.

Behavior:
  - Prompt mentions `rag_context` -> exit 0 silently (pass)
  - Prompt missing `rag_context`  -> exit 2 + stderr error (blocked)
  - architect-agent spawn without PROPOSAL_ONLY + 2 citations
                                  -> exit 2 + stderr error (blocked)

Exits 2 (blocking) when the spawn prompt does not include a rag_context call.
Exits 0 (pass) when rag_context is present or when checking architect-agent contract only.
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
    description = str(tool_input.get("description", "") or "")

    # Normalize for case-insensitive substring checks
    prompt_lower = prompt.lower()

    nudges: list[str] = []

    # Primary check: does the spawn prompt instruct the agent to call
    # rag_context? We accept: rag_context (the function name) or
    # mcp__rag-server__rag_context (the fully-qualified MCP tool name).
    # "RAG context" (two words) was previously accepted but is too ambiguous —
    # it matches plain-English phrases like "ensure RAG context is available"
    # without the prompt actually instructing a rag_context() tool call.
    # Accept MCP rag_context call OR HTTP REST call to the context endpoint
    has_rag = (
        "rag_context" in prompt_lower
        or "mcp__rag-server__rag_context" in prompt_lower
        or "127.0.0.1:8612/context" in prompt_lower
        or "localhost:8612/context" in prompt_lower
    )
    if not has_rag:
        nudges.append(
            "[agent-spawn nudge] Spawn prompt does not instruct the agent to load RAG context. "
            "Include a call to POST http://127.0.0.1:8612/context "
            "(e.g. via curl or python urllib) as the first action in the prompt."
        )
    elif "project_path" not in prompt_lower and "127.0.0.1:8612" not in prompt_lower:
        nudges.append(
            "[agent-spawn nudge] rag_context call is missing project_path. "
            "Include project_path=\"<cwd>\" so the agent loads project-specific "
            "codebase context (Tier 4 RAG). Run `pwd` before spawning to get the path."
        )

    # Secondary check: architect-agent proposal contract.
    # Only fires when the spawn IS an architect-agent, not when the prompt merely
    # references it (e.g. as a rag_context agent= parameter or in a description).
    # The description field is the reliable signal — the orchestrator sets it
    # explicitly when spawning architect-agent. Prompt body checks use identity
    # phrases only to avoid false positives from rag_context parameter values.
    is_architect = (
        "architect-agent" in description.lower()
        or "you are architect-agent" in prompt_lower
        or "acting as architect-agent" in prompt_lower
        or "i am architect-agent" in prompt_lower
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

    if nudges:
        for n in nudges:
            print(n, file=sys.stderr)
        # Block when RAG context call is absent from spawn prompt — hard requirement
        return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
