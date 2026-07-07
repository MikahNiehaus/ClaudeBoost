"""
workspace_identity.py — Shared workspace identity resolution for ClaudeBoost.

Extracted from get-active-workspace.py, session-primer.py, workspace-primer.py,
compaction-save.py, workspace-status.py, rag-statusline.py, context-nudge.py,
and prompt-rules-injector.py to eliminate ~60 lines of duplication per consumer.

Public API:
    get_boost_home()                       -> Path
    normalize_cwd(path)                    -> str
    get_instance_id()                      -> str
    read_ws_instance(inst_path, cwd)       -> str
    write_ws_instance(state_dir, id, cwd, ws) -> None
    resolve_active_workspace(state_dir, cwd) -> str
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def get_boost_home() -> Path:
    """Return the ClaudeBoost home directory."""
    env = os.environ.get("CLAUDEBOOST_HOME", "")
    if env:
        return Path(env)
    return Path(__file__).resolve().parent.parent


def normalize_cwd(path: str) -> str:
    """Normalize a CWD string: forward slashes, no trailing slash."""
    return path.replace("\\", "/").rstrip("/")


def _find_claude_pid_windows() -> int | None:
    """Walk the Windows process tree to find the Claude/Node ancestor PID."""
    if sys.platform != "win32":
        return None
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
                    pid = entry.th32ProcessID
                    ppid = entry.th32ParentProcessID
                    exe = entry.szExeFile.decode("utf-8", errors="replace").lower()
                    process_map[pid] = (ppid, exe)
                    if not ctypes.windll.kernel32.Process32Next(snap, ctypes.byref(entry)):
                        break
        finally:
            ctypes.windll.kernel32.CloseHandle(snap)

        claude_exec = os.environ.get("CLAUDE_CODE_EXECPATH", "").replace("\\", "/").lower()
        target_exe = claude_exec.split("/")[-1] if claude_exec else "node.exe"

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


def get_instance_id() -> str:
    """Return a stable, per-Claude-instance identifier.

    Priority:
      1. CLAUDE_CODE_SESSION_ID env var (set by Claude Code)
      2. Windows process tree walk to find claude.exe ancestor PID
      3. CLAUDEBOOST_INSTANCE_ID env var (fallback)
      4. os.getppid() as last resort
    """
    session_id = os.environ.get("CLAUDE_CODE_SESSION_ID", "")
    if session_id:
        return f"session-{session_id}"

    node_pid = _find_claude_pid_windows()
    if node_pid:
        return f"node-{node_pid}"

    env_id = os.environ.get("CLAUDEBOOST_INSTANCE_ID", "")
    if env_id:
        return env_id

    return f"ppid-{os.getppid()}"


def read_ws_instance(inst_path: Path, cwd: str) -> str:
    """Extract workspace ID for cwd from a ws-instance file. Returns '' on miss."""
    try:
        data = json.loads(inst_path.read_text(encoding="utf-8"))
        cwd_norm = normalize_cwd(cwd).lower()

        if "workspace_id" not in data:
            # New format: {cwd_path: workspace_id, ...}
            ws = data.get(cwd)
            if ws is None:
                for key, val in data.items():
                    if isinstance(val, str) and normalize_cwd(key).lower() == cwd_norm:
                        ws = val
                        break
            return str(ws) if ws else ""

        # Old format: {"workspace_id": "...", "cwd": "..."}
        stored = normalize_cwd(data.get("cwd", ""))
        if stored.lower() == cwd_norm:
            return str(data.get("workspace_id", "") or "")
        return ""
    except Exception:
        return ""


def write_ws_instance(
    state_dir: Path, instance_id: str, cwd: str, workspace_id: str
) -> None:
    """Write or update a ws-instance file. Pass workspace_id='' to clear."""
    ws_dir = state_dir / "ws-instance"
    ws_dir.mkdir(parents=True, exist_ok=True)
    inst_path = ws_dir / f"{instance_id}.json"

    data: dict = {}
    try:
        raw = json.loads(inst_path.read_text(encoding="utf-8"))
        if "workspace_id" in raw:
            # Migrate old format to new
            old_cwd = normalize_cwd(raw.get("cwd", ""))
            old_ws = raw.get("workspace_id", "")
            if old_cwd and old_ws:
                data[old_cwd] = old_ws
        else:
            data = raw
    except Exception:
        pass

    cwd_norm = normalize_cwd(cwd)
    if workspace_id:
        data[cwd_norm] = workspace_id
    else:
        data.pop(cwd_norm, None)
        # Also remove any case-variant keys
        to_remove = [
            k for k in data
            if isinstance(data[k], str) and normalize_cwd(k).lower() == cwd_norm.lower()
        ]
        for k in to_remove:
            data.pop(k, None)

    inst_path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def resolve_active_workspace(state_dir: Path, cwd: str) -> str:
    """Resolve which workspace is active for this instance and CWD.

    Fallback chain:
      1. Per-instance ws-instance file for this process
      2. Scan all ws-instance files for this CWD (most recent wins)
      3. active-workspace.json (last resort, for fresh-session recovery)
      4. Return '' (no workspace found)
    """
    cwd_norm = normalize_cwd(cwd)

    # 1. This instance's file
    instance_id = get_instance_id()
    inst_path = state_dir / "ws-instance" / f"{instance_id}.json"
    ws = read_ws_instance(inst_path, cwd_norm)
    if ws:
        return ws

    # 2. Scan all instance files for this CWD
    inst_dir = state_dir / "ws-instance"
    candidates: list[tuple[float, str]] = []
    try:
        for f in inst_dir.iterdir():
            if f.suffix != ".json":
                continue
            found = read_ws_instance(f, cwd_norm)
            if found:
                candidates.append((f.stat().st_mtime, found))
    except Exception:
        pass
    if candidates:
        candidates.sort(reverse=True)
        return candidates[0][1]

    # 3. active-workspace.json (last resort for fresh sessions after /clear-safe)
    try:
        aw = json.loads((state_dir / "active-workspace.json").read_text(encoding="utf-8"))
        ws_id = aw.get("workspace", "")
        if ws_id:
            return ws_id
    except Exception:
        pass

    return ""
