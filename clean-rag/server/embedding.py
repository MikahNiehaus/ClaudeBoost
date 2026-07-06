"""Embedding service using sentence-transformers. Lazy-loaded singleton.

Extracted from ClaudeBoost mcp-rag-server (self-contained, no external imports).
"""

import logging
import threading

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "BAAI/bge-base-en-v1.5"

# Task-specific prefixes: (query_prefix, document_prefix)
# Required for asymmetric retrieval models.
_TASK_PREFIX_MODELS = {
    "BAAI/bge-base-en-v1.5": ("Represent this sentence for searching relevant passages: ", ""),
    "BAAI/bge-large-en-v1.5": ("Represent this sentence for searching relevant passages: ", ""),
    "BAAI/bge-small-en-v1.5": ("Represent this sentence for searching relevant passages: ", ""),
}

# Models that require trust_remote_code=True
_TRUST_REMOTE_CODE_MODELS: set[str] = set()


class SentenceTransformerEmbedding:
    """Embedding service backed by sentence-transformers.

    Model is loaded lazily on first use (~2s cold start, ~200MB RAM).
    """

    def __init__(self, model_name: str = DEFAULT_MODEL):
        self._model_name = model_name
        self._model = None
        self._batch_size = 32
        prefixes = _TASK_PREFIX_MODELS.get(model_name, ("", ""))
        self._query_prefix, self._doc_prefix = prefixes
        self._trust_remote = model_name in _TRUST_REMOTE_CODE_MODELS
        self._load_lock = threading.Lock()

    def _load_model(self):
        if self._model is not None:
            return
        with self._load_lock:
            if self._model is None:
                from server.config import DEVICE, EMBED_BATCH_SIZE
                logger.info("Loading embedding model: %s (device=%s)", self._model_name, DEVICE)
                from sentence_transformers import SentenceTransformer
                kwargs: dict = {"device": DEVICE}
                if self._trust_remote:
                    kwargs["trust_remote_code"] = True
                # Offline first, fall back to download
                try:
                    self._model = SentenceTransformer(
                        self._model_name, local_files_only=True, **kwargs
                    )
                except OSError:
                    logger.warning(
                        "Model %s not cached locally. Downloading from HuggingFace (~1 min).",
                        self._model_name,
                    )
                    self._model = SentenceTransformer(
                        self._model_name, local_files_only=False, **kwargs
                    )
                self._batch_size = EMBED_BATCH_SIZE
                get_dim = getattr(
                    self._model, "get_embedding_dimension",
                    self._model.get_sentence_embedding_dimension,
                )
                logger.info("Model loaded. Dimensions: %d", get_dim())

    @property
    def is_loaded(self) -> bool:
        return self._model is not None

    def embed(self, texts: list[str]) -> list[list[float]]:
        self._load_model()
        if self._doc_prefix:
            texts = [self._doc_prefix + t for t in texts]
        embeddings = self._model.encode(
            texts, show_progress_bar=False, batch_size=self._batch_size
        )
        return embeddings.tolist()

    def embed_query(self, text: str) -> list[float]:
        self._load_model()
        if self._query_prefix:
            text = self._query_prefix + text
        embedding = self._model.encode(
            text, show_progress_bar=False, batch_size=self._batch_size
        )
        return embedding.tolist()

    def dimensions(self) -> int:
        self._load_model()
        get_dim = getattr(
            self._model, "get_embedding_dimension",
            self._model.get_sentence_embedding_dimension,
        )
        return get_dim()
