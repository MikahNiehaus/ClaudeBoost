#!/usr/bin/env python3
"""clean-rag installer. Registers the proof gate hook and optionally seeds topics.

Usage:
  python clean-rag/install.py                    # full install with pre-seeding
  python clean-rag/install.py --no-seed          # skip pre-seeding (fast)
  python clean-rag/install.py --seed react,fastapi  # seed only specific topics
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

CLEAN_RAG_HOME = Path(__file__).resolve().parent
CLAUDE_DIR = Path.home() / ".claude"
SETTINGS_PATH = CLAUDE_DIR / "settings.json"

# Hook sentinel: proof-gate.py in the command string
HOOK_SENTINEL = "proof-gate.py"


def _say(msg: str) -> None:
    print(f"  {msg}")


def _ok(msg: str) -> None:
    print(f"  [OK] {msg}")


def _warn(msg: str) -> None:
    print(f"  [WARN] {msg}")


def _err(msg: str) -> None:
    print(f"  [ERROR] {msg}")


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


# ---------------------------------------------------------------------------
# Step 1: Create directories
# ---------------------------------------------------------------------------
def ensure_directories() -> None:
    dirs = ["knowledge", "databases", "databases/_projects", "state",
            "server", "hooks", "verifier", "research", "cli"]
    for d in dirs:
        (CLEAN_RAG_HOME / d).mkdir(parents=True, exist_ok=True)
    _ok("Directories created")


# ---------------------------------------------------------------------------
# Step 2: Install Python deps
# ---------------------------------------------------------------------------
def install_deps() -> None:
    req_file = CLEAN_RAG_HOME / "requirements.txt"
    if not req_file.exists():
        _warn("requirements.txt not found, skipping pip install")
        return
    _say("Installing Python dependencies...")
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "-q", "-r", str(req_file)],
        capture_output=True, text=True,
    )
    if result.returncode == 0:
        _ok("Dependencies installed")
    else:
        _warn(f"pip install returned {result.returncode}: {result.stderr[:200]}")


# ---------------------------------------------------------------------------
# Step 3: Register proof gate hook in settings.json
# ---------------------------------------------------------------------------
def register_hook() -> None:
    settings = read_json(SETTINGS_PATH)
    hooks = settings.setdefault("hooks", {})

    hook_command = f'python "{CLEAN_RAG_HOME.as_posix()}/hooks/proof-gate.py"'

    hook_entry = {
        "matcher": "Edit|Write|MultiEdit",
        "hooks": [
            {
                "type": "command",
                "command": hook_command,
            }
        ],
    }

    # Check if already registered
    pre_tool_hooks = hooks.get("PreToolUse", [])
    if not isinstance(pre_tool_hooks, list):
        pre_tool_hooks = []

    for existing in pre_tool_hooks:
        for h in existing.get("hooks", []):
            cmd = h.get("command", "")
            if HOOK_SENTINEL in cmd:
                # Already installed. Refresh the command path.
                if cmd != hook_command:
                    h["command"] = hook_command
                    _ok("proof-gate hook path refreshed")
                else:
                    _ok("proof-gate hook already registered")
                write_json(SETTINGS_PATH, settings)
                return

    # Prepend (proof gate should fire before ClaudeBoost hooks)
    pre_tool_hooks.insert(0, hook_entry)
    hooks["PreToolUse"] = pre_tool_hooks
    write_json(SETTINGS_PATH, settings)
    _ok("proof-gate hook registered (PreToolUse)")


# ---------------------------------------------------------------------------
# Step 4: Set CLEAN_RAG_HOME env var in settings.json
# ---------------------------------------------------------------------------
def set_env_var() -> None:
    settings = read_json(SETTINGS_PATH)
    env = settings.setdefault("env", {})
    env["CLEAN_RAG_HOME"] = CLEAN_RAG_HOME.as_posix()
    write_json(SETTINGS_PATH, settings)
    _ok(f"CLEAN_RAG_HOME set to {CLEAN_RAG_HOME.as_posix()}")


# ---------------------------------------------------------------------------
# Step 5: Add SessionStart prompt with enforcement rules
# ---------------------------------------------------------------------------
def register_session_prompt() -> None:
    settings = read_json(SETTINGS_PATH)
    hooks = settings.setdefault("hooks", {})

    port = os.environ.get("CLEAN_RAG_PORT", "8613")
    prompt_text = (
        "CLEAN-RAG ENFORCEMENT: Every Edit/Write/MultiEdit on source code "
        "requires verified proof. Before editing:\n"
        "1. Search via POST http://127.0.0.1:{port}/search\n"
        "2. Spawn a Haiku verification agent (model='haiku') with your proof\n"
        "3. Use write_pending_proof() to write a keyed proof file with "
        "content_hash (SHA-256 of edit) and min_score (>= 0.5)\n"
        "4. Retry the edit. The gate verifies: verdict==VERIFIED, "
        "content_hash matches, min_score >= 0.5, timestamp is timezone-aware "
        "and under 120s old.\n"
        "Exempt: workspace/, knowledge/, .md, .txt files. "
        "NOT exempt: .json, .yaml, .toml, .xml, clean-rag/ files."
    ).format(port=port)

    session_entry = {
        "hooks": [
            {
                "type": "prompt",
                "prompt": prompt_text,
            }
        ],
    }

    # Check existing SessionStart hooks
    session_hooks = hooks.get("SessionStart", [])
    if not isinstance(session_hooks, list):
        session_hooks = []

    sentinel = "CLEAN-RAG ENFORCEMENT"
    for existing in session_hooks:
        for h in existing.get("hooks", []):
            if sentinel in h.get("prompt", ""):
                # Already registered. Refresh.
                h["prompt"] = prompt_text
                _ok("SessionStart prompt refreshed")
                hooks["SessionStart"] = session_hooks
                write_json(SETTINGS_PATH, settings)
                return

    session_hooks.append(session_entry)
    hooks["SessionStart"] = session_hooks
    write_json(SETTINGS_PATH, settings)
    _ok("SessionStart prompt registered (clean-rag enforcement)")


# ---------------------------------------------------------------------------
# Step 6: Pre-seed topic databases (optional)
# ---------------------------------------------------------------------------
def seed_topics(topic_filter: list[str] | None = None) -> None:
    # Add clean-rag root to sys.path so research/ is importable
    import sys as _sys
    _crag_root = str(CLEAN_RAG_HOME)
    if _crag_root not in _sys.path:
        _sys.path.insert(0, _crag_root)
    from research.source_map import SEED_TOPICS

    topics_to_seed = SEED_TOPICS
    if topic_filter:
        topics_to_seed = [t for t in SEED_TOPICS if t["topic"] in topic_filter]

    if not topics_to_seed:
        _warn("No matching seed topics found")
        return

    _say(f"Pre-seeding {len(topics_to_seed)} topics from GitHub...")

    for entry in topics_to_seed:
        topic = entry["topic"]
        repo = entry["repo"]
        path = entry["path"]
        extensions = entry.get("extensions", ".md,.mdx,.rst")
        kb_dir = CLEAN_RAG_HOME / "knowledge" / topic

        _say(f"  Cloning {repo} -> knowledge/{topic}/")

        try:
            from research.clone_docs import clone_docs
            extensions_set = {e.strip() for e in extensions.split(",")}
            stats = clone_docs(
                repo=repo, docs_path=path, topic=topic,
                extensions=extensions_set, kb_dir=kb_dir,
            )
            _ok(f"{topic}: {stats['files_copied']} files")
        except Exception as e:
            _warn(f"{topic}: {e}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Install clean-rag")
    parser.add_argument("--no-seed", action="store_true",
                        help="Skip pre-seeding topic databases")
    parser.add_argument("--seed", default="",
                        help="Comma-separated list of topics to seed (default: all)")
    parser.add_argument("--skip-deps", action="store_true",
                        help="Skip pip install")
    args = parser.parse_args()

    print("=" * 60)
    print("clean-rag installer")
    print("=" * 60)
    print()

    # Step 1
    print("Step 1: Creating directories...")
    ensure_directories()

    # Step 2
    if not args.skip_deps:
        print("\nStep 2: Installing dependencies...")
        install_deps()
    else:
        print("\nStep 2: Skipped (--skip-deps)")

    # Step 3
    print("\nStep 3: Registering proof gate hook...")
    register_hook()

    # Step 4
    print("\nStep 4: Setting environment variables...")
    set_env_var()

    # Step 5
    print("\nStep 5: Registering session prompt...")
    register_session_prompt()

    # Step 6
    if not args.no_seed:
        print("\nStep 6: Pre-seeding topic databases...")
        topic_filter = [t.strip() for t in args.seed.split(",") if t.strip()] if args.seed else None
        seed_topics(topic_filter)
    else:
        print("\nStep 6: Skipped (--no-seed)")

    print()
    print("=" * 60)
    print("clean-rag installed successfully!")
    print()
    print(f"  Home:    {CLEAN_RAG_HOME}")
    print(f"  Hook:    proof-gate.py (PreToolUse on Edit|Write|MultiEdit)")
    print(f"  Server:  python {CLEAN_RAG_HOME.as_posix()}/cli/server_ctl.py start")
    print()
    print("Start the server, then every code edit will require verified proof.")
    print("=" * 60)


if __name__ == "__main__":
    main()
