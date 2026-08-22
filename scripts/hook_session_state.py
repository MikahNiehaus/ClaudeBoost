"""
Per conversation scratch state for UserPromptSubmit hooks.

A hook that injects context is charged for it more than once. The text lands in
the transcript and every later request in the session re-reads it, so a block
repeated on all N prompts costs on the order of N squared to carry. The way out
is to emit a thing when it changes and stay quiet when it has not, which needs
somewhere to remember what was already said.

Keyed on session_id from the hook payload. The obvious alternative, os.getpid(),
looks right and is not: Claude Code spawns a fresh process for every hook
invocation, so a pid key never repeats, every read misses, and a new file is
left behind on each prompt. session-primer.py had exactly that bug in its
status cache.

    key = session_key(payload)
    last = read_state("primer", key)
    ...
    write_state("primer", key, {"sig": digest(block)})
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path


def temp_dir() -> Path:
    return Path(os.environ.get("TEMP") or os.environ.get("TMPDIR") or "/tmp")


def digest(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8", "replace")).hexdigest()[:16]


def session_key(payload: dict) -> str:
    """A key that stays constant for one conversation and differs across them."""
    import re
    sid = str((payload or {}).get("session_id") or "").strip()
    if sid:
        return re.sub(r"[^A-Za-z0-9_.]", "_", sid)[:64]
    # No session_id in the payload: fall back to the working directory so two
    # projects open in parallel windows do not share one state file.
    return hashlib.sha1(os.getcwd().encode("utf-8", "replace")).hexdigest()[:16]


def _path(kind: str, key: str) -> Path:
    safe = "".join(c for c in kind if c.isalnum() or c in "_.")
    return temp_dir() / f"claudeboost_{safe}_state_{key}.json"


def read_state(kind: str, key: str) -> dict:
    """What this hook emitted on the previous prompt. Empty dict on the first."""
    try:
        data = json.loads(_path(kind, key).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def write_state(kind: str, key: str, state: dict) -> None:
    """Best effort. A hook must never fail the turn over its own scratch file."""
    try:
        _path(kind, key).write_text(json.dumps(state), encoding="utf-8")
    except Exception:
        pass


def read_payload(raw: str) -> dict:
    """Parse a hook stdin payload without ever raising."""
    try:
        data = json.loads(raw) if raw else {}
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}
