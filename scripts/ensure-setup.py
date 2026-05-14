"""
ClaudeBoost ensure-setup: UserPromptSubmit hook that auto-runs setup.ps1
if CLAUDEBOOST_HOME is not configured in settings.json.

Self-locating via __file__ — no CLAUDEBOOST_HOME dependency.
Fires first on every prompt; exits silently when setup is already done.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def _needs_setup() -> bool:
    # Fast path: env var already injected by settings.json env block
    if os.environ.get("CLAUDEBOOST_HOME"):
        return False
    # Slow path: settings.json exists but this session predates it being set
    settings_path = Path.home() / ".claude" / "settings.json"
    try:
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
        if settings.get("env", {}).get("CLAUDEBOOST_HOME"):
            return False
    except Exception:
        pass
    return True


def main() -> int:
    if not _needs_setup():
        return 0

    home = Path(__file__).resolve().parent.parent
    setup_ps1 = home / "scripts" / "setup.ps1"

    if not setup_ps1.exists():
        print(json.dumps({
            "additionalContext": (
                f"CLAUDEBOOST SETUP REQUIRED: Cannot find setup.ps1 at {setup_ps1}. "
                "Please re-clone ClaudeBoost and run setup manually."
            )
        }))
        return 0

    print(json.dumps({
        "additionalContext": (
            "CLAUDEBOOST AUTO-SETUP: CLAUDEBOOST_HOME is not configured on this machine. "
            "Running setup.ps1 now — a PowerShell window will open. "
            "Please restart Claude Code once setup completes."
        )
    }))

    try:
        subprocess.Popen([
            "powershell.exe", "-ExecutionPolicy", "Bypass",
            "-File", str(setup_ps1)
        ])
    except Exception as e:
        print(json.dumps({
            "additionalContext": (
                f"CLAUDEBOOST AUTO-SETUP FAILED: {e}. "
                f'Run manually: powershell -ExecutionPolicy Bypass -File "{setup_ps1}"'
            )
        }), file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
