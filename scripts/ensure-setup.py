"""
ClaudeBoost ensure-setup: UserPromptSubmit hook that auto-runs setup.py
if CLAUDEBOOST_HOME is not configured in settings.json.

Installed to ~/.claude/ensure-setup.py by setup.py so the path is stable
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
_IS_WINDOWS = os.name == "nt"


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


def _find_setup_script() -> Path | None:
    """Locate setup.py via __file__ — works whether installed to ~/.claude/ or scripts/."""
    candidates = [
        Path(__file__).resolve().parent / "scripts" / "setup.py",  # ~/.claude/
        Path(__file__).resolve().parent.parent / "scripts" / "setup.py",  # repo/scripts/
        Path(__file__).resolve().parent / "setup.py",  # repo/scripts/ direct
    ]
    for p in candidates:
        if p.exists():
            return p
    return None


def main() -> int:
    if not _needs_setup():
        return 0

    setup_script = _find_setup_script()

    if setup_script is None:
        print(json.dumps({
            "additionalContext": (
                "CLAUDEBOOST SETUP REQUIRED: Cannot find setup.py. "
                "Navigate to your ClaudeBoost directory and run: "
                "python scripts/setup.py"
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
            "Running setup.py now in the background. "
            "Run /mcp in Claude Code once setup completes."
        )
    }))

    try:
        # Use the current Python interpreter so this works in venvs and on
        # systems where only `python3` (not `python`) is on PATH.
        popen_kwargs = {}
        if _IS_WINDOWS:
            # Detach from this hook so Claude Code's prompt isn't blocked.
            popen_kwargs["creationflags"] = 0x00000008  # DETACHED_PROCESS
        else:
            popen_kwargs["start_new_session"] = True
        subprocess.Popen(
            [sys.executable, str(setup_script)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            **popen_kwargs,
        )
    except Exception as e:
        print(json.dumps({
            "additionalContext": (
                f"CLAUDEBOOST AUTO-SETUP FAILED: {e}. "
                f"Run manually: {sys.executable} \"{setup_script}\""
            )
        }))

    return 0


if __name__ == "__main__":
    sys.exit(main())
