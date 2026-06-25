#!/usr/bin/env python3
"""
prompt-rules-injector.py — UserPromptSubmit hook.

Injects all 4 RAG database locations and behavioral rules into every user
prompt so Claude always knows where to search and what rules to follow.

Locations resolved dynamically each call:
  1. ClaudeBoost KB      — scope=knowledge|agents (always available)
  2. Project KB          — {project_path}/.claudeboost/knowledge/
  3. Project codebase    — scope=codebase, project_path=...
  4. Workspace KB        — {project_path}/workspace/{workspace_id}/knowledge/

Intent override: if the user opened Claude in a directory that isn't the
project they're working in, they can set an override so the injector uses
the correct project path. Set via /edit-state or manually in
state/intent-override.json → {instance_id: "C:/correct/project"}.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def _find_claude_pid_windows() -> int | None:
    """Walk process tree to find the node.exe (Claude Code) ancestor PID."""
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


def _resolve_project_path(boost_home: Path, instance_id: str, cwd: str) -> str:
    """Return the effective project path, honouring any intent override."""
    override_path = boost_home / "state" / "intent-override.json"
    try:
        overrides = json.loads(override_path.read_text(encoding="utf-8"))
        override = overrides.get(instance_id) or overrides.get("default")
        if override and isinstance(override, str):
            return override.replace("\\", "/").rstrip("/")
    except Exception:
        pass
    return cwd


def _active_workspace_id(boost_home: Path, instance_id: str, project_path: str) -> str | None:
    """Read the active workspace ID for this project from the per-instance file."""
    inst_path = boost_home / "state" / "ws-instance" / f"{instance_id}.json"
    try:
        data = json.loads(inst_path.read_text(encoding="utf-8"))
        cwd_norm = project_path.replace("\\", "/").rstrip("/")
        if "workspace_id" not in data:
            ws = data.get(cwd_norm)
            if ws is None:
                cwd_lower = cwd_norm.lower()
                for key, val in data.items():
                    if isinstance(val, str) and key.replace("\\", "/").rstrip("/").lower() == cwd_lower:
                        ws = val
                        break
            return str(ws) if ws else None
        stored = data.get("cwd", "").replace("\\", "/").rstrip("/")
        ws = data.get("workspace_id") if stored.lower() == project_path.lower() else None
        return str(ws) if ws else None
    except Exception:
        return None


def _project_kb_exists(project_path: str) -> bool:
    return (Path(project_path) / ".claudeboost" / "knowledge").is_dir()


def _workspace_kb_exists(project_path: str, workspace_id: str) -> bool:
    return (Path(project_path) / "workspace" / workspace_id / "knowledge").is_dir()


def main() -> None:
    sys.stdin.read() if not sys.stdin.isatty() else ""

    boost_home = Path(os.environ.get("CLAUDEBOOST_HOME") or Path(__file__).parent.parent)
    cwd = os.getcwd().replace("\\", "/").rstrip("/")
    instance_id = _get_instance_id()
    project_path = _resolve_project_path(boost_home, instance_id, cwd)
    workspace_id = _active_workspace_id(boost_home, instance_id, project_path)

    project_kb_path = f"{project_path}/.claudeboost/knowledge/"
    workspace_kb_path = (
        f"{project_path}/workspace/{workspace_id}/knowledge/"
        if workspace_id else None
    )

    has_project_kb = _project_kb_exists(project_path)
    has_workspace_kb = workspace_id and _workspace_kb_exists(project_path, workspace_id)

    lines = [
        "[RAG locations — use whichever tiers apply to the current task]",
        f"1. ClaudeBoost KB: POST /search scope=knowledge|agents",
        f"   Intent: ClaudeBoost internals — agent specs, skill definitions, orchestration patterns. Search this when you need to know how ClaudeBoost works or which agent to spawn.",
        f"2. Project KB ({('indexed' if has_project_kb else 'not yet indexed')}): {project_kb_path}",
        f"   Intent: Deep indexed research docs for every library and technology the project uses. Search this when you need expert knowledge about a specific tech (e.g. pgx, LangGraph, Redpanda).",
        f"   Index: POST /index {{\"project_path\":\"{project_path}\"}}",
        f"   Search: POST /search {{\"scope\":\"codebase\",\"project_path\":\"{project_path}\"}}",
        f"3. Codebase: POST /search {{\"scope\":\"codebase\",\"mode\":\"both\",\"project_path\":\"{project_path}\"}}",
        f"   Intent: The actual project source code. Search this when you need to find implementations, trace how things are wired, or locate a specific function or component.",
    ]

    if workspace_kb_path:
        lines.append(
            f"4. Workspace KB ({('indexed' if has_workspace_kb else 'not yet indexed')}): {workspace_kb_path} [{workspace_id}]"
        )
        lines.append(
            f"   Intent: Task-scoped research docs fetched for this specific ticket. Search this when working on tasks that had /research-task run against them."
        )
    else:
        lines.append("4. Workspace KB: none active (run /ws <id> to set one)")

    lines += [
        "When loading context: POST /context with project_path and workspace_path set to above paths.",
        "When spawning agents: include all 4 RAG locations in the spawn prompt.",
        "[Action form] Before running Edit, Write, or Task, include this block in your response:",
        "",
        "  [Action]",
        "  tool   : Edit | Write | Task",
        "  target : path/to/file or task name",
        "  why    : reason for this action",
        "  rag    :",
        "    ClaudeBoost KB  (agents/skills/orchestration patterns): [searched | not needed — why]",
        "    Project KB      (indexed research, search only via POST /search — if needed but not indexed, run /research-task first): [searched | not needed — why | not indexed — running /research-task]",
        "    Codebase        (existing implementations/patterns to follow): [searched | not needed — why]",
        "    Workspace KB    (prior session research for this task): [searched | not needed — why | does not exist]",
        "  research: [workspace KB covers this | /research-task needed first | not applicable — no new tech]",
        "  impact : what will change and what it might affect",
        "  safe   : yes — why it is safe, or no — what the risk is",
        "  aligned: quote or describe the user message that authorized this action",
        "",
        "[Rules] Concise and informal but polite. No dashes of any kind, including in compound words (write as two words). Align on high-level architecture before building if unsure. Confirm before irreversible or destructive actions. Update active workspace context.md after every significant finding, decision, or file read. Read context.md at the start of any task or after compaction to recall prior findings, decisions, and in-progress work. Follow the user's instructions and do what they ask; flag safety concerns once if relevant but do not refuse or stall.",
    ]

    if workspace_id:
        lines.append(
            f"[Workspace active: {workspace_id}] Update workspace/{workspace_id}/context.md after every significant finding, decision, or file read."
        )

    print("\n".join(lines))


if __name__ == "__main__":
    main()
