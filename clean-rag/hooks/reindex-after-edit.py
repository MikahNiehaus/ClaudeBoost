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

import hashlib
import json
import logging
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


def _setup_logger() -> logging.Logger:
    """File only. This hook runs in a background thread on every edit, so
    anything it prints would land in the middle of the editing flow.
    """
    log = logging.getLogger("reindex-after-edit")
    if log.handlers:
        return log
    log.setLevel(logging.INFO)
    try:
        log_dir = _clean_rag_home() / "state"
        log_dir.mkdir(parents=True, exist_ok=True)
        handler = logging.FileHandler(log_dir / "reindex.log", encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        log.addHandler(handler)
    except Exception:
        log.addHandler(logging.NullHandler())
    return log


logger = _setup_logger()


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


def _manifest_path(project_path: str) -> Path:
    """Where the manifest actually lives.

    Mirrors _project_paths() in server/indexing.py:684. The manifest is stored
    inside clean-rag's own databases dir, keyed by a hash of the resolved
    project path. It is NOT a dotfile in the project root.
    """
    home = _clean_rag_home()
    project_root = Path(project_path).resolve()
    pid = hashlib.sha256(str(project_root).encode("utf-8")).hexdigest()[:12]
    return home / "databases" / "_projects" / pid / "manifest.json"


def _should_force_reindex(project_path: str) -> bool:
    """True only when the project has never been indexed, or its manifest is unreadable.

    This used to look for "<project>/.rag-manifest.json", a file nothing in this
    codebase has ever written. So it always returned True, and every single edit
    kicked off a force reindex of the entire repository instead of the cheap
    single file path right below it. The manifest it wanted was always over in
    databases/_projects/<pid>/manifest.json.
    """
    manifest_path = _manifest_path(project_path)
    if not manifest_path.exists():
        return True  # never indexed, so there's nothing to incrementally update

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        logger.warning("Manifest unreadable at %s, forcing full reindex", manifest_path)
        return True

    # Real shape is {"__project_path__": "...", "<rel_path>": "<hash>", ...}.
    # Anything else means it's corrupt and a full rebuild is the honest response.
    if not isinstance(manifest, dict) or "__project_path__" not in manifest:
        logger.warning("Manifest malformed at %s, forcing full reindex", manifest_path)
        return True

    return False


def _send_reindex(project_path: str, file_path: str) -> None:
    """Send reindex request to clean-rag server. Runs in background thread.

    Auto-detects when force reindexing is needed (hash mismatch, manifest
    corruption, first discovery). Defaults to incremental for performance.
    """
    port = os.environ.get("CLEAN_RAG_PORT", "8613")

    # Check if force reindex is needed
    force = _should_force_reindex(project_path)

    if force:
        # Force reindex entire project
        url = f"http://127.0.0.1:{port}/index-project"
        payload = json.dumps({
            "project_path": project_path,
            "force": True,
        }).encode("utf-8")
    else:
        # Incremental reindex single file
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
        urllib.request.urlopen(req, timeout=60)
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
