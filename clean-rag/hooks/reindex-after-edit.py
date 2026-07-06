#!/usr/bin/env python3
"""clean-rag PostToolUse hook: incremental reindex after edits.

Fires after successful Edit/Write/MultiEdit. Sends the changed file
to the clean-rag server for incremental reindexing. This keeps the
project index fresh without requiring manual reindex commands.

The reindex request runs in a background thread so the hook returns
immediately and never blocks the editing flow. If the server is down
or the file is not in an indexed project, it silently does nothing.

Exit codes:
  0 = always (PostToolUse hooks should not block)
"""

import json
import os
import sys
import threading
import urllib.request
from pathlib import Path


def _clean_rag_home() -> Path:
    env = os.environ.get("CLEAN_RAG_HOME")
    if env:
        return Path(env)
    return Path(__file__).resolve().parent.parent


def _read_project_registry() -> dict:
    """Read state/projects.json to find indexed projects."""
    home = _clean_rag_home()
    reg_path = home / "state" / "projects.json"
    if not reg_path.exists():
        return {}
    try:
        return json.loads(reg_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _find_project_for_file(file_path: str) -> str | None:
    """Find which indexed project contains this file."""
    canonical = Path(file_path).resolve()
    registry = _read_project_registry()

    for pid, info in registry.items():
        proj_path = info.get("project_path", "")
        if not proj_path:
            continue
        try:
            proj_root = Path(proj_path).resolve()
            canonical.relative_to(proj_root)
            return str(proj_root)
        except ValueError:
            continue

    return None


def _send_reindex(project_path: str, file_path: str) -> None:
    """Send reindex request to clean-rag server. Runs in background thread."""
    port = os.environ.get("CLEAN_RAG_PORT", "8613")
    url = f"http://127.0.0.1:{port}/reindex-file"

    payload = json.dumps({
        "project_path": project_path,
        "file_path": file_path,
    }).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        urllib.request.urlopen(req, timeout=30)
    except Exception:
        pass


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read())
    except Exception:
        return 0

    tool_name = payload.get("tool_name", "")
    if tool_name not in ("Edit", "Write", "MultiEdit"):
        return 0

    tool_input = payload.get("tool_input", {})
    file_path = tool_input.get("file_path", "")
    if not file_path:
        return 0

    canonical = str(Path(file_path).resolve())

    # Skip files in clean-rag (internal files, not project code)
    home = _clean_rag_home()
    try:
        Path(canonical).relative_to(home)
        return 0
    except ValueError:
        pass

    # Skip doc extensions (rarely need code indexing)
    exempt_ext = {".md", ".mdx", ".rst", ".txt", ".gitignore", ".env.example"}
    if Path(canonical).suffix.lower() in exempt_ext:
        return 0

    # Find which indexed project this file belongs to
    project_path = _find_project_for_file(canonical)
    if not project_path:
        return 0

    # Fire and forget: background thread sends the reindex request
    t = threading.Thread(
        target=_send_reindex,
        args=(project_path, canonical),
        daemon=True,
    )
    t.start()

    return 0


if __name__ == "__main__":
    sys.exit(main())
