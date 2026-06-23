"""
ClaudeBoost ensure-setup: UserPromptSubmit hook that auto-runs setup.py
if CLAUDEBOOST_HOME is not configured in settings.json.

Installed to ~/.claude/ensure-setup.py by setup.py so the path is stable
across machines regardless of where ClaudeBoost is cloned.

Locates setup.py via ~/.claude/claudeboost-home.txt (written by setup.py on
first install) with a __file__-relative fallback. No CLAUDEBOOST_HOME dependency.
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
    # Sentinel: setup was already triggered this session — don't spawn again
    if _SENTINEL.exists():
        return False
    # Fast path: CLAUDEBOOST_HOME env present. Also check CLAUDEBOOST_PYTHON.
    if os.environ.get("CLAUDEBOOST_HOME"):
        py_path = os.environ.get("CLAUDEBOOST_PYTHON", "")
        # If CLAUDEBOOST_PYTHON is set to a path that no longer exists on this
        # machine (e.g. after copying settings.json from another machine), every
        # hook command will fail. Re-run setup.py to fix CLAUDEBOOST_PYTHON.
        if py_path and not Path(py_path).exists():
            return True
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
    """Locate setup.py. Works when running from ~/.claude/ or directly from scripts/."""
    candidates = []

    # Primary: read the path that setup.py wrote on first install. This works even
    # when this file is copied outside the repo (e.g. ~/.claude/ensure-setup.py).
    home_file = Path.home() / ".claude" / "claudeboost-home.txt"
    try:
        boost_home = Path(home_file.read_text(encoding="utf-8").strip())
        candidates.append(boost_home / "scripts" / "setup.py")
    except OSError:
        pass

    # Fallback: __file__-relative search for when the script is run from the repo
    here = Path(__file__).resolve().parent
    candidates += [
        here / "setup.py",               # running as scripts/ensure-setup.py
        here.parent / "scripts" / "setup.py",  # running from repo root
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
