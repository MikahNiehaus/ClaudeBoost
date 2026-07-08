"""
ClaudeBoost agent-spawn gate - command-type PreToolUse hook on Task.

Lives under clean-rag/hooks/ alongside proof-gate.py, rag-enforce.py, and
reindex-after-edit.py, but enforces core ClaudeBoost RAG (POST
http://127.0.0.1:8612/context — the mcp-rag-server), not clean-rag's own
research gate (port 8613). Installed unconditionally by setup.py regardless
of whether clean-rag is bundled.

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
  - Prompt missing RAG context call (8612/context) -> exit 2 + stderr error (blocked)
  - research-agent spawn without depth research citations -> exit 2 + stderr error (blocked)
  - research-agent spawn without bulk acquire-topic system -> exit 2 + stderr error (blocked)
  - architect-agent spawn without PROPOSAL_ONLY + 2 citations -> exit 2 + stderr error (blocked)
  - All checks pass -> exit 0 silently (pass)

Enforces DEPTH + BREADTH research pattern:
  1. All spawns: RAG context call (rag_context or POST http://127.0.0.1:8612/context)
  2. Research spawns: DEPTH check — Claude must cite direct research (file:line, grep, websearch)
  3. Research spawns: BREADTH check — Agent must use POST /acquire-topic (4-layer waterfall)
  4. Architect spawns: PROPOSAL_ONLY contract + 2 file:line citations

Exits 2 (blocking) when any requirement is missing.
Exits 0 (pass) when all applicable checks pass.
"""
from __future__ import annotations
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path


def _log_usage(boost_home: Path, description: str, prompt: str, blocked: bool) -> None:
    try:
        agent = description.strip() or "unknown"
        record = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "agent": agent,
            "blocked": blocked,
        }
        log_path = boost_home / "state" / "agent-usage.jsonl"
        with log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
    except Exception:
        pass


def _write_block_telemetry(boost_home: Path, tool: str, summary: str, reason: str) -> None:
    """Write a PreToolUse block event to claude-actions.jsonl.

    PostToolUse never fires when a PreToolUse hook exits 2, so we write
    the telemetry record here before returning. Uses the same output file
    as telemetry-hook.py so block events appear inline in the action log.
    """
    try:
        sys.path.insert(0, str(boost_home / "scripts"))
        from telemetry_writer import now_iso, session_id, write_telemetry
        record = {
            "ts": now_iso(),
            "session_id": session_id(),
            "tool": tool,
            "summary": f"{tool} {summary[:200]}",
            "result": "blocked",
            "hook_event": "PreToolUse",
            "block_reason": reason[:300],
        }
        write_telemetry(record, "claude-actions.jsonl")
    except Exception:
        pass


def main() -> int:
    raw = sys.stdin.read() if not sys.stdin.isatty() else ""
    try:
        payload = json.loads(raw) if raw else {}
    except Exception:
        payload = {}

    tool_input = payload.get("tool_input", {}) or {}
    prompt = str(tool_input.get("prompt", "") or "")
    description = str(tool_input.get("description", "") or "")
    # Normalize for case-insensitive substring checks. Must happen before the
    # research-spawn checks below, which read prompt_lower.
    prompt_lower = prompt.lower()

    # This file lives at clean-rag/hooks/agent-spawn-gate.py — three levels
    # below the ClaudeBoost root (hooks -> clean-rag -> ClaudeBoost). The env
    # var is always set in practice (settings.json's env block); this is only
    # a fallback for direct/manual invocation.
    boost_home = Path(os.environ.get("CLAUDEBOOST_HOME") or Path(__file__).resolve().parent.parent.parent)
    nudges: list[str] = []

    # ENFORCEMENT: research-agent spawns follow DEPTH + BREADTH pattern
    # DEPTH: Claude does direct research first to answer specific question
    # BREADTH: Agent acquires and indexes comprehensive coverage (doesn't read/answer)
    is_research_spawn = "research-agent" in description.lower() or "research" in description.lower()
    if is_research_spawn:
        # Check 1: Has Claude done depth research? (file:line, Grep, WebSearch citations)
        has_depth_research = (
            "file:" in prompt or "grep" in prompt_lower or "websearch" in prompt_lower
            or "found in" in prompt_lower or "direct research" in prompt_lower
        )
        if not has_depth_research:
            nudges.append(
                "[research-agent depth check] You must do direct research FIRST (depth) "
                "before spawning a research agent for breadth. Search RAG or read files "
                "to answer your specific question with citations (file:line or grep results). "
                "Then spawn research-agent only for comprehensive acquisition and indexing, "
                "not to answer your original question."
            )

        # Check 2: Is agent using the bulk acquisition system (acquire-topic 4-layer waterfall)?
        # acquire-topic automatically: (1) GitHub sparse checkout, (2) llms.txt scraping,
        # (3) BFS doc crawl, (4) WebSearch fallback. This is how we scale knowledge breadth.
        uses_acquire_topic = "acquire-topic" in prompt or "8613/acquire-topic" in prompt

        if not uses_acquire_topic:
            nudges.append(
                "[research-agent breadth check] Research-agent MUST use the bulk acquisition system. "
                "Instead of manual research, spawn with: POST http://127.0.0.1:8613/acquire-topic "
                "{\"topic\": \"<slug>\"} in the agent prompt. This runs the 4-layer waterfall: "
                "(1) GitHub sparse checkout, (2) llms.txt scraping, (3) BFS doc crawl, (4) WebSearch. "
                "Agent does NOT read/analyze — just calls acquire-topic and reports chunks indexed. "
                "See clean-rag/CLAUDE.md lines 48-153 for the system design."
            )

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
        # Use get-active-workspace.py resolve() for per-instance detection.
        # This matches the blue "WS XXXX" status bar — reads per-instance CWD-keyed
        # state, not the stale shared active-workspace.json which reflects the last
        # window to write it rather than the current Claude instance.
        ws_path = ""
        try:
            import importlib.util as _ilu
            _gaw_path = str(boost_home / "scripts" / "get-active-workspace.py")
            _spec = _ilu.spec_from_file_location("_get_active_workspace", _gaw_path)
            _gaw = _ilu.module_from_spec(_spec)
            _spec.loader.exec_module(_gaw)
            ws_path = _gaw.resolve().get("workspace_path", "")
        except Exception:
            pass
        # Fallback: per-instance file missing (e.g. test env, old schema).
        # Read active-workspace.json for the workspace ID, then look up the
        # path in workspaces.json.
        if not ws_path:
            try:
                state_dir = boost_home / "state"
                ws_id = json.loads(
                    (state_dir / "active-workspace.json").read_text(encoding="utf-8")
                ).get("workspace", "")
                if ws_id:
                    reg = json.loads(
                        (state_dir / "workspaces.json").read_text(encoding="utf-8")
                    )
                    ws_path = reg.get(ws_id, {}).get("workspace_path", "")
            except Exception:
                pass
        if ws_path:
            nudges.append(
                "[agent-spawn nudge] Active workspace detected but workspace_path is not in the spawn prompt. "
                f"Include workspace_path=\"{ws_path}\" in the context call so the agent "
                "receives Tier 3c workspace research (task-specific docs indexed by /research-task)."
            )

    # Clean-rag enforcement: agents that will edit files must know about clean-rag
    # proof requirements. Check that the spawn prompt mentions clean-rag search
    # (port 8613) so the agent knows it needs to search and write proof before editing.
    # Evaluator and research agents are exempt (they don't edit source files).
    is_evaluator_spawn = "evaluator" in description.lower() or "verdict" in description.lower()
    is_non_editing = is_evaluator_spawn or is_research_spawn
    has_clean_rag = (
        "8613" in prompt
        or "clean-rag" in prompt_lower
        or "proof-gate" in prompt_lower
        or "clean_rag" in prompt_lower
    )
    if not is_non_editing and not has_clean_rag:
        nudges.append(
            "[clean-rag enforcement] Spawn prompt does not mention clean-rag research enforcement. "
            "Agents that edit files must search clean-rag (POST http://127.0.0.1:8613/search) "
            "and write proof before editing. Include these instructions in the spawn prompt: "
            "\"Before editing any file, search clean-rag (POST http://127.0.0.1:8613/search) "
            "for relevant research, write proof to clean-rag/state/, then retry the edit. "
            "The proof-gate hook will block edits without verified proof.\""
        )

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
    flag = boost_home / "state" / "needs-verification.json"
    audit_active = (boost_home / "state" / "audit-in-progress.json").exists()
    if flag.exists() and not audit_active:
        # A flag from a different project's session, or one older than the
        # expiry window, is stale leftover state rather than a real pending
        # verification for THIS session — drop it instead of blocking on it.
        # (verify-gate-cmd.py stamps "cwd" when it writes the flag; older
        # flags written before that field existed have no "cwd" and are
        # treated as not-matching, so this also self-heals any flag already
        # on disk from before this check was added.)
        FLAG_MAX_AGE_S = 4 * 3600
        flag_data: dict = {}
        try:
            flag_data = json.loads(flag.read_text(encoding="utf-8"))
        except Exception:
            flag_data = {}
        flag_stale = True
        try:
            flagged_at = datetime.fromisoformat(flag_data.get("flagged_at", ""))
            flag_stale = (datetime.now(timezone.utc) - flagged_at).total_seconds() > FLAG_MAX_AGE_S
        except Exception:
            flag_stale = True
        same_project = flag_data.get("cwd") == os.getcwd()

        if flag_stale or not same_project:
            try:
                flag.unlink(missing_ok=True)
            except Exception:
                pass
        else:
            # "verdict" covers evaluator passes named e.g. "Opus verdict synthesis"
            is_evaluator = (
                "evaluator-agent" in prompt_lower
                or "evaluator_agent" in prompt_lower
                or "verdict" in prompt_lower
                or "verdict" in description.lower()
            )
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
        _log_usage(boost_home, description, prompt, blocked=True)
        _write_block_telemetry(boost_home, "Task", description or "unknown", nudges[0])
        # Block when RAG context call is absent from spawn prompt — hard requirement
        return 2

    _log_usage(boost_home, description, prompt, blocked=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
