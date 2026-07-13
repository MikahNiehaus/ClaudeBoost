#!/usr/bin/env python3
"""clean-rag uninstaller. Un-enforces clean-rag. Keeps your data and dependencies.

Its whole job is to make sure nothing clean-rag installed is still enforcing
anything, so editing code is never blocked by a gate whose server or agents are
gone. It does NOT pip-uninstall anything and does NOT delete your indexes unless
you ask.

Usage:
  python clean-rag/uninstall.py            # remove hooks, env, deny rules, agents, skills
  python clean-rag/uninstall.py --purge    # also delete databases/ and state/

Kept always: pip dependencies, knowledge/. Kept unless --purge: databases/, state/.
Left in place: ~/.claude/hook-run.py, which ClaudeBoost's other hooks also use.
ClaudeBoost's own scripts/uninstall.py owns removing that shared launcher.
"""

import argparse
import json
import shutil
import sys
from pathlib import Path

CLEAN_RAG_HOME = Path(__file__).resolve().parent
CLAUDE_DIR = Path.home() / ".claude"
SETTINGS_PATH = CLAUDE_DIR / "settings.json"

# Every hook clean-rag's install.py registers, by the inner script name. The
# command may be wrapped through hook-run.py, so match on the substring rather
# than the exact command. Old names kept too, so this cleans up stale installs.
HOOK_SCRIPTS = (
    "research-gate.py",
    "research-record.py",
    "rag-enforce.py",
    "reindex-after-edit.py",
    "code-pattern-inject.py",
    "graph-context-inject.py",
    "spec-compliance-gate.py",
    # legacy, deleted this era but may linger in an old settings.json
    "proof-gate.py",
    "rag-search-on-edit.py",
)

# SessionStart prompt from the old proof era.
SESSION_SENTINEL = "CLEAN-RAG ENFORCEMENT"

# Env vars clean-rag's install sets. CLAUDEBOOST_* are NOT ours, leave them.
ENV_VARS = (
    "CLEAN_RAG_HOME",
    "CLEAN_RAG_GATE_MODE",
    "CLEAN_RAG_WEB_SEARCH",
    "CLEAN_RAG_WEB_SEARCH_TIMEOUT",
    "CLEAN_RAG_WEB_SEARCH_MAX_RESULTS",
    "CLEAN_RAG_WEB_SEARCH_THRESHOLD",
    "CLEAN_RAG_PATTERN_INJECT",
)

# The two permission deny rules install.py's protect_research_state adds.
DENY_RULES = (
    "Edit(**/clean-rag/state/research/**)",
    "Write(**/clean-rag/state/research/**)",
)

# User assets install_user_assets copies. hook-run.py is deliberately NOT here.
USER_AGENTS = ("research-agent.md", "triage-agent.md")
USER_SKILLS = ("research", "research-routing")


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


def _entry_runs_a_clean_rag_hook(entry: dict) -> bool:
    for h in entry.get("hooks", []):
        cmd = h.get("command", "")
        if any(script in cmd for script in HOOK_SCRIPTS):
            return True
    return False


def _entry_is_session_prompt(entry: dict) -> bool:
    for h in entry.get("hooks", []):
        if SESSION_SENTINEL in h.get("prompt", ""):
            return True
    return False


def remove_hooks() -> None:
    """Strip every clean-rag hook registration from every event.

    This is the load bearing part. If research-gate.py stays registered after an
    uninstall, every code edit keeps getting blocked with no way to satisfy the
    gate. Un-enforcing means removing these, full stop.
    """
    settings = read_json(SETTINGS_PATH)
    hooks = settings.get("hooks", {})
    if not isinstance(hooks, dict) or not hooks:
        _skip("no hooks in settings.json")
        return

    removed = 0
    for event, entries in list(hooks.items()):
        if not isinstance(entries, list):
            continue
        kept = []
        for entry in entries:
            if _entry_runs_a_clean_rag_hook(entry) or _entry_is_session_prompt(entry):
                removed += 1
            else:
                kept.append(entry)
        hooks[event] = kept

    if removed:
        write_json(SETTINGS_PATH, settings)
        _ok(f"removed {removed} clean-rag hook registration(s)")
    else:
        _skip("no clean-rag hooks registered")


def remove_deny_rules() -> None:
    settings = read_json(SETTINGS_PATH)
    deny = settings.get("permissions", {}).get("deny", [])
    if not isinstance(deny, list):
        _skip("no deny list")
        return
    kept = [d for d in deny if d not in DENY_RULES]
    if len(kept) < len(deny):
        settings["permissions"]["deny"] = kept
        write_json(SETTINGS_PATH, settings)
        _ok(f"removed {len(deny) - len(kept)} research-state deny rule(s)")
    else:
        _skip("no research-state deny rules present")


def remove_env_vars() -> None:
    settings = read_json(SETTINGS_PATH)
    env = settings.get("env", {})
    dropped = [k for k in ENV_VARS if k in env]
    for k in dropped:
        del env[k]
    if dropped:
        write_json(SETTINGS_PATH, settings)
        _ok(f"removed env vars: {', '.join(dropped)}")
    else:
        _skip("no clean-rag env vars set")


def remove_user_assets() -> None:
    """Remove the agents and skills install_user_assets copied. Not hook-run.py."""
    removed = 0
    for name in USER_AGENTS:
        p = CLAUDE_DIR / "agents" / name
        if p.exists():
            p.unlink()
            removed += 1
    for name in USER_SKILLS:
        d = CLAUDE_DIR / "skills" / name
        if d.is_dir():
            shutil.rmtree(d, ignore_errors=True)
            removed += 1
    if removed:
        _ok(f"removed {removed} agent/skill asset(s) from ~/.claude")
    else:
        _skip("no clean-rag agents/skills in ~/.claude")
    _skip("left ~/.claude/hook-run.py in place (shared launcher, ClaudeBoost owns it)")


def stop_server() -> None:
    server_json = CLEAN_RAG_HOME / "state" / "server.json"
    if not server_json.exists():
        _skip("no server PID file")
        return
    try:
        import os
        import signal

        info = json.loads(server_json.read_text(encoding="utf-8"))
        pid = info.get("pid")
        if pid:
            try:
                os.kill(pid, signal.SIGTERM)
                _ok(f"sent SIGTERM to server PID {pid}")
            except (OSError, ProcessLookupError):
                _skip(f"server PID {pid} not running")
        server_json.unlink(missing_ok=True)
    except Exception as e:
        _skip(f"could not stop server: {e}")


def purge_data() -> None:
    for dirname in ("databases", "state"):
        target = CLEAN_RAG_HOME / dirname
        if target.exists():
            shutil.rmtree(target, ignore_errors=True)
            _ok(f"deleted {dirname}/")
        else:
            _skip(f"{dirname}/ not found")


def main() -> None:
    parser = argparse.ArgumentParser(description="Un-enforce clean-rag. Keeps data and deps.")
    parser.add_argument("--purge", action="store_true",
                        help="also delete databases/ and state/ (keeps knowledge/)")
    args = parser.parse_args()

    print("=" * 60)
    print("clean-rag uninstaller (un-enforce, keep data and dependencies)")
    print("=" * 60)
    print()

    print("Step 1: Stopping server...")
    stop_server()

    print("\nStep 2: Removing hook registrations...")
    remove_hooks()

    print("\nStep 3: Removing research-state deny rules...")
    remove_deny_rules()

    print("\nStep 4: Removing clean-rag env vars...")
    remove_env_vars()

    print("\nStep 5: Removing agents and skills from ~/.claude...")
    remove_user_assets()

    if args.purge:
        print("\nStep 6: Purging databases/ and state/...")
        purge_data()
    else:
        print("\nStep 6: Keeping databases/ and state/ (use --purge to remove)")

    print()
    print("=" * 60)
    print("clean-rag un-enforced. Nothing it installed is still gating edits.")
    print()
    print("  Kept: pip dependencies, knowledge/")
    if not args.purge:
        print("  Kept: databases/ and state/ (run with --purge to delete)")
    print("  Left: ~/.claude/hook-run.py (shared; removed by ClaudeBoost uninstall)")
    print("=" * 60)


if __name__ == "__main__":
    main()
