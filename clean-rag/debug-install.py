#!/usr/bin/env python3
"""Install clean-rag debug enforcement hooks (temporary).

Registers debug-gate.py as a PreToolUse hook and creates the
debug-mode.json marker. While active, every proof-gate rejection
forces Claude to analyze the mistake and fix clean-rag before
continuing with any other edits.

Usage:
  python clean-rag/debug-install.py       # install debug hooks
  python clean-rag/debug-uninstall.py     # remove debug hooks
"""

import json
import sys
from datetime import datetime, timezone
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


def register_debug_hook() -> None:
    """Register debug-gate.py as a PreToolUse hook."""
    settings = read_json(SETTINGS_PATH)
    hooks = settings.setdefault("hooks", {})

    hook_command = f'python "{CLEAN_RAG_HOME.as_posix()}/hooks/debug-gate.py"'

    hook_entry = {
        "matcher": "Edit|Write|MultiEdit",
        "hooks": [
            {
                "type": "command",
                "command": hook_command,
            }
        ],
    }

    pre_tool_hooks = hooks.get("PreToolUse", [])
    if not isinstance(pre_tool_hooks, list):
        pre_tool_hooks = []

    # Check if already registered
    for existing in pre_tool_hooks:
        for h in existing.get("hooks", []):
            cmd = h.get("command", "")
            if HOOK_SENTINEL in cmd:
                if cmd != hook_command:
                    h["command"] = hook_command
                    _ok("debug-gate hook path refreshed")
                else:
                    _ok("debug-gate hook already registered")
                write_json(SETTINGS_PATH, settings)
                return

    # Add after proof-gate (proof-gate should fire first)
    # Find proof-gate position
    proof_gate_idx = -1
    for i, entry in enumerate(pre_tool_hooks):
        for h in entry.get("hooks", []):
            if "proof-gate.py" in h.get("command", ""):
                proof_gate_idx = i
                break

    if proof_gate_idx >= 0:
        pre_tool_hooks.insert(proof_gate_idx + 1, hook_entry)
    else:
        pre_tool_hooks.insert(0, hook_entry)

    hooks["PreToolUse"] = pre_tool_hooks
    write_json(SETTINGS_PATH, settings)
    _ok("debug-gate hook registered (PreToolUse, after proof-gate)")


def create_debug_mode_marker() -> None:
    """Create the debug-mode.json marker file."""
    state_dir = CLEAN_RAG_HOME / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    marker = state_dir / "debug-mode.json"
    data = {
        "active": True,
        "installed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "mistake_count": 0,
    }
    marker.write_text(json.dumps(data, indent=2), encoding="utf-8")
    _ok("debug-mode.json marker created")


def main():
    print("=" * 50)
    print("clean-rag DEBUG enforcement installer")
    print("=" * 50)
    print()
    print("This is TEMPORARY. Remove with debug-uninstall.py")
    print()

    print("Step 1: Registering debug-gate hook...")
    register_debug_hook()

    print("\nStep 2: Creating debug mode marker...")
    create_debug_mode_marker()

    print()
    print("=" * 50)
    print("Debug enforcement active!")
    print()
    print("Every proof-gate rejection now forces you to:")
    print("  1. Analyze the mistake")
    print("  2. Fix clean-rag to prevent it")
    print("  3. Delete state/debug-fix-required.json")
    print()
    print("Remove with: python clean-rag/debug-uninstall.py")
    print("=" * 50)


if __name__ == "__main__":
    main()
