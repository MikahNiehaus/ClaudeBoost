"""
restart-rag.py — Kill the rag-server MCP process so Claude Code restarts it.

Claude Code auto-restarts stdio MCP servers when they exit. This script
finds the Python process running rag_server and sends SIGTERM so the
server picks up code changes without a full Claude Code restart.

Usage (Claude can call this directly):
  python "$CLAUDEBOOST_HOME/scripts/restart-rag.py"
"""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import time


def find_rag_server_pids() -> list[int]:
    """Find PIDs of Python processes running rag_server."""
    try:
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

    # Give Claude Code a moment to restart the server
    print("Waiting for Claude Code to restart rag-server...")
    time.sleep(3)

    # Verify it restarted
    new_pids = find_rag_server_pids()
    if new_pids and new_pids != pids:
        print(f"rag-server restarted (new PID: {new_pids})")
    elif new_pids == pids:
        print("Warning: same PID still running — SIGTERM may have been ignored")
    else:
        print("rag-server process not yet visible — Claude Code may still be restarting it")
        print("Call rag_status to confirm when ready.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
