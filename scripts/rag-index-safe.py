"""
rag-index-safe.py — Safely index a project or workspace with RAG, with retries and timeouts.

Calls the RAG HTTP /index endpoint with automatic retries, progress reporting,
and hard limits (10 minute total, 3 retries per request).

Usage:
  python rag-index-safe.py --project-path C:/path/to/project
  python rag-index-safe.py --project-path C:/path/to/project --workspace-path C:/path/to/workspace

Optional:
  --timeout SECONDS          HTTP timeout per request (default: 120)
  --max-retries N            Max retries per request (default: 3)
  --max-runtime SECONDS      Absolute timeout in seconds (default: 600 = 10min)
"""

import argparse
import json
import sys
import time
import urllib.error
import urllib.request

def index_with_retries(project_path, workspace_path=None, timeout=120, max_retries=3, max_runtime=600):
    """
    Call RAG /index endpoint with retry logic and timeout guards.

    Returns: (success: bool, message: str)
    """
    start_time = time.time()
    rag_url = "http://127.0.0.1:8612/index"

    payload = {
        "project_path": project_path,
        "force": True
    }
    if workspace_path:
        payload["workspace_path"] = workspace_path

    json_data = json.dumps(payload).encode("utf-8")

    for attempt in range(1, max_retries + 1):
        elapsed = time.time() - start_time
        if elapsed > max_runtime:
            return False, f"Max runtime exceeded ({max_runtime}s). Giving up after {attempt-1} attempts."

        remaining_time = max_runtime - elapsed
        request_timeout = min(timeout, int(remaining_time))

        if request_timeout < 10:
            return False, f"Remaining runtime too low ({remaining_time:.0f}s). Giving up."

        try:
            print(f"\n[Attempt {attempt}/{max_retries}] Indexing (timeout: {request_timeout}s)...")

            req = urllib.request.Request(
                rag_url,
                data=json_data,
                headers={"Content-Type": "application/json"},
                method="POST"
            )

            with urllib.request.urlopen(req, timeout=request_timeout) as response:
                response_data = response.read().decode("utf-8")
                result = json.loads(response_data)

                files_indexed = result.get("files_indexed", 0)
                files_unchanged = result.get("files_unchanged", 0)
                files_failed = result.get("files_failed", 0)
                elapsed_s = result.get("elapsed_s", "?")

                print(f"  OK: {files_indexed} indexed, {files_unchanged} unchanged, {files_failed} failed ({elapsed_s}s)")

                if files_indexed == 0 and files_unchanged == 0:
                    return True, f"Nothing to index (all files unchanged or already indexed)"

                return True, f"Indexed {files_indexed} files in {elapsed_s}s"

        except urllib.error.HTTPError as e:
            print(f"  HTTP {e.code}: {e.reason}")
            if e.code == 503:
                print(f"  RAG server busy. Retrying...")
                time.sleep(2 ** attempt)
            else:
                return False, f"HTTP {e.code}: {e.reason}"

        except urllib.error.URLError as e:
            print(f"  Connection error: {e.reason}")
            if attempt < max_retries:
                wait_time = 2 ** attempt
                print(f"  Retrying in {wait_time}s...")
                time.sleep(wait_time)
            else:
                return False, f"Connection failed after {max_retries} retries: {e.reason}"

        except json.JSONDecodeError as e:
            print(f"  RAG returned invalid JSON (server may be overloaded)")
            if attempt < max_retries:
                wait_time = 2 ** attempt
                print(f"  Retrying in {wait_time}s...")
                time.sleep(wait_time)
            else:
                return False, f"RAG returned invalid response after {max_retries} retries"

        except Exception as e:
            return False, f"Unexpected error: {e}"

    return False, f"Failed after {max_retries} attempts"


def main():
    parser = argparse.ArgumentParser(description="Safely index project/workspace with RAG")
    parser.add_argument("--project-path", required=True, help="Absolute path to project")
    parser.add_argument("--workspace-path", help="Absolute path to workspace (optional)")
    parser.add_argument("--timeout", type=int, default=120, help="HTTP timeout per request (default: 120s)")
    parser.add_argument("--max-retries", type=int, default=3, help="Max retries per request (default: 3)")
    parser.add_argument("--max-runtime", type=int, default=600, help="Max total runtime in seconds (default: 600)")
    args = parser.parse_args()

    print(f"RAG Index — Safe Mode")
    print(f"  Project: {args.project_path}")
    if args.workspace_path:
        print(f"  Workspace: {args.workspace_path}")
    print(f"  Timeout: {args.timeout}s/request | Max retries: {args.max_retries} | Max runtime: {args.max_runtime}s")

    success, message = index_with_retries(
        args.project_path,
        args.workspace_path,
        timeout=args.timeout,
        max_retries=args.max_retries,
        max_runtime=args.max_runtime
    )

    print(f"\n{'='*60}")
    if success:
        print(f"✓ SUCCESS: {message}")
        sys.exit(0)
    else:
        print(f"✗ FAILED: {message}")
        sys.exit(1)


if __name__ == "__main__":
    main()
