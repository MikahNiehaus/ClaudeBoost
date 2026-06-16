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

    # Read the active workspace so the compaction summary is anchored to it
    workspace_line = ""
    try:
        active = json.loads(
            (home / "state" / "active-workspace.json").read_text(encoding="utf-8")
        )
        ws_id = active.get("workspace", "").strip()
        ws_path = active.get("workspace_path", "").strip()
        proj_path = active.get("project_path", "").strip()
        if ws_id:
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
