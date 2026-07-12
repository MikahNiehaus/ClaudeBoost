#!/usr/bin/env python3
"""Standalone launcher for POST /index-project. Spawned as a real subprocess
by rag-enforce.py so indexing (which can take a while for a large repo)
runs in the background without blocking the UserPromptSubmit hook.

Usage: python _index_project_runner.py <project_path> <port>
"""

import json
import sys
import urllib.request


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
            print(json.dumps(result))
        return 0
    except Exception as e:
        print(f"Index request failed: {type(e).__name__}: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
