"""
ClaudeBoost rag-read-guard -- PreToolUse hook on Grep and Read.

Hard-blocks file searching when Claude has made too many file reads without
calling a RAG tool first. RAG finds the relevant file; Grep/Read reads it.
Doing it backwards (Read first, RAG never) is the pattern this guard catches.

Also blocks if RAG is available but Claude proceeds after a RAG error --
the session-primer HARD STOP should have caught this, but this is the backstop.

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

RAG_THRESHOLD = 4  # block after this many consecutive file searches without RAG

# Always allow reads of these paths -- no RAG needed for config/workspace files
EXEMPTED_SUFFIXES = {".json", ".md", ".lock", ".env", ".gitignore", ".toml", ".yaml", ".yml"}
EXEMPTED_NAME_FRAGMENTS = {
    "context.md", "settings", "claude.md", "memory", "package", "requirements",
    "cargo.toml", "pyproject", "go.mod", "go.sum", "tsconfig",
}


def is_exempted(tool_input: dict) -> bool:
    """Return True if this file read should be allowed without a prior RAG call."""
    path_str = str(tool_input.get("file_path", "") or tool_input.get("path", "") or "").lower()
    pattern_str = str(tool_input.get("pattern", "")).lower()

    # Allow reads on workspace/state/config files
    if any(frag in path_str for frag in EXEMPTED_NAME_FRAGMENTS):
        return True
    if Path(path_str).suffix in EXEMPTED_SUFFIXES:
        return True
    # Allow glob/grep on non-source patterns (e.g. workspace/**)
    if "workspace" in pattern_str or "state/" in pattern_str:
        return True

    return False


def main() -> int:
    raw = sys.stdin.read() if not sys.stdin.isatty() else ""
    try:
        payload = json.loads(raw) if raw else {}
    except Exception:
        payload = {}

    tool_input = payload.get("tool_input") or {}

    if is_exempted(tool_input):
        return 0

    # Only block if RAG is actually available -- no point enforcing when RAG is offline
    temp = os.environ.get("TEMP") or os.environ.get("TMPDIR") or "/tmp"
    sentinel = Path(temp) / "claudeboost_rag_ok"
    if not sentinel.exists():
        return 0  # RAG unavailable -- let reads through, session-primer handles the rest

    home = Path(os.environ.get("CLAUDEBOOST_HOME") or Path(__file__).resolve().parent.parent)
    tracker_path = home / "state" / "behavior-tracker.json"

    try:
        behavior = json.loads(tracker_path.read_text(encoding="utf-8"))
    except Exception:
        return 0  # no tracker -- can't enforce, allow

    reads_since_rag = behavior.get("reads_since_rag", 0)

    if reads_since_rag < RAG_THRESHOLD:
        return 0

    tool_name = payload.get("tool_name", "Grep/Read")
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
