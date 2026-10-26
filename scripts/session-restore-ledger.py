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

def _payload_sid(payload: dict) -> str:
    """First non-blank string id under either key, else empty."""
    for key in ("session_id", "sessionId"):
        v = payload.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


def _resolve(payload: dict) -> tuple[str, str]:
    """Return (session_id, cwd) from the hook payload, with fallbacks.

    The payload is the documented source. When a field is missing, the live
    registry is consulted by matching this process's own ancestry loosely on
    cwd, and finally os.getcwd() stands in. A wrong cwd would reopen the wrong
    directory, so an entry with no cwd at all is dropped rather than guessed.
    """
    sid = _payload_sid(payload)
    cwd = str(payload.get("cwd") or "").strip()

    if sid and cwd:
        return sid, cwd

    for s in live_sessions():
        if sid and s["sessionId"].lower() == sid.lower():
            return sid, (cwd or s["cwd"])
        if not sid and cwd and s["cwd"] == cwd:
            return s["sessionId"], cwd

    if not cwd:
        cwd = os.getcwd()
    return sid, cwd


def _name_for(sid: str, cwd: str) -> str:
    """Prefer the name Claude Code derived for the session, else the folder."""
    for s in live_sessions():
        if s["sessionId"].lower() == sid.lower() and s.get("name"):
            return s["name"]
    return Path(cwd).name or cwd


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
        "startedAt": now_iso(),
        "lastSeen": now_iso(),
        "lastSeenEpoch": time.time(),
    }

    def mutate(data: dict) -> None:
        sessions = data.setdefault("sessions", {})
        twins = [k for k in sessions if k.lower() == sid.lower()]
        existing = sessions.get(sid) or (sessions.get(twins[0]) if twins else None)
        for k in twins:
            sessions.pop(k, None)
        if isinstance(existing, dict):
            # A resumed session fires SessionStart again. Keep the original
            # startedAt so the stale check measures real age, not last resume.
            entry["startedAt"] = existing.get("startedAt", entry["startedAt"])
        sessions[sid] = entry

    update_ledger(mutate)
    log(f"recorded {entry['name']} ({sid[:8]}) at {cwd}")


def handle_end(payload: dict) -> None:
    given = _payload_sid(payload)
    sid, cwd = _resolve(payload)
    reason = str(payload.get("reason") or "")
    # No cwd-matching fallback on end: guessing could drop a different live session.
    if not sid or not given:
        log("SessionEnd with no session id, ledger unchanged")
        return

    # "other" is what a window close or logoff sends, so it is not a deliberate exit.
    if reason == "other":
        log(f"kept {sid[:8]} (reason: other)")
        return
    if sum(1 for s in live_sessions() if s["sessionId"].lower() == sid.lower()) > 1:
        log(f"kept {sid[:8]}, another process still runs it")
        return

    def mutate(data: dict) -> None:
        sessions = data.get("sessions", {})
        for k in [k for k in sessions if k.lower() == sid.lower()]:
            sessions.pop(k, None)

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
