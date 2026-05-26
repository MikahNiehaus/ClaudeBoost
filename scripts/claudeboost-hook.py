"""
ClaudeBoost hook runner — validates and executes ClaudeBoost hook scripts.

This is the ONLY Python script Claude has automatic Bash permission to run.
All other python calls require user approval.

Usage:
    python claudeboost-hook.py <script-name.py> [args...]

Only scripts in WHITELIST may be executed. The script name is extracted from
the argument (any path prefix is stripped), so callers cannot escape scripts/
by providing a path.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

# Explicit whitelist — only these scripts may be executed via this runner.
# Add new hook scripts here when they are created.
WHITELIST = {
    "agent-spawn-gate.py",
    "bash-guard.py",
    "check-rag-health.py",
    "comment-humanness-check.py",
    "compaction-primer.py",
    "compaction-restore.py",
    "compaction-save.py",
    "consult-gate.py",
    "context-nudge.py",
    "project-rag-flag.py",
    "rag-agent-guard.py",
    "rag-error-guard.py",
    "reindex-check.py",
    "session-clear-save.py",
    "session-primer.py",
    "speak-stop.py",
    "speak-tts.py",
    "stop-context-guard.py",
}


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: claudeboost-hook.py <script-name.py>", file=sys.stderr)
        return 1

    # Strip any path prefix the caller may have included — name only
    script_name = os.path.basename(sys.argv[1])

    if script_name not in WHITELIST:
        print(
            f"BLOCKED: {script_name!r} is not in the ClaudeBoost hook whitelist.",
            file=sys.stderr,
        )
        return 1

    home = Path(os.environ.get("CLAUDEBOOST_HOME") or os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..")
    ))
    script_path = home / "scripts" / script_name

    if not script_path.exists():
        print(f"BLOCKED: script not found at {script_path}", file=sys.stderr)
        return 1

    # Run the script, passing stdin/stdout/stderr through unchanged
    result = subprocess.run(
        [sys.executable, str(script_path)] + sys.argv[2:],
        stdin=sys.stdin,
        stdout=sys.stdout,
        stderr=sys.stderr,
    )
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
