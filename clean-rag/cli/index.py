"""Project indexing CLI for clean-rag.

Usage:
  python clean-rag/cli/index.py <project-path>
  python clean-rag/cli/index.py <project-path> --force
"""

import argparse
import sys

import httpx


def _base_url() -> str:
    import os
    port = os.environ.get("CLEAN_RAG_PORT", "8613")
    return f"http://127.0.0.1:{port}"


def cmd_index(args):
    try:
        resp = httpx.post(
            f"{_base_url()}/index-project",
            json={"project_path": args.path, "force": args.force},
            timeout=600,
        )
        data = resp.json()
        if "error" in data:
            print(f"Error: {data['error']}")
            sys.exit(1)
        print(f"Project: {data.get('project_path', args.path)}")
        print(f"  ID: {data.get('project_id', '?')}")
        print(f"  Files indexed: {data.get('files_indexed', 0)}")
        print(f"  Chunks created: {data.get('chunks_created', 0)}")
        print(f"  Unchanged: {data.get('files_unchanged', 0)}")
        print(f"  Failed: {data.get('files_failed', 0)}")
        print(f"  Elapsed: {data.get('elapsed_s', 0)}s")
    except httpx.ConnectError:
        print("clean-rag server not running. Start it first.")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Index a project for clean-rag")
    parser.add_argument("path", help="Absolute path to the project directory")
    parser.add_argument("--force", action="store_true",
                        help="Force full reindex (discard existing)")
    args = parser.parse_args()
    cmd_index(args)


if __name__ == "__main__":
    main()
