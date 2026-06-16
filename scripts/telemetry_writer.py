"""
Shared telemetry routing module for ClaudeBoost.

All telemetry hooks import this to write records to the active workspace's
Telemetry/ folder. Falls back to state/telemetry-unrouted.jsonl when no
workspace is active. All writes are fire-and-forget (failures silently ignored).

Respects DISABLE_TELEMETRY=1 — if set, write_telemetry() and update_session_json()
return immediately without touching any file.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BOOST_HOME = Path(os.environ.get("CLAUDEBOOST_HOME") or Path(__file__).resolve().parent.parent)
_ACTIVE_WORKSPACE_FILE = BOOST_HOME / "state" / "active-workspace.json"
_FALLBACK_LOG = BOOST_HOME / "state" / "telemetry-unrouted.jsonl"
_DISABLED = os.environ.get("DISABLE_TELEMETRY", "") == "1"

# Maximum time to wait for the session.json lock before giving up.
_LOCK_TIMEOUT_S = 0.5


def _get_telemetry_dir() -> Path | None:
    """Return the Telemetry/ dir for the active workspace, creating it if needed."""
    try:
        data = json.loads(_ACTIVE_WORKSPACE_FILE.read_text(encoding="utf-8"))
        wp = data.get("workspace_path")
        if wp:
            tel_dir = Path(wp) / "Telemetry"
            tel_dir.mkdir(parents=True, exist_ok=True)
            return tel_dir
    except Exception:
        pass
    return None


def write_telemetry(record: dict[str, Any], filename: str) -> None:
    """Append one JSON record to workspace/[id]/Telemetry/<filename>."""
    if _DISABLED:
        return
    try:
        tel_dir = _get_telemetry_dir()
        if tel_dir:
            target = tel_dir / filename
        else:
            _FALLBACK_LOG.parent.mkdir(parents=True, exist_ok=True)
            target = _FALLBACK_LOG
        with target.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
    except Exception:
        pass


def update_session_json(field: str, delta: int = 1) -> None:
    """Increment a counter field in session.json for the active workspace.

    Uses a lockfile to prevent lost increments when the PostToolUse hook
    and the RAG server middleware both write session.json concurrently.
    The lock is advisory — both callers must use this function.
    """
    if _DISABLED:
        return
    import time
    try:
        tel_dir = _get_telemetry_dir()
        if not tel_dir:
            return
        session_file = tel_dir / "session.json"
        if not session_file.exists():
            return
        lock_path = tel_dir / "session.lock"
        deadline = time.monotonic() + _LOCK_TIMEOUT_S
        acquired = False
        while time.monotonic() < deadline:
            try:
                lock_path.open("x").close()  # O_EXCL — fails if lock exists
                acquired = True
                break
            except FileExistsError:
                time.sleep(0.02)
        # If we couldn't acquire the lock in time, proceed anyway — telemetry
        # is fire-and-forget; a rare lost increment beats a hung hook.
        try:
            data = json.loads(session_file.read_text(encoding="utf-8"))
            data[field] = data.get(field, 0) + delta
            session_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
        finally:
            if acquired:
                try:
                    lock_path.unlink()
                except Exception:
                    pass
    except Exception:
        pass


def query_hash(text: str | None) -> str | None:
    """SHA-256 hex digest prefixed with 'sha256:', or None for empty input."""
    if not text:
        return None
    return "sha256:" + hashlib.sha256(text.encode()).hexdigest()


# Alias used by server middleware and other callers.
path_hash = query_hash


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def session_id() -> str:
    try:
        return (BOOST_HOME / "state" / "session-id.txt").read_text(encoding="utf-8").strip()
    except Exception:
        return os.environ.get("CLAUDE_SESSION_ID", "unknown")
