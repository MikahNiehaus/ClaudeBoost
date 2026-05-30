"""
ClaudeBoost session primer — UserPromptSubmit command hook.

Injects a compact, imperative behavior briefing into Claude's context
before every substantive user message. Acts as standing orders that
re-surface at the start of each turn before Claude decides anything.

Also handles /clear recovery: if /clear-safe wrote state/clear-pending.json
before the clear, this script injects the saved workspace context on the
first message after /clear (regardless of prompt length).

Skips:
- Short prompts (<15 chars) when no clear-pending flag is present

Behavior:
- Checks clear-pending.json — if valid (< 10 min), injects restore context
  and consumes the flag (one-shot).
- Checks RAG sentinel file to detect offline/unverified RAG
- If RAG offline: injects a HARD STOP directive (no workflow may proceed)
- If RAG online: injects 6 non-negotiable standing orders
- Exits 0 always (nudge layer — PreToolUse rag-agent-guard handles hard blocks)

The 8 standing orders (RAG-online path):
1. RAG before file searching
2. Health check — rag_status at investigation start (unresolved edges = stop and fix)
3. Write findings — update context.md after each search or read that reveals something
4. Verify Gate (file:line for every finding)
5. Evaluator for all findings (never self-verify)
6. CONSULT before new endpoints/tables/dependencies
7. rag_context as first step in every agent spawn
8. If any RAG tool is unavailable or errors mid-task: STOP, report to user
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


def consult_mode_active(home: Path) -> bool:
    mode_file = home / "state" / "claudeboost-mode.json"
    if not mode_file.exists():
        return True  # default is CONSULT when file is missing
    try:
        data = json.loads(mode_file.read_text(encoding="utf-8"))
        return data.get("mode", "CONSULT").upper() != "AUTO"
    except Exception:
        return True  # default to CONSULT on read error


def rag_verified() -> bool:
    temp = os.environ.get("TEMP") or os.environ.get("TMPDIR") or "/tmp"
    return (Path(temp) / "claudeboost_rag_ok").exists()


def _get_home() -> Path:
    return Path(os.environ.get("CLAUDEBOOST_HOME") or os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..")
    ))


def _consume_clear_pending(home: Path) -> str:
    """
    Check for a clear-pending flag written by /clear-safe.
    If present and < 10 minutes old, return restore context string and consume the flag.
    The flag is always deleted (one-shot) whether or not it is valid.
    """
    flag_path = home / "state" / "clear-pending.json"
    if not flag_path.exists():
        return ""

    # Always consume the flag — one use only, regardless of outcome
    try:
        flag = json.loads(flag_path.read_text(encoding="utf-8"))
    except Exception:
        flag = {}
    finally:
        try:
            flag_path.unlink(missing_ok=True)
        except Exception:
            pass

    if not flag.get("pending"):
        return ""

    ts_str = flag.get("timestamp", "")
    try:
        ts = datetime.fromisoformat(ts_str)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        age = (datetime.now(timezone.utc) - ts).total_seconds()
        if age > 600:  # 10-minute window — stale flag after that
            return ""
    except Exception:
        return ""

    # Load workspace memo from handoff-latest.json
    handoff_path = home / "state" / "handoff-latest.json"
    try:
        handoff = json.loads(handoff_path.read_text(encoding="utf-8"))
    except Exception:
        return ""

    workspace_memo = handoff.get("workspace_memo", "") or handoff.get("memo", "")
    if not workspace_memo:
        return ""

    # The auto-save hook writes ALL workspace memos into one string.
    # Filter to just the active workspace section — injecting everything wastes tokens.
    active_ws = handoff.get("active_workspace", "").strip()
    if active_ws:
        marker = f"### {active_ws}\n"
        idx = workspace_memo.find(marker)
        if idx != -1:
            rest = workspace_memo[idx + len(marker):]
            next_section = rest.find("\n### ")
            workspace_memo = rest[:next_section].strip() if next_section != -1 else rest.strip()

    return (
        "POST-CLEAR CONTEXT RESTORATION\n"
        "===============================\n\n"
        "You just returned from a /clear. Below is your saved working state "
        "(written by /clear-safe immediately before the clear).\n\n"
        + workspace_memo
        + "\n\nRESUME INSTRUCTIONS:\n"
        "- Read workspace context.md files above for full detail\n"
        "- Continue from the last documented next step\n"
        "- Keep workspace context.md files updated as you work\n"
        "- If the user gave you a task before the clear, pick it back up\n"
    )


def main() -> int:
    raw = sys.stdin.read() if not sys.stdin.isatty() else ""
    try:
        data = json.loads(raw) if raw else {}
    except Exception:
        data = {}

    prompt = data.get("prompt", "").strip()
    home = _get_home()

    # Always check for clear-pending flag — inject even on short prompts like "continue"
    clear_context = _consume_clear_pending(home)

    # Skip standing orders for short prompts with no clear-pending context
    if len(prompt) < 15 and not clear_context:
        return 0

    # Post-clear restore path — bypass RAG hard-stop.
    # rag-session-reset.py unconditionally deletes the sentinel at every SessionStart,
    # so rag_verified() is always false on the first post-clear message. Blocking on
    # RAG here means auto-restore can never work. Inject context directly with a soft nudge.
    if clear_context and not rag_verified():
        context = (
            clear_context
            + "\n\nNOTE: RAG not yet verified. Run /boost before spawning agents "
            "or starting any investigation."
        )
        print(json.dumps({"additionalContext": context}))
        return 0

    if not rag_verified():
        # RAG not verified, no clear context — hard stop
        context = (
            "CRITICAL — RAG NOT VERIFIED: "
            "The RAG server has not been verified this session. "
            "You MUST NOT spawn agents, call rag_context/rag_search, "
            "or proceed with any multi-step workflow. "
            "Before doing ANYTHING else, stop and tell the user exactly: "
            "'RAG is not connected. Run /boost to verify RAG before I can continue.' "
            "Do not attempt to self-recover by reading files or grepping. Just stop."
        )
        print(json.dumps({"additionalContext": context}))
        return 0

    # RAG verified — inject normal standing orders (applies to slash commands too)
    standing_orders = (
        "STANDING ORDERS (non-negotiable): "
        "(1) RAG before files — rag_search before Read/Grep. "
        "(2) Health check — at start of any investigation, call rag_status to verify index "
        "health; if unresolved edges or errors, stop and fix before continuing. "
        "(3) Write findings — after each RAG search or file read that reveals something, "
        "update workspace/[task-id]/context.md with what you found before moving on. "
        "Do not accumulate findings in your head; write them down as you go. "
        "(4) Cite file:line — for every finding. "
        "(5) Evaluator — spawn evaluator-agent, never self-verify. "
        "(6) rag_context first — in every agent spawn prompt. "
        "(7) RAG all modes — use rag_context for knowledge, rag_search mode=vector for semantic "
        "code search, and rag_search mode=graph for import and dependency chains. "
        "When RAG errors mid-task, fix it (run /mcp to reconnect) — never skip RAG and "
        "substitute grep or file reads. "
        "(8) RAG offline = STOP — if any RAG MCP tool is unavailable or errors, "
        "do NOT self-recover by searching files; tell the user RAG is offline and wait. "
        "(9) Human voice — every word you write must sound like a human wrote it. "
        "Use contractions. Vary sentence length. Start with the substance. "
        "Never use: delve, leverage, utilize, seamless, robust, comprehensive, "
        "pivotal, facilitate, harness, foster, transformative, paradigm, synergy, holistic, empower. "
        "Never open with: Certainly!, Great question!, Absolutely!, Furthermore,, Moreover,, "
        "It's worth noting, In today's rapidly evolving. "
        "No em-dashes at all. Rewrite as separate sentences instead. "
        "No hyphenated compound jargon (no-go, hard-block, soft-fail, non-trivial). "
        "Say what you mean in plain words instead. "
        "(10) Code comments — non-formal but professional, concise, say why not what. "
        "No dashes of any kind in comments (no hyphens as separators, no em dashes, no double dashes). "
        "(11) Tasks — for any multi-step or non-trivial work, call TaskCreate before starting. "
        "Mark in_progress when you begin a task, completed when you finish it. "
        "Update as you go, not in a batch at the end."
    )

    if consult_mode_active(home):
        standing_orders += (
            " (CONSULT MODE IS ACTIVE) Before making any architectural decision the user has not "
            "already approved — new endpoint, table, dependency, module, middleware, auth strategy, "
            "API design, config change, or concurrency model — STOP and present your proposal using "
            "AskUserQuestion. Do not proceed until the user approves. This applies even when the "
            "change seems small or obviously correct."
        )

    if clear_context:
        context = clear_context + "\n\n" + standing_orders
    else:
        context = standing_orders

    print(json.dumps({"additionalContext": context}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
