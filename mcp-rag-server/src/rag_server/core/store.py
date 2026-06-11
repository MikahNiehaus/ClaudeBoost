"""ChromaDB vector store implementation."""

import logging
import threading
from pathlib import Path

from rag_server.ports.store_port import Chunk, SearchResult, StorePort

# ChromaDB and its Settings are imported lazily in __init__ to avoid a 2.5-second
# import penalty at module load time. This keeps MCP server startup under 1 second
# so Claude Code doesn't time out before tools/list can be served.

logger = logging.getLogger(__name__)

# Process-wide client cache keyed by canonical persist_dir string.
# ChromaDB's SegmentAPI has a process-wide shared singleton: opening two PersistentClient
# instances in the same process causes the singleton to return wrong segment metadata for
# the second client (manifests as dimension mismatch errors). Caching by path ensures only
# one client ever exists per directory.
_client_cache: dict[str, object] = {}
_client_cache_lock = threading.Lock()


class ChromaStore(StorePort):
    """Vector store backed by ChromaDB in embedded (SQLite) mode."""

    @staticmethod
    def evict_cache(persist_dir: str) -> None:
        """Remove cached client for a path, e.g. after shutil.rmtree deletes the directory.
        Next ChromaStore(persist_dir) call will create a fresh client against the new files.
        """
        key = str(Path(persist_dir).resolve())
        with _client_cache_lock:
            client = _client_cache.pop(key, None)
        if client is not None:
            # Popping our cache is not enough: chromadb keeps its own process-wide
            # system cache keyed by settings, so a new PersistentClient for this path
            # would reuse the stale system whose SQLite pool still points at the
            # deleted files (every write then fails with "attempt to write a
            # readonly database"). close() releases the system and stops it once
            # the refcount hits zero — we hold the only client per path.
            try:
                client.close()
            except Exception as e:
                logger.debug("ChromaDB client close during evict (non-fatal): %s", e)

    def __init__(self, persist_dir: str):
        # Lazy import: chromadb takes ~2.5s to import due to its Rust/Tokio extensions.
        # Deferring until first instantiation keeps server.py's module-level import fast.
        import chromadb
        from chromadb.config import Settings

        # ChromaDB 1.5+ uses a Rust/Tokio backend by default. On Windows, this backend
        # crashes with ACCESS_VIOLATION when the process's stdout is a pipe (e.g. when
        # launched as an MCP subprocess by Claude Code). Force the pure-Python SegmentAPI.
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
        """Drop this store's reference to the shared client. The client stays in the
        process-level cache so other ChromaStore instances (and future ones for the
        same path) are unaffected. Actual SQLite handles are reclaimed by GC when the
        cache is cleared at process exit.
        """
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
        try:
            self._client.get_collection(collection)
            return True
        except Exception:
            return False

    def delete_collection(self, collection: str) -> None:
        """Drop a collection entirely (used for dimension-change re-index)."""
        try:
            self._client.delete_collection(collection)
        except Exception as e:
            logger.warning("Failed to delete collection %r — stale data may persist: %s", collection, e)

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
            # Convert to similarity score: 1 - (distance / 2)
            score = 1.0 - (distance / 2.0)
            if score >= min_score:
                search_results.append(SearchResult(
                    content=doc,
                    metadata=meta,
                    score=round(score, 4),
                ))

        return search_results

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
        except Exception as e:
            logger.error("count() failed for collection %r (returning 0 — may falsely appear empty): %s", collection, e)
            return 0

    def get_by_source(self, collection: str, source_file: str) -> list[SearchResult]:
        try:
            col = self._get_collection(collection)
        except Exception as e:
            logger.error("get_by_source: collection %r not found for %r: %s", collection, source_file, e)
            return []
        results = col.get(where={"source_file": source_file}, include=["documents", "metadatas"])
        return [
            SearchResult(content=doc, metadata=meta, score=1.0)
            for doc, meta in zip(results["documents"], results["metadatas"])
        ]

    def sample_dimension(self, collection: str) -> int | None:
        """Return the embedding dimension of the first stored vector, or None.

        Must request embeddings explicitly — peek()/get() in current ChromaDB omit
        them by default, which would silently return None and disable dimension
        mismatch detection. Use len() rather than truthiness since embeddings come
        back as numpy arrays (bare `if array:` raises).
        """
        try:
            col = self._get_collection(collection)
            result = col.get(limit=1, include=["embeddings"])
            embs = result.get("embeddings")
            if embs is not None and len(embs) > 0:
                first = embs[0]
                if first is not None and len(first) > 0:
                    return int(len(first))
        except Exception as e:
            logger.warning("sample_dimension failed for %r — dimension mismatch detection may be skipped: %s", collection, e)
        return None

    def count_sources(self, collection: str) -> int:
        """Fast distinct-source count using ChromaDB metadata (no full scan)."""
        try:
            col = self._get_collection(collection)
            results = col.get(include=["metadatas"])
            sources = {m.get("source_file") for m in results["metadatas"] if m.get("source_file")}
            return len(sources)
        except Exception as e:
            logger.error("count_sources failed for %r: %s", collection, e)
            return 0

    def list_sources(self, collection: str) -> list[str]:
        col = self._get_collection(collection)
        results = col.get(include=["metadatas"])
        sources = set()
        for meta in results["metadatas"]:
            if "source_file" in meta:
                sources.add(meta["source_file"])
        return sorted(sources)
