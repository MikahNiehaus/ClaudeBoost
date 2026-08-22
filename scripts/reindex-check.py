"""
ClaudeBoost reindex check — SessionStart command hook.

Detects when the git HEAD has changed since the last rag_index_project
call and warns Claude that the project RAG index may be stale. Common
triggers: branch switch, new commits pulled, rebase.

Reads state/last-indexed-head.json (written by project-rag-flag.py
after every successful rag_index_project call).

Behavior:
- If HEAD unchanged: exits silently (0)
- If HEAD changed: injects additionalContext warning with branch info
- If state file missing: exits silently (no baseline to compare against)
- If not a git repo: exits silently
- Always exits 0 (nudge, never blocks)
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from rag_port import rag_url


def main() -> int:
    home = Path(os.environ.get("CLAUDEBOOST_HOME") or os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..")
    ))
    state_file = home / "state" / "last-indexed-head.json"

    # No baseline — nothing to compare against, skip silently
    if not state_file.exists():
        return 0

    # Get current git HEAD and branch in one subprocess call instead of two.
    try:
        git_out = subprocess.check_output(
            ["git", "rev-parse", "HEAD", "--abbrev-ref", "HEAD"],
            stderr=subprocess.DEVNULL,
            cwd=str(home),
        ).decode().strip().splitlines()
        current_head = git_out[0] if len(git_out) > 0 else ""
        current_branch = git_out[1] if len(git_out) > 1 else ""
    except (subprocess.CalledProcessError, FileNotFoundError):
        return 0   # Not a git repo or git unavailable

    # Load last-indexed state
    try:
        data = json.loads(state_file.read_text(encoding="utf-8"))
        last_head = data.get("head", "")
        last_branch = data.get("branch", "")
    except Exception:
        return 0

    if not last_head or last_head == current_head:
        return 0   # Index is current

    # HEAD changed — warn
    if last_branch and last_branch != current_branch:
        change_note = f" (branch switched: {last_branch} -> {current_branch})"
    else:
        change_note = " (new commits since last index)"

    print(json.dumps({
        "additionalContext": (
            f"PROJECT RAG STALE{change_note}: "
            "The codebase search index is outdated. "
            # /index on 8612 was the retired server's route. clean-rag calls it
            # /index-project and takes no force flag.
            f"Call POST {rag_url('/index-project')} with "
            '{"project_path": "<cwd>"} '
            "before searching the codebase, stale results will mislead."
        )
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
