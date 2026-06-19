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


def main() -> int:
    home = Path(os.environ.get("CLAUDEBOOST_HOME") or os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..")
    ))

    # Read the active workspace for this project so the compaction summary is anchored to it
    workspace_line = ""
    try:
        cwd_norm = os.getcwd().replace("\\", "/").rstrip("/")
        pws = json.loads((home / "state" / "project-workspaces.json").read_text(encoding="utf-8"))
        ws_id = pws.get(cwd_norm)
        if ws_id is None:
            cwd_lower = cwd_norm.lower()
            for key, val in pws.items():
                if key.replace("\\", "/").rstrip("/").lower() == cwd_lower:
                    ws_id = val
                    break
        if ws_id and isinstance(ws_id, str):
            reg = json.loads((home / "state" / "workspaces.json").read_text(encoding="utf-8"))
            entry = reg.get(ws_id, {})
            ws_path = entry.get("workspace_path", "").strip()
            proj_path = entry.get("project_path", "").strip()
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
            + "STANDING ORDERS (re-injected before compaction): "
            "Search RAG before reading files. "
            "Cite file:line for every finding. "
            "Spawn evaluator-agent — never self-verify. "
            "CONSULT before new endpoints/tables/dependencies. "
            "POST http://127.0.0.1:8612/context first in every agent spawn prompt."
        )
    }))
    sys.exit(0)


if __name__ == "__main__":
    main()
