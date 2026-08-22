"""
One place that knows which port the RAG server listens on.

The number was written down by hand in fourteen scripts and four slash
commands as 8612. That was the old bundled ClaudeBoost server, deleted in
754a2d4 along with the rest of mcp-rag-server, so every one of those call sites
now points at nothing. clean-rag owns the number in
`clean-rag/server/config.py` and `clean-rag/cli/server_ctl.py` already reads it
exactly this way; this module exists so nobody copies the literal again.

    from rag_port import rag_port
    url = f"http://127.0.0.1:{rag_port()}/search"
"""
from __future__ import annotations

import functools
import os
import sys
from pathlib import Path

# Only used when clean-rag's own config cannot be imported, which normally means
# a partial install rather than a different port.
FALLBACK_PORT = 8613


def _boost_home() -> Path:
    return Path(os.environ.get("CLAUDEBOOST_HOME") or Path(__file__).resolve().parent.parent)


@functools.lru_cache(maxsize=1)
def rag_port() -> int:
    """The port clean-rag actually listens on, from clean-rag's own config."""
    override = os.environ.get("CLEAN_RAG_PORT")
    if override:
        try:
            return int(override)
        except ValueError:
            pass
    try:
        root = str(_boost_home() / "clean-rag")
        if root not in sys.path:
            sys.path.insert(0, root)
        from server.config import STANDALONE_PORT
        return int(STANDALONE_PORT)
    except Exception:
        return FALLBACK_PORT


def rag_url(path: str = "") -> str:
    """Base URL for the RAG server, with an optional path appended."""
    base = f"http://127.0.0.1:{rag_port()}"
    if not path:
        return base
    return base + ("" if path.startswith("/") else "/") + path


def server_ctl() -> Path:
    """
    The script that starts and stops the server.

    `scripts/rag-server-start.py` and `scripts/rag-supervisor.py` were deleted
    with the 8612 server but are still named by /rag and by this hook's auto
    recovery, so both silently do nothing. This is the one that exists.
    """
    return _boost_home() / "clean-rag" / "cli" / "server_ctl.py"
