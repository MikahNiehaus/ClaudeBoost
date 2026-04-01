"""Embedding service using sentence-transformers. Lazy-loaded singleton."""

import logging

from rag_server.ports.embedding_port import EmbeddingPort

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "all-MiniLM-L6-v2"


class SentenceTransformerEmbedding(EmbeddingPort):
    """Embedding service backed by sentence-transformers.

    Model is loaded lazily on first use (~2s cold start, ~200MB RAM).
    """

    def __init__(self, model_name: str = DEFAULT_MODEL):
        self._model_name = model_name
        self._model = None

    def _load_model(self):
        if self._model is None:
            logger.info("Loading embedding model: %s", self._model_name)
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self._model_name)
            logger.info("Model loaded. Dimensions: %d", self.dimensions())

    @property
    def is_loaded(self) -> bool:
        """Check if the model has been loaded without triggering a load."""
        return self._model is not None

    def embed(self, texts: list[str]) -> list[list[float]]:
        self._load_model()
        embeddings = self._model.encode(texts, show_progress_bar=False)
        return embeddings.tolist()

    def embed_query(self, text: str) -> list[float]:
        self._load_model()
        embedding = self._model.encode(text, show_progress_bar=False)
        return embedding.tolist()

    def dimensions(self) -> int:
        self._load_model()
        return self._model.get_sentence_embedding_dimension()
