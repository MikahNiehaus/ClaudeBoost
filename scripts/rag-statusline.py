#!/usr/bin/env python3
"""
rag-statusline.py — Claude Code status line indicator for RAG server health.

Runs every ~2s by Claude Code to update the bottom status bar.
Cross-platform: works on Windows, macOS, Linux.

Output examples (ANSI colored):
  > ClaudeBoost | RAG ●                  (server live, project indexed)
  > ClaudeBoost | RAG ○                  (server starting, model loading)
  > ClaudeBoost | RAG x                  (server up, model init failed, waiting will not fix it)
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
RED    = "\033[31;1m"
BLUE   = "\033[34;1m"
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
    """Return 'live', 'starting', 'failed', or 'down' from the heartbeat file.

    'failed' is separate from 'starting' on purpose. A heartbeat only carrying
    `model_loaded: false` cannot distinguish a model still loading from one that
    raised and will never load, so a permanently broken server displayed as
    "starting" indefinitely. A server that writes an explicit `status` gets
    reported honestly; one that does not keeps the old two state behaviour.
    """
    hb = _rag_index_dir() / ".heartbeat"
    if not hb.exists():
        return "down"
    try:
        raw = hb.read_text(encoding="utf-8").strip()
        explicit = ""
        try:
            data = json.loads(raw)
            ts = float(data.get("ts", 0))
            model_loaded = bool(data.get("model_loaded", True))
            explicit = str(data.get("status", "") or "")
        except (ValueError, KeyError):
            ts = float(raw)
            model_loaded = True
        age = time.time() - ts
        if age > 90:
            return "down"
        if explicit == "failed":
            return "failed"
        return "live" if model_loaded else "starting"
    except Exception:
        return "down"


from workspace_identity import get_instance_id, normalize_cwd, read_ws_instance


def _active_workspace() -> str | None:
    """Return the active workspace ID for this Claude instance.

    Uses only the per-instance file keyed by CLAUDE_CODE_SESSION_ID so each
    Claude window tracks its own workspace independently, and new instances
    start with no workspace set.
    """
    boost_home = Path(os.environ.get("CLAUDEBOOST_HOME", Path(__file__).resolve().parent.parent))
    instance_id = get_instance_id()
    cwd = normalize_cwd(os.getcwd())
    inst_path = boost_home / "state" / "ws-instance" / f"{instance_id}.json"
    ws = read_ws_instance(inst_path, cwd)
    return ws or None


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
    # Read stdin JSON — Claude Code passes context_window data on every status poll
    raw = sys.stdin.read() if not sys.stdin.isatty() else ""
    try:
        stdin_data = json.loads(raw) if raw else {}
    except Exception:
        stdin_data = {}
    ctx = stdin_data.get("context_window", {})
    used_pct = float(ctx.get("used_percentage", 0.0))

    status = _heartbeat_status()

    # Use short prefix so status bar doesn't clip on narrow terminals
    parts = [f"{GREEN}CB{RESET}"]

    if status == "live":
        parts.append(f"{DIM}|{RESET} {GREEN}RAG ●{RESET}")
    elif status == "starting":
        parts.append(f"{DIM}|{RESET} {YELLOW}RAG ○{RESET}")
    elif status == "failed":
        # Red and distinct from starting. The whole point is that waiting will
        # not fix this one, so it must not look like the yellow one that will.
        parts.append(f"{DIM}|{RESET} {RED}RAG x{RESET}")
    # "down" — no RAG segment shown

    if _mcp_registered("playwright"):
        parts.append(f"{DIM}|{RESET} {GREEN}PW ●{RESET}")

    if _mcp_registered("mcp-debugger"):
        parts.append(f"{DIM}|{RESET} {GREEN}DBG ●{RESET}")

    if _mcp_registered("chrome-devtools"):
        parts.append(f"{DIM}|{RESET} {GREEN}CDP ●{RESET}")

    if _mcp_registered("test-coverage"):
        parts.append(f"{DIM}|{RESET} {GREEN}COV ●{RESET}")

    ws = _active_workspace()
    if ws:
        parts.append(f"{DIM}|{RESET} {BLUE}WS {ws}{RESET}")
    else:
        parts.append(f"{DIM}| WS N/A{RESET}")

    # Low Token Mode indicator — only shown when enabled in state/low-token-mode.json
    boost_home = Path(os.environ.get("CLAUDEBOOST_HOME", "") or Path(__file__).resolve().parent.parent)
    try:
        lt_state = json.loads((boost_home / "state" / "low-token-mode.json").read_text(encoding="utf-8"))
    except Exception:
        lt_state = {}

    if lt_state.get("enabled", False):
        threshold = int(lt_state.get("threshold_pct", 70))
        if used_pct >= threshold + 10:
            lt_color = RED
        elif used_pct >= threshold:
            lt_color = YELLOW
        else:
            lt_color = GREEN
        parts.append(f"{DIM}|{RESET} {lt_color}LT ●{RESET}")

    print(" ".join(parts), end="", flush=True)


if __name__ == "__main__":
    main()
