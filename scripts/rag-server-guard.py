"""DEPRECATED — no longer used.

Previously a PreToolUse guard for mcp__rag-server__ MCP tools. The RAG server
no longer uses MCP. All RAG access goes through the HTTP API on port 8612.

This file is kept for reference but no hook references it.
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
