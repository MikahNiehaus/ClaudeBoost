"""
SessionStart / SessionEnd hook for ClaudeBoost telemetry.

Creates workspace/[id]/Telemetry/session.json on SessionStart.
Updates ended_at and final counts on SessionEnd.

Detects the event from stdin JSON (hook_event_name field).
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

BOOST_HOME = Path(os.environ.get("CLAUDEBOOST_HOME") or Path(__file__).resolve().parent.parent)
sys.path.insert(0, str(BOOST_HOME / "scripts"))

from telemetry_writer import (  # noqa: E402
    _DISABLED,
    _get_telemetry_dir,
    now_iso,
    path_hash,
    session_id,
)


def _read_active_workspace() -> dict:
    try:
        return json.loads(
            (BOOST_HOME / "state" / "active-workspace.json").read_text(encoding="utf-8")
        )
    except Exception:
        return {}


def handle_session_start() -> None:
    tel_dir = _get_telemetry_dir()
    if not tel_dir:
        return

    ws = _read_active_workspace()
    workspace_id = ws.get("workspace", "unknown")
    project_path = ws.get("project_path", "")

    session_file = tel_dir / "session.json"

    # Don't overwrite a still-active session (ended_at is None means it never closed).
    # This protects accumulated tool_count/rag_count if Claude Code reconnects without
    # firing SessionEnd first.
    if session_file.exists():
        try:
            existing = json.loads(session_file.read_text(encoding="utf-8"))
            if existing.get("ended_at") is None:
                return
        except Exception:
            pass  # Corrupted file — overwrite it below

    record = {
        "session_id": session_id(),
        "workspace_id": workspace_id,
        "project_path_hash": path_hash(project_path),
        "started_at": now_iso(),
        "ended_at": None,
        "tool_count": 0,
        "rag_count": 0,
    }
    try:
        session_file.write_text(json.dumps(record, indent=2), encoding="utf-8")
    except Exception:
        pass


def handle_session_end() -> None:
    tel_dir = _get_telemetry_dir()
    if not tel_dir:
        return

    session_file = tel_dir / "session.json"
    if not session_file.exists():
        return
    try:
        data = json.loads(session_file.read_text(encoding="utf-8"))
        data["ended_at"] = now_iso()
        session_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception:
        pass


def main() -> int:
    if _DISABLED:
        return 0

    raw = sys.stdin.read() if not sys.stdin.isatty() else ""
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except Exception:
        payload = {}

    event = payload.get("hook_event_name", "")

    if event == "SessionStart":
        handle_session_start()
    elif event == "SessionEnd":
        handle_session_end()

    return 0


if __name__ == "__main__":
    sys.exit(main())
