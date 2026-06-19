"""
ClaudeBoost workspace primer - SessionStart command hook.

When an active workspace is set in state/active-workspace.json, injects a
RAG tier briefing into the session: workspace path, project path, full tier
breakdown with token budgets, and Tier 3c status (EXISTS vs NOT BUILT).

This gives Claude a clear picture of what context is available before it
calls POST /context or spawns agents. When Tier 3c is missing, it nudges
to run /research-task before delegating to implementation agents.

Silent when no workspace is active.
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
    node_pid = _find_claude_pid_windows()
    if node_pid:
        return f"node-{node_pid}"
    env_id = os.environ.get("CLAUDEBOOST_INSTANCE_ID", "")
    if env_id:
        return env_id
    return f"ppid-{os.getppid()}"


def _detect_stack(project_path: str) -> str:
    """Return a human-readable stack label by checking indicator files."""
    p = Path(project_path)
    if not p.is_dir():
        return ""
    stacks = []
    if (p / "go.mod").exists():
        stacks.append("Go")
    # Check for .csproj one level deep (avoids slow recursive glob on large repos)
    if any(p.glob("*.csproj")) or any((p / d).glob("*.csproj") for d in ("src", "app") if (p / d).is_dir()):
        stacks.append("C# / ASP.NET Core")
    if (p / "tsconfig.json").exists():
        stacks.append("TypeScript")
    elif (p / "package.json").exists():
        stacks.append("JavaScript / Node")
    if (p / "pyproject.toml").exists() or (p / "requirements.txt").exists():
        stacks.append("Python")
    if (p / "pom.xml").exists():
        stacks.append("Java")
    return " · ".join(stacks)


def _tier3c_status(workspace_path: str) -> tuple[bool, int]:
    """Check whether the Tier 3c research index exists and how many files it has."""
    research_dir = Path(workspace_path) / ".rag-index" / "research"
    if not research_dir.exists():
        return False, 0
    data_files = [f for f in research_dir.rglob("*") if f.is_file()]
    return True, len(data_files)


def main() -> int:
    home = _get_home()

    # Resolve active workspace for this Claude instance
    cwd_norm = os.getcwd().replace("\\", "/").rstrip("/")
    workspace_id = ""
    workspace_path = ""
    project_path = ""

    # 1. Per-instance file — CWD-keyed map (unique per Claude window, survives compaction)
    instance_id = _get_instance_id()
    try:
        inst_path = home / "state" / "ws-instance" / f"{instance_id}.json"
        data = json.loads(inst_path.read_text(encoding="utf-8"))
        if "workspace_id" not in data:
            # New format: {cwd: workspace_id}
            ws = data.get(cwd_norm)
            if ws is None:
                cwd_lower = cwd_norm.lower()
                for key, val in data.items():
                    if isinstance(val, str) and key.replace("\\", "/").rstrip("/").lower() == cwd_lower:
                        ws = val
                        break
        else:
            # Old format: only use if stored CWD matches
            stored = data.get("cwd", "").replace("\\", "/").rstrip("/")
            ws = data.get("workspace_id") if stored.lower() == cwd_norm.lower() else None
        if ws and isinstance(ws, str):
            workspace_id = ws
    except Exception:
        pass

    # 2. Project-level fallback (shared within project, keyed by CWD)
    if not workspace_id:
        try:
            pws = json.loads((home / "state" / "project-workspaces.json").read_text(encoding="utf-8"))
            ws_id = pws.get(cwd_norm)
            if ws_id is None:
                cwd_lower = cwd_norm.lower()
                for key, val in pws.items():
                    if key.replace("\\", "/").rstrip("/").lower() == cwd_lower:
                        ws_id = val
                        break
            if ws_id and isinstance(ws_id, str):
                workspace_id = ws_id
        except Exception:
            pass

    if not workspace_id:
        return 0

    # Fill in missing paths from the workspace registry
    if not workspace_path or not project_path:
        reg_path = home / "state" / "workspaces.json"
        try:
            reg = json.loads(reg_path.read_text(encoding="utf-8"))
            entry = reg.get(workspace_id, {})
            if not workspace_path:
                workspace_path = entry.get("workspace_path", "")
            if not project_path:
                project_path = entry.get("project_path", "")
        except Exception:
            pass

    # Last resort: default ClaudeBoost workspace location
    if not workspace_path:
        candidate = home / "workspace" / workspace_id
        if candidate.is_dir():
            workspace_path = str(candidate)

    if not workspace_path:
        return 0

    stack = _detect_stack(project_path) if project_path else ""
    tier3_suffix = f" (stack: {stack})" if stack else ""

    t3c_exists, t3c_files = _tier3c_status(workspace_path)
    if t3c_exists:
        t3c_line = f"  Tier 3c  Task research           ~400 tok  [EXISTS - {t3c_files} index files]\n"
        t3c_action = "Tier 3c is ready. Task research auto-loads when workspace_path is in /context.\n"
    else:
        t3c_line = f"  Tier 3c  Task research           ~400 tok  [NOT BUILT - run /research-task {workspace_id}]\n"
        t3c_action = f"Tier 3c is NOT BUILT. Run /research-task {workspace_id} before delegating to implementation agents.\n"

    project_info = ""
    if project_path:
        project_info = f"\nProject:          {project_path}" + (f" ({stack})" if stack else "")

    context_body = (
        '  {\n'
        '    "agent": "...",\n'
        '    "task_description": "...",\n'
    )
    if project_path:
        context_body += f'    "project_path": "{project_path}",\n'
    context_body += f'    "workspace_path": "{workspace_path}"\n'
    context_body += '  }'

    briefing = (
        f"ACTIVE WORKSPACE: {workspace_id}\n"
        f"Workspace path:   {workspace_path}"
        f"{project_info}\n"
        "\n"
        "RAG CONTEXT TIERS - include workspace_path in every /context call:\n"
        "\n"
        "  POST http://127.0.0.1:8612/context\n"
        + context_body + "\n"
        "\n"
        "Token budget (~6000 tokens total):\n"
        "  Tier 0   Agent definition        ~200 tok   (always included)\n"
        "  Tier 1   Guardrails              ~800 tok   (always included)\n"
        "  Tier 2   Declared knowledge      ~400 tok   (agent-specific)\n"
        f"  Tier 3   General best practices ~1200 tok  (semantic search{tier3_suffix})\n"
        + t3c_line
        + "  Tier 4   Project codebase        ~3000 tok  (requires project_path and indexed project)\n"
        "\n"
        + t3c_action
    )

    print(json.dumps({"additionalContext": briefing}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
