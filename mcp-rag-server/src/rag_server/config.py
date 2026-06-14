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

# Persistence — default to LOCALAPPDATA on Windows so the index is machine-local
# and never gets corrupted by OneDrive syncing incompatible HNSW binaries across machines.
_local_appdata = os.environ.get("LOCALAPPDATA")
_default_index_dir = (
    Path(_local_appdata) / "rag-server-index"
    if _local_appdata
    else PROJECT_ROOT / "mcp-rag-server" / ".rag-index"
)
RAG_INDEX_DIR = Path(os.environ.get("RAG_INDEX_DIR", _default_index_dir))

CHROMA_DIR = RAG_INDEX_DIR / "chroma"
MANIFEST_PATH = RAG_INDEX_DIR / "manifest.json"

# Embedding model for knowledge, agents, memories, and research RAG.
# BAAI/bge-base-en-v1.5 (768d, ~440MB) — benchmarked best for semantic search.
# Uses asymmetric retrieval: queries get a prefix, documents don't (handled in embedding.py).
# Override per-machine via RAG_EMBEDDING_MODEL env var if needed.
EMBEDDING_MODEL = os.environ.get("RAG_EMBEDDING_MODEL", "BAAI/bge-base-en-v1.5")

# Code-specific embedding model for codebase indexing and search.
# st-codesearch-distilroberta-base (768d) — trained on code-query pairs, benchmarked best
# across Python, JavaScript, Java, Go, Ruby, PHP (CodeSearchNet 1K-pool MRR > 0.80 on all).
# Override via RAG_CODE_EMBEDDING_MODEL env var if needed.
CODE_EMBEDDING_MODEL = os.environ.get(
    "RAG_CODE_EMBEDDING_MODEL",
    "flax-sentence-embeddings/st-codesearch-distilroberta-base",
)

# Memory system path — where the file-based memory files live.
# Defaults to the ClaudeBoost-project memory dir derived from CLAUDEBOOST_HOME.
_default_memory_dir = ""
_cb_home = os.environ.get("CLAUDEBOOST_HOME", "")
if _cb_home:
    import hashlib as _hl
    _cb_path_hash = _hl.sha256(_cb_home.replace("\\", "/").encode()).hexdigest()[:12]
    _proj_key = _cb_home.replace("\\", "-").replace(":", "-").replace("/", "-").strip("-")
    _default_memory_dir = str(
        Path(os.environ.get("USERPROFILE", os.environ.get("HOME", "")))
        / ".claude" / "projects" / _proj_key / "memory"
    )
MEMORY_DIR = Path(os.environ.get("RAG_MEMORY_DIR", _default_memory_dir)) if _default_memory_dir else None

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
    "memories": {
        "patterns": [],  # indexed via rag_index_memories, not file patterns
        "collection": "memories",
    },
}

# Chunking
MAX_CHUNK_TOKENS = 500
MIN_CHUNK_TOKENS = 50

# Search defaults
DEFAULT_SEARCH_LIMIT = 5
DEFAULT_MIN_SCORE = 0.5

# Dynamic language routing: detect dominant language at index time and select the
# best embedding model for that language family.
# Set RAG_LANG_ROUTING=0 to disable and always use CODE_EMBEDDING_MODEL.
LANG_ROUTING_ENABLED: bool = os.environ.get("RAG_LANG_ROUTING", "1").strip().lower() not in ("0", "false", "off")

# Cross-encoder reranker — re-scores top-k codebase candidates jointly with the query.
# Fixes near-duplicate confusions (get_content vs post_content, two "wrapper" functions).
# CPU-compatible: ms-marco-MiniLM-L6-v2 is 22M params, ~100ms for 10 candidates on CPU.
# Set RAG_RERANKER_ENABLED=0 to disable.
RERANKER_MODEL = os.environ.get("RAG_RERANKER_MODEL", "cross-encoder/ms-marco-MiniLM-L6-v2")
RERANKER_ENABLED = os.environ.get("RAG_RERANKER_ENABLED", "1").strip().lower() not in ("0", "false", "off")

# Compute device for embedding and reranker models.
#
# Detection priority (first match wins):
#   1. RAG_DEVICE env var — force a specific device ("cuda", "cpu", "mps", "xpu", "dml")
#   2. CUDA  — NVIDIA discrete GPU, or AMD discrete GPU via ROCm
#              Install: pip install torch --index-url https://download.pytorch.org/whl/cu121
#   3. MPS   — Apple Silicon (built into PyTorch, no extra install needed)
#   4. XPU   — Intel Arc discrete or Intel Xe integrated
#              Install: pip install intel-extension-for-pytorch
#   5. DirectML ("dml") — any DirectX 12 GPU on Windows, including integrated
#              Intel HD/UHD/Iris/Xe and AMD Radeon integrated graphics.
#              CAVEAT: torch-directml pins torch==2.4.1, which conflicts with
#              sentence-transformers ≥3.x (requires torch≥2.5). Works only when
#              installed in a dedicated environment without CUDA torch.
#              Install: pip install torch-directml  (then downgrade torch)
#   6. CPU   — always available, no GPU needed.
#
# For integrated-GPU-only machines the cleanest path is ONNX Runtime + DirectML
# (no torch version conflict). TODO: add OnnxDirectMLEmbedding class.
def _detect_device() -> str:
    override = os.environ.get("RAG_DEVICE", "").strip()
    if override:
        return override
    try:
        import torch
        if torch.cuda.is_available():      # NVIDIA CUDA or AMD ROCm
            return "cuda"
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            return "mps"                   # Apple Silicon
        if hasattr(torch, "xpu") and torch.xpu.is_available():
            return "xpu"                   # Intel Arc/Xe (needs intel-extension-for-pytorch)
    except ImportError:
        pass
    try:
        import onnxruntime as _ort       # onnxruntime-directml: any DX12 GPU, no torch conflict
        if "DmlExecutionProvider" in _ort.get_available_providers():
            return "onnx-dml"
    except (ImportError, Exception):
        pass
    try:
        import torch_directml             # legacy: any DX12 GPU, but pins torch==2.4.1
        if torch_directml.is_available():
            return "dml"
    except (ImportError, Exception):
        pass
    return "cpu"

DEVICE: str = _detect_device()

# Embedding batch size. Larger batches saturate GPU parallelism; CPU is fine at 32.
EMBED_BATCH_SIZE: int = int(os.environ.get("RAG_EMBED_BATCH_SIZE", "64" if DEVICE != "cpu" else "32"))

# Minimum token count for a chunk to be indexed.
# Belt-and-suspenders below MIN_CHUNK_TOKENS for edge cases (PDF/URL chunkers,
# tiny stubs) that might slip through with nearly empty content.
DEGENERATE_CHUNK_MIN_TOKENS = 10

# Chunk overlap: tokens carried from the end of one chunk into the start of the next.
# Research (arxiv 2407.01219 Table 3) shows 10-20% overlap improves faithfulness at
# chunk boundaries. Default is ~10% of MAX_CHUNK_TOKENS. Set to 0 to disable.
CHUNK_OVERLAP_TOKENS = int(os.environ.get("RAG_CHUNK_OVERLAP", "50"))

# Candidate multiplier for the cross-encoder reranker.
# Fetch limit * N candidates before reranking, then trim to limit after.
# "Retrieve wide, rerank narrow" — research consistently shows this beats fixed-small N.
RERANKER_CANDIDATE_MULTIPLIER = int(os.environ.get("RAG_RERANKER_CANDIDATES", "4"))
