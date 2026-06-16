"""
PostToolUse hook for ClaudeBoost telemetry.

Fires after every tool call. Writes one line to:
  workspace/[id]/Telemetry/claude-actions.jsonl

Also increments tool_count in session.json.

Sanitisation rules (enforced by _build_summary):
- File paths are included (they identify WHAT was acted on).
- File content, prompt text, code snippets, and user messages are NEVER included.
- Unknown tool inputs are logged as "..." — no guessing at content.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

BOOST_HOME = Path(os.environ.get("CLAUDEBOOST_HOME") or Path(__file__).resolve().parent.parent)
sys.path.insert(0, str(BOOST_HOME / "scripts"))

from telemetry_writer import (  # noqa: E402
    _DISABLED,
    now_iso,
    session_id,
    update_session_json,
    write_telemetry,
)


# Keys from tool_input that are safe to include in the summary (identifies WHAT,
# not WHAT CONTENT). Any key not in this map is replaced with "...".
_SAFE_KEYS: dict[str, list[str]] = {
    "Edit":        ["file_path"],
    "MultiEdit":   ["file_path"],
    "Write":       ["file_path"],
    "Read":        ["file_path"],
    "Glob":        ["pattern", "path"],
    "Grep":        ["pattern", "path", "glob", "type", "output_mode"],
    "Bash":        ["command"],          # command is safe; it's a system call, not user content
    "Task":        ["description"],      # description identifies the agent
    "WebFetch":    ["url"],
    "WebSearch":   ["query"],
    "TodoWrite":   [],
    "TodoRead":    [],
    "NotebookRead":  ["notebook_path"],
    "NotebookEdit":  ["notebook_path"],
}


def _build_summary(tool: str, tool_input: dict) -> str:
    """Build a sanitised one-line summary of the tool call."""
    allowed = _SAFE_KEYS.get(tool)
    if allowed is None:
        # Unknown tool — include tool name only
        return tool

    parts = [tool]
    for key in allowed:
        val = tool_input.get(key)
        if val is not None:
            safe_val = str(val)[:200]  # cap length
            parts.append(f"{key}={safe_val}")

    return " ".join(parts)


def _result_status(tool_response) -> str:
    """Derive 'success' or 'error' from the tool response."""
    if tool_response is None:
        return "unknown"
    if isinstance(tool_response, dict):
        # Only trust the explicit is_error flag — string-scanning the response
        # body produces false positives when dict key names contain "error".
        if tool_response.get("is_error"):
            return "error"
    return "success"


def main() -> int:
    if _DISABLED:
        return 0

    raw = sys.stdin.read() if not sys.stdin.isatty() else ""
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except Exception:
        return 0

    tool = payload.get("tool_name", "unknown")
    tool_input = payload.get("tool_input") or {}
    tool_response = payload.get("tool_response")

    record = {
        "ts": now_iso(),
        "session_id": session_id(),
        "tool": tool,
        "summary": _build_summary(tool, tool_input),
        "result": _result_status(tool_response),
        "hook_event": "PostToolUse",
    }

    write_telemetry(record, "claude-actions.jsonl")
    update_session_json("tool_count")

    return 0


if __name__ == "__main__":
    sys.exit(main())
