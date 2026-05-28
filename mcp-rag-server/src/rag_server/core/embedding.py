"""Embedding service using sentence-transformers. Lazy-loaded singleton."""

import logging
import threading

from rag_server.ports.embedding_port import EmbeddingPort

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

# Models that use search_query:/search_document: prefixes for better retrieval
_PREFIX_MODELS = {"nomic-ai/nomic-embed-text-v1.5"}


class SentenceTransformerEmbedding(EmbeddingPort):
    """Embedding service backed by sentence-transformers.

    Model is loaded lazily on first use (~2s cold start, ~200MB RAM).
    """

    def __init__(self, model_name: str = DEFAULT_MODEL):
        self._model_name = model_name
        self._model = None
        self._uses_prefixes = model_name in _PREFIX_MODELS
        self._load_lock = threading.Lock()

    def _load_model(self):
        # Fast path — model already loaded (no lock needed for a read).
        if self._model is not None:
            return
        with self._load_lock:
            # Re-check inside the lock: another thread may have loaded while we waited.
            if self._model is None:
                logger.info("Loading embedding model: %s", self._model_name)
                from sentence_transformers import SentenceTransformer
                kwargs = {}
                if self._model_name in _PREFIX_MODELS:
                    kwargs["trust_remote_code"] = True
                self._model = SentenceTransformer(self._model_name, local_files_only=True, **kwargs)
                # Don't call self.dimensions() here — it calls _load_model() which
                # tries to re-acquire _load_lock, deadlocking since this is non-reentrant.
                logger.info("Model loaded. Dimensions: %d", self._model.get_sentence_embedding_dimension())

    @property
    def is_loaded(self) -> bool:
        """Check if the model has been loaded without triggering a load."""
        return self._model is not None

    def embed(self, texts: list[str]) -> list[list[float]]:
        self._load_model()
        if self._uses_prefixes:
            texts = [f"search_document: {t}" for t in texts]
        embeddings = self._model.encode(texts, show_progress_bar=False)
        return embeddings.tolist()

    def embed_query(self, text: str) -> list[float]:
        self._load_model()
        if self._uses_prefixes:
            text = f"search_query: {text}"
        embedding = self._model.encode(text, show_progress_bar=False)
        return embedding.tolist()

    def dimensions(self) -> int:
        self._load_model()
        return self._model.get_sentence_embedding_dimension()
