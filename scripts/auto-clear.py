"""
ClaudeBoost auto-clear — Stop command hook.

When /clear-safe writes state/auto-clear-pending.json, this hook injects
/clear into the terminal after Claude finishes responding (tmux only).

Injection method:
  - tmux ($TMUX set): tmux send-keys
  - Non-tmux: no-op. User types /clear manually.

The flag is one-shot: deleted immediately on first check regardless of
whether injection succeeds, so it never fires twice.

Stale guard: flags older than MAX_AGE_SECONDS are discarded silently.

Exit codes:
  0 = always (this hook never blocks)
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

MAX_AGE_SECONDS = 300  # 5 minutes

_CREATE_NO_WINDOW = 0x08000000
_CREATE_NEW_PROCESS_GROUP = 0x00000200


from workspace_identity import _find_claude_pid_windows


def main() -> int:
    home = os.environ.get("CLAUDEBOOST_HOME", "")
    if not home:
        return 0

    # Low Token Mode terminal kill: lt-precompact.py writes this signal when
    # context fills and it has already launched a new terminal. We kill the
    # Claude Code process here so the current tab closes cleanly.
    lt_signal = Path(home) / "state" / "lt-terminal-signal.json"
    if lt_signal.exists():
        try:
            data = json.loads(lt_signal.read_text(encoding="utf-8"))
        except Exception:
            data = {}
        lt_signal.unlink(missing_ok=True)
        if time.time() - data.get("timestamp", 0) < MAX_AGE_SECONDS:
            node_pid = _find_claude_pid_windows()
            if node_pid:
                try:
                    os.kill(node_pid, 9)
                except Exception:
                    pass
        return 0

    flag_path = Path(home) / "state" / "auto-clear-pending.json"
    if not flag_path.exists():
        return 0

    try:
        flag = json.loads(flag_path.read_text(encoding="utf-8"))
    except Exception:
        flag_path.unlink(missing_ok=True)
        return 0

    # One-shot: delete immediately
    flag_path.unlink(missing_ok=True)

    # Staleness guard
    ts = flag.get("timestamp", 0.0)
    if time.time() - ts > MAX_AGE_SECONDS:
        return 0

    session_name = flag.get("session_name", "").strip()

    if os.environ.get("TMUX"):
        subprocess.run(["tmux", "send-keys", "/clear", "Enter"], check=False)
        if session_name:
            safe_name = session_name.replace("'", "\\'")
            cmd = f"sleep 5 && tmux send-keys '/rename {safe_name}' Enter"
            subprocess.Popen(
                ["bash", "-c", cmd],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                start_new_session=True,
            )

    return 0


if __name__ == "__main__":
    sys.exit(main())
