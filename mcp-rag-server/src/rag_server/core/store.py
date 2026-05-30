"""ChromaDB vector store implementation."""

import logging
from pathlib import Path

from rag_server.ports.store_port import Chunk, SearchResult, StorePort

# ChromaDB and its Settings are imported lazily in __init__ to avoid a 2.5-second
# import penalty at module load time. This keeps MCP server startup under 1 second
# so Claude Code doesn't time out before tools/list can be served.

logger = logging.getLogger(__name__)


class ChromaStore(StorePort):
    """Vector store backed by ChromaDB in embedded (SQLite) mode."""

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

        self._persist_dir = Path(persist_dir)
        self._persist_dir.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(path=str(self._persist_dir), settings=chroma_settings)
        logger.info("ChromaDB initialized at %s", self._persist_dir)

    def close(self) -> None:
        """Release references so GC can reclaim SQLite file handles.

        Avoids calling _client._system.stop() — that stops shared ChromaDB components
        and breaks other live ChromaStore instances in the same process. With project
        indexes now stored outside OneDrive, plain GC is sufficient.
        """
        try:
            del self._client
        except Exception:
            pass
        import gc
        gc.collect()

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
        except Exception:
            pass

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
        except Exception:
            return 0

    def get_by_source(self, collection: str, source_file: str) -> list[SearchResult]:
        try:
            col = self._get_collection(collection)
        except Exception:
            return []
        results = col.get(where={"source_file": source_file}, include=["documents", "metadatas"])
        return [
            SearchResult(content=doc, metadata=meta, score=1.0)
            for doc, meta in zip(results["documents"], results["metadatas"])
        ]

    def sample_dimension(self, collection: str) -> int | None:
        """Return the embedding dimension of the first stored vector, or None."""
        try:
            col = self._get_collection(collection)
            result = col.peek(limit=1)
            if result["embeddings"] and result["embeddings"][0]:
                return len(result["embeddings"][0])
        except Exception:
            pass
        return None

    def count_sources(self, collection: str) -> int:
        """Fast distinct-source count using ChromaDB metadata (no full scan)."""
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
