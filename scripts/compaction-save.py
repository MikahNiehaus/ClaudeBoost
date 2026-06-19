"""
ClaudeBoost compaction save — PreCompact command hook.

Reads workspace context files and active state, builds a structured
compaction memo, and saves it to state/compaction-memo.json. The memo
is restored after compaction by compaction-restore.py so Claude knows
where it left off.

Archives previous memos to state/compaction-history/ for debugging.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


def read_json(path: str | os.PathLike, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return default if default is not None else {}


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


def _resolve_active_workspace(state_dir: Path, hook_cwd: str = "") -> str:
    """Return the active workspace ID for this Claude instance.

    Priority:
    1. Per-instance file keyed by Claude process PID (unique per window)
    2. project-workspaces.json keyed by CWD
    3. Legacy active-workspace.json (global fallback)
    """
    cwd = (hook_cwd or os.getcwd()).replace("\\", "/").rstrip("/")

    instance_id = _get_instance_id()
    inst_path = state_dir / "ws-instance" / f"{instance_id}.json"
    try:
        data = json.loads(inst_path.read_text(encoding="utf-8"))
        if "workspace_id" not in data:
            # New format: {cwd: workspace_id}
            ws = data.get(cwd)
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
    try:
        pws = json.loads((state_dir / "project-workspaces.json").read_text(encoding="utf-8"))
        ws = pws.get(cwd)
        if ws is None:
            cwd_lower = cwd.lower()
            for key, val in pws.items():
                if key.replace("\\", "/").rstrip("/").lower() == cwd_lower:
                    ws = val
                    break
        if ws and isinstance(ws, str):
            return ws
    except Exception:
        pass

    return read_json(state_dir / "active-workspace.json").get("workspace", "")


def extract_summary(content: str, char_budget: int = 2000) -> str:
    """
    Split content on ## headings. Include sections up to char_budget,
    skipping known large/low-signal sections. Priority sections go first.
    """
    import re

    SKIP_SECTIONS = {
        "research sources", "cloned repos", "agent contributions",
        "improvement rounds", "work done",
    }
    PRIORITY_KEYWORDS = [
        "goal", "status", "next step", "decision", "blocked", "blocker",
        "remaining", "constraint", "requirement", "user said", "user preference",
        "progress", "completion criteria", "gotcha", "implement",
    ]

    # Split on any ## or ### heading
    parts = re.split(r'\n(?=#{1,3} )', content.strip())
    preamble = parts[0][:500]  # first 500 chars always (title, task id, status)

    priority, other = [], []
    for section in parts[1:]:
        heading = section.split('\n')[0].lower()
        if any(skip in heading for skip in SKIP_SECTIONS):
            continue
        bucket = priority if any(kw in heading for kw in PRIORITY_KEYWORDS) else other
        bucket.append(section)

    result = [preamble]
    used = len(preamble)
    for section in priority + other:
        chunk = section[:400]  # 400 chars per section max
        if used + len(chunk) > char_budget:
            break
        result.append(chunk)
        used += len(chunk)

    return "\n\n".join(result)


def main() -> int:
    home = Path(os.environ.get("CLAUDEBOOST_HOME") or os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..")
    ))
    state_dir = home / "state"
    workspace_dir = home / "workspace"

    # Read hook input from stdin
    raw = sys.stdin.read() if not sys.stdin.isatty() else ""
    try:
        hook_input = json.loads(raw) if raw else {}
    except Exception:
        hook_input = {}

    session_id = hook_input.get("session_id", "unknown")

    # Read existing memo for compaction count
    memo_path = state_dir / "compaction-memo.json"
    existing = read_json(memo_path)
    compaction_number = existing.get("compaction_number", 0) + 1

    # Archive previous memo if it has content
    if existing.get("memo"):
        history_dir = state_dir / "compaction-history"
        history_dir.mkdir(parents=True, exist_ok=True)
        prev_num = existing.get("compaction_number", 0)
        prev_session = existing.get("session_id", "unknown")[:16]
        archive_name = f"{prev_session}-compact-{prev_num}.json"
        try:
            (history_dir / archive_name).write_text(
                json.dumps(existing, indent=2), encoding="utf-8",
            )
        except Exception:
            pass

    # Collect workspace context summaries
    workspace_summaries = []
    seen_ws_paths: set[str] = set()
    if workspace_dir.exists():
        for ctx_file in sorted(workspace_dir.glob("*/context.md")):
            task_id = ctx_file.parent.name
            seen_ws_paths.add(str(ctx_file.parent))
            try:
                content = ctx_file.read_text(encoding="utf-8")
                summary = extract_summary(content)
                workspace_summaries.append(f"### {task_id}\n{summary}")
            except Exception:
                workspace_summaries.append(f"### {task_id}\n[unreadable]")

    # Also include project-scoped workspaces stored outside home/workspace/
    try:
        reg = read_json(state_dir / "workspaces.json")
        for ws_id, entry in reg.items():
            ws_path = entry.get("workspace_path", "")
            if not ws_path:
                continue
            ws_dir = Path(ws_path)
            if str(ws_dir) in seen_ws_paths:
                continue
            seen_ws_paths.add(str(ws_dir))
            ctx_file = ws_dir / "context.md"
            if not ctx_file.exists():
                continue
            try:
                content = ctx_file.read_text(encoding="utf-8")
                summary = extract_summary(content)
                workspace_summaries.append(f"### {ws_id}\n{summary}")
            except Exception:
                workspace_summaries.append(f"### {ws_id}\n[unreadable]")
    except Exception:
        pass

    # Read active workspace so the restore can filter to just the right section
    hook_cwd = hook_input.get("cwd", "")
    active_ws = _resolve_active_workspace(state_dir, hook_cwd)

    # Read mode state
    mode = read_json(state_dir / "claudeboost-mode.json").get("mode", "CONSULT")

    # Build memo
    parts = [
        f"# Compaction Memo #{compaction_number}",
        f"Session: {session_id}",
        f"Time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}",
        f"Mode: {mode}",
        "",
    ]

    if workspace_summaries:
        parts.append("## Active Workspaces")
        parts.extend(workspace_summaries)
    else:
        parts.append("## Active Workspaces")
        parts.append("None.")

    parts.append("")
    parts.append("## Recovery Instructions")
    parts.append("Read workspace/*/context.md for full task detail.")
    parts.append("Continue from the last documented next step.")

    memo_text = "\n".join(parts)

    # Extract conversation highlights from transcript
    sys.path.insert(0, str(Path(__file__).parent))
    try:
        from handoff_core import extract_conversation, format_conversation_md
        transcript_path_str = hook_input.get("transcript_path", "")
        conversation = extract_conversation(transcript_path_str) if transcript_path_str else None
    except Exception:
        conversation = None

    # Save compaction-memo.json (backward compat — compaction-restore.py fallback reads this)
    memo_data = {
        "session_id": session_id,
        "compaction_number": compaction_number,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "memo": memo_text,
    }
    state_dir.mkdir(parents=True, exist_ok=True)
    memo_path.write_text(json.dumps(memo_data, indent=2), encoding="utf-8")

    # Write unified handoff-latest.json (read by compaction-restore.py for both compact + clear)
    handoff_data = {
        "session_id": session_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "trigger": "PreCompact",
        "cwd": hook_input.get("cwd", ""),
        "workspace_memo": memo_text,
        "active_workspace": active_ws,
        "conversation": conversation or {},
    }
    try:
        (state_dir / "handoff-latest.json").write_text(
            json.dumps(handoff_data, indent=2), encoding="utf-8"
        )
    except Exception:
        pass

    # Reset counters so guards start fresh after compaction
    tracker_path = state_dir / "compaction-tracker.json"
    try:
        tracker_path.write_text('{"edit_count": 0}', encoding="utf-8")
    except Exception:
        pass
    try:
        (state_dir / "behavior-tracker.json").write_text(
            '{"reads_since_rag": 0, "tasks_since_evaluator": 0}', encoding="utf-8"
        )
    except Exception:
        pass

    # Write a one-shot flag so session-primer.py bypasses the 15-char guard on the
    # first post-compaction message (same pattern as clear-pending.json).
    try:
        (state_dir / "compaction-pending.json").write_text(
            json.dumps({"pending": True, "timestamp": datetime.now(timezone.utc).isoformat()}),
            encoding="utf-8",
        )
    except Exception:
        pass

    # Inject workspace state + conversation highlights into the compaction summary
    context_out = memo_text
    if conversation and (conversation.get("user_messages") or conversation.get("files_touched")):
        try:
            context_out += "\n\n## Conversation Highlights\n" + format_conversation_md(conversation)
        except Exception:
            pass
    print(json.dumps({"additionalContext": context_out}))

    return 0


if __name__ == "__main__":
    sys.exit(main())
