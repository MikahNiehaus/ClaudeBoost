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
spawn prompt instructs the agent to call POST http://127.0.0.1:8612/context as its first action,
and exits 2 (blocking) if it doesn't.

Behavior:
  - Prompt mentions RAG context call (rag_context or 8612/context) -> exit 0 silently (pass)
  - Prompt missing RAG context call  -> exit 2 + stderr error (blocked)
  - architect-agent spawn without PROPOSAL_ONLY + 2 citations
                                  -> exit 2 + stderr error (blocked)

Exits 2 (blocking) when the spawn prompt does not include a RAG context call (rag_context or POST http://127.0.0.1:8612/context).
Exits 0 (pass) when a RAG context call is present or when checking architect-agent contract only.
"""
from __future__ import annotations
import json
import os
import re
import sys
from pathlib import Path


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
    # Accept: rag_context (legacy), mcp__rag-server__rag_context (legacy MCP name),
    # or HTTP REST call to the context endpoint (127.0.0.1:8612/context).
    # "RAG context" (two words) is too ambiguous — matches plain-English phrases
    # without actually instructing a context call.
    has_rag = (
        "8612/context" in prompt_lower
        or "rag_context" in prompt_lower  # legacy — kept for backward compat
    )
    if not has_rag:
        nudges.append(
            "[agent-spawn nudge] Spawn prompt does not instruct the agent to load RAG context. "
            "Include a call to POST http://127.0.0.1:8612/context "
            "(e.g. via curl or python urllib) as the first action in the prompt."
        )
    elif "project_path" not in prompt_lower:
        nudges.append(
            "[agent-spawn nudge] Context call (POST http://127.0.0.1:8612/context) is missing project_path. "
            "Include project_path=\"<cwd>\" so the agent loads project-specific "
            "codebase context (Tier 4 RAG). Run `pwd` before spawning to get the path."
        )
    if "workspace_path" not in prompt_lower:
        # Check if there is an active workspace — only nudge when one exists.
        import os
        boost_home = os.environ.get("CLAUDEBOOST_HOME", "")
        active_ws_file = os.path.join(boost_home, "state", "active-workspace.json") if boost_home else ""
        if active_ws_file and os.path.exists(active_ws_file):
            try:
                import json as _json
                from pathlib import Path as _Path
                ws_data = _json.loads(open(active_ws_file).read())
                # New schema has workspace_path directly; old schema has only workspace (ID)
                ws_path = ws_data.get("workspace_path") or ws_data.get("path") or ""
                if not ws_path:
                    # Fall back: look up workspace_path in the registry by workspace ID
                    ws_id = ws_data.get("workspace", "")
                    if ws_id and boost_home:
                        reg_file = os.path.join(boost_home, "state", "workspaces.json")
                        if os.path.exists(reg_file):
                            reg = _json.loads(open(reg_file).read())
                            ws_path = (reg.get(ws_id) or {}).get("workspace_path", "")
                if ws_path:
                    nudges.append(
                        "[agent-spawn nudge] Active workspace detected but workspace_path is not in the spawn prompt. "
                        f"Include workspace_path=\"{ws_path}\" in the context call so the agent "
                        "receives Tier 3c workspace research (task-specific docs indexed by /research-rag)."
                    )
            except Exception:
                pass

    # Secondary check: architect-agent proposal contract.
    # Only fires when the spawn IS an architect-agent, not when the prompt merely
    # references it (e.g. as a context call agent= parameter or in a description).
    # The description field is the reliable signal — the orchestrator sets it
    # explicitly when spawning architect-agent. Prompt body checks use identity
    # phrases only to avoid false positives from context call parameter values.
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

    # Evaluator routing check: if a NEEDS_VERIFICATION flag is pending,
    # block any spawn that isn't an evaluator-agent. Clear the flag on
    # evaluator spawn so normal work can resume immediately after.
    # Exception: bypass during active parallel batch runs (audit-in-progress.json).
    boost_home = Path(os.environ.get("CLAUDEBOOST_HOME") or Path(__file__).resolve().parent.parent)
    flag = boost_home / "state" / "needs-verification.json"
    audit_active = (boost_home / "state" / "audit-in-progress.json").exists()
    if flag.exists() and not audit_active:
        is_evaluator = "evaluator-agent" in prompt_lower or "evaluator_agent" in prompt_lower
        if is_evaluator:
            try:
                flag.unlink(missing_ok=True)
            except Exception:
                pass
        else:
            nudges.append(
                "[verify gate] NEEDS_VERIFICATION pending — a prior agent flagged findings "
                "that require verification. Spawn evaluator-agent before proceeding with "
                "other work. This gate clears automatically when evaluator-agent runs."
            )

    if nudges:
        for n in nudges:
            print(n, file=sys.stderr)
        # Block when RAG context call is absent from spawn prompt — hard requirement
        return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
