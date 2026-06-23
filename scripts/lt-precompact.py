"""
lt-precompact.py — PreCompact hook for Low Token Mode.

When Low Token Mode is enabled in state/low-token-mode.json:
  1. Launches a new Windows Terminal tab in the current project directory
  2. Writes state/lt-terminal-signal.json so auto-clear.py (Stop hook) can
     kill this session after the current turn ends
  3. Blocks compaction (exit 2) — the new session picks up via handoff-latest.json
     which compaction-save.py already wrote earlier in this PreCompact run

When not enabled: exits 0 immediately — no change to normal behavior.

Cross-platform: on non-Windows the signal is written but no new terminal is
launched. The session continues at high context until the user starts one manually.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path


def _read_json(path: Path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default if default is not None else {}


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

    # Launch a new terminal tab pointing at the same directory (Windows only)
    if sys.platform == "win32":
        try:
            subprocess.Popen(
                ["wt.exe", "-w", "-1", "new-tab", "-d", cwd],
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
                start_new_session=True,
            )
        except FileNotFoundError:
            # wt.exe not available — signal is still written so the Stop hook
            # closes this session; user needs to open a terminal manually
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

    # Exit 2 blocks compaction. The new session starts fresh and reads
    # handoff-latest.json (written by compaction-save.py in this same
    # PreCompact run) via compaction-restore.py at SessionStart.
    return 2


if __name__ == "__main__":
    sys.exit(main())
