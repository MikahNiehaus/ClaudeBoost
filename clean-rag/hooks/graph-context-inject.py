#!/usr/bin/env python3
"""clean-rag caller-context + reflective-nudge hook: PreToolUse on Edit|Write|MultiEdit.

Plan Stage 5 + Stage 7. Two things happen automatically before every real
edit, neither of which can fail the edit:

1. Caller context (Stage 5): looks up who actually calls/imports/inherits
   the file being edited, directly from the local graph.db -- not through
   vector-seeded /search (which would probabilistically guess at the seed
   file rather than knowing it exactly), so no HTTP round-trip and no
   dependency on the clean-rag server being up. If real callers are found,
   writes a search-log.jsonl entry in the same shape _log_search() would,
   so it's a normal citable search_id usable later in /prove -- Stage 4's
   caller-evidence requirement can be satisfied by this automatic fetch
   instead of the agent remembering to search for it.
2. Reflective nudge (Stage 7): a short, change-type-aware "did you
   consider X" prompt, matching the Do-Confirm checklist pattern (pause to
   confirm, not to teach) -- printed every time, never blocking, distinct
   from the hard requirements in handle_prove.

Exit code is always 0 -- this hook only informs, never blocks. proof-gate.py
is the separate hook that actually gates edits.
"""
from __future__ import annotations
import hashlib
import json
import re
import sys
import tempfile
from pathlib import Path

_CLEAN_RAG_ROOT = Path(__file__).resolve().parent.parent
if str(_CLEAN_RAG_ROOT) not in sys.path:
    sys.path.insert(0, str(_CLEAN_RAG_ROOT))


# ---------------------------------------------------------------------------
# Path helpers (small, self-contained copies -- hooks are meant to be
# independently runnable, matching proof-gate.py's own style, rather than
# cross-importing between hook scripts)
# ---------------------------------------------------------------------------

EXEMPT_SEGMENTS = ["workspace", "knowledge", "plans", "docs", "state", ".claudeboost", ".claude"]


def _canonicalize(file_path: str) -> str:
    try:
        resolved = Path(file_path).resolve()
    except (OSError, ValueError):
        resolved = Path(file_path)
    return resolved.as_posix().lower()


def _path_has_segment(canonical_path: str, segment: str) -> bool:
    parts = canonical_path.split("/")
    return segment.strip("/").lower() in parts


def _is_temp_path(canonical_path: str) -> bool:
    try:
        temp_dir = Path(tempfile.gettempdir()).resolve().as_posix().lower()
        return canonical_path.startswith(temp_dir + "/") or canonical_path == temp_dir
    except Exception:
        return False


def _detect_project_root(file_path: str) -> Path | None:
    try:
        current = Path(file_path).resolve().parent
    except (OSError, ValueError):
        return None
    for _ in range(15):
        if (current / ".git").exists():
            return current
        parent = current.parent
        if parent == current:
            break
        current = parent
    return None


# ---------------------------------------------------------------------------
# Caller-context lookup (Stage 5)
# ---------------------------------------------------------------------------

def _fetch_caller_context(file_path: str, project_root: Path) -> dict | None:
    """Direct local graph lookup -- no HTTP, no vector seeding, no server
    dependency. Returns None if there's no graph for this project."""
    pid = hashlib.sha256(str(project_root).encode("utf-8")).hexdigest()[:12]
    databases_dir = _clean_rag_databases_dir()
    graph_db_path = databases_dir / "_projects" / pid / "graph.db"
    if not graph_db_path.exists():
        return None

    try:
        from server.graph_store import SQLiteGraphStore
    except ImportError:
        return None

    try:
        rel_path = Path(file_path).resolve().relative_to(project_root).as_posix()
    except ValueError:
        return None

    try:
        graph = SQLiteGraphStore(str(graph_db_path))
        if not graph.has_graph():
            return None
        edges = graph.get_neighbours(rel_path, depth=2, direction="callers")
    except Exception:
        return None

    callers = sorted({e.source_file for e in edges if e.source_file and e.source_file != rel_path})
    return {"rel_path": rel_path, "callers": callers, "pid": pid, "graph_db_path": graph_db_path}


def _clean_rag_databases_dir() -> Path:
    try:
        from server.config import DATABASES_DIR
        return DATABASES_DIR
    except ImportError:
        return _CLEAN_RAG_ROOT / "databases"


def _log_caller_search(file_path: str, project_root: Path, callers: list[str]) -> str | None:
    """Write a search-log.jsonl entry in the same shape _log_search()
    produces, so this auto-fetch is a normal citable search_id."""
    import uuid
    from datetime import datetime, timezone

    state_dir = _CLEAN_RAG_ROOT / "state"
    search_log_path = state_dir / "search-log.jsonl"
    search_id = uuid.uuid4().hex[:16]
    entry = {
        "search_id": search_id,
        "ts": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "query": f"auto-injected caller context for {file_path}",
        "sources": [f"project:{project_root}"],
        "mode": "graph",
        "results_count": len(callers),
        "top_score": 1.0,  # deterministic direct graph lookup, not a similarity estimate
        "graph_status": "hit" if callers else "empty",
        "graph_hit_count": len(callers),
        "caller_count": len(callers),
    }
    try:
        state_dir.mkdir(parents=True, exist_ok=True)
        with open(search_log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except OSError:
        return None
    return search_id


# ---------------------------------------------------------------------------
# Reflective nudge (Stage 7)
# ---------------------------------------------------------------------------

_NUDGES_BY_EXT: dict[str, list[str]] = {
    ".py": ["error handling for the failure paths", "backward compatibility for existing callers"],
    ".ts": ["type safety at the boundaries", "async error handling"],
    ".tsx": ["re-render behavior", "accessibility of the changed UI"],
    ".js": ["error handling for the failure paths", "backward compatibility for existing callers"],
    ".sql": ["migration safety on existing data", "index impact"],
    ".yaml": ["what breaks if this config is missing/malformed", "default values for new keys"],
    ".yml": ["what breaks if this config is missing/malformed", "default values for new keys"],
}
_GENERIC_NUDGES = ["edge cases (empty/null/huge input)", "concurrency if this runs more than once at a time", "test coverage for this change"]


def _reflective_nudge(file_path: str, is_new_file: bool) -> str:
    ext = Path(file_path).suffix.lower()
    specific = _NUDGES_BY_EXT.get(ext, [])
    picks = (specific[:1] + _GENERIC_NUDGES[:1]) if specific else _GENERIC_NUDGES[:2]
    if is_new_file:
        picks = ["whether an existing library/pattern already does this"] + picks[:1]
    return "; ".join(picks)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    raw = sys.stdin.read() if not sys.stdin.isatty() else ""
    try:
        payload = json.loads(raw) if raw else {}
    except Exception:
        return 0

    tool_name = payload.get("tool_name", "")
    if tool_name not in ("Edit", "Write", "MultiEdit"):
        return 0

    tool_input = payload.get("tool_input", {}) or {}
    file_path = tool_input.get("file_path", "")
    if not file_path:
        return 0

    canonical = _canonicalize(file_path)
    for seg in EXEMPT_SEGMENTS:
        if _path_has_segment(canonical, seg):
            return 0
    if _is_temp_path(canonical):
        return 0

    is_new_file = tool_name == "Write" and not Path(file_path).exists()
    lines = []

    project_root = _detect_project_root(file_path)
    if project_root:
        ctx = _fetch_caller_context(file_path, project_root)
        if ctx is not None:
            search_id = _log_caller_search(file_path, project_root, ctx["callers"])
            if ctx["callers"]:
                lines.append(
                    f"[graph-context] {len(ctx['callers'])} file(s) call/import/inherit from "
                    f"{ctx['rel_path']}: {', '.join(ctx['callers'][:8])}"
                    + (f" (+{len(ctx['callers']) - 8} more)" if len(ctx["callers"]) > 8 else "")
                )
            else:
                lines.append(f"[graph-context] No callers found for {ctx['rel_path']} (real leaf file, or check the seed).")
            if search_id:
                lines.append(f"[graph-context] search_id={search_id} -- citable directly in /prove as the codebase angle.")

    lines.append(f"[reflect] Before this change, consider: {_reflective_nudge(file_path, is_new_file)}.")

    if lines:
        print("\n".join(lines), file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
