#!/usr/bin/env python3
"""
rag-statusline.py — Claude Code status line indicator for RAG server health.

Runs every ~2s by Claude Code to update the bottom status bar.
Cross-platform: works on Windows, macOS, Linux.

Output examples (ANSI colored):
  > ClaudeBoost | RAG ●                  (server live, project indexed)
  > ClaudeBoost | RAG ○                  (server starting, model loading)
  > ClaudeBoost                          (server down)
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

# Force UTF-8 output so Unicode status chars render on Windows terminals
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

GREEN  = "\033[32;1m"
YELLOW = "\033[33;1m"
DIM    = "\033[2m"
RESET  = "\033[0m"

RAG_HTTP_PORT = 8612  # SHA256("ClaudeBoost-rag-server") % 900 + 8100


def _rag_index_dir() -> Path:
    local_appdata = os.environ.get("LOCALAPPDATA", "")
    rag_index_dir = os.environ.get("RAG_INDEX_DIR", "")
    if rag_index_dir:
        return Path(rag_index_dir)
    if local_appdata:
        return Path(local_appdata) / "rag-server-index"
    # macOS / Linux: use the same path rag-server-start.py writes to
    return Path(__file__).resolve().parent.parent / "mcp-rag-server" / ".rag-index"


def _heartbeat_status() -> str:
    """Return 'live', 'starting', or 'down' based on heartbeat file."""
    hb = _rag_index_dir() / ".heartbeat"
    if not hb.exists():
        return "down"
    try:
        raw = hb.read_text(encoding="utf-8").strip()
        try:
            data = json.loads(raw)
            ts = float(data.get("ts", 0))
            model_loaded = bool(data.get("model_loaded", True))
        except (ValueError, KeyError):
            ts = float(raw)
            model_loaded = True
        age = time.time() - ts
        if age > 90:
            return "down"
        return "live" if model_loaded else "starting"
    except Exception:
        return "down"



def _mcp_registered(name: str) -> bool:
    """Check if an MCP server is registered in ~/.claude.json."""
    p = Path.home() / ".claude.json"
    if not p.exists():
        return False
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return name in data.get("mcpServers", {})
    except Exception:
        return False


def main() -> None:
    status = _heartbeat_status()

    # Use short prefix so status bar doesn't clip on narrow terminals
    parts = [f"{GREEN}CB{RESET}"]

    if status == "live":
        parts.append(f"{DIM}|{RESET} {GREEN}RAG ●{RESET}")
    elif status == "starting":
        parts.append(f"{DIM}|{RESET} {YELLOW}RAG ○{RESET}")
    # "down" — no RAG segment shown

    if _mcp_registered("playwright"):
        parts.append(f"{DIM}|{RESET} {GREEN}PW ●{RESET}")

    if _mcp_registered("mcp-debugger"):
        parts.append(f"{DIM}|{RESET} {GREEN}DBG ●{RESET}")

    print(" ".join(parts), end="", flush=True)


if __name__ == "__main__":
    main()
