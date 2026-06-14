"""Dynamic language-based embedding model routing.

Detects the dominant programming language in a project at index time and
selects the best embedding model for that language family.

  CSN family   (Python, JS, TS, Java, Go, PHP, Ruby) → CodeRankEmbed 137M
  Systems      (C#, Rust, Kotlin, Swift, C, C++)     → SFR-Code 400M (COIR #1)
  Broad        (30+ others: Scala, Haskell, Lua …)   → jina-v2-base-code 161M
  Fallback     (unknown / exotic)                    → StarEncoder 137M (86 langs)

Text/doc files (.md, .rst, .txt, PDF) do not influence language selection —
they are embedded with whatever model the project's code selects.
"""

from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from rag_server.ports.embedding_port import EmbeddingPort

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Language families
# ---------------------------------------------------------------------------

#: CodeSearchNet family — CodeRankEmbed fine-tuned on exactly these languages.
CSN_FAMILY: frozenset[str] = frozenset({
    "python", "javascript", "typescript", "java", "go", "php", "ruby",
})

#: Systems/compiled languages — SFR-Embedding-Code-400M_R (COIR #1) excels here.
SFR_FAMILY: frozenset[str] = frozenset({
    "csharp", "rust", "kotlin", "swift", "c", "cpp",
})

#: Broad coverage — jina-embeddings-v2-base-code supports 30 languages.
JINA_FAMILY: frozenset[str] = frozenset({
    "scala", "haskell", "lua", "bash", "shell", "sql", "r", "dart",
    "elixir", "erlang", "perl", "powershell", "groovy", "objective-c",
    "clojure", "fortran", "matlab", "coffeescript", "verilog", "vhdl",
    "prolog", "ocaml", "fsharp", "scheme", "racket", "crystal",
    "nim", "zig", "asm", "assembly",
})

#: Doc/config languages excluded from dominant-language detection.
DOC_LANGUAGES: frozenset[str] = frozenset({
    "markdown", "text", "rst", "json", "yaml", "toml", "xml",
    "html", "css", "cshtml", "pdf",
})

# ---------------------------------------------------------------------------
# Routing table
# ---------------------------------------------------------------------------

MODEL_CSN = "nomic-ai/CodeRankEmbed"
MODEL_SFR = "Salesforce/SFR-Embedding-Code-400M_R"
MODEL_JINA = "jinaai/jina-embeddings-v2-base-code"
MODEL_FALLBACK = "bigcode/starencoder"

ROUTING_TABLE: dict[str, str] = {
    **{lang: MODEL_CSN for lang in CSN_FAMILY},
    **{lang: MODEL_SFR for lang in SFR_FAMILY},
    **{lang: MODEL_JINA for lang in JINA_FAMILY},
}


def get_model_for_language(language: str) -> str:
    """Return the best embedding model ID for *language*.

    Falls back to MODEL_FALLBACK for languages not in the routing table.
    The lookup is case-insensitive.
    """
    return ROUTING_TABLE.get(language.lower(), MODEL_FALLBACK)


def detect_dominant_language(files_by_language: dict[str, int]) -> str | None:
    """Return the dominant CODE language in *files_by_language*.

    Doc/config languages (markdown, JSON, YAML, …) are excluded so that a
    Python project with extensive README files still routes to CodeRankEmbed
    rather than a text model.

    Args:
        files_by_language: ``{language_name: file_count}`` dict from scan_project.

    Returns:
        Language name with the highest file count among code languages, or
        ``None`` if only doc/config files were found.
    """
    code_counts = {
        lang: count
        for lang, count in files_by_language.items()
        if lang.lower() not in DOC_LANGUAGES
    }
    if not code_counts:
        return None
    return max(code_counts, key=lambda lang: code_counts[lang])


def get_model_for_project(files_by_language: dict[str, int]) -> str:
    """Detect dominant language and return the best embedding model ID.

    Convenience wrapper over :func:`detect_dominant_language` +
    :func:`get_model_for_language`.

    Args:
        files_by_language: ``{language_name: file_count}`` dict from scan_project.

    Returns:
        HuggingFace model ID of the best-fit embedding model.
    """
    lang = detect_dominant_language(files_by_language)
    if lang is None:
        logger.debug("No code files detected — using fallback model %s", MODEL_FALLBACK)
        return MODEL_FALLBACK
    model = get_model_for_language(lang)
    logger.info("Lang router: dominant_language=%r → model=%s", lang, model)
    return model


# ---------------------------------------------------------------------------
# Model cache
# ---------------------------------------------------------------------------

class ModelCache:
    """Thread-safe lazy cache of :class:`EmbeddingPort` instances keyed by model ID.

    Embedders are created on first request and reused on subsequent calls.
    Thread safety is per-slot: only one thread loads a given model at a time,
    but two different models can load concurrently.

    Usage::

        cache = ModelCache()
        embedder = cache.get("nomic-ai/CodeRankEmbed")
        vectors = embedder.embed(["def foo(): pass"])
    """

    def __init__(self) -> None:
        self._cache: dict[str, EmbeddingPort] = {}
        self._slot_locks: dict[str, threading.Lock] = {}
        self._global_lock = threading.Lock()

    def _slot_lock(self, model_id: str) -> threading.Lock:
        """Return (creating if needed) the per-model load lock."""
        with self._global_lock:
            if model_id not in self._slot_locks:
                self._slot_locks[model_id] = threading.Lock()
            return self._slot_locks[model_id]

    def get(self, model_id: str) -> EmbeddingPort:
        """Return the :class:`EmbeddingPort` for *model_id*, loading it lazily.

        The first call for a given model_id triggers a download + load from
        HuggingFace (cached on disk after the first run). Subsequent calls
        return the cached instance immediately.
        """
        if model_id in self._cache:
            return self._cache[model_id]
        with self._slot_lock(model_id):
            if model_id not in self._cache:
                from rag_server.core.embedding import SentenceTransformerEmbedding
                logger.info("ModelCache: loading %s", model_id)
                self._cache[model_id] = SentenceTransformerEmbedding(model_name=model_id)
        return self._cache[model_id]

    def loaded_models(self) -> list[str]:
        """Return model IDs that have been instantiated (not necessarily warmed up)."""
        return list(self._cache.keys())

    def warmed_models(self) -> list[str]:
        """Return model IDs whose underlying model is fully loaded into memory."""
        return [mid for mid, emb in self._cache.items() if emb.is_loaded]

    def __len__(self) -> int:
        return len(self._cache)

    def __contains__(self, model_id: str) -> bool:
        return model_id in self._cache
