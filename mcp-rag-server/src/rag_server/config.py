"""Configuration for the RAG server."""

import os
from pathlib import Path

# Project root — set via env var, or derive from module location
# Module lives at ClaudeBoost/mcp-rag-server/src/rag_server/config.py
# so parent x4 = ClaudeBoost/mcp-rag-server, parent x5 would overshoot.
# We want ClaudeBoost (the repo root that contains agents/ and knowledge/).
_MODULE_DIR = Path(__file__).resolve().parent  # .../mcp-rag-server/src/rag_server
_INFERRED_ROOT = _MODULE_DIR.parent.parent.parent  # .../ClaudeBoost

def _resolve_project_root() -> Path:
    env_val = os.environ.get("RAG_PROJECT_ROOT")
    if env_val:
        return Path(env_val)
    # Verify inferred root has expected dirs
    if (_INFERRED_ROOT / "agents").is_dir() and (_INFERRED_ROOT / "knowledge").is_dir():
        return _INFERRED_ROOT
    return Path.cwd()

PROJECT_ROOT = _resolve_project_root()

# Persistence
RAG_INDEX_DIR = Path(os.environ.get(
    "RAG_INDEX_DIR",
    PROJECT_ROOT / "mcp-rag-server" / ".rag-index",
))

CHROMA_DIR = RAG_INDEX_DIR / "chroma"
MANIFEST_PATH = RAG_INDEX_DIR / "manifest.json"

# Embedding model
EMBEDDING_MODEL = os.environ.get("RAG_EMBEDDING_MODEL", "all-MiniLM-L6-v2")

# Scoped collection paths (relative to PROJECT_ROOT)
SCOPES = {
    "knowledge": {
        "patterns": ["knowledge/*.md", "knowledge/*.xml"],
        "collection": "knowledge",
    },
    "agents": {
        "patterns": ["agents/*.md", "agents/*.xml"],
        "collection": "agents",
    },
}

# Chunking
MAX_CHUNK_TOKENS = 500
MIN_CHUNK_TOKENS = 50

# Search defaults
DEFAULT_SEARCH_LIMIT = 5
DEFAULT_MIN_SCORE = 0.3
