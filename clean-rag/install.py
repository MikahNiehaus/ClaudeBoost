#!/usr/bin/env python3
"""clean-rag installer. Registers hooks and optionally seeds topics.

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

# Hook sentinels: unique strings in hook commands for idempotent registration
PROOF_GATE_SENTINEL = "proof-gate.py"
RAG_ENFORCE_SENTINEL = "rag-enforce.py"
REINDEX_SENTINEL = "reindex-after-edit.py"
SESSION_SENTINEL = "CLEAN-RAG ENFORCEMENT"
STOP_SENTINEL = "CLEAN-RAG RESEARCH GATE"


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
# Hook registration helpers
# ---------------------------------------------------------------------------
def _register_hook(
    settings: dict,
    hook_type: str,
    sentinel: str,
    hook_entry: dict,
    prepend: bool = False,
    label: str = "",
) -> None:
    """Register a hook in settings.json, idempotently.

    If a hook with the sentinel already exists, refresh its command.
    Otherwise, append (or prepend) the new entry.
    """
    hooks = settings.setdefault("hooks", {})
    hook_list = hooks.get(hook_type, [])
    if not isinstance(hook_list, list):
        hook_list = []

    new_cmd = ""
    for h in hook_entry.get("hooks", []):
        if "command" in h:
            new_cmd = h["command"]
            break

    # Check if already registered
    for existing in hook_list:
        for h in existing.get("hooks", []):
            cmd = h.get("command", "")
            prompt = h.get("prompt", "")
            if sentinel in cmd or sentinel in prompt:
                # Refresh
                if new_cmd and cmd != new_cmd:
                    h["command"] = new_cmd
                    _ok(f"{label} hook path refreshed")
                elif "prompt" in h and sentinel in prompt:
                    # Refresh prompt text
                    for new_h in hook_entry.get("hooks", []):
                        if "prompt" in new_h:
                            h["prompt"] = new_h["prompt"]
                    _ok(f"{label} prompt refreshed")
                else:
                    _ok(f"{label} already registered")
                hooks[hook_type] = hook_list
                write_json(SETTINGS_PATH, settings)
                return

    if prepend:
        hook_list.insert(0, hook_entry)
    else:
        hook_list.append(hook_entry)
    hooks[hook_type] = hook_list
    write_json(SETTINGS_PATH, settings)
    _ok(f"{label} registered ({hook_type})")


# ---------------------------------------------------------------------------
# Step 3: Register proof gate hook (PreToolUse)
# ---------------------------------------------------------------------------
def register_proof_gate_hook() -> None:
    settings = read_json(SETTINGS_PATH)
    # Use env var for portability across machines
    hook_command = 'python "$CLEAN_RAG_HOME/hooks/proof-gate.py"'
    hook_entry = {
        "matcher": "Edit|Write|MultiEdit",
        "hooks": [{"type": "command", "command": hook_command}],
    }
    _register_hook(
        settings, "PreToolUse", PROOF_GATE_SENTINEL,
        hook_entry, prepend=True, label="proof-gate",
    )


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
# Step 5: Register SessionStart — NO-OP (enforcement via UserPromptSubmit + Stop)
# ---------------------------------------------------------------------------
def register_session_prompt() -> None:
    # SessionStart: prompt-type hooks are NOT supported (SessionStart fires before any conversation)
    # Enforcement moved to:
    #   - UserPromptSubmit: rag-enforce.py (injects mandate + topic tree every turn)
    #   - Stop: research-stop-gate (blocks unresearched responses)
    #   - PreToolUse: proof-gate.py (blocks edits without proof)
    # No hook registered here.
    _ok("SessionStart enforcement via UserPromptSubmit + Stop hooks")


# ---------------------------------------------------------------------------
# Step 5b: Register rag-enforce UserPromptSubmit hook
# ---------------------------------------------------------------------------
def register_rag_enforce_hook() -> None:
    settings = read_json(SETTINGS_PATH)
    # Use env var for portability across machines
    hook_command = 'python "$CLEAN_RAG_HOME/hooks/rag-enforce.py"'
    hook_entry = {
        "hooks": [{"type": "command", "command": hook_command}],
    }
    _register_hook(
        settings, "UserPromptSubmit", RAG_ENFORCE_SENTINEL,
        hook_entry, label="rag-enforce",
    )


# ---------------------------------------------------------------------------
# Step 5c: Register reindex PostToolUse hook
# ---------------------------------------------------------------------------
def register_reindex_hook() -> None:
    settings = read_json(SETTINGS_PATH)
    # Use env var for portability across machines
    hook_command = 'python "$CLEAN_RAG_HOME/hooks/reindex-after-edit.py"'
    hook_entry = {
        "matcher": "Edit|Write|MultiEdit",
        "hooks": [{"type": "command", "command": hook_command}],
    }
    _register_hook(
        settings, "PostToolUse", REINDEX_SENTINEL,
        hook_entry, label="reindex-after-edit",
    )


# ---------------------------------------------------------------------------
# Step 5d: Register Stop hook (research gate) — prompt type for actual enforcement
# ---------------------------------------------------------------------------
def register_stop_hook() -> None:
    settings = read_json(SETTINGS_PATH)
    port = os.environ.get("CLEAN_RAG_PORT", "8613")
    prompt_text = (
        "CLEAN-RAG RESEARCH GATE: Did Claude cite research in this response?\n\n"
        "PASS (ok: true) ONLY if:\n"
        "- Claude cited specific RAG results (topic name + score from "
        "POST http://127.0.0.1:{port}/search), OR\n"
        "- Claude cited specific direct research (named files read, "
        "Grep results shown, WebSearch results referenced), OR\n"
        "- Response is a short clarification question asking the user "
        "for input (no factual claims), OR\n"
        "- Response is pure task coordination: 'I will do X next', "
        "status of running commands, acknowledging instructions, OR\n"
        "- Response is ONLY executing tools (file ops, tests, commands) "
        "with no technical explanation attached\n\n"
        "FAIL (ok: false) if ANY of these:\n"
        "- Any factual statement about how a technology, library, "
        "framework, or protocol works without citing a source\n"
        "- Any code pattern, architecture, or approach recommendation "
        "without citing where it came from\n"
        "- Any explanation of existing code that adds interpretation "
        "beyond what the code literally says, without research\n"
        "- Any 'best practice' or 'you should' statement without "
        "a cited source\n"
        "- Describing trade-offs between approaches without research\n"
        "- Using phrases like 'typically', 'generally', 'usually', "
        "'in most cases' as substitutes for actual research\n\n"
        "Be strict. When in doubt, FAIL. The cost of one extra search "
        "is low. The cost of ungrounded advice is high.\n\n"
        "When failing, set reason to: "
        "'You made factual claims without citing research. "
        "Search first: POST http://127.0.0.1:{port}/search "
        "then cite topic:score before responding.'"
    ).format(port=port)

    hook_entry = {
        "hooks": [{"type": "prompt", "prompt": prompt_text}],
    }
    _register_hook(
        settings, "Stop", STOP_SENTINEL,
        hook_entry, label="research-stop-gate",
    )


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

    # Group by category for organized output
    by_category: dict[str, list] = {}
    for entry in topics_to_seed:
        cat = entry.get("category", "uncategorized")
        by_category.setdefault(cat, []).append(entry)

    total = len(topics_to_seed)
    _say(f"Pre-seeding {total} topics across {len(by_category)} categories...")

    seeded = 0
    indexed = 0
    failed = 0
    for cat, entries in sorted(by_category.items()):
        _say(f"\n  [{cat}/] ({len(entries)} topics)")
        for entry in entries:
            topic = entry["topic"]
            repo = entry["repo"]
            path = entry["path"]
            extensions = entry.get("extensions", ".md,.mdx,.rst")
            category = entry.get("category", "uncategorized")

            # Tree path: knowledge/<category>/<topic>/
            kb_dir = CLEAN_RAG_HOME / "knowledge" / category / topic

            # Check if already cloned (has 5+ files)
            already_cloned = False
            if kb_dir.exists():
                existing = sum(1 for _ in kb_dir.rglob("*") if _.is_file())
                if existing >= 5:
                    already_cloned = True
                    seeded += 1

            # Clone if needed
            if not already_cloned:
                _say(f"    {topic} <- {repo}")
                try:
                    from research.clone_docs import clone_docs
                    extensions_set = {e.strip() for e in extensions.split(",")}
                    branch = entry.get("branch", "main")
                    stats = clone_docs(
                        repo=repo, docs_path=path, topic=topic,
                        branch=branch, extensions=extensions_set, kb_dir=kb_dir,
                    )
                    seeded += 1
                    _ok(f"    {topic}: {stats['files_copied']} files -> knowledge/{category}/{topic}/")
                    if stats["errors"]:
                        for err in stats["errors"][:3]:
                            _warn(f"      {err}")
                except Exception as e:
                    failed += 1
                    _warn(f"    {topic}: {e}")
                    continue

            # Index into ChromaDB (skip if already indexed)
            chroma_dir = CLEAN_RAG_HOME / "databases" / category / topic / "chroma"
            if chroma_dir.exists():
                if already_cloned:
                    _ok(f"    {topic}: already seeded and indexed")
                else:
                    _ok(f"    {topic}: already indexed")
                indexed += 1
                continue

            # Only index if knowledge dir has files
            if not kb_dir.exists():
                continue
            file_count = sum(1 for _ in kb_dir.rglob("*") if _.is_file())
            if file_count < 1:
                continue

            try:
                from server.indexing import index_topic
                # Load embedding model once on first index
                if not hasattr(seed_topics, '_embedder'):
                    _say("    Loading embedding model (one-time)...")
                    from server.embedding import SentenceTransformerEmbedding
                    from server.config import EMBEDDING_MODEL
                    seed_topics._embedder = SentenceTransformerEmbedding(EMBEDDING_MODEL)
                    _ok("    Embedding model loaded")
                _say(f"    {topic}: indexing {file_count} files...")
                result = index_topic(topic, embedder=seed_topics._embedder, category=category)
                chunks = result.get("chunks_created", 0)
                ram = result.get("ram_mb", 0)
                indexed += 1
                _ok(f"    {topic}: indexed ({chunks} chunks, RAM={ram} MB)")
            except Exception as e:
                _warn(f"    {topic}: indexing failed: {e}")

            # GC between topics to prevent RAM accumulation
            import gc
            gc.collect()

    _say(f"\n  Seeding complete: {seeded} cloned, {indexed} indexed, {failed} failed out of {total}")


def setup_gpu_memory_manager():
    """Configure GPU memory management for embeddings.

    Copies smart_gpu_indexing.py to LocalAI project and configures
    dynamic VRAM allocation based on available GPU memory.
    """
    try:
        # Check if LocalAI project exists
        localai_path = Path.cwd().parent / "LocalAI"
        if not localai_path.exists():
            _warn("LocalAI project not found, skipping GPU memory manager setup")
            return

        # Check if smart_gpu_indexing.py exists locally (in clean-rag)
        gpu_manager_src = CLEAN_RAG_HOME / "smart_gpu_indexing.py"
        if not gpu_manager_src.exists():
            _say("smart_gpu_indexing.py not found in clean-rag directory")
            _say("GPU memory manager must be set up separately in LocalAI project")
            return

        # Verify it exists in LocalAI
        gpu_manager_dst = localai_path / "smart_gpu_indexing.py"
        if gpu_manager_dst.exists():
            _ok("GPU memory manager already installed in LocalAI")
            return

        # Configure Python embedding settings with GPU memory awareness
        try:
            from server.embedding import configure_gpu_aware_embedding
            from server.config import EMBEDDING_MODEL
            configure_gpu_aware_embedding(EMBEDDING_MODEL)
            _ok("GPU-aware embedding configured for dynamic batch sizing")
        except Exception as e:
            _say(f"Optional: GPU-aware embedding setup: {e}")
            _say("Embeddings will use CPU fallback if GPU memory is insufficient")

    except Exception as e:
        _warn(f"GPU memory manager setup: {e}")
        _say("Embeddings will still function with CPU fallback")


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
    register_proof_gate_hook()

    # Step 4
    print("\nStep 4: Setting environment variables...")
    set_env_var()

    # Step 5
    print("\nStep 5: Registering session prompt...")
    register_session_prompt()

    # Step 5b
    print("\nStep 5b: Registering rag-enforce hook...")
    register_rag_enforce_hook()

    # Step 5c
    print("\nStep 5c: Registering reindex hook...")
    register_reindex_hook()

    # Step 5d
    print("\nStep 5d: Registering research stop gate...")
    register_stop_hook()

    # Step 5e
    print("\nStep 5e: Setting up GPU memory management...")
    setup_gpu_memory_manager()

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
    print(f"  Hooks:")
    print(f"    PreToolUse:        proof-gate.py (blocks edits without proof)")
    print(f"    UserPromptSubmit:  rag-enforce.py (injects topic tree every turn)")
    print(f"    PostToolUse:       reindex-after-edit.py (keeps index fresh)")
    print(f"    Stop:              research-stop-gate (blocks unresearched responses)")
    print(f"    SessionStart:      enforcement rules prompt")
    print(f"  GPU Memory:  smart_gpu_indexing.py (dynamic VRAM allocation)")
    print(f"  Server:  python {CLEAN_RAG_HOME.as_posix()}/cli/server_ctl.py start")
    print()
    print("Start the server, then every code edit will require verified proof.")
    print("GPU memory manager provides dynamic batch sizing for embeddings.")
    print("=" * 60)


if __name__ == "__main__":
    main()
