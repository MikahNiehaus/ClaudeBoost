"""
get-active-workspace.py — Print the active workspace ID for this Claude instance.

Resolves the workspace via the shared workspace_identity module (per-instance
ws-instance file, then scan, then active-workspace.json fallback).

Output: JSON with workspace_id, workspace_path, project_path
        or {"workspace_id": "", "workspace_path": "", "project_path": ""} if none active.

Usage:
  python get-active-workspace.py
  python get-active-workspace.py --id-only   # just print the workspace ID (or empty)
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from workspace_identity import (
    get_boost_home,
    get_instance_id,
    normalize_cwd,
    read_ws_instance,
    resolve_active_workspace,
)


def resolve() -> dict:
    """Return workspace info for this Claude instance."""
    home = get_boost_home()
    state_dir = home / "state"
    cwd = normalize_cwd(os.getcwd())

    # 1+2. Shared module handles per-instance lookup and scan fallback
    workspace_id = resolve_active_workspace(state_dir, cwd)

    # 3. Fallback: most recently modified workspace in <cwd>/workspace/ that has context.md
    if not workspace_id:
        ws_dir = Path(cwd) / "workspace"
        try:
            best_mtime = 0.0
            for d in ws_dir.iterdir():
                if not d.is_dir() or d.name.startswith("."):
                    continue
                ctx = d / "context.md"
                if ctx.exists():
                    mtime = ctx.stat().st_mtime
                    if mtime > best_mtime:
                        best_mtime = mtime
                        workspace_id = d.name
        except Exception:
            pass

    if not workspace_id:
        return {"workspace_id": "", "workspace_path": "", "project_path": ""}

    # Resolve paths from registry
    workspace_path = ""
    project_path = ""
    try:
        reg = json.loads((state_dir / "workspaces.json").read_text(encoding="utf-8"))
        entry = reg.get(workspace_id, {})
        workspace_path = entry.get("workspace_path", "")
        project_path = entry.get("project_path", "")
    except Exception:
        pass

    # Last resort: check default location
    if not workspace_path:
        candidate = home / "workspace" / workspace_id
        if candidate.is_dir():
            workspace_path = str(candidate)

    instance_id = get_instance_id()

    return {
        "workspace_id": workspace_id,
        "workspace_path": workspace_path,
        "project_path": project_path,
        "instance_id": instance_id,
    }


def main() -> int:
    id_only = "--id-only" in sys.argv
    result = resolve()
    if id_only:
        print(result["workspace_id"])
    else:
        print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
