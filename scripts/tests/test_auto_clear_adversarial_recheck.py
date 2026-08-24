"""Adversarial re-check: cross-session delivery of the auto-clear-pending flag.

clear-safe-launch.py writes BOTH state files in the same run, before the old
tab's Stop hook ever fires:
    - auto-clear-pending.json        (tmux /clear injection)
    - clear-safe-terminal-signal.json (Windows-tab kill handoff)

The OLD session's Stop hook hits the signal branch first and returns 0
immediately (that is the fix under test: _close_old_clear_safe_tab). It never
reaches the auto-clear-pending.json check on that call, so the flag it wrote
for itself is left on disk, still "fresh" by MAX_AGE_SECONDS.

The existing suite (test_signal_does_not_block_the_tmux_path_later) proves the
flag is not starved forever -- some later main() call does consume it. This
file proves WHO consumes it: in the real sequence the old session is dead
(SIGKILL'd inside the first call), so the "later call" is the brand-new
session's own first Stop hook, not the old session's. If that new session
happens to be running under tmux too, it gets an unsolicited /clear injected
on its very first response, despite never asking for one.

Each main() call below is a fully separate subprocess (run_hook), exactly
matching two different Claude sessions reading/writing the same on-disk
state -- not two calls sharing process memory.
"""
from __future__ import annotations

import json
import time

from helpers import run_hook


def test_stray_pending_flag_survives_the_old_sessions_stop_call(boost_home):
    """After the OLD session's Stop consumes the terminal signal, the
    auto-clear-pending.json flag it wrote for itself is still sitting there
    -- proving the early return really does skip it, not just doesn't crash.
    """
    pending = boost_home / "state" / "auto-clear-pending.json"
    signal = boost_home / "state" / "clear-safe-terminal-signal.json"

    # Exactly what clear-safe-launch.py writes, same run, same timestamp epoch.
    now = time.time()
    pending.write_text(json.dumps({"timestamp": now, "session_name": ""}), encoding="utf-8")
    signal.write_text(json.dumps({"cwd": "C:/prj/x", "timestamp": now}), encoding="utf-8")

    # OLD session's Stop hook fires.
    result = run_hook(
        "auto-clear.py",
        {"hook_event_name": "Stop", "session_id": "old-session"},
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home), "TMUX": ""},
    )
    assert result.returncode == 0

    assert not signal.exists(), "signal must be one-shot"
    assert pending.exists(), (
        "the fix's early return means the OLD session never reaches the "
        "auto-clear-pending.json branch on this call -- the flag survives it")


def test_stray_pending_flag_is_then_delivered_to_a_brand_new_session(boost_home):
    """The NEW session's first Stop hook -- a fresh process, fresh session,
    nothing to do with the old handoff -- finds that same stray flag still
    fresh, and (if it happens to be in tmux too) fires the /clear injection
    meant for the session that already died.
    """
    pending = boost_home / "state" / "auto-clear-pending.json"
    signal = boost_home / "state" / "clear-safe-terminal-signal.json"
    now = time.time()
    pending.write_text(json.dumps({"timestamp": now, "session_name": "old-session"}), encoding="utf-8")
    signal.write_text(json.dumps({"cwd": "C:/prj/x", "timestamp": now}), encoding="utf-8")

    # OLD session's Stop: consumes signal, leaves the pending flag behind.
    run_hook(
        "auto-clear.py",
        {"hook_event_name": "Stop", "session_id": "old-session"},
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home), "TMUX": ""},
    )
    assert pending.exists(), "precondition: flag must still be there"

    # NEW session's first Stop -- a different process entirely, TMUX happens
    # to be set because the new tab is also a tmux pane (a real Windows +
    # WSL/git-bash + tmux combination).
    result = run_hook(
        "auto-clear.py",
        {"hook_event_name": "Stop", "session_id": "brand-new-session"},
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home), "TMUX": "/tmp/tmux-1000/default,1,0"},
    )
    assert result.returncode == 0
    assert not pending.exists(), (
        "the brand-new session's Stop hook consumed a flag it never set -- "
        "it belonged to the session that is already gone")


if __name__ == "__main__":
    import sys
    import subprocess as sp
    sp.run([sys.executable, "-m", "pytest", "-v", __file__])
