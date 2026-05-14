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

    if scope == "codebase" and not project_path:
        return {"error": "project_path is required when scope='codebase'"}

    if scope == "research" and not workspace_path:
        return {"error": "workspace_path is required when scope='research'"}

    start = time.time()

    query_embedding = embedder.embed_query(query)

    all_results = []

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
            results = research_store.search(
                collection="research",
                query_embedding=query_embedding,
                limit=limit,
                min_score=min_score,
            )
            all_results.extend(results)

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
        if project_store.collection_exists("codebase") and project_store.count("codebase") > 0:
            results = project_store.search(
                collection="codebase",
                query_embedding=query_embedding,
                limit=limit,
                min_score=min_score,
            )
            all_results.extend(results)

            # Graph mode: augment seed results with structural neighbours
            if mode == "graph":
                all_results = _augment_with_graph(
                    all_results, idx_dir, project_store, limit,
                )
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
        "mode": mode,
    }

    return result


def _augment_with_graph(
    seed_results: list,
    idx_dir: "Path",
    project_store,
    limit: int,
) -> list:
    """Expand seed results with structural neighbours from the graph store.

    Fetches depth-1 neighbours for the top seed files and merges them with
    the vector results.  Returns a deduplicated list capped at *limit*.
    Silently no-ops if graph.db does not exist or has no edges.
    """
    from rag_server.adapters.sqlite_graph_store import SQLiteGraphStore
    from rag_server.ports.store_port import SearchResult

    graph_db = idx_dir / "graph.db"
    if not graph_db.exists():
        return seed_results

    graph_store = SQLiteGraphStore(graph_db)
    if not graph_store.has_graph():
        return seed_results

    seen_sources = {r.metadata.get("source_file", "") for r in seed_results}
    extra: list[SearchResult] = []

    # Limit graph expansion to top-3 seeds to control token budget
    for seed in seed_results[:3]:
        seed_file = seed.metadata.get("source_file", "")
        if not seed_file:
            continue
        neighbours = graph_store.get_neighbours(seed_file, depth=1)
        for edge in neighbours:
            # Fetch chunks from the neighbouring file (source or target)
            neighbour_file = (
                edge.target_file if edge.source_file == seed_file else edge.source_file
            )
            if not neighbour_file or neighbour_file in seen_sources:
                continue
            chunks = project_store.get_by_source("codebase", neighbour_file)
            for chunk in chunks[:2]:  # at most 2 chunks per neighbour file
                extra.append(SearchResult(
                    content=chunk.content,
                    metadata=chunk.metadata,
                    score=max(0.0, seed.score - 0.15),  # slight penalty vs vector seed
                ))
            seen_sources.add(neighbour_file)

    combined = seed_results + extra
    combined.sort(key=lambda r: r.score, reverse=True)
    return combined[:limit]
