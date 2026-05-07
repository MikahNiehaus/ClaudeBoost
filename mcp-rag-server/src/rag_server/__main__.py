"""Allow running with python -m rag_server."""

import asyncio
from rag_server.server import sync_init, main

_watcher = sync_init()
asyncio.run(main(_watcher))
