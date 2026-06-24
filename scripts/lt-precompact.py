"""
lt-precompact.py — PreCompact hook for Low Token Mode.

When Low Token Mode is enabled in state/low-token-mode.json:
  1. Reads handoff-latest.json (written by compaction-save.py earlier in this
     same PreCompact run) and extracts the task context
  2. Launches a new Windows Terminal tab, starts claude, and passes the handoff
     text as the first message — claude responds immediately, no user typing needed
  3. Writes state/lt-terminal-signal.json so auto-clear.py (Stop hook) can
     kill this session after the current turn ends
  4. Blocks compaction (exit 2) — the new session picks up immediately

When not enabled: exits 0 immediately — no change to normal behavior.

Cross-platform: on non-Windows the signal is written but no new terminal is
launched. The session continues at high context until the user starts one manually.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path


def _read_json(path: Path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default if default is not None else {}


def _build_startup_message(state_dir: Path) -> str:
    """
    Reads handoff-latest.json and returns the message to pass directly to claude
    in the new session. Uses explicit handoff_message if set, otherwise builds one
    from the workspace memo.
    """
    data = _read_json(state_dir / "handoff-latest.json")
    if not data:
        return (
            "Context compacted — continuing from handoff. "
            "Read workspace context.md for the current task and pick up from the last next step."
        )

    # Use an explicit handoff_message if one was set (e.g. by manual /handoff)
    explicit = (data.get("handoff_message") or "").strip()
    if explicit:
        return explicit

    # Build a message from structured fields
    memo = (data.get("workspace_memo") or data.get("memo") or "").strip()
    active_ws = (data.get("active_workspace") or "").strip()
    cwd_val = (data.get("cwd") or "").strip()

    parts = []
    if active_ws:
        parts.append(f"active workspace: {active_ws}")
    if cwd_val:
        parts.append(f"project: {cwd_val}")

    # Extract ## Task line from memo
    if memo:
        lines = memo.splitlines()
        in_task = False
        for line in lines:
            stripped = line.strip()
            if stripped == "## Task":
                in_task = True
                continue
            if in_task:
                if stripped.startswith("#"):
                    break
                if stripped:
                    parts.insert(0, f"task: {stripped}")
                    break

        # Extract ## Next Step line from memo
        in_next = False
        for line in lines:
            stripped = line.strip()
            if stripped == "## Next Step":
                in_next = True
                continue
            if in_next:
                if stripped.startswith("#"):
                    break
                if stripped:
                    parts.append(f"next step: {stripped}")
                    break

    if parts:
        return (
            "Context compacted. Continuing from handoff — "
            + ", ".join(parts)
            + ". Read workspace context.md for full detail."
        )

    return (
        "Context compacted. Continuing from handoff. "
        f"Active workspace: {active_ws or '(unknown)'}. "
        "Read workspace context.md for the current task and next step."
    )


def main() -> int:
    home = Path(
        os.environ.get("CLAUDEBOOST_HOME") or Path(__file__).resolve().parent.parent
    )
    state_dir = home / "state"

    # Guard: only act when Low Token Mode is explicitly enabled in state
    lt_state = _read_json(state_dir / "low-token-mode.json")
    if not lt_state.get("enabled", False):
        return 0

    # Read hook input from stdin
    raw = sys.stdin.read() if not sys.stdin.isatty() else ""
    try:
        hook_input = json.loads(raw) if raw else {}
    except Exception:
        hook_input = {}

    cwd = hook_input.get("cwd", "") or os.getcwd()

    # Open a new terminal and pass the handoff text directly as claude's first
    # message. We use a PowerShell temp script to avoid Windows escaping issues
    # with long or special-character messages. claude $msg passes the full text
    # as the initial user prompt — claude responds immediately without any typing.
    if sys.platform == "win32":
        try:
            startup_msg = _build_startup_message(state_dir)
            tmp = Path(tempfile.gettempdir())
            msg_file = tmp / "cb_lt_msg.txt"
            ps_file = tmp / "cb_lt_resume.ps1"
            msg_file.write_text(startup_msg, encoding="utf-8")
            ps_file.write_text(
                '$msg = [System.IO.File]::ReadAllText("'
                + str(msg_file).replace("\\", "\\\\")
                + '")\nclaude $msg\n',
                encoding="utf-8",
            )
            subprocess.Popen(
                [
                    "wt.exe", "-w", "-1", "new-tab", "-d", cwd,
                    "pwsh", "-NoExit", "-ExecutionPolicy", "Bypass",
                    "-File", str(ps_file),
                ],
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
                start_new_session=True,
            )
        except FileNotFoundError:
            # pwsh or wt.exe not available — fall back to plain cmd launch
            try:
                subprocess.Popen(
                    ["wt.exe", "-w", "-1", "new-tab", "-d", cwd,
                     "cmd.exe", "/k", "claude"],
                    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
                    start_new_session=True,
                )
            except FileNotFoundError:
                pass

    # Write the kill signal that auto-clear.py (Stop hook) picks up after
    # this turn ends to close the current session cleanly
    try:
        state_dir.mkdir(parents=True, exist_ok=True)
        (state_dir / "lt-terminal-signal.json").write_text(
            json.dumps({"cwd": cwd, "timestamp": time.time()}),
            encoding="utf-8",
        )
    except Exception:
        pass

    # Keep clear-pending so session-primer.py also injects handoff context
    # on the first message — belt-and-suspenders with the direct message above
    try:
        (state_dir / "clear-pending.json").write_text(
            json.dumps({
                "pending": True,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "from_lt": True,
            }),
            encoding="utf-8",
        )
    except Exception:
        pass

    # Exit 2 blocks compaction — new session starts fresh with full context
    return 2


if __name__ == "__main__":
    sys.exit(main())
