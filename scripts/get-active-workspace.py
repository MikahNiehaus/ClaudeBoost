"""
get-active-workspace.py — Print the active workspace ID for this Claude instance.

Used by skills to resolve the workspace per-instance (matching the blue statusline indicator)
rather than reading the shared project-workspaces.json directly.

Output: JSON with workspace_id, workspace_path, project_path
        or {"workspace_id": "", "workspace_path": "", "project_path": ""} if none active.

Usage:
  python get-active-workspace.py
  python get-active-workspace.py --id-only   # just print the workspace ID (or empty)
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def _get_home() -> Path:
    return Path(os.environ.get("CLAUDEBOOST_HOME") or Path(__file__).parent.parent)


def _find_claude_pid_windows() -> int | None:
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
                    pid  = entry.th32ProcessID
                    ppid = entry.th32ParentProcessID
                    exe  = entry.szExeFile.decode("utf-8", errors="replace").lower()
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


def _get_instance_id() -> str:
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


def _ws_from_inst_file(inst_path: Path, cwd: str) -> str:
    """Extract workspace ID for cwd from a ws-instance file. Returns "" on miss."""
    try:
        data = json.loads(inst_path.read_text(encoding="utf-8"))
        cwd_lower = cwd.lower()
        if "workspace_id" not in data:
            ws = data.get(cwd)
            if ws is None:
                for key, val in data.items():
                    if isinstance(val, str) and key.replace("\\", "/").rstrip("/").lower() == cwd_lower:
                        ws = val
                        break
            return str(ws) if ws else ""
        stored = data.get("cwd", "").replace("\\", "/").rstrip("/")
        if stored.lower() == cwd_lower:
            return str(data.get("workspace_id", "") or "")
        return ""
    except Exception:
        return ""


def resolve() -> dict:
    """Return workspace info for this Claude instance."""
    home = _get_home()
    state_dir = home / "state"
    workspace_id = ""

    cwd = os.getcwd().replace("\\", "/").rstrip("/")

    # 1. Per-instance file keyed by this process's Claude instance ID
    instance_id = _get_instance_id()
    inst_path = state_dir / "ws-instance" / f"{instance_id}.json"
    workspace_id = _ws_from_inst_file(inst_path, cwd)

    # 2. Fallback: scan all ws-instance files for this CWD, most recently modified wins
    if not workspace_id:
        inst_dir = state_dir / "ws-instance"
        candidates: list[tuple[float, str]] = []
        try:
            for f in inst_dir.iterdir():
                if f.suffix != ".json":
                    continue
                ws = _ws_from_inst_file(f, cwd)
                if ws:
                    candidates.append((f.stat().st_mtime, ws))
        except Exception:
            pass
        if candidates:
            candidates.sort(reverse=True)
            workspace_id = candidates[0][1]

    # 3. Fallback: most recently modified workspace in <cwd>/workspace/ that has context.md
    if not workspace_id:
        ws_dir = Path(cwd) / "workspace"
        try:
            best_mtime = 0.0
            for d in ws_dir.iterdir():
                if not d.is_dir() or d.name.startswith("."):
                    continue
                ctx = d / "context.md"
                if ctx.exists():
                    mtime = ctx.stat().st_mtime
                    if mtime > best_mtime:
                        best_mtime = mtime
                        workspace_id = d.name
        except Exception:
            pass

    if not workspace_id:
        return {"workspace_id": "", "workspace_path": "", "project_path": ""}

    # Resolve paths from registry
    workspace_path = ""
    project_path = ""
    try:
        reg = json.loads((state_dir / "workspaces.json").read_text(encoding="utf-8"))
        entry = reg.get(workspace_id, {})
        workspace_path = entry.get("workspace_path", "")
        project_path = entry.get("project_path", "")
    except Exception:
        pass

    # Last resort: check default location
    if not workspace_path:
        candidate = home / "workspace" / workspace_id
        if candidate.is_dir():
            workspace_path = str(candidate)

    return {
        "workspace_id": workspace_id,
        "workspace_path": workspace_path,
        "project_path": project_path,
        "instance_id": instance_id,
    }


def main() -> int:
    id_only = "--id-only" in sys.argv
    result = resolve()
    if id_only:
        print(result["workspace_id"])
    else:
        print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
