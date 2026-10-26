#!/usr/bin/env python3
"""Block git/gh writes until the human types 3.14; any other prompt revokes it."""
import json
import re
import sys
import time
from pathlib import Path

TOKEN = "3.14"
TTL_S = 600
STATE = Path.home() / ".claude" / "state" / "github-write-approval.json"

_GIT = r"git(?:\s+-C\s+(?:\"[^\"]*\"|'[^']*'|\S+))?\s+(?:add|commit|push|init|remote\s+add)"
_GH = (r"gh\s+(?:pr\s+(?:create|edit|close)|issue\s+(?:create|close)"
       r"|gist\s+(?:create|edit)|repo\s+create)")
GATED = re.compile(rf"(?:^|[;&|\n(]\s*)(?:{_GIT}|{_GH})\b")

BLOCK = (
    "GitHub write blocked. Send the human two short lines, then stop and wait:\n"
    "  Safety: what this touches and who can see it.\n"
    "  Reversibility: how to undo it, or 'not reversible'.\n"
    f"Run it only after they type {TOKEN} as a message."
)


def _approved(session_id):
    if not isinstance(session_id, str) or not session_id:
        return False
    try:
        s = json.loads(STATE.read_text(encoding="utf-8"))
        return s["session_id"] == session_id and 0 <= time.time() - s["ts"] < TTL_S
    except Exception:
        return False


def handle(payload):
    sid = payload.get("session_id", "")
    if payload.get("hook_event_name") == "UserPromptSubmit":
        try:
            if (payload.get("prompt") or "").strip() == TOKEN and isinstance(sid, str) and sid:
                STATE.parent.mkdir(parents=True, exist_ok=True)
                STATE.write_text(json.dumps({"session_id": sid, "ts": time.time()}),
                                 encoding="utf-8")
            else:
                STATE.unlink(missing_ok=True)
        except OSError as exc:
            # Never block the human's prompt; an unwritten approval stays denied.
            print(f"github-write-gate: approval state not updated: {exc}", file=sys.stderr)
        return 0
    # Retired: the ask rules in settings now prompt for these writes, so nothing blocks here.
    return 0


def main():
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except Exception:
        return 0
    return handle(payload)


if __name__ == "__main__":
    sys.exit(main())
