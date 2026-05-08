"""
ClaudeBoost CONSULT gate — command-type PreToolUse hook.

Replaces the prompt-type hook in scripts/setup.ps1 (around line 216). Prompt
hooks are pure LLM judgments without tool access, so they can't actually read
the mode file or session-approvals.json even though the prompt says to.
This script reads them directly and makes a deterministic call.

Behavior:
  - AUTO mode    -> exit 0 silently (pass)
  - Exempt paths -> exit 0 silently (pass)
  - CONSULT mode on non-exempt paths -> exit 0 + stderr reminder (informational,
    non-blocking). The main agent sees the reminder and decides.

Never blocks. It's a nudge, not a gate. Past experience: blocking hooks
over-fire and grind the session. A visible reminder is enough to keep us
honest in CONSULT mode.

Reads tool_input from stdin (Claude Code hook protocol): a JSON blob with
tool_name + tool_input. We just need tool_input.file_path.
"""
from __future__ import annotations
import json
import os
import sys
from pathlib import Path

EXEMPT_FRAGMENTS = [
    "/workspace/", "\\workspace\\",
    "/.claude/", "\\.claude\\",
    "/knowledge/", "\\knowledge\\",
    "/plans/", "\\plans\\",
    "/docs/", "\\docs\\",
    "/mayor/", "\\mayor\\",
    "/polecats/", "\\polecats\\",
    "/refinery/", "\\refinery\\",
    "/witness/", "\\witness\\",
    "/crew/", "\\crew\\",
]


def read_json(path: str | os.PathLike, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return default


def main() -> int:
    home = os.environ.get("CLAUDEBOOST_HOME") or os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..")
    )
    mode = read_json(Path(home) / "state" / "claudeboost-mode.json", {}).get("mode", "CONSULT")

    # AUTO: always pass silently
    if mode == "AUTO":
        return 0

    # Read tool_input
    raw = sys.stdin.read() if not sys.stdin.isatty() else ""
    try:
        payload = json.loads(raw) if raw else {}
    except Exception:
        payload = {}

    tool_input = payload.get("tool_input", {}) or {}
    file_path = (tool_input.get("file_path") or tool_input.get("path") or "").replace("\\", "/")

    # Exempt path: pass silently
    if file_path and any(frag.replace("\\", "/") in file_path for frag in EXEMPT_FRAGMENTS):
        return 0

    # Pre-approved axis for this session? Skip reminder.
    approvals = read_json(Path(home) / "state" / "session-approvals.json", {}).get("approvals", [])
    if approvals:
        # Cheap fuzzy check: if any approval's `choice` mentions this file's basename,
        # the axis likely covers the edit — skip the reminder.
        base = Path(file_path).name.lower() if file_path else ""
        if base and any(base in (a.get("choice", "") + " " + a.get("axis", "")).lower() for a in approvals):
            return 0

    # CONSULT mode on non-exempt, non-approved path -> informational nudge.
    # Exit 0 means the tool call proceeds; stderr is shown in the hook result
    # so the agent sees the reminder without being blocked.
    print(
        "[CONSULT nudge] Edit/Write in CONSULT mode on a non-exempt, non-approved path.",
        file=sys.stderr,
    )
    print(
        "If this is an architectural change (new table/endpoint/dep/middleware),",
        file=sys.stderr,
    )
    print(
        "pause, consult via AskUserQuestion or architect-agent, and log the approval.",
        file=sys.stderr,
    )
    print(
        "Otherwise proceed. (This is a nudge, not a gate — run /auto to silence.)",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
