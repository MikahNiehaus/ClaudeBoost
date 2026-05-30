"""Allow running with python -m rag_server [--http] [--host H] [--port N]."""

import argparse
import asyncio
from rag_server.server import RAG_HTTP_PORT, sync_init, main, main_http

parser = argparse.ArgumentParser(description="ClaudeBoost RAG server")
parser.add_argument("--http", action="store_true", help="Run as persistent HTTP/SSE server")
parser.add_argument("--host", default="127.0.0.1")
parser.add_argument("--port", type=int, default=RAG_HTTP_PORT)
args = parser.parse_args()

_watcher = sync_init()
try:
    if args.http:
        asyncio.run(main_http(_watcher, args.host, args.port))
    else:
        asyncio.run(main(_watcher))
except KeyboardInterrupt:
    pass
