"""
ClaudeBoost rag-read-guard -- PreToolUse hook on Grep and Read.

Hard-blocks file searching when Claude has made too many file reads without
calling a RAG tool first. RAG finds the relevant file; Grep/Read reads it.
Doing it backwards (Read first, RAG never) is the pattern this guard catches.

Thresholds:
  RAG_THRESHOLD: consecutive Grep/Read calls without any RAG call before blocking
  EXEMPTED_PATHS: file paths that are always allowed (config, workspace files, etc.)

Exit codes:
  0 = allow (RAG was called recently, or below threshold, or RAG unavailable)
  2 = block (too many reads without RAG -- call rag_search first)
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

RAG_THRESHOLD = 2  # block after this many consecutive file searches without RAG

# Always allow reads of these paths -- no RAG needed for config/workspace files
EXEMPTED_SUFFIXES = {".json", ".lock", ".env", ".gitignore", ".toml", ".yaml", ".yml"}
EXEMPTED_NAME_FRAGMENTS = {
    "context.md", "settings", "claude.md", "memory", "package", "requirements",
    "cargo.toml", "pyproject", "go.mod", "go.sum", "tsconfig",
}


def is_exempted(tool_input: dict) -> bool:
    """Return True if this file read should be allowed without a prior RAG call."""
    path_str = str(tool_input.get("file_path", "") or tool_input.get("path", "") or "").lower()
    pattern_str = str(tool_input.get("pattern", "")).lower()

    if any(frag in path_str for frag in EXEMPTED_NAME_FRAGMENTS):
        return True
    if Path(path_str).suffix in EXEMPTED_SUFFIXES:
        return True
    if Path(path_str).suffix == ".md":
        if "workspace/" in path_str or "/workspace" in path_str or "state/" in path_str:
            return True
        return False
    if "workspace" in pattern_str or "state/" in pattern_str:
        return True
    return False


def _rag_is_live() -> bool:
    """Return True only if the RAG server is both activated AND currently running.

    Two checks:
    1. Sentinel ($TEMP/claudeboost_rag_ok) -- set by /boost. If missing, RAG was never
       activated this session.
    2. Heartbeat ($RAG_INDEX_DIR/.heartbeat) -- written every 30s by the live server
       process. If stale (>90s old) or missing, the server has died since /boost ran.

    Both must pass. If either fails, reads are allowed -- blocking reads when RAG is
    down creates a circular dependency that makes debugging impossible.
    """
    import time as _time

    temp = os.environ.get("TEMP") or os.environ.get("TMPDIR") or "/tmp"
    sentinel = Path(temp) / "claudeboost_rag_ok"
    if not sentinel.exists():
        return False  # /boost hasn't run this session

    # Check heartbeat freshness.
    _local_appdata = os.environ.get("LOCALAPPDATA", "")
    _rag_index_dir = os.environ.get(
        "RAG_INDEX_DIR",
        str(Path(_local_appdata) / "rag-server-index") if _local_appdata else "",
    )
    if not _rag_index_dir:
        return True  # can't locate index dir -- assume live (original behaviour)

    _heartbeat = Path(_rag_index_dir) / ".heartbeat"
    if not _heartbeat.exists():
        return False  # server hasn't written a heartbeat -- not running

    try:
        _age = _time.time() - float(_heartbeat.read_text(encoding="utf-8").strip())
        if _age > 150:
            return False  # heartbeat stale -- server has died
    except Exception:
        pass  # unreadable heartbeat -- assume live to avoid false blocks

    return True


def main() -> int:
    raw = sys.stdin.read() if not sys.stdin.isatty() else ""
    try:
        payload = json.loads(raw) if raw else {}
    except Exception:
        payload = {}

    tool_input = payload.get("tool_input") or {}

    if is_exempted(tool_input):
        return 0

    if not _rag_is_live():
        return 0

    home = Path(os.environ.get("CLAUDEBOOST_HOME") or Path(__file__).resolve().parent.parent)
    tracker_path = home / "state" / "behavior-tracker.json"

    try:
        behavior = json.loads(tracker_path.read_text(encoding="utf-8"))
    except Exception:
        behavior = {"reads_since_rag": 0}

    reads_since_rag = behavior.get("reads_since_rag", 0)

    if reads_since_rag < RAG_THRESHOLD:
        return 0

    print(
        f"BLOCKED -- {reads_since_rag} file searches since last RAG call. "
        "Call rag_search FIRST before reading more files. "
        "RAG finds the relevant file; Grep/Read reads it -- not the other way around. "
        "Run: rag_search(scope='codebase', query='<what you are looking for>') "
        "then read only the files RAG identifies as relevant. "
        "Do NOT bypass this by reading files directly.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
