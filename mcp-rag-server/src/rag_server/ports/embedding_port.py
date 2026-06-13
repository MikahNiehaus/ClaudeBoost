"""Abstract interface for embedding generation."""

from abc import ABC, abstractmethod


class EmbeddingPort(ABC):
    """Port for generating text embeddings."""

    @property
    @abstractmethod
    def is_loaded(self) -> bool:
        """True if the model has been loaded into memory."""
        ...

    @abstractmethod
    def embed(self, texts: list[str], *, language: str | None = None) -> list[list[float]]:
        """Embed a batch of texts. Returns list of vectors.

        Args:
            texts: Texts to embed.
            language: Optional language hint (e.g. ``"python"``, ``"csharp"``).
                Routing embedders use this to select the best sub-model.
                Plain embedders ignore it.
        """
        ...

    @abstractmethod
    def embed_query(self, text: str) -> list[float]:
        """Embed a single query. May use different encoding than documents."""
        ...

    @abstractmethod
    def dimensions(self) -> int:
        """Return the embedding dimensionality."""
        ...
