#!/usr/bin/env python3
"""Standalone launcher for crawl_and_index_urls(). Spawned as a real
subprocess by rag-enforce.py so it survives after the short-lived hook
process exits. Not meant to be run interactively.

web_crawler.py uses relative imports (part of the server package), so it
cannot run as `python web_crawler.py`. This script adds clean-rag's root to
sys.path and imports it properly instead.

Usage: python _crawl_runner.py <topic_slug> <source_query> <url1> [url2] ...
"""

import json
import sys
from pathlib import Path

CLEAN_RAG_HOME = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(CLEAN_RAG_HOME))

from server.web_crawler import crawl_and_index_urls  # noqa: E402


def main() -> int:
    if len(sys.argv) < 4:
        print("Usage: _crawl_runner.py <topic_slug> <source_query> <url1> [url2] ...", file=sys.stderr)
        return 1

    topic_slug = sys.argv[1]
    source_query = sys.argv[2]
    urls = sys.argv[3:]

    stats = crawl_and_index_urls(urls, topic_slug, source_query)
    print(json.dumps(stats))
    return 0


if __name__ == "__main__":
    sys.exit(main())
