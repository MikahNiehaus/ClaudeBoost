#!/usr/bin/env python3
"""Remove clean-rag debug enforcement hooks.

Removes the debug-gate.py PreToolUse hook and deletes debug state files.
Normal proof-gate enforcement continues to work after this.

Usage:
  python clean-rag/debug-uninstall.py
"""

import json
import sys
from pathlib import Path

CLEAN_RAG_HOME = Path(__file__).resolve().parent
CLAUDE_DIR = Path.home() / ".claude"
SETTINGS_PATH = CLAUDE_DIR / "settings.json"

HOOK_SENTINEL = "debug-gate.py"


def _say(msg: str) -> None:
    print(f"  {msg}")


def _ok(msg: str) -> None:
    print(f"  [OK] {msg}")


def read_json(path: Path, default=None):
    if default is None:
        default = {}
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def remove_debug_hook() -> None:
    """Remove debug-gate.py from PreToolUse hooks."""
    settings = read_json(SETTINGS_PATH)
    hooks = settings.get("hooks", {})

    pre_tool_hooks = hooks.get("PreToolUse", [])
    if not isinstance(pre_tool_hooks, list):
        _ok("No PreToolUse hooks found")
        return

    filtered = []
    removed = False
    for entry in pre_tool_hooks:
        keep = True
        for h in entry.get("hooks", []):
            if HOOK_SENTINEL in h.get("command", ""):
                keep = False
                removed = True
                break
        if keep:
            filtered.append(entry)

    if removed:
        hooks["PreToolUse"] = filtered
        write_json(SETTINGS_PATH, settings)
        _ok("debug-gate hook removed")
    else:
        _ok("debug-gate hook was not registered")


def remove_debug_state() -> None:
    """Remove debug mode marker and fix-required files."""
    state_dir = CLEAN_RAG_HOME / "state"

    files_to_remove = [
        state_dir / "debug-mode.json",
        state_dir / "debug-fix-required.json",
    ]

    for f in files_to_remove:
        if f.exists():
            f.unlink()
            _ok(f"Removed {f.name}")
        else:
            _ok(f"{f.name} not present")


def main():
    print("=" * 50)
    print("clean-rag DEBUG enforcement remover")
    print("=" * 50)
    print()

    print("Step 1: Removing debug-gate hook...")
    remove_debug_hook()

    print("\nStep 2: Removing debug state files...")
    remove_debug_state()

    print()
    print("=" * 50)
    print("Debug enforcement removed.")
    print("Normal proof-gate enforcement still active.")
    print("=" * 50)


if __name__ == "__main__":
    main()
