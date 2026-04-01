"""Abstract interface for vector store operations."""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class Chunk:
    """A text chunk with metadata, ready for storage."""
    id: str
    content: str
    embedding: list[float]
    metadata: dict


@dataclass
class SearchResult:
    """A search result with score."""
    content: str
    metadata: dict
    score: float


class StorePort(ABC):
    """Port for vector store operations."""

    @abstractmethod
    def add_chunks(self, collection: str, chunks: list[Chunk]) -> int:
        """Add chunks to a collection. Returns count added."""
        ...

    @abstractmethod
    def search(
        self,
        collection: str,
        query_embedding: list[float],
        limit: int = 5,
        min_score: float = 0.3,
    ) -> list[SearchResult]:
        """Search a collection by embedding similarity."""
        ...

    @abstractmethod
    def delete_by_source(self, collection: str, source_file: str) -> int:
        """Delete all chunks from a specific source file. Returns count deleted."""
        ...

    @abstractmethod
    def count(self, collection: str) -> int:
        """Return number of chunks in a collection."""
        ...

    @abstractmethod
    def list_sources(self, collection: str) -> list[str]:
        """Return all unique source files in a collection."""
        ...

    @abstractmethod
    def collection_exists(self, collection: str) -> bool:
        """Check if a collection exists."""
        ...

    @abstractmethod
    def create_collection(self, collection: str) -> None:
        """Create a collection if it doesn't exist."""
        ...
