"""Configuration for the clean-rag server."""

import os
from pathlib import Path

_MODULE_DIR = Path(__file__).resolve().parent          # clean-rag/server/


def _load_env_files() -> None:
    """Load config from .env files, so a machine can be configured without
    touching settings.json or exporting shell vars.

    Separated and conjoined: clean-rag reads its OWN clean-rag/.env first
    (separated), then falls back to a ClaudeBoost/.env one level up when it's
    bundled there (conjoined). Precedence, highest wins:

        real env vars (settings.json)  >  clean-rag/.env  >  ClaudeBoost/.env  >  code defaults

    Real env vars win because setdefault never overwrites an already set key.
    clean-rag/.env wins over ClaudeBoost/.env because it's loaded first, and the
    first file to set a key keeps it.

    Both .env files are gitignored, so each machine has its own. The committed
    templates are .env.example. Hand rolled on purpose, a KEY=VALUE reader isn't
    worth a python-dotenv dependency.
    """
    clean_rag_root = _MODULE_DIR.parent                # clean-rag/
    for env_path in (clean_rag_root / ".env", clean_rag_root.parent / ".env"):
        if not env_path.is_file():
            continue
        try:
            for raw in env_path.read_text(encoding="utf-8").splitlines():
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key:
                    os.environ.setdefault(key, value)
        except OSError:
            # A missing or unreadable .env is not fatal, defaults still apply.
            pass


_load_env_files()

# clean-rag home: the root of the clean-rag installation.
# Set via CLEAN_RAG_HOME env var, or derive from this file's location.
CLEAN_RAG_HOME = Path(os.environ.get(
    "CLEAN_RAG_HOME",
    str(_MODULE_DIR.parent),                           # clean-rag/
))

# Subdirectories
DATABASES_DIR = CLEAN_RAG_HOME / "databases"
STATE_DIR = CLEAN_RAG_HOME / "state"

# Embedding model for project codebase indexing.
# CodeRankEmbed (768d) trained on CodeSearchNet code-query pairs.
CODE_EMBEDDING_MODEL = os.environ.get(
    "CLEAN_RAG_CODE_EMBEDDING_MODEL",
    "nomic-ai/CodeRankEmbed",
)

# Bumped when the chunking or embedding pipeline changes in a way that
# requires a full re-index. When a project's manifest records a different
# version, the next index_project run forces a rebuild automatically.
PIPELINE_VERSION = 2

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
    return "cpu"


DEVICE: str = _detect_device()

# Web search fallback config
WEB_SEARCH_ENABLED = os.environ.get("CLEAN_RAG_WEB_SEARCH", "true").lower() in ("true", "1", "yes")
WEB_SEARCH_TIMEOUT = float(os.environ.get("CLEAN_RAG_WEB_SEARCH_TIMEOUT", "4.0"))
WEB_SEARCH_MAX_RESULTS = int(os.environ.get("CLEAN_RAG_WEB_SEARCH_MAX_RESULTS", "3"))
WEB_SEARCH_SCORE_THRESHOLD = float(os.environ.get("CLEAN_RAG_WEB_SEARCH_THRESHOLD", "0.4"))
