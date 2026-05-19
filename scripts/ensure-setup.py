"""
ClaudeBoost ensure-setup: UserPromptSubmit hook that auto-runs setup.ps1
if CLAUDEBOOST_HOME is not configured in settings.json.

Installed to ~/.claude/ensure-setup.py by setup.ps1 so the path is stable
across machines regardless of where ClaudeBoost is cloned.

Self-locating via __file__ — no CLAUDEBOOST_HOME dependency.
Fires first on every prompt; exits silently when setup is already done.

Sentinel file (~/.claude/.ensure-setup-triggered) prevents spawning multiple
setup windows when the user types before restarting Claude Code.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

_SENTINEL = Path.home() / ".claude" / ".ensure-setup-triggered"


def _needs_setup() -> bool:
    # Fast path: env var already injected by settings.json env block
    if os.environ.get("CLAUDEBOOST_HOME"):
        return False
    # Sentinel: setup was already triggered this session — don't spawn again
    if _SENTINEL.exists():
        return False
    # Slow path: settings.json exists but this session predates it being set
    settings_path = Path.home() / ".claude" / "settings.json"
    try:
        settings = json.loads(settings_path.read_text(encoding="utf-8-sig"))
        if settings.get("env", {}).get("CLAUDEBOOST_HOME"):
            return False
    except (json.JSONDecodeError, OSError):
        pass
    return True


def _find_setup_ps1() -> Path | None:
    """Locate setup.ps1 via __file__ (works whether installed to ~/.claude or scripts/)."""
    candidates = [
        Path(__file__).resolve().parent / "scripts" / "setup.ps1",  # ~/.claude/
        Path(__file__).resolve().parent.parent / "scripts" / "setup.ps1",  # repo/scripts/
    ]
    for p in candidates:
        if p.exists():
            return p
    return None


def main() -> int:
    if not _needs_setup():
        return 0

    setup_ps1 = _find_setup_ps1()

    if setup_ps1 is None:
        print(json.dumps({
            "additionalContext": (
                "CLAUDEBOOST SETUP REQUIRED: Cannot find setup.ps1. "
                "Run: powershell -ExecutionPolicy Bypass -File "
                "\"C:/Development/ClaudeBoost/scripts/setup.ps1\""
            )
        }))
        return 0

    # Write sentinel BEFORE Popen so concurrent prompts don't spawn more windows
    try:
        _SENTINEL.touch()
    except OSError:
        pass

    print(json.dumps({
        "additionalContext": (
            "CLAUDEBOOST AUTO-SETUP: CLAUDEBOOST_HOME is not configured on this machine. "
            "Running setup.ps1 now — a PowerShell window will open. "
            "Run /mcp in Claude Code once setup completes."
        )
    }))

    try:
        subprocess.Popen([
            "powershell.exe", "-ExecutionPolicy", "Bypass",
            "-File", str(setup_ps1)
        ])
    except Exception as e:
        # Print to stdout so Claude Code surfaces it via additionalContext
        print(json.dumps({
            "additionalContext": (
                f"CLAUDEBOOST AUTO-SETUP FAILED: {e}. "
                f"Run manually: powershell -ExecutionPolicy Bypass -File \"{setup_ps1}\""
            )
        }))

    return 0


if __name__ == "__main__":
    sys.exit(main())
