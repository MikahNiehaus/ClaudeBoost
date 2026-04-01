"""Abstract interface for embedding generation."""

from abc import ABC, abstractmethod


class EmbeddingPort(ABC):
    """Port for generating text embeddings."""

    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts. Returns list of vectors."""
        ...

    @abstractmethod
    def embed_query(self, text: str) -> list[float]:
        """Embed a single query. May use different encoding than documents."""
        ...

    @abstractmethod
    def dimensions(self) -> int:
        """Return the embedding dimensionality."""
        ...
