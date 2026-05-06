"""rag_search tool implementation."""

import json
import logging
import time

from rag_server.config import DEFAULT_MIN_SCORE, DEFAULT_SEARCH_LIMIT, SCOPES
from rag_server.ports.embedding_port import EmbeddingPort
from rag_server.ports.store_port import StorePort

logger = logging.getLogger(__name__)

VALID_SCOPES = ["all", "knowledge", "agents", "codebase"]


def _refresh_if_stale(project_path: str, embedder: EmbeddingPort) -> dict | None:
    """Check if a project index is stale (git HEAD moved) and re-index if so.

    Returns the re-index result dict if refreshed, None if up-to-date.
    """
    from rag_server.core.project import git_head, project_index_dir

    idx_dir = project_index_dir(project_path)
    manifest_path = idx_dir / "manifest.json"
    if not manifest_path.exists():
        return None

    current_head = git_head(project_path)
    if not current_head:
        return None  # Not a git repo, can't check staleness

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    stored_head = manifest.get("__git_head__")

    if stored_head == current_head:
        return None  # Up to date

    logger.info(
        "Index stale for %s (stored=%s, current=%s). Refreshing...",
        project_path, stored_head[:8] if stored_head else "none", current_head[:8],
    )

    # Lazy import to avoid circular dependency
    from rag_server.core.store import ChromaStore
    from rag_server.indexing.engine import IndexingEngine

    project_store = ChromaStore(persist_dir=str(idx_dir / "chroma"))
    engine = IndexingEngine(embedder=embedder, store=project_store)
    return engine.index_project(project_path)


def rag_search(
    embedder: EmbeddingPort,
    store: StorePort,
    query: str,
    scope: str = "all",
    project_path: str | None = None,
    limit: int = DEFAULT_SEARCH_LIMIT,
    min_score: float = DEFAULT_MIN_SCORE,
) -> dict:
    """Execute semantic search across indexed content."""
    if scope not in VALID_SCOPES:
        return {"error": f"Invalid scope: {scope}. Valid: {VALID_SCOPES}"}

    if scope == "codebase" and not project_path:
        return {"error": "project_path is required when scope='codebase'"}

    start = time.time()

    query_embedding = embedder.embed_query(query)

    all_results = []
    refreshed = None

    # Codebase search uses a separate per-project store
    if scope == "codebase":
        from rag_server.core.project import project_index_dir
        from rag_server.core.store import ChromaStore

        # Auto-refresh stale index before searching
        refreshed = _refresh_if_stale(project_path, embedder)

        idx_dir = project_index_dir(project_path)
        chroma_dir = idx_dir / "chroma"
        if not chroma_dir.exists():
            return {
                "results": [],
                "total_found": 0,
                "query_time_ms": 0,
                "error": "Project not indexed. Call rag_index_project first.",
            }

        project_store = ChromaStore(persist_dir=str(chroma_dir))
        if project_store.collection_exists("codebase") and project_store.count("codebase") > 0:
            results = project_store.search(
                collection="codebase",
                query_embedding=query_embedding,
                limit=limit,
                min_score=min_score,
            )
            all_results.extend(results)
    else:
        # Standard scopes: knowledge, agents, or all
        if scope == "all":
            collections = [s["collection"] for s in SCOPES.values()]
        else:
            collections = [scope]

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

    result = {
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

    if refreshed:
        result["index_refreshed"] = {
            "files_indexed": refreshed["files_indexed"],
            "chunks_created": refreshed["chunks_created"],
        }

    return result
