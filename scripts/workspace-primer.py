"""
ClaudeBoost workspace primer - SessionStart command hook.

When an active workspace is set in state/active-workspace.json, injects a
RAG tier briefing into the session: workspace path, project path, full tier
breakdown with token budgets, and Tier 3c status (EXISTS vs NOT BUILT).

This gives Claude a clear picture of what context is available before it
calls POST /context or spawns agents. Tier 3c task research is built
automatically by the research gate as agents edit code.

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


def _tier3c_status(workspace_path: str) -> tuple[bool, int]:
    """Check whether the Tier 3c research index exists and how many files it has."""
    research_dir = Path(workspace_path) / ".rag-index" / "research"
    if not research_dir.exists():
        return False, 0
    data_files = [f for f in research_dir.rglob("*") if f.is_file()]
    return True, len(data_files)


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
    tier3_suffix = f" (stack: {stack})" if stack else ""

    t3c_exists, t3c_files = _tier3c_status(workspace_path)
    if t3c_exists:
        t3c_line = f"  Tier 3c  Task research           ~400 tok  [EXISTS - {t3c_files} index files]\n"
        t3c_action = "Tier 3c is ready. Task research auto-loads when workspace_path is in /context.\n"
    else:
        t3c_line = "  Tier 3c  Task research           ~400 tok  [NOT BUILT - research gate builds it on code edits]\n"
        t3c_action = "Tier 3c is NOT BUILT yet. The research gate builds it automatically as agents edit code.\n"

    project_info = ""
    if project_path:
        project_info = f"\nProject:          {project_path}" + (f" ({stack})" if stack else "")

    context_body = (
        '  {\n'
        '    "agent": "...",\n'
        '    "task_description": "...",\n'
    )
    if project_path:
        context_body += f'    "project_path": "{project_path}",\n'
    context_body += f'    "workspace_path": "{workspace_path}"\n'
    context_body += '  }'

    briefing = (
        f"ACTIVE WORKSPACE: {workspace_id}\n"
        f"Workspace path:   {workspace_path}"
        f"{project_info}\n"
        "\n"
        "RAG CONTEXT TIERS - include workspace_path in every /context call:\n"
        "\n"
        "  POST http://127.0.0.1:8612/context\n"
        + context_body + "\n"
        "\n"
        "Token budget (~6000 tokens total):\n"
        "  Tier 0   Agent definition        ~200 tok   (always included)\n"
        "  Tier 1   Guardrails              ~800 tok   (always included)\n"
        "  Tier 2   Declared knowledge      ~400 tok   (agent-specific)\n"
        f"  Tier 3   General best practices ~1200 tok  (semantic search{tier3_suffix})\n"
        + t3c_line
        + "  Tier 4   Project codebase        ~3000 tok  (requires project_path and indexed project)\n"
        "\n"
        + t3c_action
    )

    print(json.dumps({"additionalContext": briefing}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
