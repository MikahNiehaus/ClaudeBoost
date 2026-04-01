"""Configuration for the RAG server."""

import os
from pathlib import Path

# Project root — set via env var, or defaults to current working directory
PROJECT_ROOT = Path(os.environ.get("RAG_PROJECT_ROOT", Path.cwd()))

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
    "workspaces": {
        "patterns": ["workspace/*/context.md", "workspace/*/ticket.md"],
        "collection": "workspaces",
    },
}

# Codebase scope is configured dynamically via rag_index tool
CODEBASE_COLLECTION = "codebase"

# Chunking
MAX_CHUNK_TOKENS = 500
MIN_CHUNK_TOKENS = 50

# Search defaults
DEFAULT_SEARCH_LIMIT = 5
DEFAULT_MIN_SCORE = 0.3

# File extensions to index for codebase scope
CODE_EXTENSIONS = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".rs", ".java",
    ".cs", ".rb", ".php", ".c", ".cpp", ".h", ".hpp",
    ".css", ".scss", ".html", ".sql", ".sh", ".bash",
    ".yaml", ".yml", ".json", ".toml", ".md", ".xml",
}

# Paths to skip when indexing codebase
SKIP_PATTERNS = {
    "node_modules", ".git", "__pycache__", ".venv", "venv",
    "dist", "build", ".rag-index", ".next", "target",
    ".tox", ".mypy_cache", ".pytest_cache", "egg-info",
}
