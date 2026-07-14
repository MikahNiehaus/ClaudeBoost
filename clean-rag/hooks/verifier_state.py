"""Shared state for the verifier gate.

verifier-gate.py used to count how many times it printed a nudge, not whether
verifier-agent had actually run. After 2 nudges it gave up for the rest of the
session regardless of whether anything was ever reviewed. This is the real
check that replaces the counter: a stamp, written only when verifier-agent
actually completes, the same shape research-gate.py already uses for research.

The scope is different from research's, on purpose. research-agent's stamp is
per TURN, reset by rag-enforce.py's open_turn() on every UserPromptSubmit,
because the research gate blocks a single edit and a fresh turn should require
fresh research. verifier-gate.py reviews the accumulated uncommitted git diff,
which spans however many turns happened since the last commit, so a stamp here
is scoped to the SESSION, not the turn, and is invalidated per file instead: if
a file's mtime advances past its stamp's timestamp, it was edited again after
being reviewed, and the stamp no longer covers what is on disk now.

Reuses research_state's file_in_scope and extract_covered_files rather than
forking them; the only real difference is the marker line ("VERIFIED:" instead
of "COVERS:") and the mtime based invalidation.
"""

import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from research_state import extract_covered_files, file_in_scope  # noqa: E402

VERIFIER_MARKER = "VERIFIED:"


def _clean_rag_home() -> Path:
    env = os.environ.get("CLEAN_RAG_HOME")
    if env:
        return Path(env)
    return Path(__file__).resolve().parent.parent


def _state_dir() -> Path:
    d = _clean_rag_home() / "state" / "verifier"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _record_path(session_id: str) -> Path:
    import hashlib

    key = hashlib.sha256((session_id or "no-session").encode("utf-8")).hexdigest()[:16]
    return _state_dir() / f"session-{key}.json"


def _write_lock(path: Path):
    """Best effort cross process lock, same degrade-to-none shape research_state uses."""
    try:
        import research_state

        return research_state._write_lock(path)
    except Exception:
        import contextlib

        return contextlib.nullcontext()


def _first_verdict_line(text: str) -> str:
    for line in (text or "").splitlines():
        stripped = line.strip()
        if stripped.upper().startswith("VERDICT:"):
            return stripped[:200]
    return (text or "")[:200]


def record_verifier(session_id: str, report: str) -> None:
    """Called on PostToolUse after verifier-agent finishes. Appends a stamp.

    Session scoped: unlike research's per-turn record, this file is never reset
    by a new prompt, since the diff it covers spans turns too.
    """
    path = _record_path(session_id)

    with _write_lock(path):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            record = {"session_id": session_id, "stamps": []}

        record.setdefault("stamps", []).append({
            "agent": "verifier-agent",
            "at": time.time(),
            "covers": extract_covered_files(report, prefix=VERIFIER_MARKER),
            "verdict": _first_verdict_line(report),
        })

        try:
            path.write_text(json.dumps(record, indent=2), encoding="utf-8")
        except OSError:
            pass


def check_file_verified(session_id: str, file_path: str) -> tuple[bool, str]:
    """Was this file reviewed by verifier-agent, and not edited again since?

    Returns (ok, reason). Picks the newest stamp that covers the file, then
    checks whether the file's mtime is still older than that stamp's
    timestamp; if the file changed again after the stamp, the review no
    longer describes what's on disk, so it doesn't count.
    """
    path = _record_path(session_id)
    if not path.exists():
        return False, "no verifier-agent run has covered this file"

    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False, "the verifier record is unreadable"

    stamps = record.get("stamps", []) if isinstance(record, dict) else []
    matching = [s for s in stamps if file_in_scope(file_path, s.get("covers", []))]
    if not matching:
        return False, "no verifier-agent run has covered this file"

    newest = max(matching, key=lambda s: s.get("at", 0))

    try:
        mtime = Path(file_path).stat().st_mtime
    except OSError:
        # File is gone; nothing to re-verify against, and nothing to block either.
        return True, "verified by verifier-agent (file no longer present)"

    if mtime > newest.get("at", 0):
        return False, "verified earlier, but edited again since"

    return True, "verified by verifier-agent"
