"""
restart-rag.py — Kill the RAG HTTP server process to force a clean restart.

The RAG server is a standalone HTTP daemon, not an MCP process. It listens on
the port clean-rag's own config names (8613 by default).

After killing it, restart with:
  python clean-rag/cli/server_ctl.py start

This used to say `python scripts/rag-server-start.py`. That script was deleted
along with the 8612 server, so the instruction pointed at nothing.

Use this when the RAG server is stuck or needs to pick up code changes.

Usage (Claude can call this directly):
  python scripts/restart-rag.py
"""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import time


def find_rag_server_pids() -> list[int]:
    """Find PIDs of Python processes running rag_server. Works on Windows, macOS, and Linux."""
    try:
        if sys.platform == "win32":
            result = subprocess.run(
                [
                    "powershell",
                    "-Command",
                    "Get-WmiObject Win32_Process "
                    "| Where-Object {$_.CommandLine -like '*rag_server*' -and $_.Name -like 'python*'} "
                    "| Select-Object -ExpandProperty ProcessId",
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
        else:
            # macOS / Linux: pgrep searches by command line pattern
            result = subprocess.run(
                ["pgrep", "-f", "rag_server"],
                capture_output=True,
                text=True,
                timeout=10,
            )
        return [int(p.strip()) for p in result.stdout.strip().splitlines() if p.strip().isdigit()]
    except Exception as e:
        print(f"Error finding rag_server process: {e}", file=sys.stderr)
        return []


def main() -> int:
    pids = find_rag_server_pids()

    if not pids:
        print("No rag_server process found — server is not running.")
        return 0

    print(f"Found rag_server PID(s): {pids}")
    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
            print(f"  Sent SIGTERM to PID {pid}")
        except ProcessLookupError:
            print(f"  PID {pid} already exited")
        except PermissionError:
            print(f"  Permission denied for PID {pid} — try running as administrator")
            return 1
        except Exception as e:
            print(f"  Failed to kill PID {pid}: {e}")
            return 1

    # Give the process a moment to exit
    print("Waiting for process to exit...")
    time.sleep(2)

    # Verify it stopped
    new_pids = find_rag_server_pids()
    if not new_pids:
        print("RAG server stopped. Restart with:")
        print("  python clean-rag/cli/server_ctl.py start")
        print("Or run /rag in Claude Code.")
    elif new_pids == pids:
        print("Warning: same PID still running — SIGTERM may have been ignored")
    else:
        print(f"New rag_server process found (PID: {new_pids}) — may have auto-restarted")

    return 0


if __name__ == "__main__":
    sys.exit(main())
