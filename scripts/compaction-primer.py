#!/usr/bin/env python3
"""
PreCompact hook: re-inject standing orders and active workspace identity
immediately before context compaction. Ensures behavior rules and workspace
context survive the compaction boundary and are present in the summary
that Claude builds from compressed context.

Exit codes:
  0 = always (this hook never blocks)
"""
import json
import os
import sys
from pathlib import Path

from workspace_identity import normalize_cwd, resolve_active_workspace


def main() -> int:
    home = Path(os.environ.get("CLAUDEBOOST_HOME") or os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..")
    ))

    # Read the active workspace so the compaction summary is anchored to it
    workspace_line = ""
    try:
        cwd_norm = normalize_cwd(os.getcwd())
        state_dir = home / "state"
        ws_id = resolve_active_workspace(state_dir, cwd_norm)
        if ws_id:
            reg = json.loads((state_dir / "workspaces.json").read_text(encoding="utf-8"))
            entry = reg.get(ws_id, {})
            ws_path = entry.get("workspace_path", "").strip()
            proj_path = entry.get("project_path", "").strip()
            if not ws_path or not proj_path:
                try:
                    aw = json.loads((state_dir / "active-workspace.json").read_text(encoding="utf-8"))
                    if not ws_path:
                        ws_path = aw.get("workspace_path", "")
                    if not proj_path:
                        proj_path = aw.get("project_path", "")
                except Exception:
                    pass
            parts = [f"ACTIVE WORKSPACE: {ws_id}"]
            if ws_path:
                parts.append(f"  workspace_path: {ws_path}")
            if proj_path:
                parts.append(f"  project_path:   {proj_path}")
            workspace_line = "\n".join(parts) + "\n\n"
    except Exception:
        pass

    print(json.dumps({
        "additionalContext": (
            workspace_line
            # evaluator-agent and POST /context both went away with the 8612
            # server. Naming them here sent every post compaction turn after
            # machinery that does not exist.
            + "STANDING ORDERS (re-injected before compaction): "
            "Search RAG before reading files. "
            "Cite file:line for every finding. "
            "Verify with bad-cop in a fresh context, never self review your own diff. "
            "CONSULT before new endpoints, tables or dependencies. "
            "The full rules are in CLAUDE.md."
        )
    }))
    sys.exit(0)


if __name__ == "__main__":
    main()
