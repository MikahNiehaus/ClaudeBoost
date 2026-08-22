"""
ClaudeBoost context nudge — PostToolUse command hook on all tool uses.

Two independent nudge channels that can both fire in the same turn:

CHANNEL A — Behavior enforcement (one per turn, elif chain):
   - After 5 consecutive file searches without RAG: RAG reminder
   - After 2 Task spawns without evaluator: evaluator reminder
   - At 100+ tool uses (every 25 past): /clear-safe suggestion
   - Every 25 tool uses: comprehensive 5-behavior checklist

CHANNEL B — Workspace checkpoint (independent):
   - On Edit/Write: always auto-save handoff-latest.json (silent, no context cost)
     then nudge if context.md is stale (>5 min old)
   - On other tools: every 20 tool uses, names workspace/[task-id]/context.md to update
     and escalates to URGENT if it hasn't changed since last nudge

Both channels fire in the same turn when both conditions are met.
Messages are combined into a single additionalContext output.
"""
from __future__ import annotations

import functools
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from workspace_identity import resolve_active_workspace, get_instance_id

NUDGE_INTERVAL = 8         # workspace checkpoint every N tool uses (was 20 — more continuous)
NO_WORKSPACE_NUDGE_THRESHOLD = 60
# Reads without RAG before the soft reminder. Lowered from 5 alongside the block
# in rag_read_guard, which moved from 6 to 3. This has to stay BELOW that number
# or the reminder never fires at all: a PreToolUse block stops the read, so this
# PostToolUse hook never runs and the counter never gets past 3. At 2 the
# sequence is one warning, then the block.
RAG_THRESHOLD = 2          # reads without RAG before reminding
EVALUATOR_THRESHOLD = 2    # agent spawns without evaluator before reminding
COMPREHENSIVE_INTERVAL = 25  # full behavior checklist every N tool uses
CLEAR_CONSIDERATION_THRESHOLD = 100   # start suggesting /clear-safe at this tool count
CLEAR_CONSIDERATION_INTERVAL = 25     # repeat every N uses past threshold
READS_BEFORE_CONTEXT_UPDATE = 5  # consecutive reads/greps that trigger a "write findings" nudge

# Context window pressure detection
# PostToolUse payload may include context_window_usage.input_tokens — used when available.
# Falls back to tool-count heuristic when the field is absent.
CONTEXT_WINDOW_SIZE = 200_000   # tokens — default for Claude Sonnet/Opus in Claude Code
CONTEXT_PCT_WARN = 0.75         # warn when >75% of the window is used (< 25% remaining)

# Auto-save + stale nudge on Edit/Write
AUTO_SAVE_TOOLS = {"Edit", "Write"}
STALE_NUDGE_SECONDS = 300  # 5 minutes — nudge if context.md older than this after an edit

RAG_TOOLS: set = set()  # RAG is HTTP-only now; detection uses _is_http_rag below


@functools.lru_cache(maxsize=1)
def _rag_port() -> int:
    """The port clean-rag actually listens on, from clean-rag's own config.

    Written down here once before, as 8612, and left behind when that server was
    retired. `clean-rag/server/config.py` owns the number and
    `clean-rag/cli/server_ctl.py:37-42` already imports it exactly this way.
    """
    try:
        boost_home = Path(os.environ.get("CLAUDEBOOST_HOME") or Path(__file__).parent.parent)
        root = str(boost_home / "clean-rag")
        if root not in sys.path:
            sys.path.insert(0, root)
        from server.config import STANDALONE_PORT
        return int(STANDALONE_PORT)
    except Exception:
        return 8613
FILE_TOOLS = {"Read", "Grep", "Glob", "Bash"}


def _target_workspace(ctx_files: list, home: Path) -> Path | None:
    """Return the context.md file to nudge about, or None if unresolvable.

    Uses per-instance workspace resolution (same as statusline) so each terminal
    targets its own active workspace, not a stale global file.
    """
    state_dir = home / "state"
    cwd = os.getcwd().replace("\\", "/").rstrip("/")
    ws_id = resolve_active_workspace(state_dir, cwd)

    if ws_id:
        # Check the workspace registry for the path
        try:
            reg = json.loads((state_dir / "workspaces.json").read_text(encoding="utf-8"))
            entry = reg.get(ws_id, {})
            ws_path = entry.get("workspace_path", "")
            if ws_path:
                candidate = Path(ws_path) / "context.md"
                if candidate.exists():
                    return candidate
        except Exception:
            pass
        # Fallback: check local workspace/ directory
        local = home / "workspace" / ws_id / "context.md"
        if local.exists():
            return local

    # No per-instance workspace found; fall back to most recently modified
    if ctx_files:
        try:
            return max(ctx_files, key=lambda f: f.stat().st_mtime)
        except (OSError, ValueError):
            return ctx_files[0]
    return None


def _auto_save_handoff(home: Path, ctx_files: list, session_id: str = "") -> None:
    """Silently write handoff-latest.json from current workspace context.md files.

    Called after every Edit/Write so /clear is always safe — no additionalContext
    output, no token cost. Reads whatever context.md files currently contain.
    The compaction-save.py (PreCompact) will overwrite this with richer conversation
    data; this is the lightweight in-session safety net.
    """
    if not ctx_files:
        return

    summaries = []
    for ctx_file in sorted(ctx_files):
        task_id = ctx_file.parent.name
        try:
            content = ctx_file.read_text(encoding="utf-8")
            summaries.append(f"### {task_id}\n{content[:3000]}")
        except Exception:
            pass

    if not summaries:
        return

    workspace_memo = "\n\n".join(summaries)
    handoff_data = {
        "session_id": session_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "trigger": "PostToolUse:auto-save",
        "workspace_memo": workspace_memo,
        "conversation": {},
    }

    try:
        (home / "state" / "handoff-latest.json").write_text(
            json.dumps(handoff_data, indent=2), encoding="utf-8"
        )
    except Exception:
        pass


def main() -> int:
    home = Path(os.environ.get("CLAUDEBOOST_HOME") or os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..")
    ))

    # Compute ctx_files once — used by both Channel B paths and auto-save.
    # Read from the workspace registry so project workspaces (outside
    # $CLAUDEBOOST_HOME/workspace/) are also monitored. Falls back to a
    # direct glob of home/workspace/ if the registry is absent or empty.
    SESSION_WINDOW_HOURS = 4
    session_cutoff = time.time() - SESSION_WINDOW_HOURS * 3600

    reg_path = home / "state" / "workspaces.json"
    try:
        reg = json.loads(reg_path.read_text(encoding="utf-8"))
        _all_ctx = [
            Path(ws["workspace_path"]) / "context.md"
            for ws in reg.values()
            if ws.get("workspace_path")
        ]
        ctx_files = [
            f for f in _all_ctx
            if f.exists() and f.stat().st_mtime >= session_cutoff
        ]
    except Exception:
        # Fallback: scan the local workspace directory
        workspace_dir = home / "workspace"
        if workspace_dir.exists():
            ctx_files = [
                f for f in workspace_dir.glob("*/context.md")
                if f.stat().st_mtime >= session_cutoff
            ]
        else:
            ctx_files = []

    has_workspace = bool(ctx_files)

    # Bypass workspace checkpoint during cross-cutting operations that read many
    # files by design. Mirrors the same pattern in agent-spawn-gate.py (line ~180).
    audit_active = (home / "state" / "audit-in-progress.json").exists()

    # --- Read hook payload ---
    raw = sys.stdin.read() if not sys.stdin.isatty() else ""
    try:
        payload = json.loads(raw) if raw else {}
    except Exception:
        payload = {}

    tool_name = payload.get("tool_name", "")
    session_id = payload.get("session_id", "")

    # --- Behavior tracker ---
    behavior_path = home / "state" / "behavior-tracker.json"
    try:
        behavior = json.loads(behavior_path.read_text(encoding="utf-8"))
    except Exception:
        behavior = {"reads_since_rag": 0, "tasks_since_evaluator": 0}

    # Safety net for dirty trackers after a crash (session-clear-save.py didn't run).
    # Only fires when the tracker already has a session_id that is DIFFERENT from the
    # current one — meaning the previous session ended uncleanly. When session_id is
    # absent from the tracker (normal after a clean /clear), skip the reset entirely
    # because session-clear-save.py already zeroed everything out.
    _prev_session = behavior.get("session_id")
    if session_id and _prev_session and _prev_session != session_id:
        behavior["reads_since_context_update"] = 0
        behavior["reads_since_rag"] = 0
        behavior["tasks_since_evaluator"] = 0
        behavior["last_nudge_ctx_mtime"] = 0.0
        behavior["last_nudge_ctx_path"] = ""
        behavior["last_nudge_count"] = 0
        behavior["reads_ctx_workspace_id"] = ""
        try:
            behavior_path.write_text(json.dumps(behavior), encoding="utf-8")
        except Exception:
            pass
    # Always track the current session so the next call can detect a future change.
    if session_id:
        behavior["session_id"] = session_id

    # --- Context window pressure (from hook payload when available) ---
    ctx_usage = payload.get("context_window_usage") or {}
    input_tokens = ctx_usage.get("input_tokens", 0)
    context_pct_used: "float | None" = (
        input_tokens / CONTEXT_WINDOW_SIZE if input_tokens else None
    )

    # --- Compaction counter ---
    tracker_path = home / "state" / "compaction-tracker.json"
    try:
        tracker = json.loads(tracker_path.read_text(encoding="utf-8"))
    except Exception:
        tracker = {"edit_count": 0}

    tracker["edit_count"] = tracker.get("edit_count", 0) + 1

    try:
        tracker_path.write_text(json.dumps(tracker), encoding="utf-8")
    except Exception:
        pass

    # Reset the per-read counter when the active workspace changes.
    # Without this, reads from one workspace accumulate and fire against
    # a different workspace after switching tasks.
    cwd = os.getcwd().replace("\\", "/").rstrip("/")
    _current_ws_id = resolve_active_workspace(home / "state", cwd)
    if _current_ws_id and behavior.get("reads_ctx_workspace_id", "") != _current_ws_id:
        behavior["reads_since_context_update"] = 0
        behavior["reads_since_rag"] = 0
        behavior["tasks_since_evaluator"] = 0
        behavior["reads_ctx_workspace_id"] = _current_ws_id

    # Detect context.md write (Edit/Write to a file named context.md) — resets investigation counter
    tool_input = payload.get("tool_input") or {}
    wrote_context = (
        tool_name in AUTO_SAVE_TOOLS
        and "context.md" in str(tool_input.get("file_path", ""))
    )

    # Update RAG/file counters
    # An HTTP call to the RAG REST API counts the same as an MCP RAG tool call.
    #
    # This used to match the literal "8612" only. That server was retired, so the
    # check silently stopped ever firing: every real RAG search looked like no
    # search at all, reads_since_rag climbed forever, and the nudges fired against
    # sessions that were using RAG correctly. Match whichever port clean-rag is
    # actually on, read from its own config.
    _bash_cmd = str(tool_input.get("command", "")) if tool_name == "Bash" else ""
    _is_http_rag = bool(_bash_cmd) and any(
        f"{host}:{_rag_port()}" in _bash_cmd for host in ("127.0.0.1", "localhost")
    )

    if tool_name in RAG_TOOLS or _is_http_rag:
        behavior["reads_since_rag"] = 0
    elif tool_name in FILE_TOOLS:
        behavior["reads_since_rag"] = behavior.get("reads_since_rag", 0) + 1

    # Track reads since last context.md update — fires "write your findings" nudge.
    # Don't count reads during audit: suppressing the nudge but not the counter
    # causes the BLOCK escalation to fire immediately when the audit ends.
    if wrote_context:
        behavior["reads_since_context_update"] = 0
    elif (tool_name in FILE_TOOLS or tool_name in RAG_TOOLS) and not audit_active:
        behavior["reads_since_context_update"] = behavior.get("reads_since_context_update", 0) + 1

    # Update evaluator counter
    # Reset only when evaluator Task *completes* with a real verdict, not on spawn.
    # This prevents a stalled evaluator (37 tokens, no verdict) from clearing the counter.
    EVALUATOR_VERDICT_KEYWORDS = ("confirmed", "false_positive", "grade:", "blocker", "warning")
    if tool_name == "Task":
        desc = str((payload.get("tool_input") or {}).get("description", "")).lower()
        tool_response_raw = payload.get("tool_response", "") or ""
        tool_response_lower = str(tool_response_raw).lower()

        is_evaluator = "evaluator" in desc
        has_verdict = any(kw in tool_response_lower for kw in EVALUATOR_VERDICT_KEYWORDS)

        # Code-review passes have their own evaluator (Pass 15) at the end.
        # Don't count them toward tasks_since_evaluator — they generate many
        # agent spawns by design and must not trigger mid-batch evaluator nudges.
        REVIEW_PASS_MARKERS = ("review pass", "pass 1 —", "pass 2 —", "pass 3 —",
                               "pass 4 —", "pass 5 —", "pass 6 —", "pass 7 —",
                               "pass 8 —", "pass 9 —", "pass 10 —", "pass 11 —",
                               "pass 12 —", "pass 13 —", "pass 14 —",
                               "simplicity review", "dead code review",
                               "ticket alignment review", "migration/schema review",
                               "banned dependencies review")
        is_review_pass = any(marker in desc for marker in REVIEW_PASS_MARKERS)

        if is_evaluator and has_verdict:
            behavior["tasks_since_evaluator"] = 0
        elif not is_evaluator and not is_review_pass:
            behavior["tasks_since_evaluator"] = behavior.get("tasks_since_evaluator", 0) + 1
        # is_evaluator but no verdict (stalled/minimal output) → no reset, no increment
        # is_review_pass → no increment (has its own evaluator at the end)

        # Store recent task response for citation extraction in nudge messages
        if tool_response_raw:
            behavior["last_task_response"] = str(tool_response_raw)[:2000]

    reads = behavior.get("reads_since_rag", 0)
    reads_since_ctx = behavior.get("reads_since_context_update", 0)
    tasks = behavior.get("tasks_since_evaluator", 0)
    total = tracker.get("edit_count", 0)

    nudges = []
    _should_block = False  # set True when WRITE FINDINGS escalates to decision:block

    # --- CHANNEL A: Behavior enforcement (one per turn, elif chain) ---
    if context_pct_used is not None and context_pct_used >= CONTEXT_PCT_WARN:
        nudges.append(
            f"CONTEXT PRESSURE ({int(context_pct_used * 100)}% of window used — "
            f"{int((1 - context_pct_used) * CONTEXT_WINDOW_SIZE / 1000)}k tokens remain): "
            "Run /clear-safe NOW — do not start new subtasks. "
            "Finish the current sentence, update workspace context.md with status + next step, "
            "then run /clear-safe to save state and clear. "
            "Only skip if an agent is mid-task; finish it first, then clear immediately after."
        )
    elif (
        reads_since_ctx >= READS_BEFORE_CONTEXT_UPDATE
        and reads_since_ctx % READS_BEFORE_CONTEXT_UPDATE == 0
        and has_workspace
        and not audit_active
    ):
        if reads_since_ctx >= READS_BEFORE_CONTEXT_UPDATE * 2:
            # 2nd+ nudge without compliance — escalate to hard stop
            _should_block = True
            nudges.append(
                f"WRITE FINDINGS — BLOCKED: You've done {reads_since_ctx} reads/searches "
                "without updating your workspace's context.md. "
                "Update it NOW (status, what you found, next step) before continuing. "
                "The agentic loop is stopped until context.md is updated."
            )
        else:
            nudges.append(
                f"WRITE FINDINGS: You've done {reads_since_ctx} reads/searches since last updating "
                "your workspace's context.md. "
                "Record what you found NOW before continuing — hypothesis, evidence, next lead. "
                "Findings in context.md survive compaction; findings only in your head do not."
            )
    elif reads >= RAG_THRESHOLD and reads % RAG_THRESHOLD == 0:
        nudges.append(
            f"RAG REMINDER ({reads} file searches since last RAG call): "
            "STOP reading files. Search RAG FIRST — "
            f"POST http://127.0.0.1:{_rag_port()}/search with "
            '{"sources":["project:<abs path>"],"mode":"both"}. '
            "Only read files after RAG confirms which ones are relevant."
        )
    elif tasks >= EVALUATOR_THRESHOLD and tasks % EVALUATOR_THRESHOLD == 0 and not audit_active:
        # Extract file:line citations from the most recent agent output so the
        # evaluator spawn prompt has something concrete to verify against.
        last_response = behavior.get("last_task_response", "")
        raw_citations = re.findall(r'[\w./\\-]+\.\w{1,6}:\d+', last_response)
        unique_citations = list(dict.fromkeys(raw_citations))[:5]
        if unique_citations:
            citation_hint = (
                f" Citations from last agent output: {', '.join(unique_citations)}. "
                "Include these verbatim in the evaluator spawn prompt description."
            )
        else:
            citation_hint = (
                " No file:line citations found in last agent output — "
                "go back and extract specific file:line locations before spawning evaluator."
            )
        nudges.append(
            f"EVALUATOR REMINDER ({tasks} agent spawns without evaluator): "
            "Spawn evaluator-agent on your findings before acting on them. "
            "Never self-verify — evaluator reads only the cited file:lines."
            + citation_hint
        )
    elif (
        total >= CLEAR_CONSIDERATION_THRESHOLD
        and (total - CLEAR_CONSIDERATION_THRESHOLD) % CLEAR_CONSIDERATION_INTERVAL == 0
    ):
        nudges.append(
            f"CONTEXT HEALTH CHECK ({total} tool uses this session): "
            "You are approaching context limits. Run /clear-safe — it will verify your "
            "workspace context.md is current, show you what survives, and confirm before clearing. "
            "Only suggest /clear-safe if: (1) no agent is mid-task; "
            "(2) no file edit is partially open; "
            "(3) you are at a natural stopping point. "
            "If conditions are not met, finish the current subtask first."
        )
    elif total > 0 and total % COMPREHENSIVE_INTERVAL == 0:
        nudges.append(
            "BEHAVIOR CHECKPOINT — five rules you tend to skip: "
            f"(1) STUCK? -> POST http://127.0.0.1:{_rag_port()}/search before more file reads. "
            "(2) FINDING? -> cite file:line, then spawn evaluator-agent. "
            "(3) NEW endpoint/table/dependency? -> CONSULT mode, spawn architect-agent. "
            "(4) COMPLEX task? -> workspace/[task-id]/context.md. "
            f"(5) SPAWNING AGENT? -> give it a POST http://127.0.0.1:{_rag_port()}/search "
            "against the relevant project: source as its first step."
        )

    # --- CHANNEL B: Workspace checkpoint (independent — fires even when Channel A fired) ---
    if tool_name in AUTO_SAVE_TOOLS and has_workspace:
        # Always: silently save handoff state so /clear is always safe regardless of
        # whether context.md was just updated. No additionalContext — zero token cost.
        _auto_save_handoff(home, ctx_files, session_id)

        # Nudge only when context.md is stale — no spam when it was just written.
        # No audit_active guard here: stale context.md is worth flagging even during audits,
        # and audits don't do Edit/Write to code files so this rarely fires.
        most_recent = _target_workspace(ctx_files, home)
        if most_recent:
            age_seconds = time.time() - most_recent.stat().st_mtime
            if age_seconds > STALE_NUDGE_SECONDS:
                age_min = int(age_seconds / 60)
                nudges.append(
                    f"CONTEXT UPDATE — your workspace's context.md is {age_min}m stale. "
                    "Update it now: current status, decision made, next step."
                )

    elif has_workspace and total % NUDGE_INTERVAL == 0 and not audit_active:
        # Fallback: periodic nudge for sessions without recent Edit/Write activity
        most_recent = _target_workspace(ctx_files, home)
        if most_recent:
            current_mtime = most_recent.stat().st_mtime

            last_mtime = behavior.get("last_nudge_ctx_mtime", 0.0)
            last_path = behavior.get("last_nudge_ctx_path", "")
            last_count = behavior.get("last_nudge_count", 0)

            unchanged = (
                last_path == str(most_recent)
                and abs(current_mtime - last_mtime) < 2.0
            )

            if unchanged and last_count > 0:
                uses_since = total - last_count
                nudges.append(
                    f"URGENT CONTEXT CHECKPOINT: your workspace's context.md "
                    f"has NOT been updated since the reminder {uses_since} tool uses ago. "
                    "Update it NOW before continuing — status, next step, decisions made. "
                    "This file is what survives /clear and compaction."
                )
            else:
                nudges.append(
                    "CONTEXT CHECKPOINT: Update your workspace's context.md now with: "
                    "(1) what was just implemented or decided, "
                    "(2) current status and specific next step, "
                    "(3) user requirements or constraints stated this session."
                )

            behavior["last_nudge_ctx_mtime"] = current_mtime
            behavior["last_nudge_ctx_path"] = str(most_recent)
        behavior["last_nudge_count"] = total

    elif not has_workspace and total == NO_WORKSPACE_NUDGE_THRESHOLD:
        nudges.append(
            "No active workspace detected. You've done significant work — if this is "
            "getting complex, consider creating a workspace "
            "(workspace/[task-id]/context.md) to capture code changes AND important "
            "user statements (requirements, decisions, preferences) so progress "
            "survives compaction."
        )

    try:
        behavior_path.write_text(json.dumps(behavior), encoding="utf-8")
    except Exception:
        pass

    if nudges and _should_block:
        print(json.dumps({
            "decision": "block",
            "reason": "\n\n".join(nudges),
        }))
    elif nudges:
        print(json.dumps({"additionalContext": "\n\n".join(nudges)}))

    return 0


if __name__ == "__main__":
    sys.exit(main())
