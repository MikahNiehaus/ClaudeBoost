"""
ClaudeBoost compaction restore — SessionStart command hook.

After compaction or /clear, reads the saved handoff state and injects it
as additionalContext so Claude knows where it left off and what to do next.

Fires on:
- source="compact" — after auto-compact or /compact command
- source="clear"   — after /clear command (with age and cwd guards)
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

AGE_GUARD_SECONDS = 1800   # 30 minutes — reject stale clear handoffs


def _load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _load_handoff_latest(state_dir: Path) -> dict:
    path = state_dir / "handoff-latest.json"
    if not path.exists():
        return {}
    return _load_json(path)


def _load_compact_memo(state_dir: Path) -> dict:
    path = state_dir / "compaction-memo.json"
    if not path.exists():
        return {}
    data = _load_json(path)
    # Normalize to handoff-latest schema
    if "memo" in data and "workspace_memo" not in data:
        data["workspace_memo"] = data["memo"]
    return data


def _age_ok(data: dict, max_seconds: int = AGE_GUARD_SECONDS) -> bool:
    timestamp_str = data.get("timestamp", "")
    if not timestamp_str:
        return False
    try:
        ts = datetime.fromisoformat(timestamp_str)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        age = (datetime.now(timezone.utc) - ts).total_seconds()
        return age <= max_seconds
    except Exception:
        return False


def _cwd_ok(data: dict, session_cwd: str) -> bool:
    handoff_cwd = (data.get("cwd", "") or "").strip()
    session_cwd = (session_cwd or "").strip()
    if not handoff_cwd or not session_cwd:
        return True  # can't verify, allow
    return (
        handoff_cwd.replace("\\", "/").lower()
        == session_cwd.replace("\\", "/").lower()
    )


def _format_conversation(conversation: dict) -> str:
    """Inline formatting — avoids import dependency for the restore script."""
    if not conversation:
        return ""
    parts = []
    user_messages = conversation.get("user_messages", [])
    if user_messages:
        parts.append("## Recent User Messages")
        for i, msg in enumerate(user_messages, 1):
            display = msg[:500] + ("..." if len(msg) > 500 else "")
            parts.append(f"{i}. {display}")
    files_touched = conversation.get("files_touched", [])
    if files_touched:
        parts.append("\n## Files Touched")
        for f in files_touched:
            parts.append(f"- {f}")
    return "\n".join(parts)


def main() -> int:
    home = Path(os.environ.get("CLAUDEBOOST_HOME") or os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..")
    ))
    state_dir = home / "state"

    # Read hook input
    raw = sys.stdin.read() if not sys.stdin.isatty() else ""
    try:
        hook_input = json.loads(raw) if raw else {}
    except Exception:
        hook_input = {}

    source = hook_input.get("source", "")
    session_cwd = hook_input.get("cwd", "")

    if source == "compact":
        # Prefer unified handoff-latest.json; fall back to compaction-memo.json
        data = _load_handoff_latest(state_dir)
        if not data:
            data = _load_compact_memo(state_dir)
        if not data:
            return 0
        label = "compaction"

    elif source == "clear":
        data = _load_handoff_latest(state_dir)
        if not data:
            return 0
        if not _age_ok(data):
            return 0  # handoff is stale — don't inject stale context
        if not _cwd_ok(data, session_cwd):
            return 0  # different project — don't inject wrong context
        label = "clear transition"

    else:
        return 0  # startup or unknown source — no-op

    workspace_memo = data.get("workspace_memo", "") or data.get("memo", "")
    if not workspace_memo:
        return 0

    # Build conversation section if available
    conversation = data.get("conversation", {})
    conversation_section = _format_conversation(conversation)

    header = label.upper()
    context_parts = [
        f"POST-{header} CONTEXT RESTORATION",
        "=" * (len(header) + 27),
        "",
        f"You just went through a {label}. Below is your saved working state.",
        "",
        workspace_memo,
    ]

    if conversation_section:
        context_parts += ["", "## Conversation Highlights", "", conversation_section]

    context_parts += [
        "",
        "RESUME INSTRUCTIONS:",
        "- Read workspace context.md files above for full detail",
        "- Continue from the last documented next step",
        "- Keep workspace context.md files updated as you work",
        f"- If the user gave you a task before the {label}, pick it back up",
    ]

    context = "\n".join(context_parts)
    print(json.dumps({"additionalContext": context}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
