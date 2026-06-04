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


def _is_pid_alive(pid: int) -> bool:
    """Check if a process with the given PID is still running."""
    if sys.platform == "win32":
        try:
            result = subprocess.run(
                ["tasklist", "/fi", f"PID eq {pid}", "/fo", "csv", "/nh"],
                capture_output=True, text=True,
            )
            return str(pid) in result.stdout
        except Exception:
            return False
    else:
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False


def start_server(port: int) -> subprocess.Popen:
    """Launch the RAG server as a detached background process."""
    python = sys.executable
    env = os.environ.copy()
    env["PYTHONPATH"] = str(RAG_SERVER_SRC)
    # Disable tqdm/HF progress bars — they crash when stdout is a log file (closed fd)
    env["TQDM_DISABLE"] = "1"
    env["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"
    env["TOKENIZERS_PARALLELISM"] = "false"
    env["TRANSFORMERS_VERBOSITY"] = "error"

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

    # Check if already running
    info = _server_info()
    if info and info.get("port") == port:
        pid = info.get("pid", 0)
        if _is_pid_alive(pid) and _is_server_alive(port):
            print(f"RAG server already running (pid={pid}, port={port})")
            return 0
        # PID gone or port not responding — stale info, restart
        print(f"Stale server info (pid={pid}) — restarting...")

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
