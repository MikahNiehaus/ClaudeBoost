"""ChromaDB vector store implementation.

Extracted from ClaudeBoost mcp-rag-server (self-contained, no external imports).
"""

import logging
import threading
import time
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


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


# Process-wide client cache keyed by canonical persist_dir string.
# ChromaDB's SegmentAPI has a process-wide shared singleton: opening two
# PersistentClient instances causes dimension mismatch errors. Caching by
# path ensures only one client ever exists per directory.
_client_cache: dict[str, object] = {}
_client_cache_lock = threading.Lock()


class ChromaStore:
    """Vector store backed by ChromaDB in embedded (SQLite) mode."""

    @staticmethod
    def evict_cache(persist_dir: str) -> None:
        """Remove cached client for a path after directory deletion."""
        key = str(Path(persist_dir).resolve())
        with _client_cache_lock:
            client = _client_cache.pop(key, None)
        if client is not None:
            try:
                client.close()
            except Exception as e:
                logger.debug("ChromaDB client close during evict (non-fatal): %s", e)

    @staticmethod
    def clear_cache() -> None:
        """Close all cached clients. Called during graceful shutdown."""
        with _client_cache_lock:
            for key, client in list(_client_cache.items()):
                try:
                    client.close()
                except Exception as e:
                    logger.debug("ChromaDB client close for %s (non-fatal): %s", key, e)
            _client_cache.clear()

    def __init__(self, persist_dir: str):
        import chromadb
        from chromadb.config import Settings

        # Force pure-Python SegmentAPI to avoid Rust/Tokio crashes on Windows
        # when stdout is a pipe.
        chroma_settings = Settings(
            chroma_api_impl="chromadb.api.segment.SegmentAPI",
            anonymized_telemetry=False,
        )

        self._persist_dir = Path(persist_dir).resolve()
        self._persist_dir.mkdir(parents=True, exist_ok=True)
        cache_key = str(self._persist_dir)

        with _client_cache_lock:
            if cache_key not in _client_cache:
                _client_cache[cache_key] = chromadb.PersistentClient(
                    path=cache_key, settings=chroma_settings
                )
                logger.info("ChromaDB initialized at %s", self._persist_dir)
            else:
                logger.debug("ChromaDB client reused for %s", self._persist_dir)
            self._client = _client_cache[cache_key]

    def close(self) -> None:
        """Drop this store's reference to the shared client."""
        try:
            del self._client
        except Exception as e:
            logger.debug("ChromaDB client cleanup (non-fatal): %s", e)

    def _get_collection(self, name: str):
        return self._client.get_collection(name)

    def create_collection(self, collection: str) -> None:
        self._client.get_or_create_collection(
            name=collection,
            metadata={"hnsw:space": "cosine"},
        )

    def collection_exists(self, collection: str) -> bool:
        import chromadb.errors
        try:
            self._client.get_collection(collection)
            return True
        except chromadb.errors.NotFoundError:
            return False
        except Exception as e:
            logger.warning(
                "collection_exists(%r): %s: %s", collection, type(e).__name__, e
            )
            return False

    def delete_collection(self, collection: str) -> bool:
        for attempt in range(3):
            try:
                self._client.delete_collection(collection)
                return True
            except Exception as e:
                if attempt < 2:
                    logger.warning(
                        "delete_collection(%r) attempt %d failed: %s — retrying in 0.5s",
                        collection, attempt + 1, e,
                    )
                    time.sleep(0.5)
                else:
                    logger.error(
                        "delete_collection(%r) failed after 3 attempts: %s", collection, e
                    )
                    return False

    def add_chunks(self, collection: str, chunks: list[Chunk]) -> int:
        if not chunks:
            return 0
        col = self._get_collection(collection)
        col.upsert(
            ids=[c.id for c in chunks],
            documents=[c.content for c in chunks],
            embeddings=[c.embedding for c in chunks],
            metadatas=[c.metadata for c in chunks],
        )
        return len(chunks)

    def search(
        self,
        collection: str,
        query_embedding: list[float],
        limit: int = 5,
        min_score: float = 0.3,
    ) -> list[SearchResult]:
        col = self._get_collection(collection)
        col_count = int(col.count())
        if col_count == 0:
            return []

        results = col.query(
            query_embeddings=[query_embedding],
            n_results=min(limit, col_count),
            include=["documents", "metadatas", "distances"],
        )

        search_results = []
        for doc, meta, distance in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        ):
            # ChromaDB cosine distance: 0 = identical, 2 = opposite
            score = 1.0 - (distance / 2.0)
            if score >= min_score:
                search_results.append(SearchResult(
                    content=doc,
                    metadata=meta,
                    score=round(score, 4),
                ))

        return search_results

    def get_by_source(
        self, collection: str, source_file: str, limit: int = 5,
    ) -> list[SearchResult]:
        """Get chunks for a specific source file (no embedding query needed).

        Used by graph search to fetch content for structurally related files
        discovered via edge traversal.
        """
        col = self._get_collection(collection)
        results = col.get(
            where={"source_file": source_file},
            include=["documents", "metadatas"],
            limit=limit,
        )
        if not results["ids"]:
            return []

        return [
            SearchResult(content=doc, metadata=meta, score=1.0)
            for doc, meta in zip(results["documents"], results["metadatas"])
        ]

    def delete_by_source(self, collection: str, source_file: str) -> int:
        col = self._get_collection(collection)
        existing = col.get(where={"source_file": source_file})
        if existing["ids"]:
            col.delete(ids=existing["ids"])
            return len(existing["ids"])
        return 0

    def count(self, collection: str) -> int:
        try:
            return int(self._get_collection(collection).count())
        except Exception:
            return 0

    def count_sources(self, collection: str) -> int:
        """Count distinct source files in a collection."""
        try:
            col = self._get_collection(collection)
            results = col.get(include=["metadatas"])
            sources = {m.get("source_file") for m in results["metadatas"] if m.get("source_file")}
            return len(sources)
        except Exception:
            return 0

    def list_sources(self, collection: str) -> list[str]:
        col = self._get_collection(collection)
        results = col.get(include=["metadatas"])
        sources = set()
        for meta in results["metadatas"]:
            if "source_file" in meta:
                sources.add(meta["source_file"])
        return sorted(sources)
