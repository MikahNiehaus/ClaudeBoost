"""Topic management CLI for clean-rag.

Usage:
  python clean-rag/cli/topic.py list
  python clean-rag/cli/topic.py create <name>
  python clean-rag/cli/topic.py delete <name>
  python clean-rag/cli/topic.py search <name> "query text"
"""

import argparse
import json
import sys
from pathlib import Path

# Add clean-rag root to sys.path so server.config is importable
_root = str(Path(__file__).resolve().parent.parent)
if _root not in sys.path:
    sys.path.insert(0, _root)

import re

import httpx

_TOPIC_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


def _validate_topic_name(name: str) -> str | None:
    """Return an error message if topic name is invalid, None if OK."""
    if not name:
        return "Missing topic name"
    if len(name) > 64:
        return "Topic name too long (max 64 chars)"
    if not _TOPIC_NAME_RE.match(name):
        return "Topic name must be lowercase alphanumeric, hyphens, or underscores"
    return None


def _base_url() -> str:
    import os
    port = os.environ.get("CLEAN_RAG_PORT", "8613")
    return f"http://127.0.0.1:{port}"


def cmd_list(args):
    try:
        resp = httpx.get(f"{_base_url()}/topics", timeout=10)
        data = resp.json()
        topics = data.get("topics", {})
        if not topics:
            print("No topics indexed.")
            return
        print(f"{'Topic':<25} {'Chunks':<10} {'Files':<10} {'Indexed'}")
        print("-" * 70)
        for name, info in sorted(topics.items()):
            print(f"{name:<25} {info.get('chunks', 0):<10} "
                  f"{info.get('files', 0):<10} {info.get('indexed_at', '')[:10]}")
    except httpx.ConnectError:
        print("clean-rag server not running. Start it first.")
        sys.exit(1)


def cmd_create(args):
    err = _validate_topic_name(args.name)
    if err:
        print(f"Error: {err}")
        sys.exit(1)
    from server.config import KNOWLEDGE_DIR
    topic_dir = KNOWLEDGE_DIR / args.name
    topic_dir.mkdir(parents=True, exist_ok=True)
    print(f"Created topic directory: {topic_dir}")
    print(f"Add documentation files to this directory, then run:")
    print(f"  python clean-rag/cli/topic.py index {args.name}")


def cmd_index(args):
    try:
        resp = httpx.post(
            f"{_base_url()}/index-topic",
            json={"topic": args.name, "force": args.force},
            timeout=300,
        )
        data = resp.json()
        if "error" in data:
            print(f"Error: {data['error']}")
            sys.exit(1)
        print(f"Topic: {data.get('topic', args.name)}")
        print(f"  Files indexed: {data.get('files_indexed', 0)}")
        print(f"  Chunks created: {data.get('chunks_created', 0)}")
        print(f"  Unchanged: {data.get('files_unchanged', 0)}")
        print(f"  Failed: {data.get('files_failed', 0)}")
        print(f"  Elapsed: {data.get('elapsed_s', 0)}s")
    except httpx.ConnectError:
        print("clean-rag server not running. Start it first.")
        sys.exit(1)


def cmd_delete(args):
    try:
        resp = httpx.delete(f"{_base_url()}/topics/{args.name}", timeout=30)
        data = resp.json()
        if "error" in data:
            print(f"Error: {data['error']}")
            sys.exit(1)
        print(f"Deleted topic '{args.name}': {', '.join(data.get('removed', []))}")
    except httpx.ConnectError:
        print("clean-rag server not running. Start it first.")
        sys.exit(1)


def cmd_search(args):
    try:
        resp = httpx.post(
            f"{_base_url()}/search",
            json={
                "query": args.query,
                "sources": [f"topic:{args.name}"],
                "limit": args.limit,
            },
            timeout=30,
        )
        data = resp.json()
        results = data.get("results", [])
        if not results:
            print("No results found.")
            return
        for i, r in enumerate(results, 1):
            print(f"\n--- Result {i} (score: {r['score']:.3f}) ---")
            print(f"File: {r.get('file', '')} | Section: {r.get('section', '')}")
            print(r.get("content", "")[:500])
    except httpx.ConnectError:
        print("clean-rag server not running. Start it first.")
        sys.exit(1)


def cmd_acquire(args):
    try:
        print(f"Acquiring docs for topic '{args.name}'...")
        resp = httpx.post(
            f"{_base_url()}/acquire-topic",
            json={"topic": args.name},
            timeout=600,
        )
        data = resp.json()
        if "error" in data:
            print(f"Error: {data['error']}")
            sys.exit(1)
        print(f"Topic: {args.name}")
        print(f"  Files acquired: {data.get('files_acquired', 0)}")
        print(f"  Source: {data.get('source', '?')}")
        if "index" in data:
            idx = data["index"]
            print(f"  Indexed: {idx.get('chunks_created', 0)} chunks "
                  f"from {idx.get('files_indexed', 0)} files")
        if data.get("needs_websearch"):
            print("  Note: layers 1-3 produced < 5 files. "
                  "Consider running WebSearch for this topic.")
    except httpx.ConnectError:
        print("clean-rag server not running. Start it first.")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="clean-rag topic management")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("list", help="List all topics")

    p_create = sub.add_parser("create", help="Create a topic directory")
    p_create.add_argument("name", help="Topic name (lowercase slug)")

    p_index = sub.add_parser("index", help="Index a topic")
    p_index.add_argument("name", help="Topic name")
    p_index.add_argument("--force", action="store_true", help="Force full reindex")

    p_delete = sub.add_parser("delete", help="Delete a topic")
    p_delete.add_argument("name", help="Topic name")

    p_search = sub.add_parser("search", help="Search a topic")
    p_search.add_argument("name", help="Topic name")
    p_search.add_argument("query", help="Search query")
    p_search.add_argument("--limit", type=int, default=5)

    p_acquire = sub.add_parser("acquire", help="Auto-research and index a topic")
    p_acquire.add_argument("name", help="Topic name (lowercase slug)")

    args = parser.parse_args()

    if args.command == "list":
        cmd_list(args)
    elif args.command == "create":
        cmd_create(args)
    elif args.command == "index":
        cmd_index(args)
    elif args.command == "delete":
        cmd_delete(args)
    elif args.command == "search":
        cmd_search(args)
    elif args.command == "acquire":
        cmd_acquire(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
