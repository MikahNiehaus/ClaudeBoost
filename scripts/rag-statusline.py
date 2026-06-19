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


def _find_claude_pid_windows() -> int | None:
    """Walk the Windows process tree to find the node.exe (Claude Code) ancestor.

    Uses ctypes/kernel32 — no external dependencies required.
    Returns the PID of the nearest node.exe ancestor, or None if not found.
    Each Claude Code instance is a separate node.exe process, so this PID is
    unique per Claude terminal window.
    """
    try:
        import ctypes
        import ctypes.wintypes

        TH32CS_SNAPPROCESS = 0x00000002

        class PROCESSENTRY32(ctypes.Structure):
            _fields_ = [
                ("dwSize",              ctypes.wintypes.DWORD),
                ("cntUsage",            ctypes.wintypes.DWORD),
                ("th32ProcessID",       ctypes.wintypes.DWORD),
                ("th32DefaultHeapID",   ctypes.POINTER(ctypes.c_ulong)),
                ("th32ModuleID",        ctypes.wintypes.DWORD),
                ("cntThreads",          ctypes.wintypes.DWORD),
                ("th32ParentProcessID", ctypes.wintypes.DWORD),
                ("pcPriClassBase",      ctypes.c_long),
                ("dwFlags",             ctypes.wintypes.DWORD),
                ("szExeFile",           ctypes.c_char * 260),
            ]

        snap = ctypes.windll.kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
        if snap == ctypes.wintypes.HANDLE(-1).value:
            return None

        process_map: dict[int, tuple[int, str]] = {}
        try:
            entry = PROCESSENTRY32()
            entry.dwSize = ctypes.sizeof(PROCESSENTRY32)
            if ctypes.windll.kernel32.Process32First(snap, ctypes.byref(entry)):
                while True:
                    pid  = entry.th32ProcessID
                    ppid = entry.th32ParentProcessID
                    exe  = entry.szExeFile.decode("utf-8", errors="replace").lower()
                    process_map[pid] = (ppid, exe)
                    if not ctypes.windll.kernel32.Process32Next(snap, ctypes.byref(entry)):
                        break
        finally:
            ctypes.windll.kernel32.CloseHandle(snap)

        # Determine which exe name to look for (from CLAUDE_CODE_EXECPATH or default "node")
        claude_exec = os.environ.get("CLAUDE_CODE_EXECPATH", "").replace("\\", "/").lower()
        target_exe = claude_exec.split("/")[-1] if claude_exec else "node.exe"

        # Walk from current process upward to find the target ancestor
        pid = os.getpid()
        seen: set[int] = set()
        for _ in range(20):
            if pid in seen or pid not in process_map:
                break
            seen.add(pid)
            ppid, _ = process_map[pid]
            if ppid not in process_map:
                break
            _, parent_exe = process_map[ppid]
            if target_exe in parent_exe or "node" in parent_exe:
                return ppid
            pid = ppid

        return None
    except Exception:
        return None


def _get_instance_id() -> str:
    """Return a stable, per-Claude-instance identifier.

    Priority:
      1. Windows ctypes process tree walk → node.exe (Claude Code) ancestor PID
         → unique per Claude window, zero setup required
      2. CLAUDEBOOST_INSTANCE_ID env var (shell init fallback for non-Windows)
      3. os.getppid() as last resort (may not be stable across skill invocations)
    """
    if sys.platform == "win32":
        node_pid = _find_claude_pid_windows()
        if node_pid:
            return f"node-{node_pid}"

    env_id = os.environ.get("CLAUDEBOOST_INSTANCE_ID", "")
    if env_id:
        return env_id

    return f"ppid-{os.getppid()}"


def _active_workspace() -> str | None:
    """Return the active workspace ID for this Claude instance.

    Priority:
      1. Per-instance file keyed by Claude process PID (automatic, zero setup)
      2. Project-level project-workspaces.json[cwd] (shared fallback)

    Returns the workspace ID string if one is set, or None if not set or cleared.
    """
    boost_home = Path(os.environ.get("CLAUDEBOOST_HOME", Path(__file__).resolve().parent.parent))
    instance_id = _get_instance_id()

    cwd = os.getcwd().replace("\\", "/").rstrip("/")

    # Per-instance check — CWD-keyed map (one file per Claude window, one entry per project)
    inst_path = boost_home / "state" / "ws-instance" / f"{instance_id}.json"
    try:
        data = json.loads(inst_path.read_text(encoding="utf-8"))
        if "workspace_id" not in data:
            # New format: {cwd: workspace_id}
            ws = data.get(cwd) or data.get(cwd.lower())
            if ws is None:
                cwd_lower = cwd.lower()
                for key, val in data.items():
                    if isinstance(val, str) and key.replace("\\", "/").rstrip("/").lower() == cwd_lower:
                        ws = val
                        break
        else:
            # Old format: only use if stored CWD matches
            stored = data.get("cwd", "").replace("\\", "/").rstrip("/")
            ws = data.get("workspace_id") if stored.lower() == cwd.lower() else None
        if ws:
            return str(ws)
    except Exception:
        pass

    # Project-level fallback: keyed by CWD
    pws_path = boost_home / "state" / "project-workspaces.json"
    try:
        data = json.loads(pws_path.read_text(encoding="utf-8"))
        if cwd in data:
            return data[cwd]
        cwd_lower = cwd.lower()
        for key, val in data.items():
            if key.replace("\\", "/").rstrip("/").lower() == cwd_lower:
                return val
    except Exception:
        pass
    return None


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

    ws = _active_workspace()
    if ws:
        parts.append(f"{DIM}|{RESET} {BLUE}WS {ws}{RESET}")
    else:
        parts.append(f"{DIM}| WS N/A{RESET}")

    print(" ".join(parts), end="", flush=True)


if __name__ == "__main__":
    main()
