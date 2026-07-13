"""Configuration for the clean-rag server."""

import os
from pathlib import Path

# clean-rag home: the root of the clean-rag installation.
# Set via CLEAN_RAG_HOME env var, or derive from this file's location.
_MODULE_DIR = Path(__file__).resolve().parent          # clean-rag/server/
CLEAN_RAG_HOME = Path(os.environ.get(
    "CLEAN_RAG_HOME",
    str(_MODULE_DIR.parent),                           # clean-rag/
))

# Subdirectories
DATABASES_DIR = CLEAN_RAG_HOME / "databases"
STATE_DIR = CLEAN_RAG_HOME / "state"

# Embedding model for project codebase indexing.
# st-codesearch-distilroberta-base (768d) trained on code-query pairs.
CODE_EMBEDDING_MODEL = os.environ.get(
    "CLEAN_RAG_CODE_EMBEDDING_MODEL",
    "flax-sentence-embeddings/st-codesearch-distilroberta-base",
)

# Server port: 8613 standalone, 8612 routes when bundled with ClaudeBoost
STANDALONE_PORT = int(os.environ.get("CLEAN_RAG_PORT", "8613"))

# Chunking defaults
MAX_CHUNK_TOKENS = 500
MIN_CHUNK_TOKENS = 50
CHUNK_OVERLAP_TOKENS = int(os.environ.get("CLEAN_RAG_CHUNK_OVERLAP", "50"))

# Search defaults
DEFAULT_SEARCH_LIMIT = 5
DEFAULT_MIN_SCORE = 0.5

# Degenerate chunk filter: skip chunks with fewer tokens than this
DEGENERATE_CHUNK_MIN_TOKENS = 10

# Embedding batch size
EMBED_BATCH_SIZE = int(os.environ.get("CLEAN_RAG_EMBED_BATCH_SIZE", "32"))

def _detect_device() -> str:
    """Detect the best available compute device."""
    override = os.environ.get("CLEAN_RAG_DEVICE", "").strip()
    if override:
        return override
    try:
        import torch
        if torch.cuda.is_available():
            return "cuda"
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            return "mps"
    except ImportError:
        pass
    try:
        import onnxruntime as _ort
        if "DmlExecutionProvider" in _ort.get_available_providers():
            return "onnx-dml"
    except (ImportError, Exception):
        pass
    return "cpu"


DEVICE: str = _detect_device()

# Web search fallback config
WEB_SEARCH_ENABLED = os.environ.get("CLEAN_RAG_WEB_SEARCH", "true").lower() in ("true", "1", "yes")
WEB_SEARCH_TIMEOUT = float(os.environ.get("CLEAN_RAG_WEB_SEARCH_TIMEOUT", "4.0"))
WEB_SEARCH_MAX_RESULTS = int(os.environ.get("CLEAN_RAG_WEB_SEARCH_MAX_RESULTS", "3"))
WEB_SEARCH_SCORE_THRESHOLD = float(os.environ.get("CLEAN_RAG_WEB_SEARCH_THRESHOLD", "0.4"))
