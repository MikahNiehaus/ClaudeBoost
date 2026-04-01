"""Allow running with python -m rag_server."""

import asyncio
from rag_server.server import main

asyncio.run(main())
