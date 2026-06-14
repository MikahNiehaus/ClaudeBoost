"""Flip the bash-guard.py off-switch in settings.json.

bash-guard.py (the PreToolUse Bash hook) reads CLAUDEBOOST_BASH_GUARD from the
env block of ~/.claude/settings.json. When it's "off" the guard passes every
command through. This script sets or clears that key without disturbing the rest
of settings.json, safer than hand-editing a big shared JSON file.

Usage:
    python scripts/toggle-bash-guard.py status   # report current setting (default)
    python scripts/toggle-bash-guard.py off       # disable the guard
    python scripts/toggle-bash-guard.py on        # re-enable the guard (removes the key)

The /bash-guard slash command wraps this.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

KEY = "CLAUDEBOOST_BASH_GUARD"
SETTINGS_PATH = Path.home() / ".claude" / "settings.json"
# Values bash-guard.py treats as "off" (see check at the top of its main()).
OFF_VALUES = {"off", "0", "false", "disabled", "no"}


def _load() -> dict:
    try:
        return json.loads(SETTINGS_PATH.read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError:
        print(f"ERROR: {SETTINGS_PATH} is malformed JSON. Fix it by hand, then retry.")
        sys.exit(1)


def _save(settings: dict) -> None:
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_PATH.write_text(json.dumps(settings, indent=2), encoding="utf-8")


def _is_off(value: str | None) -> bool:
    return (value or "").strip().lower() in OFF_VALUES


def main() -> int:
    action = (sys.argv[1].lower() if len(sys.argv) > 1 else "status")

    settings = _load()
    env = settings.get("env") or {}
    current = env.get(KEY)

    if action in ("status", ""):
        state = "OFF (guard disabled)" if _is_off(current) else "ON (guard active)"
        print(f"bash-guard is {state}")
        print(f"  {KEY} = {current!r} in {SETTINGS_PATH}")
        return 0

    if action in ("off", "disable", "stop"):
        env[KEY] = "off"
        settings["env"] = env
        _save(settings)
        print("bash-guard DISABLED, Bash commands now pass through unguarded.")
        print(f"  set {KEY}=off in {SETTINGS_PATH}")
        print("  Re-enable any time with: /bash-guard on")
        return 0

    if action in ("on", "enable", "start"):
        if KEY in env:
            del env[KEY]
            if env:
                settings["env"] = env
            else:
                settings.pop("env", None)
            _save(settings)
            print("bash-guard ENABLED, the safety guard is active again.")
            print(f"  removed {KEY} from {SETTINGS_PATH}")
        else:
            print("bash-guard already ENABLED, no off-switch was set.")
        return 0

    print(f"Unknown action {action!r}. Use: on | off | status")
    return 2


if __name__ == "__main__":
    sys.exit(main())
