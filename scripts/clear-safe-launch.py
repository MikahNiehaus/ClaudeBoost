"""
ClaudeBoost clear-safe-launch — called by the /clear-safe skill after context.md is updated.

Writes all handoff state files and opens a new Windows Terminal tab with the
workspace context pre-loaded in the startup prompt. The old tab closes automatically
via auto-clear.py (Stop hook) which reads lt-terminal-signal.json.

Usage:
    python clear-safe-launch.py \
        --workspace-id <id> \
        --workspace-path <path> \
        --next-step "<text>" \
        [--cwd <dir>]
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


def read_json(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return default if default is not None else {}


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace-id", required=True)
    parser.add_argument("--workspace-path", required=True)
    parser.add_argument("--next-step", required=True)
    parser.add_argument("--cwd", default=os.getcwd())
    args = parser.parse_args()

    home = Path(os.environ.get("CLAUDEBOOST_HOME", ""))
    if not home or not home.exists():
        print("ERROR: CLAUDEBOOST_HOME not set or missing", file=sys.stderr)
        return 1

    state = home / "state"
    state.mkdir(parents=True, exist_ok=True)

    ws_path = Path(args.workspace_path)
    context_text = ""
    ctx_file = ws_path / "context.md"
    if ctx_file.exists():
        try:
            context_text = ctx_file.read_text(encoding="utf-8")
        except Exception:
            pass

    now_iso = datetime.now(timezone.utc).isoformat()
    now_unix = time.time()

    write_json(state / "active-workspace.json", {"workspace": args.workspace_id})

    workspace_memo = (
        f"# Clear Handoff Memo\n"
        f"Session: manual-clear-safe\n"
        f"Time: {now_iso}\n\n"
        f"## Active Workspace\n### {args.workspace_id}\n\n"
        f"{context_text}\n\n"
        f"## Next Step\n{args.next_step}\n\n"
        f"## Recovery\n"
        f"Read {ctx_file} for full detail. Continue from the next step above."
    )

    write_json(state / "handoff-latest.json", {
        "session_id": "manual-clear-safe",
        "timestamp": now_iso,
        "trigger": "SessionEnd(clear)",
        "active_workspace": args.workspace_id,
        "handoff_message": args.next_step,
        "workspace_memo": workspace_memo,
    })

    write_json(state / "clear-pending.json", {
        "pending": True,
        "timestamp": now_iso,
    })

    write_json(state / "auto-clear-pending.json", {
        "pending": True,
        "timestamp": now_unix,
        "session_name": "",
    })

    launch_msg = (
        f"Continue work on {args.workspace_id}. "
        f"Read {ctx_file} first. "
        f"Next: {args.next_step}"
    )

    cwd = args.cwd

    if sys.platform == "win32":
        # Write a tiny batch file to dodge cmd.exe quoting hell with nested quotes
        tmp_bat = state / "_clear_safe_launch.bat"
        safe_msg = launch_msg.replace('"', "'")
        tmp_bat.write_text(
            f'@echo off\nclaude "{safe_msg}"\n',
            encoding="utf-8",
        )
        subprocess.Popen(
            ["wt.exe", "-w", "-1", "new-tab", "-d", cwd, "cmd.exe", "/k", str(tmp_bat)],
            creationflags=0x00000200,  # CREATE_NEW_PROCESS_GROUP
            start_new_session=True,
        )
    else:
        print(f"Open a new terminal in {cwd} and run: claude '{launch_msg}'")

    # Signal auto-clear.py (Stop hook) to kill the current node.exe after this response
    write_json(state / "lt-terminal-signal.json", {
        "cwd": cwd,
        "timestamp": now_unix,
    })

    print(f"Launched: {args.workspace_id} — new tab opening, this tab will close.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
