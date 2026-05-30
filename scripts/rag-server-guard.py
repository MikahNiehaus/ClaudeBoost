"""PreToolUse guard for mcp__rag-server__ tools.

Reads the heartbeat file written by the RAG server every 30 seconds.
- If heartbeat is MISSING: server is running old code without heartbeat support — allow through.
- If heartbeat is FRESH (<90s): server is alive — allow.
- If heartbeat is STALE (>90s): server was alive but died — block.

This way enforcement only activates once the new server code has written
at least one heartbeat. Old/fresh installs are not broken.
"""
import json
import os
import sys
import time
from pathlib import Path

HEARTBEAT_MAX_AGE_SECONDS = 90

local_appdata = os.environ.get("LOCALAPPDATA", "")
heartbeat = Path(local_appdata) / "rag-server-index" / ".heartbeat"

# No heartbeat file = old server code running, no enforcement yet — allow through.
if not heartbeat.exists():
    sys.exit(0)

try:
    raw = heartbeat.read_text(encoding="utf-8").strip()
    try:
        data = json.loads(raw)
        ts = float(data.get("ts", 0))
    except (ValueError, KeyError):
        ts = float(raw)
    age = time.time() - ts
except Exception:
    sys.exit(0)  # Can't read it? Allow through rather than false-block.

if age > HEARTBEAT_MAX_AGE_SECONDS:
    print(json.dumps({
        "continue": False,
        "stopReason": (
            f"RAG server heartbeat is {int(age)}s old (max {HEARTBEAT_MAX_AGE_SECONDS}s) — "
            "run /mcp to reconnect, then retry."
        ),
    }))
    sys.exit(0)
