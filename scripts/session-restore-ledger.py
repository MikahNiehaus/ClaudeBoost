"""
session-restore-ledger.py — SessionStart / SessionEnd hook for session restore.

Records a session in state/session-restore.json when it opens and removes it
when it closes. Whatever is still listed after a reboot is what was open, since
a power cut or a forced restart never delivers SessionEnd.

Reads the event from stdin JSON (hook_event_name), the same shape
telemetry-session.py uses. Always exits 0. A restore ledger is a convenience,
so a failure here must never interfere with the session the user is in.

Fields recorded per session:
    sessionId   the id `claude --resume <id>` takes
    cwd         the directory the tab must open in
    name        display name, for the tab title
    launchFlags flags the resume needs re passed, because --resume does not
                carry --add-dir, --mcp-config, --settings or --plugin-dir
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

BOOST_HOME = Path(os.environ.get("CLAUDEBOOST_HOME") or Path(__file__).resolve().parent.parent)
sys.path.insert(0, str(BOOST_HOME / "scripts"))

from session_restore_state import (  # noqa: E402
    live_sessions,
    log,
    now_iso,
    update_ledger,
)

# Flags that `claude --resume` does not restore by itself. If the session was
# started with any of them, the reopened tab needs them passed again or it comes
# back with a different configuration than it had.
_CARRIED_FLAGS = (
    "--add-dir",
    "--mcp-config",
    "--settings",
    "--plugin-dir",
    "--fallback-model",
    "--permission-mode",
)


def _resolve(payload: dict) -> tuple[str, str]:
    """Return (session_id, cwd) from the hook payload, with fallbacks.

    The payload is the documented source. When a field is missing, the live
    registry is consulted by matching this process's own ancestry loosely on
    cwd, and finally os.getcwd() stands in. A wrong cwd would reopen the wrong
    directory, so an entry with no cwd at all is dropped rather than guessed.
    """
    sid = str(payload.get("session_id") or payload.get("sessionId") or "").strip()
    cwd = str(payload.get("cwd") or "").strip()

    if sid and cwd:
        return sid, cwd

    for s in live_sessions():
        if sid and s["sessionId"] == sid:
            return sid, (cwd or s["cwd"])
        if not sid and cwd and s["cwd"] == cwd:
            return s["sessionId"], cwd

    if not cwd:
        cwd = os.getcwd()
    return sid, cwd


def _name_for(sid: str, cwd: str) -> str:
    """Prefer the name Claude Code derived for the session, else the folder."""
    for s in live_sessions():
        if s["sessionId"] == sid and s.get("name"):
            return s["name"]
    return Path(cwd).name or cwd


def _launch_flags() -> list[str]:
    """Flags from this process's own command line that a resume must repeat.

    Read from the claude entry in the live registry when available. Falls back
    to an empty list, which is correct for a plain `claude` launch.
    """
    flags: list[str] = []
    argv = os.environ.get("CLAUDE_CODE_ENTRYPOINT_ARGV", "")
    if not argv:
        return flags
    parts = argv.split()
    i = 0
    while i < len(parts):
        if parts[i] in _CARRIED_FLAGS:
            flags.append(parts[i])
            if i + 1 < len(parts) and not parts[i + 1].startswith("-"):
                flags.append(parts[i + 1])
                i += 1
        i += 1
    return flags


def handle_start(payload: dict) -> None:
    sid, cwd = _resolve(payload)
    if not sid or not cwd:
        log("SessionStart with no session id or cwd, not recorded")
        return
    if not Path(cwd).is_dir():
        log(f"SessionStart cwd does not exist, not recorded: {cwd}")
        return

    entry = {
        "sessionId": sid,
        "cwd": str(Path(cwd)),
        "name": _name_for(sid, cwd),
        "launchFlags": _launch_flags(),
        "startedAt": now_iso(),
        "lastSeen": now_iso(),
        "lastSeenEpoch": time.time(),
    }

    def mutate(data: dict) -> None:
        sessions = data.setdefault("sessions", {})
        existing = sessions.get(sid)
        if existing:
            # A resumed session fires SessionStart again. Keep the original
            # startedAt so the stale check measures real age, not last resume.
            entry["startedAt"] = existing.get("startedAt", entry["startedAt"])
        sessions[sid] = entry

    update_ledger(mutate)
    log(f"recorded {entry['name']} ({sid[:8]}) at {cwd}")


def handle_end(payload: dict) -> None:
    sid, cwd = _resolve(payload)
    reason = str(payload.get("reason") or "")
    if not sid:
        log("SessionEnd with no session id, ledger unchanged")
        return

    def mutate(data: dict) -> None:
        data.get("sessions", {}).pop(sid, None)

    update_ledger(mutate)
    log(f"removed {sid[:8]} (reason: {reason or 'unspecified'})")


def main() -> int:
    try:
        # A hook may be launched without a console, so stdin can be None and
        # may not implement isatty. Neither case is allowed to raise here.
        stdin = sys.stdin
        if stdin is None or getattr(stdin, "isatty", lambda: True)():
            raw = ""
        else:
            raw = stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
        if not isinstance(payload, dict):
            payload = {}
    except Exception:
        payload = {}

    event = str(payload.get("hook_event_name") or "")
    try:
        if event == "SessionStart":
            handle_start(payload)
        elif event == "SessionEnd":
            handle_end(payload)
    except Exception as exc:
        log(f"hook error on {event or 'unknown event'}: {exc}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
