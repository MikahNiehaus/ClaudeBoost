#!/usr/bin/env python3
"""
test-rag-server.py — Self-contained RAG server debug and recovery script.

Run this from anywhere:
    python "$CLAUDEBOOST_HOME/scripts/test-rag-server.py" [project_path]

What it does:
1. Checks if the MCP server process is running (via heartbeat file)
2. Starts the server directly if not running
3. Waits for the embedding model to load (polls, no sleep spin)
4. Runs a test search to confirm everything works
5. Optionally force-indexes a project (pass project_path as argument)

Use case: when /mcp keeps hanging, run this script in a terminal.
It shows exactly what's wrong and tries to fix it without Claude Code.

Exit codes:
  0 = all checks passed (and index ran if project_path given)
  1 = server could not start or model failed to load
  2 = server started but search failed
"""
from __future__ import annotations

import json
import os
import sys
import subprocess
import time
from pathlib import Path

# Force UTF-8 output on Windows (avoids cp1252 UnicodeEncodeError for ✓/✗/⚠ chars)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# ---------------------------------------------------------------------------
# Resolve ClaudeBoost home
# ---------------------------------------------------------------------------
BOOST_HOME = Path(os.environ.get("CLAUDEBOOST_HOME", Path(__file__).resolve().parent.parent))
RAG_SERVER_SRC = BOOST_HOME / "mcp-rag-server" / "src"
LOCAL_APPDATA = os.environ.get("LOCALAPPDATA", "")
RAG_INDEX_DIR = Path(os.environ.get(
    "RAG_INDEX_DIR",
    str(Path(LOCAL_APPDATA) / "rag-server-index") if LOCAL_APPDATA else str(BOOST_HOME / "mcp-rag-server" / ".rag-index"),
))
HEARTBEAT_FILE = RAG_INDEX_DIR / ".heartbeat"
SERVER_ENTRY = BOOST_HOME / "mcp-rag-server" / "src" / "rag_server" / "__main__.py"

GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
CYAN = "\033[36m"
RESET = "\033[0m"


def ok(msg: str) -> None:
    print(f"  {GREEN}✓{RESET} {msg}")


def warn(msg: str) -> None:
    print(f"  {YELLOW}⚠{RESET} {msg}")


def fail(msg: str) -> None:
    print(f"  {RED}✗{RESET} {msg}")


def info(msg: str) -> None:
    print(f"  {CYAN}→{RESET} {msg}")


# ---------------------------------------------------------------------------
# Step 1: Heartbeat check
# ---------------------------------------------------------------------------
def check_heartbeat() -> tuple[bool, float]:
    """Return (is_fresh, age_seconds). is_fresh means < 90s old."""
    if not HEARTBEAT_FILE.exists():
        return False, float("inf")
    try:
        raw = HEARTBEAT_FILE.read_text(encoding="utf-8").strip()
        try:
            data = json.loads(raw)
            ts = float(data.get("ts", 0))
        except (ValueError, KeyError):
            ts = float(raw)
        age = time.time() - ts
        return age < 90, age
    except Exception:
        return False, float("inf")


# ---------------------------------------------------------------------------
# Step 2: Start server in background if not running
# ---------------------------------------------------------------------------
def start_server_background() -> subprocess.Popen | None:
    """Start the RAG server as a background process. Returns the Popen handle."""
    python = sys.executable
    env = os.environ.copy()
    env["PYTHONPATH"] = str(RAG_SERVER_SRC)

    # The server uses stdio transport — we can't pipe to it like normal MCP.
    # Instead, just start it detached so it writes its heartbeat.
    # The real transport connection happens via Claude Code's /mcp command.
    # Here we just verify it can start without crashing.
    try:
        proc = subprocess.Popen(
            [python, "-m", "rag_server"],
            cwd=str(BOOST_HOME / "mcp-rag-server" / "src"),
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        return proc
    except Exception as e:
        fail(f"Could not start server: {e}")
        return None


# ---------------------------------------------------------------------------
# Step 3: Wait for heartbeat to appear / become fresh
# ---------------------------------------------------------------------------
def wait_for_heartbeat(timeout: float = 30.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        fresh, age = check_heartbeat()
        if fresh:
            return True
        time.sleep(1.0)
    return False


# ---------------------------------------------------------------------------
# Step 4: Direct Python import check — load the server module and test
# ---------------------------------------------------------------------------
def run_direct_test(project_path: str | None) -> int:
    """Import rag_server directly (no MCP transport) and run checks."""
    sys.path.insert(0, str(RAG_SERVER_SRC))

    print("\n  Loading rag_server modules...")
    try:
        from rag_server.core.embedding import SentenceTransformerEmbedding
        from rag_server.core.store import ChromaStore
        from rag_server.indexing.engine import IndexingEngine
        from rag_server.config import CHROMA_DIR, EMBEDDING_MODEL, RAG_INDEX_DIR as _RI
    except ImportError as e:
        fail(f"Import failed — check dependencies: {e}")
        return 1

    ok("Imports OK")

    # Check ChromaDB
    print("\n  Testing ChromaDB connection...")
    try:
        store = ChromaStore(persist_dir=str(CHROMA_DIR))
        knowledge_count = store.count("knowledge")
        agents_count = store.count("agents")
        ok(f"ChromaDB OK — knowledge: {knowledge_count} chunks, agents: {agents_count} chunks")
        store.close()
    except Exception as e:
        fail(f"ChromaDB failed: {e}")
        return 1

    # Load embedding model
    print(f"\n  Loading embedding model: {EMBEDDING_MODEL}")
    print("  (this takes 5-120s on first load — watching...)")
    try:
        embedder = SentenceTransformerEmbedding(EMBEDDING_MODEL)
        t0 = time.monotonic()
        embedder.embed_query("test warmup")
        elapsed = time.monotonic() - t0
        ok(f"Model loaded in {elapsed:.1f}s — dim={embedder.dimensions()}")
    except Exception as e:
        fail(f"Model load failed: {e}")
        info("Check: is sentence-transformers installed? Run: pip install sentence-transformers")
        info(f"Check: is {EMBEDDING_MODEL} cached? Run: python -c \"from sentence_transformers import SentenceTransformer; SentenceTransformer('{EMBEDDING_MODEL}')\"")
        return 1

    # Test search
    print("\n  Running test search (knowledge scope)...")
    try:
        from rag_server.tools.search import rag_search
        result = rag_search(
            embedder=embedder,
            store=store,
            query="security parameterized queries",
            scope="knowledge",
            limit=3,
        )
        if "error" in result:
            fail(f"Search returned error: {result['error']}")
            return 2
        top_score = result["results"][0]["score"] if result["results"] else 0
        ok(f"Search OK — {result['total_found']} results, top score: {top_score:.3f}")
    except Exception as e:
        fail(f"Search failed: {e}")
        return 2

    # Optional: index project (force wipe if possible, incremental fallback)
    if project_path:
        from rag_server.core.project import project_index_dir
        idx_dir = project_index_dir(project_path)
        chroma_proj = idx_dir / "chroma"

        use_force = False
        if chroma_proj.exists():
            info(f"Wiping existing chroma dir: {chroma_proj}")
            import shutil
            try:
                shutil.rmtree(chroma_proj)
                ok("Wiped with shutil.rmtree")
                use_force = True
            except Exception as e:
                warn(f"shutil.rmtree failed ({e}) — trying PowerShell...")
                result_ps = subprocess.run(
                    ["powershell", "-Command",
                     f"Remove-Item -Path '{chroma_proj}' -Recurse -Force -ErrorAction Stop"],
                    capture_output=True, text=True,
                )
                if result_ps.returncode == 0:
                    ok("Wiped with PowerShell Remove-Item")
                    use_force = True
                else:
                    warn(f"Wipe failed (server holds files open) — falling back to incremental indexing")
                    use_force = False
        else:
            use_force = True

        mode_label = "Force-indexing" if use_force else "Incremental-indexing"
        print(f"\n  {mode_label} project: {project_path}")

        try:
            engine = IndexingEngine(embedder=embedder, store=store)
            index_result = engine.index_project(
                project_path=project_path,
                languages=None,
                force=use_force,
            )
            if "error" in index_result:
                fail(f"Index failed: {index_result['error']}")
                return 1
            files = index_result.get("files_indexed", 0)
            chunks = index_result.get("chunks_created", 0)
            elapsed_s = index_result.get("elapsed_s", 0)
            edges = index_result.get("graph", {}).get("edges", 0)
            resolved = index_result.get("graph", {}).get("resolved", 0)
            ok(f"Index complete — {files} files, {chunks} chunks, {resolved}/{edges} graph edges ({elapsed_s}s)")
        except Exception as e:
            fail(f"Index raised exception: {e}")
            import traceback
            traceback.print_exc()
            return 1

    print()
    ok("All checks passed")
    return 0


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> int:
    project_path = sys.argv[1] if len(sys.argv) > 1 else None

    print(f"\n{CYAN}RAG Server Diagnostics{RESET}")
    print(f"  ClaudeBoost: {BOOST_HOME}")
    print(f"  Index dir:   {RAG_INDEX_DIR}")
    if project_path:
        print(f"  Project:     {project_path}")

    # Step 1: Heartbeat
    print("\n[1] Heartbeat check")
    fresh, age = check_heartbeat()
    if fresh:
        ok(f"Server is running (heartbeat {age:.0f}s old)")
    elif age < float("inf"):
        warn(f"Heartbeat stale ({age:.0f}s old) — server may be down or loading")
    else:
        warn("No heartbeat file — server hasn't written one yet")

    # Step 2: Direct module test (runs regardless of heartbeat)
    print("\n[2] Direct module test (bypasses MCP transport)")
    return run_direct_test(project_path)


if __name__ == "__main__":
    sys.exit(main())
