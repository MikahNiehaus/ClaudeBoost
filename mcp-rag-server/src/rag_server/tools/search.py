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

    warnings: list[str] = []
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
                warnings.append(f"Research search failed: {e}")
        elif not research_store.collection_exists("research"):
            warnings.append("Research collection not found — run rag_index_research first.")

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
                warnings.append(f"Codebase vector search failed: {e}")

            # Graph mode: augment seed results with structural neighbours
            if mode == "graph":
                if all_results:
                    all_results, _graph_augmented, graph_warning = _augment_with_graph(
                        all_results, idx_dir, project_store, limit,
                    )
                    if graph_warning:
                        warnings.append(graph_warning)
                else:
                    # Vector search found nothing — graph expansion has no seeds to follow
                    warnings.append(
                        "graph mode: skipping graph expansion because vector search returned 0 results"
                    )
        elif project_store.collection_exists(collection) and project_store.count(collection) == 0:
            warnings.append("Codebase collection exists but is empty — run rag_index_project first.")
        else:
            warnings.append("Codebase collection not found — run rag_index_project first.")
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
                warnings.append(f"Search failed for collection {collection!r}: {e}")
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

    if warnings:
        result["warnings"] = warnings

    return result


def _augment_with_graph(
    seed_results: list,
    idx_dir: "Path",
    project_store,
    limit: int,
) -> "tuple[list, bool, str | None]":
    """Expand seed results with structural neighbours from the graph store.

    Graph neighbours compete naturally with vector results by score — no slots
    are reserved. Returns (results, was_augmented, warning_or_none).

    was_augmented=True means graph neighbours were found and merged into the
    candidate pool; it does not guarantee any neighbour survived into the
    final top-k (a strong vector result at the same limit position will beat
    a weaker structural neighbour).

    warning_or_none is a non-None string when graph mode was requested but
    couldn't deliver — e.g. graph.db missing, no edges, or a runtime error.
    The caller surfaces this in the response warnings list so it's visible.
    """
    from rag_server.adapters.sqlite_graph_store import SQLiteGraphStore
    from rag_server.ports.store_port import SearchResult

    graph_db = idx_dir / "graph.db"
    if not graph_db.exists():
        return (
            seed_results, False,
            "graph mode requested but graph.db not found — run rag_index_project to build the graph index",
        )

    graph_store = SQLiteGraphStore(graph_db)
    if not graph_store.has_graph():
        return (
            seed_results, False,
            "graph mode requested but graph has no edges — run rag_index_project to rebuild",
        )

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
            # No structural neighbours for these seed files — not an error
            return seed_results, False, None

        # Merge graph neighbours with vector results and let scores compete.
        # Neighbours are scored at (seed.score - 0.15), so only structurally
        # related files that are also semantically close will rank highly.
        # Forcing slot reservation caused low-relevance structural files to
        # displace stronger semantic matches — natural competition is cleaner.
        combined = sorted(seed_results + extra, key=lambda r: r.score, reverse=True)
        return combined[:limit], True, None
    except Exception as e:
        logger.error("Graph augmentation failed: %s", e)
        return seed_results, False, f"graph augmentation failed: {e}"
