"""Emergency hook repair — cross-platform (Windows, macOS, Linux).

Removes hook entries that block Claude Code's prompt submission:
  1. Commands containing a literal $CLAUDEBOOST_HOME bash variable reference
     (set by older setup versions; fail when the env var isn't in the env block).
  2. Commands referencing a script path that no longer exists on disk
     (e.g. ensure-setup.py copied from a machine with a different repo path).

Run this BEFORE setup.py when Claude Code is completely blocked:
    python scripts/fix_hooks.py

No prerequisites — does NOT require CLAUDEBOOST_HOME, the RAG server, or
Claude Code itself.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

SETTINGS_PATH = Path.home() / ".claude" / "settings.json"
SENTINEL_PATH = Path.home() / ".claude" / ".ensure-setup-triggered"

# ANSI colors — match setup.py's behavior so output looks consistent.
_USE_COLOR = sys.stdout.isatty()
_CYAN = "\033[36m" if _USE_COLOR else ""
_GREEN = "\033[32m" if _USE_COLOR else ""
_YELLOW = "\033[33m" if _USE_COLOR else ""
_RED = "\033[31m" if _USE_COLOR else ""
_RESET = "\033[0m" if _USE_COLOR else ""


def _ok(msg: str)    -> None: print(f"{_GREEN}[OK] {msg}{_RESET}")
def _warn(msg: str)  -> None: print(f"{_YELLOW}{msg}{_RESET}")
def _err(msg: str)   -> None: print(f"{_RED}[ERROR] {msg}{_RESET}")


def hook_stale(command: str) -> bool:
    if "$CLAUDEBOOST_HOME" in command:
        return True
    m = re.search(r'"([^"]+\.py)"', command)
    if m:
        candidate = m.group(1)
        # Skip paths that still contain env-var references — we can't verify
        # them without expansion, and they are intentionally machine-portable.
        if "$" in candidate or "%" in candidate:
            return False
        if not Path(candidate).exists():
            return True
    return False


def main() -> int:
    print(f"\n{_CYAN}=== ClaudeBoost Hook Repair ==={_RESET}")
    print(f"Settings: {SETTINGS_PATH}\n")

    if not SETTINGS_PATH.exists():
        _ok("settings.json not found - fresh install, nothing to fix.")
        return 0

    try:
        settings = json.loads(SETTINGS_PATH.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as e:
        _err(f"settings.json is malformed JSON: {e}")
        _err("  Fix the JSON manually then re-run this script.")
        return 1

    hooks = settings.get("hooks")
    if not hooks:
        _ok("No hooks block found - nothing to fix.")
        return 0

    removed = 0
    for hook_type in list(hooks.keys()):
        entries = hooks.get(hook_type) or []
        new_entries = []
        for entry in entries:
            inner = entry.get("hooks") if isinstance(entry, dict) else None
            if not inner:
                new_entries.append(entry)
                continue
            healthy = []
            for h in inner:
                cmd = h.get("command", "") if isinstance(h, dict) else ""
                if cmd and hook_stale(cmd):
                    preview = cmd[:72]
                    _warn(f"[REMOVE] hooks.{hook_type} : {preview}")
                    removed += 1
                else:
                    healthy.append(h)
            if healthy:
                entry["hooks"] = healthy
                new_entries.append(entry)
            # else: every hook in this entry was stale — drop the entry too
        if new_entries:
            hooks[hook_type] = new_entries
        else:
            del hooks[hook_type]

    # Clear the ensure-setup sentinel so the bootstrap hook can re-fire after repair.
    if SENTINEL_PATH.exists():
        try:
            SENTINEL_PATH.unlink()
            _ok("Cleared ensure-setup sentinel")
        except OSError:
            pass

    if removed == 0:
        _ok("No stale hooks found - nothing to fix.")
        return 0

    try:
        SETTINGS_PATH.write_text(json.dumps(settings, indent=2), encoding="utf-8")
    except OSError as e:
        _err(f"Failed to write settings.json: {e}")
        _err("  Is the file open in another process? Close Claude Code and retry.")
        return 1

    print("")
    _ok(f"Removed {removed} stale hook(s) from settings.json")
    print("")
    print(f"{_YELLOW}Next steps:{_RESET}")
    print(f"  1. Run full setup:  {sys.executable} {Path(__file__).parent / 'setup.py'}")
    print( "  2. Run /rag in Claude Code to start the RAG server")
    return 0


if __name__ == "__main__":
    sys.exit(main())
