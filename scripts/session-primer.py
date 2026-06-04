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

Boost injection modes (state/boost-injection.json):
- "false"  — skip all injection entirely
- "true"   — inject always-on rules only, skip RAG verification
- "verify" — (default) full RAG-gated behavior

Always-on rules (A-H) inject in both "true" and "verify" modes:
A. Tasks first — create tasks before multi-step work
B. Human voice
C. Code comments, no dashes
D. Architectural approval before changes
E. RAG usage when available
F. Workspace update when one exists
G. Dynamic RAG tiers — project_path/workspace_path params and what each enables
H. Irreversible actions — stop and confirm before anything that can't be undone

RAG standing orders (1-8) only inject in "verify" mode when RAG is confirmed online.

Workspace reminder injects when active-workspace.json resolves to a real path (any mode):
- Active workspace ID, workspace_path, project_path
- Tier 3c status (EXISTS or NOT BUILT + /research-rag command)
- Hard rule: every /context call must include workspace_path
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


def _active_workspace_reminder(home: Path) -> str:
    """
    Return a compact workspace reminder when an active workspace is set and resolvable.
    Empty string when no workspace is active or path can't be found.
    """
    active_path = home / "state" / "active-workspace.json"
    if not active_path.exists():
        return ""
    try:
        active = json.loads(active_path.read_text(encoding="utf-8"))
        ws_id = active.get("workspace", "")
        ws_path = active.get("workspace_path", "")
        project_path = active.get("project_path", "")
    except Exception:
        return ""

    if not ws_id:
        return ""

    # Fill missing paths from registry
    if not ws_path or not project_path:
        reg_file = home / "state" / "workspaces.json"
        try:
            reg = json.loads(reg_file.read_text(encoding="utf-8"))
            entry = reg.get(ws_id, {})
            ws_path = ws_path or entry.get("workspace_path", "")
            project_path = project_path or entry.get("project_path", "")
        except Exception:
            pass

    # Last resort: default location
    if not ws_path:
        candidate = home / "workspace" / ws_id
        if candidate.is_dir():
            ws_path = str(candidate)

    if not ws_path:
        return ""

    # Tier 3c status
    t3c_exists = (Path(ws_path) / ".rag-index" / "research").exists()
    t3c_note = "EXISTS" if t3c_exists else f"NOT BUILT - run /research-rag {ws_id} before agents"

    lines = [
        f"ACTIVE WORKSPACE: {ws_id}",
        f"  workspace_path: {ws_path}",
    ]
    if project_path:
        lines.append(f"  project_path:   {project_path}")
    lines += [
        f"  Tier 3c:        {t3c_note}",
        "DYNAMIC RAG - what each param enables in POST /context:",
        f'  project_path="{project_path}"' if project_path else "  project_path: (not set)",
        "    -> Tier 3 stack boost (detects language, boosts matching knowledge)",
        "    -> Tier 4 codebase search + graph neighbours (needs indexed project)",
        f'  workspace_path="{ws_path}"',
        "    -> Tier 3c task research (auto-loads docs indexed by /research-rag)",
        "  Omit either param -> that tier is skipped entirely",
        "WORKSPACE RULE: Every /context call MUST include both params above —"
        " whether called by you (orchestrator) OR in an agent spawn prompt."
        " This applies to all RAG context loads this session, not just agent spawns.",
    ]
    return "\n".join(lines)


def _get_boost_injection_mode(home: Path) -> str:
    """Return boost injection mode: 'true', 'false', or 'verify' (default)."""
    state_path = home / "state" / "boost-injection.json"
    try:
        data = json.loads(state_path.read_text(encoding="utf-8"))
        return data.get("mode", "verify").lower()
    except Exception:
        return "verify"


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

    boost_mode = _get_boost_injection_mode(home)

    # boost false: skip all injection entirely
    if boost_mode == "false":
        return 0

    # Always check for clear-pending flag — inject even on short prompts like "continue"
    clear_context = _consume_clear_pending(home)

    # Skip standing orders for short prompts with no clear-pending context
    if len(prompt) < 15 and not clear_context:
        return 0

    # Always-inject rules: fire regardless of RAG state
    always_inject = (
        "ALWAYS-ON RULES (apply to every response): "
        "(A) TASKS FIRST — before doing any work that involves more than one action, call TaskCreate. "
        "This is not optional. If the user's request can be broken into steps, create tasks before starting. "
        "Mark each task in_progress when you begin it. Mark it completed the moment you finish it — not in a batch at the end. "
        "Never forget a step because it was not tracked. Tasks are your memory. Use them. "
        "(B) Human voice — every word you write must sound like a human wrote it. "
        "Use contractions. Vary sentence length. Start with the substance. "
        "Never use: delve, leverage, utilize, seamless, robust, comprehensive, "
        "pivotal, facilitate, harness, foster, transformative, paradigm, synergy, holistic, empower. "
        "Never open with: Certainly!, Great question!, Absolutely!, Furthermore,, Moreover,, "
        "It's worth noting, In today's rapidly evolving. "
        "No em-dashes. Rewrite as separate sentences instead. "
        "No hyphenated compound jargon (no-go, hard-block, soft-fail, non-trivial). "
        "Say what you mean in plain words instead. "
        "(C) Code comments — non-formal but professional, concise, say why not what. "
        "No dashes of any kind in comments (no hyphens as separators, no em dashes, no double dashes). "
        "(D) Architectural changes — before making any architectural change (new class, endpoint, "
        "table, schema, service, or pattern), explain exactly what you are changing and why. "
        "Do not proceed until the user confirms they understand and approve. "
        "(E) RAG usage — when RAG is available, always call POST http://127.0.0.1:8612/search before reading files or grepping. "
        "Use mode=vector for semantic code search and mode=graph for import and dependency chains. "
        "Never substitute grep or Read for RAG when RAG is online. "
        "If RAG is erroring or unavailable, stop and fix it (run /rag to start the server). "
        "Do not skip RAG and fall back to file reads — fix the connection first, then proceed. "
        "(F) Workspace update — if a workspace context.md exists for the current task, "
        "update it after each meaningful finding or decision. "
        "Do not let findings accumulate in context only. "
        "(G) Dynamic RAG tiers — POST /context loads knowledge in layers. "
        "project_path enables Tier 3 stack-boosted knowledge + Tier 4 codebase search. "
        "workspace_path enables Tier 3c task research (built by /research-rag). "
        "Omit a param and that tier is skipped. "
        "Always pass both when you have them. "
        "If no workspace exists yet, pass project_path alone to get Tier 3 + Tier 4. "
        "(H) Irreversible actions — before doing ANYTHING that cannot be undone "
        "(deleting files, dropping tables, force-pushing, overwriting data, sending messages, "
        "publishing to external services, running destructive shell commands), STOP. "
        "Tell the user exactly what you are about to do and why it cannot be undone. "
        "Use AskUserQuestion to get explicit YES confirmation before proceeding. "
        "If uncertain whether an action is reversible, treat it as irreversible and ask. "
        "Prefer safe reversible alternatives whenever one exists — soft deletes over hard deletes, "
        "backups before overwrites, dry-runs before destructive commands."
    )

    # Compute workspace reminder once — appended to every output path below.
    # Fires whenever active-workspace.json resolves to a real workspace path,
    # regardless of RAG state or boost mode.
    workspace_reminder = _active_workspace_reminder(home)

    def _emit(ctx: str) -> int:
        full = (ctx + "\n\n" + workspace_reminder) if workspace_reminder else ctx
        print(json.dumps({"additionalContext": full}))
        return 0

    # Standing orders fire on every message — no RAG sentinel required.
    # The user should not need to run /rag just to receive workflow rules.
    standing_orders = (
        "RAG STANDING ORDERS (non-negotiable): "
        "(1) RAG before files — POST http://127.0.0.1:8612/search before Read/Grep. "
        "(2) Health check — at start of any investigation, call GET http://127.0.0.1:8612/status. "
        "If unresolved edges or errors, stop and fix before continuing. "
        "(3) Write findings — after each RAG search or file read that reveals something, "
        "update workspace/[task-id]/context.md with what you found before moving on. "
        "Do not accumulate findings in your head; write them down as you go. "
        "(4) Cite file:line — for every finding. "
        "(5) Evaluator — spawn evaluator-agent, never self-verify. "
        "(6) RAG context first — call POST http://127.0.0.1:8612/context as first step in every agent spawn prompt. "
        "(7) RAG all modes — use /context for knowledge, /search?scope=codebase for semantic "
        "code search, and /search?mode=graph for import and dependency chains. "
        "When RAG errors mid-task, fix it (run /rag to start the server) — never skip RAG and "
        "substitute grep or file reads. "
        "(8) RAG offline = STOP — if any RAG MCP tool is unavailable or errors, "
        "do NOT self-recover by searching files; tell the user RAG is offline and wait."
    )

    if consult_mode_active(home):
        standing_orders += (
            " (CONSULT MODE IS ACTIVE) Before making any architectural decision the user has not "
            "already approved — new endpoint, table, dependency, module, middleware, auth strategy, "
            "API design, config change, or concurrency model — STOP and present your proposal using "
            "AskUserQuestion. Do not proceed until the user approves. This applies even when the "
            "change seems small or obviously correct."
        )

    # boost true: inject always-on rules + standing orders, skip RAG verification
    if boost_mode == "true":
        base = (clear_context + "\n\n") if clear_context else ""
        return _emit(base + always_inject + "\n\n" + standing_orders)

    # Post-clear restore path — bypass RAG hard-stop.
    # rag-session-reset.py unconditionally deletes the sentinel at every SessionStart,
    # so rag_verified() is always false on the first post-clear message. Blocking on
    # RAG here means auto-restore can never work. Inject context directly with a soft nudge.
    if clear_context and not rag_verified():
        context = (
            clear_context
            + "\n\nNOTE: RAG not yet verified. Run /rag before spawning agents "
            "or starting any investigation."
            + "\n\n" + always_inject + "\n\n" + standing_orders
        )
        return _emit(context)

    if not rag_verified():
        # RAG not verified — inject all rules plus a warning. Standing orders still fire
        # so the user gets the full workflow brief without needing to run /rag first.
        context = (
            "NOTE: RAG not yet verified this session. Run /rag before spawning agents, "
            "calling /search, or starting any multi-step investigation. "
            "Do not self-recover by grepping or reading files — run /rag first."
            "\n\n" + always_inject + "\n\n" + standing_orders
        )
        return _emit(context)

    # RAG verified — full context, no warning needed
    base = (clear_context + "\n\n") if clear_context else ""
    return _emit(base + always_inject + "\n\n" + standing_orders)


if __name__ == "__main__":
    sys.exit(main())
