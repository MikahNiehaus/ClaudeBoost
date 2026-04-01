"""ChromaDB vector store implementation."""

import logging
from pathlib import Path

import chromadb

from rag_server.ports.store_port import Chunk, SearchResult, StorePort

logger = logging.getLogger(__name__)


class ChromaStore(StorePort):
    """Vector store backed by ChromaDB in embedded (SQLite) mode."""

    def __init__(self, persist_dir: str):
        self._persist_dir = Path(persist_dir)
        self._persist_dir.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(path=str(self._persist_dir))
        logger.info("ChromaDB initialized at %s", self._persist_dir)

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
        if col.count() == 0:
            return []

        results = col.query(
            query_embeddings=[query_embedding],
            n_results=min(limit, col.count()),
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
            return self._get_collection(collection).count()
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
