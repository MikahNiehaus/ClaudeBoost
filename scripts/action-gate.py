"""
action-gate.py — PreToolUse hook.
Fires on: Edit | Write | MultiEdit

Requires Claude to include an [Action] block in the response before these
tools execute. On the first call the tool is blocked and a fill-in form is
shown. On the retry (same tool + target within 90 seconds) the tool passes
through — Claude added the form in the meantime.

Required block format (must appear in response before the retry fires):

  [Action]
  tool   : Edit
  target : path/to/file.py
  why    : [reason for this action]
  rag    : [what was searched first, or n/a]
  impact : [what will change and what it might affect]
  safe   : [yes — why it is safe, or no — what the risk is]

Exit codes:
  0 = pass through
  2 = block — show form, save pending state
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path


RETRY_WINDOW_S = 90

EXEMPT_FRAGMENTS = [
    "/workspace/", "\\workspace\\",
    "/knowledge/", "\\knowledge\\",
    "/plans/", "\\plans\\",
    "/docs/", "\\docs\\",
]


def _read_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _get_target(tool_name: str, tool_input: dict) -> str:
    if tool_name in ("Edit", "Write", "MultiEdit"):
        return tool_input.get("file_path", "")
    if tool_name == "Bash":
        cmd = tool_input.get("command", "")
        return cmd[:80].strip()
    if tool_name == "Task":
        desc = tool_input.get("description", "")
        return desc[:80].strip()
    return ""


def _is_exempt(target: str) -> bool:
    t = target.replace("\\", "/").lower()
    for frag in EXEMPT_FRAGMENTS:
        if frag.replace("\\", "/").lower() in t:
            return True
    return False


def main() -> int:
    raw = sys.stdin.read() if not sys.stdin.isatty() else ""
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except Exception:
        return 0

    tool_name = payload.get("tool_name", "")
    tool_input = payload.get("tool_input") or {}

    home = Path(
        os.environ.get("CLAUDEBOOST_HOME") or
        Path(__file__).resolve().parent.parent
    )

    # Skip during audit runs
    audit_flag = home / "state" / "audit-in-progress.json"
    if audit_flag.exists():
        try:
            if _read_json(audit_flag, {}).get("active"):
                return 0
        except Exception:
            return 0

    # Skip in AUTO mode
    mode = _read_json(home / "state" / "claudeboost-mode.json", {}).get("mode", "CONSULT")
    if mode == "AUTO":
        return 0

    target = _get_target(tool_name, tool_input)
    if not target:
        return 0

    if _is_exempt(target):
        return 0

    state_path = home / "state" / "action-gate.json"
    state_key = f"{tool_name}::{target}"
    now = time.time()

    state = _read_json(state_path, {})

    last = state.get(state_key, {})
    if isinstance(last, dict) and (now - last.get("ts", 0)) < RETRY_WINDOW_S:
        # Retry within window — Claude filled the form. Pass through and clear.
        del state[state_key]
        try:
            state_path.parent.mkdir(parents=True, exist_ok=True)
            state_path.write_text(json.dumps(state), encoding="utf-8")
        except Exception:
            pass
        return 0

    # First call — block and show the form
    state[state_key] = {"ts": now}
    try:
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps(state), encoding="utf-8")
    except Exception:
        pass

    short_target = target if len(target) <= 70 else target[:67] + "..."

    form = (
        f"ACTION FORM REQUIRED\n\n"
        f"Before running {tool_name}, add this block to your response:\n\n"
        f"  [Action]\n"
        f"  tool   : {tool_name}\n"
        f"  target : {short_target}\n"
        f"  why    : [reason for this action]\n"
        f"  rag    :\n"
        f"    ClaudeBoost KB  (agents/skills/orchestration patterns): [searched | not needed — why]\n"
        f"    Project KB      (indexed research, search only via POST /search): [searched | not needed — why | not indexed]\n"
        f"    Codebase        (existing implementations/patterns to follow): [searched | not needed — why]\n"
        f"    Workspace KB    (prior session research for this task): [searched | not needed — why | does not exist]\n"
        f"  research: [workspace KB covers this | research gate handles it on edit | not applicable — no new tech]\n"
        f"  impact : [what will change and what it might affect]\n"
        f"  safe   : [yes — why it is safe, or no — what the risk is]\n"
        f"  aligned: [quote or describe the user message that authorized this — never assume consent]\n\n"
        f"Fill in every field then retry the tool call.\n"
        f"This applies to every Edit, Write, and MultiEdit."
    )

    print(json.dumps({"decision": "block", "reason": form}))
    return 2


if __name__ == "__main__":
    sys.exit(main())
