#!/usr/bin/env python3
"""Standalone launcher for POST /index-project. Spawned as a real subprocess
by rag-enforce.py so indexing (which can take a while for a large repo)
runs in the background without blocking the UserPromptSubmit hook.

Usage: python _index_project_runner.py <project_path> <port>
"""

import json
import os
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


def _log(message: str) -> None:
    """Append one line to state/index-runner.log.

    stdout and stderr both go to DEVNULL, because rag-enforce.py spawns this
    with subprocess.Popen(stdout=DEVNULL, stderr=DEVNULL) so a slow index cannot
    block a prompt. That made every outcome invisible, including a 423 refusal:
    the hook printed "Indexing queued in background" while nothing had been
    queued, and the only way to find out was to read the lock file by hand.
    A file is the one channel that survives being detached from the terminal.
    """
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    line = f"{stamp} {message}\n"
    try:
        home = os.environ.get("CLEAN_RAG_HOME")
        root = Path(home) if home else Path(__file__).resolve().parent.parent
        log_path = root / "state" / "index-runner.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(line)
    except Exception:
        # Logging must never be the reason indexing reports a failure.
        pass
    print(line, end="", file=sys.stderr)


def main() -> int:
    if len(sys.argv) < 3:
        print("Usage: _index_project_runner.py <project_path> <port>", file=sys.stderr)
        return 1

    project_path = sys.argv[1]
    port = sys.argv[2]

    try:
        req_data = json.dumps({"project_path": project_path}).encode("utf-8")
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/index-project",
            data=req_data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=300) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            _log(f"OK {project_path}: {json.dumps(result)}")
            print(json.dumps(result))
        return 0
    except urllib.error.HTTPError as e:
        # urlopen raises on any 4xx or 5xx, so every refusal lands here rather
        # than in the response branch above. 423 is the one that matters: the
        # index lock is held by another project's run, nothing was queued, and
        # nothing will retry on its own.
        try:
            body = e.read().decode("utf-8", errors="replace")
        except Exception:
            body = "<unreadable>"
        if e.code == 423:
            _log(
                f"BUSY {project_path}: HTTP 423, the index lock is held by "
                f"another run. Nothing was queued and nothing will retry. {body}"
            )
        else:
            _log(f"FAIL {project_path}: HTTP {e.code}. {body}")
        return 1
    except Exception as e:
        # A socket timeout does not stop the server. The request is handed to an
        # executor thread that keeps indexing after the client gives up, so a
        # timeout here means "still running", not "did not run".
        _log(f"FAIL {project_path}: {type(e).__name__}: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
