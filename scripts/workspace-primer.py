"""
ClaudeBoost workspace primer - SessionStart command hook.

When an active workspace is set in state/active-workspace.json, injects the
workspace identity into the session: workspace id, workspace path, and the
project path with its detected stack.

This used to print a RAG context tier breakdown (Tiers 0-4 plus Tier 3c) and
a POST /context call to fetch them. Both belonged to the retired bundled
server; /context has no clean-rag equivalent and the knowledge base those
tiers indexed was deleted, so the briefing described a system that no longer
exists.

Silent when no workspace is active.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from workspace_identity import get_instance_id, normalize_cwd, read_ws_instance, resolve_active_workspace


def _get_home() -> Path:
    return Path(os.environ.get("CLAUDEBOOST_HOME") or Path(__file__).parent.parent)


def _detect_stack(project_path: str) -> str:
    """Return a human-readable stack label by checking indicator files."""
    p = Path(project_path)
    if not p.is_dir():
        return ""
    stacks = []
    if (p / "go.mod").exists():
        stacks.append("Go")
    # Check for .csproj one level deep (avoids slow recursive glob on large repos)
    if any(p.glob("*.csproj")) or any((p / d).glob("*.csproj") for d in ("src", "app") if (p / d).is_dir()):
        stacks.append("C# / ASP.NET Core")
    if (p / "tsconfig.json").exists():
        stacks.append("TypeScript")
    elif (p / "package.json").exists():
        stacks.append("JavaScript / Node")
    if (p / "pyproject.toml").exists() or (p / "requirements.txt").exists():
        stacks.append("Python")
    if (p / "pom.xml").exists():
        stacks.append("Java")
    return " · ".join(stacks)


def main() -> int:
    home = _get_home()

    # Resolve active workspace for this Claude instance
    cwd_norm = normalize_cwd(os.getcwd())
    state_dir = home / "state"
    workspace_id = resolve_active_workspace(state_dir, cwd_norm)
    workspace_path = ""
    project_path = ""

    if not workspace_id:
        return 0

    # Fill in missing paths from the workspace registry
    if not workspace_path or not project_path:
        reg_path = home / "state" / "workspaces.json"
        try:
            reg = json.loads(reg_path.read_text(encoding="utf-8"))
            entry = reg.get(workspace_id, {})
            if not workspace_path:
                workspace_path = entry.get("workspace_path", "")
            if not project_path:
                project_path = entry.get("project_path", "")
        except Exception:
            pass

    # Fallback: active-workspace.json may have paths when registry doesn't
    if not workspace_path or not project_path:
        try:
            aw = json.loads((home / "state" / "active-workspace.json").read_text(encoding="utf-8"))
            if not workspace_path:
                workspace_path = aw.get("workspace_path", "")
            if not project_path:
                project_path = aw.get("project_path", "")
        except Exception:
            pass

    # Last resort: default ClaudeBoost workspace location
    if not workspace_path:
        candidate = home / "workspace" / workspace_id
        if candidate.is_dir():
            workspace_path = str(candidate)

    if not workspace_path:
        return 0

    stack = _detect_stack(project_path) if project_path else ""

    project_info = ""
    if project_path:
        project_info = f"\nProject:          {project_path}" + (f" ({stack})" if stack else "")

    briefing = (
        f"ACTIVE WORKSPACE: {workspace_id}\n"
        f"Workspace path:   {workspace_path}"
        f"{project_info}\n"
    )

    print(json.dumps({"additionalContext": briefing}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
