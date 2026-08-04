#!/usr/bin/env python3
"""
rag-server-start.py — Start the RAG HTTP server as a background daemon.

Usage:
    python rag-server-start.py           # start on default port 8612
    python rag-server-start.py --port N  # start on custom port

Exit codes:
  0 = server is running and accepting connections (started now or already was running)
  1 = failed to start server after 30s

After this script returns 0, Claude Code can connect via:
    claude mcp add --transport sse rag-server http://127.0.0.1:8612/sse

The server stays running across Claude Code restarts. Re-running this script
is a no-op if the server is already healthy.
"""
from __future__ import annotations

import json
import os
import sys
import subprocess
import time
from pathlib import Path

BOOST_HOME = Path(os.environ.get("CLAUDEBOOST_HOME", Path(__file__).resolve().parent.parent))
RAG_SERVER_SRC = BOOST_HOME / "mcp-rag-server" / "src"
LOCAL_APPDATA = os.environ.get("LOCALAPPDATA", "")
RAG_INDEX_DIR = Path(os.environ.get(
    "RAG_INDEX_DIR",
    str(Path(LOCAL_APPDATA) / "rag-server-index") if LOCAL_APPDATA else str(BOOST_HOME / "mcp-rag-server" / ".rag-index"),
))
DEFAULT_PORT = 8612  # SHA256("ClaudeBoost-rag-server") % 900 + 8100


def _server_info() -> dict | None:
    info_path = RAG_INDEX_DIR / ".server.json"
    if not info_path.exists():
        return None
    try:
        return json.loads(info_path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _is_server_alive(port: int) -> bool:
    """Check if the HTTP server is up and ready on the given port."""
    try:
        import urllib.request, json
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/status", timeout=3) as r:
            data = json.loads(r.read())
        return data.get("status") == "ready"
    except Exception:
        return False


sys.path.insert(0, str(Path(__file__).resolve().parent))
from proc_utils import is_pid_alive as _is_pid_alive  # noqa: E402


SUPERVISOR_SCRIPT = BOOST_HOME / "scripts" / "rag-supervisor.py"
SUPERVISOR_JSON = RAG_INDEX_DIR / ".supervisor.json"


def _supervisor_has_rag_server() -> bool:
    """Check if the supervisor is already running and managing the RAG server."""
    if not SUPERVISOR_JSON.exists():
        return False
    try:
        state = json.loads(SUPERVISOR_JSON.read_text(encoding="utf-8"))
        sup_pid = state.get("supervisor_pid", 0)
        if not _is_pid_alive(sup_pid):
            return False
        for s in state.get("servers", []):
            if s.get("name") == "rag-server" and s.get("alive"):
                return True
    except Exception:
        pass
    return False


def start_server(port: int) -> subprocess.Popen | None:
    """Launch the RAG server via the supervisor for crash recovery.

    Falls back to direct launch if the supervisor script is missing.
    Returns the supervisor process (or direct server process on fallback).
    """
    # If supervisor already manages it, nothing to do
    if _supervisor_has_rag_server():
        print("RAG server already managed by supervisor.")
        return None

    python = sys.executable

    if SUPERVISOR_SCRIPT.exists():
        # Launch through supervisor for auto restart on crash
        cmd = [python, str(SUPERVISOR_SCRIPT), "start", "--only", "rag"]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.stdout:
            print(result.stdout.strip())
        if result.returncode != 0 and result.stderr:
            print(result.stderr.strip(), file=sys.stderr)
        return None

    # Fallback: direct launch (no crash recovery)
    print("Warning: supervisor not found, launching directly (no auto restart).")
    env = os.environ.copy()
    env["PYTHONPATH"] = str(RAG_SERVER_SRC)
    env.pop("DISABLE_TELEMETRY", None)
    env["TQDM_DISABLE"] = "1"
    env["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"
    env["TOKENIZERS_PARALLELISM"] = "false"
    env["TRANSFORMERS_VERBOSITY"] = "error"
    env.setdefault("OMP_NUM_THREADS", "1")
    env.setdefault("MKL_NUM_THREADS", "1")
    env.setdefault("OPENBLAS_NUM_THREADS", "1")

    log_path = RAG_INDEX_DIR / "rag-server.log"
    RAG_INDEX_DIR.mkdir(parents=True, exist_ok=True)
    log_file = open(log_path, "a", encoding="utf-8")

    cmd = [python, "-m", "rag_server", "--http", "--port", str(port)]

    kwargs: dict = {
        "cwd": str(RAG_SERVER_SRC),
        "env": env,
        "stdin": subprocess.DEVNULL,
        "stdout": log_file,
        "stderr": log_file,
    }
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS

    proc = subprocess.Popen(cmd, **kwargs)
    return proc


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description="Start the ClaudeBoost RAG HTTP server")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args()
    port = args.port

    # Check if already running (direct process or via supervisor)
    if _supervisor_has_rag_server() and _is_server_alive(port):
        print(f"RAG server already running via supervisor (port={port})")
        return 0

    info = _server_info()
    if info and info.get("port") == port:
        pid = info.get("pid", 0)
        if _is_pid_alive(pid) and _is_server_alive(port):
            print(f"RAG server already running (pid={pid}, port={port})")
            return 0
        # PID gone or port not responding; stale info, restart
        print(f"Stale server info (pid={pid}), restarting...")

    print(f"Starting RAG HTTP server on port {port}...")
    # Wait briefly for Windows to release the port after killing the old process
    time.sleep(3)
    start_server(port)

    # Wait up to 60s for the server to accept connections
    deadline = time.monotonic() + 60
    dots = 0
    while time.monotonic() < deadline:
        time.sleep(2)
        dots += 1
        if _is_server_alive(port):
            print(f"\nRAG server ready at http://127.0.0.1:{port}/sse")
            print(f"To connect Claude Code:")
            print(f"  claude mcp add --transport sse rag-server http://127.0.0.1:{port}/sse")
            return 0
        print(".", end="", flush=True)

    print(f"\nERROR: RAG server did not start within 60s. Check logs at:")
    print(f"  {RAG_INDEX_DIR / 'rag-server.log'}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
