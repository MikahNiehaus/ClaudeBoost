#!/usr/bin/env python3
"""clean-rag uninstaller. Removes hooks, env vars, and optionally databases.

Usage:
  python clean-rag/uninstall.py            # remove hooks + env, keep knowledge/databases
  python clean-rag/uninstall.py --purge    # also delete databases/ and state/
"""

import argparse
import json
import shutil
import sys
from pathlib import Path

CLEAN_RAG_HOME = Path(__file__).resolve().parent
CLAUDE_DIR = Path.home() / ".claude"
SETTINGS_PATH = CLAUDE_DIR / "settings.json"

HOOK_SENTINEL = "proof-gate.py"
SESSION_SENTINEL = "CLEAN-RAG ENFORCEMENT"


def _ok(msg: str) -> None:
    print(f"  [OK] {msg}")


def _skip(msg: str) -> None:
    print(f"  [SKIP] {msg}")


def read_json(path: Path, default=None):
    if default is None:
        default = {}
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def write_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def remove_hook() -> None:
    """Remove the proof-gate.py PreToolUse hook from settings.json."""
    settings = read_json(SETTINGS_PATH)
    hooks = settings.get("hooks", {})
    pre_tool = hooks.get("PreToolUse", [])

    if not isinstance(pre_tool, list):
        _skip("PreToolUse hooks not a list")
        return

    original_len = len(pre_tool)
    filtered = []
    for entry in pre_tool:
        keep = True
        for h in entry.get("hooks", []):
            if HOOK_SENTINEL in h.get("command", ""):
                keep = False
                break
        if keep:
            filtered.append(entry)

    if len(filtered) < original_len:
        hooks["PreToolUse"] = filtered
        write_json(SETTINGS_PATH, settings)
        _ok("Removed proof-gate hook from PreToolUse")
    else:
        _skip("proof-gate hook not found in PreToolUse")


def remove_session_prompt() -> None:
    """Remove the clean-rag SessionStart prompt."""
    settings = read_json(SETTINGS_PATH)
    hooks = settings.get("hooks", {})
    session = hooks.get("SessionStart", [])

    if not isinstance(session, list):
        _skip("SessionStart hooks not a list")
        return

    original_len = len(session)
    filtered = []
    for entry in session:
        keep = True
        for h in entry.get("hooks", []):
            if SESSION_SENTINEL in h.get("prompt", ""):
                keep = False
                break
        if keep:
            filtered.append(entry)

    if len(filtered) < original_len:
        hooks["SessionStart"] = filtered
        write_json(SETTINGS_PATH, settings)
        _ok("Removed clean-rag SessionStart prompt")
    else:
        _skip("clean-rag SessionStart prompt not found")


def remove_env_var() -> None:
    """Remove CLEAN_RAG_HOME from settings.json env."""
    settings = read_json(SETTINGS_PATH)
    env = settings.get("env", {})
    if "CLEAN_RAG_HOME" in env:
        del env["CLEAN_RAG_HOME"]
        write_json(SETTINGS_PATH, settings)
        _ok("Removed CLEAN_RAG_HOME env var")
    else:
        _skip("CLEAN_RAG_HOME not in settings env")


def stop_server() -> None:
    """Stop the clean-rag server if running."""
    server_json = CLEAN_RAG_HOME / "state" / "server.json"
    if not server_json.exists():
        _skip("No server PID file")
        return

    try:
        import os
        import signal

        info = json.loads(server_json.read_text(encoding="utf-8"))
        pid = info.get("pid")
        if pid:
            try:
                os.kill(pid, signal.SIGTERM)
                _ok(f"Sent SIGTERM to server PID {pid}")
            except (OSError, ProcessLookupError):
                _skip(f"Server PID {pid} not running")
        server_json.unlink(missing_ok=True)
    except Exception as e:
        _skip(f"Could not stop server: {e}")


def purge_data() -> None:
    """Delete databases/ and state/ directories."""
    for dirname in ["databases", "state"]:
        target = CLEAN_RAG_HOME / dirname
        if target.exists():
            shutil.rmtree(target, ignore_errors=True)
            _ok(f"Deleted {dirname}/")
        else:
            _skip(f"{dirname}/ not found")


def main():
    parser = argparse.ArgumentParser(description="Uninstall clean-rag")
    parser.add_argument("--purge", action="store_true",
                        help="Also delete databases/ and state/ (keeps knowledge/)")
    args = parser.parse_args()

    print("=" * 60)
    print("clean-rag uninstaller")
    print("=" * 60)
    print()

    print("Step 1: Stopping server...")
    stop_server()

    print("\nStep 2: Removing proof-gate hook...")
    remove_hook()

    print("\nStep 3: Removing SessionStart prompt...")
    remove_session_prompt()

    print("\nStep 4: Removing CLEAN_RAG_HOME env var...")
    remove_env_var()

    if args.purge:
        print("\nStep 5: Purging databases and state...")
        purge_data()
    else:
        print("\nStep 5: Keeping databases/ and state/ (use --purge to remove)")

    print()
    print("=" * 60)
    print("clean-rag uninstalled.")
    print()
    print("  Knowledge files kept at: clean-rag/knowledge/")
    if not args.purge:
        print("  Databases kept at: clean-rag/databases/")
        print("  Run with --purge to delete databases and state.")
    print("=" * 60)


if __name__ == "__main__":
    main()
