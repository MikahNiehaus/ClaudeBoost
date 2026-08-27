"""
ClaudeBoost auto-clear — Stop command hook.

When /clear-safe writes state/auto-clear-pending.json, this hook injects
/clear into the terminal after Claude finishes responding (tmux only).

/clear-safe also has a Windows path: clear-safe-launch.py opens a new
Windows Terminal tab and writes state/clear-safe-terminal-signal.json. This
hook consumes that signal and kills the Claude process so the OLD tab closes.
Without the consumer here, /clear-safe leaves two tabs open.

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

from workspace_identity import _find_claude_pid_windows


def _audit(home: str, message: str) -> None:
    """Append one line to state/auto-clear.log. Never raises.

    This hook is the only thing in the tree that calls os.kill(pid, 9) on the
    editor it runs under. On Windows that is TerminateProcess: the session
    disappears with no exit code, no Windows Error Reporting entry, and no
    cleanup, so the terminal keeps its mouse reporting modes on.

    Claude Code sessions were dying repeatedly on 2026-08-26 and nothing
    anywhere recorded why. Four deaths were reconstructed only by diffing
    process lists in scripts/memory-watcher.py's samples, which proves a kill
    happened but not who did it. Whether this hook fired at all was unknowable,
    because the signal file is one shot and unlinked before the kill.

    A kill this quiet needs a record. Failures are swallowed: a Stop hook that
    raises is worse than one that loses a log line.
    """
    try:
        log = Path(home) / "state" / "auto-clear.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y-%m-%dT%H:%M:%S")
        with log.open("a", encoding="utf-8") as fh:
            fh.write(f"{stamp} pid={os.getpid()} {message}\n")
    except Exception:
        pass


def _close_old_clear_safe_tab(home: str) -> bool:
    """Consume /clear-safe's terminal handoff signal and close the old tab.

    clear-safe-launch.py opens the replacement Windows Terminal tab and writes
    state/clear-safe-terminal-signal.json. It is the ONLY writer, and this is
    the only reader: delete one without the other and /clear-safe silently
    leaves two tabs open.

    Returns True if a signal was found, in which case the caller is done for
    this Stop, the /clear injection below is for the tmux flow instead.
    """
    signal_path = Path(home) / "state" / "clear-safe-terminal-signal.json"
    if not signal_path.exists():
        return False

    try:
        data = json.loads(signal_path.read_text(encoding="utf-8"))
    except Exception:
        data = {}

    # One shot: gone before anything can fail, so a bad signal cannot wedge
    # every future Stop into trying to kill something.
    signal_path.unlink(missing_ok=True)

    age = time.time() - data.get("timestamp", 0)
    _audit(home, f"signal found, age={age:.1f}s, raw={data!r}")

    if age < MAX_AGE_SECONDS:
        node_pid = _find_claude_pid_windows()
        if node_pid:
            try:
                os.kill(node_pid, 9)
                _audit(home, f"KILLED claude pid={node_pid} (SIGKILL)")
            except Exception as e:
                # The tab is already gone, or is not ours to kill. Both mean
                # the job is done, so this stays non fatal. It gets recorded
                # now rather than swallowed: "the kill failed" and "the kill
                # never ran" looked identical before, and telling them apart is
                # the whole reason the log exists.
                _audit(home, f"kill FAILED pid={node_pid}: {type(e).__name__}: {e}")
        else:
            _audit(home, "no claude ancestor pid found, nothing killed")
    else:
        _audit(home, f"signal stale ({age:.1f}s > {MAX_AGE_SECONDS}s), not killing")
    return True


def main() -> int:
    home = os.environ.get("CLAUDEBOOST_HOME", "")
    if not home:
        return 0

    if _close_old_clear_safe_tab(home):
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
