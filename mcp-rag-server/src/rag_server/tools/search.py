"""rag_search tool implementation."""

import logging
import time

from rag_server.config import DEFAULT_MIN_SCORE, DEFAULT_SEARCH_LIMIT, SCOPES
from rag_server.ports.embedding_port import EmbeddingPort
from rag_server.ports.store_port import StorePort

logger = logging.getLogger(__name__)

VALID_SCOPES = ["all", "knowledge", "agents", "workspaces", "codebase"]


def rag_search(
    embedder: EmbeddingPort,
    store: StorePort,
    query: str,
    scope: str = "all",
    limit: int = DEFAULT_SEARCH_LIMIT,
    min_score: float = DEFAULT_MIN_SCORE,
) -> dict:
    """Execute semantic search across indexed content."""
    if scope not in VALID_SCOPES:
        return {"error": f"Invalid scope: {scope}. Valid: {VALID_SCOPES}"}

    start = time.time()

    query_embedding = embedder.embed_query(query)

    # Determine which collections to search
    if scope == "all":
        collections = [s["collection"] for s in SCOPES.values()] + ["codebase"]
    else:
        collections = [scope]

    all_results = []
    for collection in collections:
        if not store.collection_exists(collection) or store.count(collection) == 0:
            continue
        results = store.search(
            collection=collection,
            query_embedding=query_embedding,
            limit=limit,
            min_score=min_score,
        )
        all_results.extend(results)

    # Sort by score descending, take top N
    all_results.sort(key=lambda r: r.score, reverse=True)
    all_results = all_results[:limit]

    elapsed_ms = int((time.time() - start) * 1000)

    return {
        "results": [
            {
                "content": r.content,
                "source": r.metadata.get("source_file", "unknown"),
                "section": r.metadata.get("section", ""),
                "scope": r.metadata.get("scope", ""),
                "score": r.score,
                "line_start": r.metadata.get("line_start", 0),
            }
            for r in all_results
        ],
        "total_found": len(all_results),
        "query_time_ms": elapsed_ms,
    }
