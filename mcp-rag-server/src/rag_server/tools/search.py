"""rag_search tool implementation."""

import json
import logging
import time
from pathlib import Path

from rag_server.config import DEFAULT_MIN_SCORE, DEFAULT_SEARCH_LIMIT, SCOPES
from rag_server.ports.embedding_port import EmbeddingPort
from rag_server.ports.store_port import StorePort

logger = logging.getLogger(__name__)

VALID_SCOPES = ["all", "knowledge", "agents", "codebase", "research"]


def rag_search(
    embedder: EmbeddingPort,
    store: StorePort,
    query: str,
    scope: str = "all",
    project_path: str | None = None,
    workspace_path: str | None = None,
    limit: int = DEFAULT_SEARCH_LIMIT,
    min_score: float = DEFAULT_MIN_SCORE,
    mode: str = "vector",
) -> dict:
    """Execute semantic search across indexed content."""
    if scope not in VALID_SCOPES:
        return {"error": f"Invalid scope: {scope}. Valid: {VALID_SCOPES}"}

    VALID_MODES = {"vector", "graph"}
    if mode not in VALID_MODES:
        return {"error": f"Invalid mode: {mode!r}. Valid: {sorted(VALID_MODES)}"}

    if scope == "codebase" and not project_path:
        return {"error": "project_path is required when scope='codebase'"}

    if scope == "research" and not workspace_path:
        return {"error": "workspace_path is required when scope='research'"}

    start = time.time()

    try:
        query_embedding = embedder.embed_query(query)
    except Exception as e:
        logger.error("Embedding failed: %s", e)
        return {"results": [], "total_found": 0, "query_time_ms": 0, "error": f"Embedding failed: {e}"}

    all_results = []

    result_warning = None
    _graph_augmented = False

    # Research search uses a per-task workspace store
    if scope == "research":
        from rag_server.core.store import ChromaStore

        research_chroma = (
            Path(workspace_path).resolve() / ".rag-index" / "research" / "chroma"
        )
        if not research_chroma.exists():
            return {
                "results": [],
                "total_found": 0,
                "query_time_ms": 0,
                "error": (
                    "Research index not found at workspace. "
                    "Run rag_index_research first."
                ),
            }

        research_store = ChromaStore(persist_dir=str(research_chroma))
        if research_store.collection_exists("research") and research_store.count("research") > 0:
            try:
                results = research_store.search(
                    collection="research",
                    query_embedding=query_embedding,
                    limit=limit,
                    min_score=min_score,
                )
                all_results.extend(results)
            except Exception as e:
                logger.error("Research store search failed: %s", e)
                result_warning = f"Research search failed: {e}"
        elif not research_store.collection_exists("research"):
            result_warning = "Research collection not found — run rag_index_research first."

    # Codebase search uses a separate per-project store
    elif scope == "codebase":
        from rag_server.core.project import project_index_dir
        from rag_server.core.store import ChromaStore

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
        collection = "codebase"
        if project_store.collection_exists(collection) and project_store.count(collection) > 0:
            try:
                results = project_store.search(
                    collection=collection,
                    query_embedding=query_embedding,
                    limit=limit,
                    min_score=min_score,
                )
                all_results.extend(results)
            except Exception as e:
                logger.error("Codebase store search failed: %s", e)
                result_warning = f"Codebase search failed: {e}"

            # Graph mode: augment seed results with structural neighbours
            if mode == "graph" and all_results:
                all_results, _graph_augmented = _augment_with_graph(
                    all_results, idx_dir, project_store, limit,
                )
            else:
                _graph_augmented = False
        elif project_store.collection_exists(collection) and project_store.count(collection) == 0:
            result_warning = "Codebase collection exists but is empty — run rag_index_project first."
        else:
            result_warning = "Codebase collection not found — run rag_index_project first."
    else:
        # Standard scopes: knowledge, agents, or all
        if scope == "all":
            collections = [s["collection"] for s in SCOPES.values()]
        else:
            collections = [scope]

        for collection in collections:
            if not store.collection_exists(collection) or store.count(collection) == 0:
                continue
            try:
                results = store.search(
                    collection=collection,
                    query_embedding=query_embedding,
                    limit=limit,
                    min_score=min_score,
                )
                all_results.extend(results)
            except Exception as e:
                logger.error("Store search failed for collection %s: %s", collection, e)
                result_warning = f"Search failed for collection {collection!r}: {e}"
                continue

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
        "mode": mode,
        "graph_augmented": _graph_augmented,
    }

    if result_warning:
        result["warning"] = result_warning

    return result


def _augment_with_graph(
    seed_results: list,
    idx_dir: "Path",
    project_store,
    limit: int,
) -> "tuple[list, bool]":
    """Expand seed results with structural neighbours from the graph store.

    Reserves up to 2 result slots for structural neighbours so they are always
    visible even when their scores fall below the vector top-k.  Returns
    (results, was_augmented) where was_augmented=True only when at least one
    structural neighbour was actually added.
    Silently no-ops if graph.db does not exist or has no edges.
    Degrades gracefully to (seed_results, False) on any error.
    """
    from rag_server.adapters.sqlite_graph_store import SQLiteGraphStore
    from rag_server.ports.store_port import SearchResult

    graph_db = idx_dir / "graph.db"
    if not graph_db.exists():
        return seed_results, False

    graph_store = SQLiteGraphStore(graph_db)
    if not graph_store.has_graph():
        return seed_results, False

    try:
        seen_sources = {r.metadata.get("source_file", "").replace("\\", "/") for r in seed_results}
        extra: list[SearchResult] = []

        # Limit graph expansion to top-3 seeds to control token budget
        for seed in seed_results[:3]:
            seed_file = seed.metadata.get("source_file", "").replace("\\", "/")
            if not seed_file:
                continue
            neighbours = graph_store.get_neighbours(seed_file, depth=1)
            for edge in neighbours:
                # Fetch chunks from the neighbouring file (source or target)
                neighbour_file = (
                    edge.target_file if edge.source_file == seed_file else edge.source_file
                )
                if not neighbour_file or neighbour_file == "_external_" or neighbour_file in seen_sources:
                    continue
                chunks = project_store.get_by_source("codebase", neighbour_file)
                for chunk in chunks[:2]:  # at most 2 chunks per neighbour file
                    extra.append(SearchResult(
                        content=chunk.content,
                        metadata=chunk.metadata,
                        score=max(0.1, seed.score - 0.15),
                    ))
                seen_sources.add(neighbour_file)

        if not extra:
            return seed_results, False

        # Reserve up to 2 slots for graph neighbours so they always appear in results.
        # Without this, graph neighbours score lower than vector top-k and get cut.
        graph_slots = min(len(extra), 2, max(0, limit - 1))
        vector_slots = max(0, limit - graph_slots)
        top_vectors = sorted(seed_results, key=lambda r: r.score, reverse=True)[:vector_slots]
        top_graph = sorted(extra, key=lambda r: r.score, reverse=True)[:graph_slots]
        combined = top_vectors + top_graph
        combined.sort(key=lambda r: r.score, reverse=True)
        return combined, True
    except Exception as e:
        logger.error("Graph augmentation failed, returning seed results: %s", e)
        return seed_results, False
