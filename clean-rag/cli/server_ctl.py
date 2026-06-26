"""Server control CLI for clean-rag.

Usage:
  python clean-rag/cli/server_ctl.py start
  python clean-rag/cli/server_ctl.py stop
  python clean-rag/cli/server_ctl.py status
"""

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

_CLEAN_RAG_HOME = Path(__file__).resolve().parent.parent


def _state_dir() -> Path:
    # Add clean-rag root to path so server.config is importable
    _root = str(_CLEAN_RAG_HOME)
    if _root not in sys.path:
        sys.path.insert(0, _root)
    from server.config import STATE_DIR
    return STATE_DIR


def _port() -> int:
    _root = str(_CLEAN_RAG_HOME)
    if _root not in sys.path:
        sys.path.insert(0, _root)
    from server.config import STANDALONE_PORT
    return STANDALONE_PORT


def cmd_start(args):
    state = _state_dir()
    state.mkdir(parents=True, exist_ok=True)
    server_json = state / "server.json"

    # Check if already running
    if server_json.exists():
        try:
            info = json.loads(server_json.read_text(encoding="utf-8"))
            pid = info.get("pid")
            if pid and _is_process_alive(pid):
                print(f"clean-rag server already running (PID {pid}, port {info.get('port')})")
                return
        except Exception:
            pass

    # Start the server as a background process
    port = _port()
    clean_rag_home = str(_CLEAN_RAG_HOME)
    server_script = str(_CLEAN_RAG_HOME / "server" / "__main__.py")

    env = os.environ.copy()
    env["CLEAN_RAG_HOME"] = clean_rag_home

    if sys.platform == "win32":
        proc = subprocess.Popen(
            [sys.executable, server_script],
            cwd=clean_rag_home,
            env=env,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    else:
        proc = subprocess.Popen(
            [sys.executable, server_script],
            cwd=clean_rag_home,
            env=env,
            start_new_session=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    # Write PID file
    server_json.write_text(json.dumps({
        "pid": proc.pid,
        "port": port,
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "clean_rag_home": clean_rag_home,
    }, indent=2), encoding="utf-8")

    print(f"clean-rag server started (PID {proc.pid}, port {port})")

    # Wait a moment and verify it's running
    time.sleep(2)
    try:
        import httpx
        resp = httpx.get(f"http://127.0.0.1:{port}/status", timeout=5)
        if resp.status_code == 200:
            print("Server is ready.")
        else:
            print("Server started but /status returned non-200. Check logs.")
    except Exception:
        print("Server process started. Model loading may take 30-60 seconds.")


def cmd_stop(args):
    state = _state_dir()
    server_json = state / "server.json"

    if not server_json.exists():
        print("No server PID file found.")
        return

    try:
        info = json.loads(server_json.read_text(encoding="utf-8"))
        pid = info.get("pid")
        if pid:
            if _is_process_alive(pid):
                os.kill(pid, signal.SIGTERM)
                print(f"Sent SIGTERM to PID {pid}")
                if sys.platform != "win32":
                    # On POSIX, SIGTERM is graceful. Wait then force-kill.
                    for _ in range(10):
                        time.sleep(0.5)
                        if not _is_process_alive(pid):
                            break
                    if _is_process_alive(pid):
                        os.kill(pid, signal.SIGKILL)
                        print(f"Sent SIGKILL to PID {pid}")
                # On Windows, os.kill(SIGTERM) calls TerminateProcess (immediate)
            else:
                print(f"PID {pid} not running (stale PID file)")
    except Exception as e:
        print(f"Error stopping server: {e}")

    try:
        server_json.unlink()
    except OSError:
        pass

    print("Server stopped.")


def cmd_status(args):
    port = _port()
    try:
        import httpx
        resp = httpx.get(f"http://127.0.0.1:{port}/status", timeout=5)
        data = resp.json()
        print(f"Status: {data.get('status', 'unknown')}")
        print(f"Uptime: {data.get('uptime_s', 0):.0f}s")
        print(f"Embedding: {data.get('embedding_model', '?')} "
              f"(loaded: {data.get('embedding_loaded', False)})")
        print(f"Code embedding: {data.get('code_embedding_model', '?')} "
              f"(loaded: {data.get('code_embedding_loaded', False)})")
        topics = data.get("topics", {})
        print(f"Topics: {topics.get('count', 0)} ({', '.join(topics.get('names', []))})")
        projects = data.get("projects", {})
        print(f"Projects: {projects.get('count', 0)}")
    except Exception:
        print(f"Server not responding on port {port}")

        # Check PID file
        state = _state_dir()
        server_json = state / "server.json"
        if server_json.exists():
            try:
                info = json.loads(server_json.read_text(encoding="utf-8"))
                pid = info.get("pid")
                if pid and _is_process_alive(pid):
                    print(f"  Process {pid} is running but not responding yet (model loading?)")
                else:
                    print(f"  PID {pid} is not running. Start with: python clean-rag/cli/server_ctl.py start")
            except Exception:
                pass
        else:
            print("  No PID file. Start with: python clean-rag/cli/server_ctl.py start")


def _is_process_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


def main():
    parser = argparse.ArgumentParser(description="clean-rag server control")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("start", help="Start the server")
    sub.add_parser("stop", help="Stop the server")
    sub.add_parser("status", help="Check server status")

    args = parser.parse_args()
    if args.command == "start":
        cmd_start(args)
    elif args.command == "stop":
        cmd_stop(args)
    elif args.command == "status":
        cmd_status(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
