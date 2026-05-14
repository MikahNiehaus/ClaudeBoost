"""
ClaudeBoost session-clear-save — SessionEnd command hook.

Fires when the user runs /clear (or on implicit session end). Saves workspace
context + conversation highlights to state/handoff-latest.json so the next
session's compaction-restore.py (source=clear path) can restore them.

SessionEnd default timeout: 1.5 seconds. Transcript parsing is O(N lines).
If sessions are very long and this times out, set:
  CLAUDE_CODE_SESSIONEND_HOOKS_TIMEOUT_MS=5000
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add scripts/ to sys.path so sibling imports work
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def read_json(path: "str | os.PathLike", default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return default if default is not None else {}


def extract_summary(content: str, char_budget: int = 2000) -> str:
    """Section-based extraction — mirrors compaction-save.py's logic."""
    import re

    SKIP_SECTIONS = {
        "research sources", "cloned repos", "agent contributions",
        "improvement rounds", "work done",
    }
    PRIORITY_KEYWORDS = [
        "goal", "status", "next step", "decision", "blocked", "blocker",
        "remaining", "constraint", "requirement", "user said", "user preference",
        "progress", "completion criteria", "gotcha", "implement",
    ]

    parts = re.split(r'\n(?=#{1,3} )', content.strip())
    preamble = parts[0][:500]

    priority, other = [], []
    for section in parts[1:]:
        heading = section.split('\n')[0].lower()
        if any(skip in heading for skip in SKIP_SECTIONS):
            continue
        bucket = priority if any(kw in heading for kw in PRIORITY_KEYWORDS) else other
        bucket.append(section)

    result = [preamble]
    used = len(preamble)
    for section in priority + other:
        chunk = section[:400]
        if used + len(chunk) > char_budget:
            break
        result.append(chunk)
        used += len(chunk)

    return "\n\n".join(result)


def _get_project_workspace_path(home: Path, task_id: str) -> "Path | None":
    """Look up absolute workspace path from workspaces.json registry."""
    reg_path = home / "state" / "workspaces.json"
    try:
        reg = json.loads(reg_path.read_text(encoding="utf-8"))
        entry = reg.get(task_id)
        if entry and entry.get("workspace_path"):
            return Path(entry["workspace_path"])
    except Exception:
        pass
    return None


def _workspace_context_path(home: Path, task_id: str) -> "Path | None":
    """Return the context.md path for task_id, checking both local and registry."""
    local = home / "workspace" / task_id / "context.md"
    if local.exists():
        return local
    proj_ws = _get_project_workspace_path(home, task_id)
    if proj_ws:
        p = proj_ws / "context.md"
        if p.exists():
            return p
    return None


def detect_active_workspace(home: Path) -> "str | None":
    """Return the task-id of the active workspace, or None.

    Priority:
    1. state/active-workspace.json  — set explicitly by /clear-safe
    2. Most recently modified workspace/*/context.md (local + project-scoped) — auto-detect fallback

    Cross-check: active-workspace.json is only written at /clear-safe time, so it
    may reflect a PREVIOUS session's workspace. After resolving a Priority 1
    candidate, compare its context.md mtime against all other workspaces. If
    another workspace's context.md is more than 30 minutes newer, prefer it —
    the user most likely switched workspaces without re-running /clear-safe.
    """
    state_path = home / "state" / "active-workspace.json"
    candidate = None
    try:
        data = json.loads(state_path.read_text(encoding="utf-8"))
        ws = data.get("workspace", "")
        if ws and _workspace_context_path(home, ws):
            candidate = ws
    except Exception:
        pass

    # Collect all context.md paths: local ClaudeBoost workspaces + project-scoped
    ctx_files: list[Path] = []
    workspace_dir = home / "workspace"
    if workspace_dir.exists():
        ctx_files.extend(workspace_dir.glob("*/context.md"))

    # Also include project-scoped workspaces from registry
    reg_path = home / "state" / "workspaces.json"
    try:
        reg = json.loads(reg_path.read_text(encoding="utf-8"))
        for task_id, entry in reg.items():
            wp = entry.get("workspace_path", "")
            if wp:
                ctx = Path(wp) / "context.md"
                if ctx.exists():
                    ctx_files.append(ctx)
    except Exception:
        pass

    if not ctx_files:
        return candidate

    mtime_winner_path = max(ctx_files, key=lambda f: f.stat().st_mtime)
    # Determine task_id from winner path
    # Local: home/workspace/<task_id>/context.md → parent.name
    # Project: <project>/workspace/<task_id>/context.md → parent.name
    mtime_winner = mtime_winner_path.parent.name

    if candidate is None:
        return mtime_winner

    # If the mtime winner is meaningfully newer (>30 min), prefer it over the
    # stored candidate — guards against stale active-workspace.json across sessions.
    try:
        candidate_ctx = _workspace_context_path(home, candidate)
        if candidate_ctx:
            candidate_mtime = candidate_ctx.stat().st_mtime
            winner_mtime = mtime_winner_path.stat().st_mtime
            if mtime_winner != candidate and (winner_mtime - candidate_mtime) > 1800:
                return mtime_winner
    except Exception:
        pass

    return candidate


def collect_workspace_memo(
    home: Path, session_id: str, mode: str, active_workspace: "str | None" = None
) -> str:
    """Build the workspace memo from context.md files.

    If active_workspace is set, includes only that workspace (local or project-scoped).
    Otherwise falls back to all workspaces (local + registry).
    """
    workspace_dir = home / "workspace"
    workspace_summaries = []

    if active_workspace:
        # Check local first, then project-scoped registry
        local_ctx = workspace_dir / active_workspace / "context.md"
        if local_ctx.exists():
            ctx_files = [local_ctx]
        else:
            proj_path = _get_project_workspace_path(home, active_workspace)
            proj_ctx = proj_path / "context.md" if proj_path else None
            ctx_files = [proj_ctx] if proj_ctx and proj_ctx.exists() else []
    else:
        ctx_files = sorted(workspace_dir.glob("*/context.md")) if workspace_dir.exists() else []
        # Also include project-scoped workspaces from registry
        reg_path = home / "state" / "workspaces.json"
        try:
            reg = json.loads(reg_path.read_text(encoding="utf-8"))
            for task_id, entry in reg.items():
                wp = entry.get("workspace_path", "")
                if wp:
                    ctx = Path(wp) / "context.md"
                    if ctx.exists() and ctx not in ctx_files:
                        ctx_files.append(ctx)
        except Exception:
            pass

    for ctx_file in ctx_files:
        task_id = ctx_file.parent.name
        try:
            content = ctx_file.read_text(encoding="utf-8")
            summary = extract_summary(content)
            workspace_summaries.append(f"### {task_id}\n{summary}")
        except Exception:
            workspace_summaries.append(f"### {task_id}\n[unreadable]")

    parts = [
        "# Clear Handoff Memo",
        f"Session: {session_id}",
        f"Time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}",
        f"Mode: {mode}",
        "",
    ]

    if workspace_summaries:
        parts.append("## Active Workspaces")
        parts.extend(workspace_summaries)
    else:
        parts.append("## Active Workspaces")
        parts.append("None.")

    parts.append("")
    parts.append("## Recovery Instructions")
    parts.append("Read workspace/*/context.md for full task detail.")
    parts.append("Continue from the last documented next step.")

    return "\n".join(parts)


def main() -> int:
    home = Path(os.environ.get("CLAUDEBOOST_HOME") or os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..")
    ))
    state_dir = home / "state"

    # Read hook input from stdin
    raw = sys.stdin.read() if not sys.stdin.isatty() else ""
    try:
        hook_input = json.loads(raw) if raw else {}
    except Exception:
        hook_input = {}

    # Gate: only fire on /clear (source=clear) or implicit session end (source="")
    source = hook_input.get("source", "")
    if source and source != "clear":
        return 0

    session_id = hook_input.get("session_id", "unknown")
    transcript_path_str = hook_input.get("transcript_path", "")
    source_cwd = hook_input.get("cwd", "")

    # Detect active workspace and build scoped memo
    mode = read_json(state_dir / "claudeboost-mode.json").get("mode", "CONSULT")
    active_workspace = detect_active_workspace(home)
    memo_text = collect_workspace_memo(home, session_id, mode, active_workspace)

    # Extract conversation highlights from transcript
    conversation = None
    if transcript_path_str:
        try:
            from handoff_core import extract_conversation
            conversation = extract_conversation(transcript_path_str)
        except Exception:
            pass

    # Write unified handoff-latest.json
    handoff_data = {
        "session_id": session_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "trigger": "SessionEnd(clear)",
        "cwd": source_cwd,
        "active_workspace": active_workspace or "",
        "workspace_memo": memo_text,
        "conversation": conversation or {},
    }
    state_dir.mkdir(parents=True, exist_ok=True)
    handoff_path = state_dir / "handoff-latest.json"
    try:
        handoff_path.write_text(json.dumps(handoff_data, indent=2), encoding="utf-8")
    except Exception:
        pass

    # Also update compaction-memo.json so workspace memo stays current
    existing_compact = read_json(state_dir / "compaction-memo.json")
    memo_compat = {
        "session_id": session_id,
        "compaction_number": existing_compact.get("compaction_number", 0),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "memo": memo_text,
    }
    try:
        (state_dir / "compaction-memo.json").write_text(
            json.dumps(memo_compat, indent=2), encoding="utf-8"
        )
    except Exception:
        pass

    # Reset counters so the new session starts clean (mirrors compaction-save.py)
    for tracker_name, default in (
        ("compaction-tracker.json", '{"edit_count": 0}'),
        ("behavior-tracker.json", '{"reads_since_rag": 0, "tasks_since_evaluator": 0}'),
    ):
        try:
            (state_dir / tracker_name).write_text(default, encoding="utf-8")
        except Exception:
            pass

    # Report what was saved
    n_user = len((conversation or {}).get("user_messages", []))
    n_files = len((conversation or {}).get("files_touched", []))

    output = {
        "additionalContext": (
            f"[Clear Handoff] Context saved — "
            f"{n_user} user turns, {n_files} files touched. "
            f"Restore path: {handoff_path}"
        )
    }
    print(json.dumps(output))

    return 0  # SessionEnd cannot block termination


if __name__ == "__main__":
    sys.exit(main())
