"""rag_search tool implementation."""

import json
import logging
import threading
import time
from pathlib import Path

from rag_server.config import DEFAULT_MIN_SCORE, DEFAULT_SEARCH_LIMIT, RAG_INDEX_DIR, SCOPES
from rag_server.ports.embedding_port import EmbeddingPort
from rag_server.ports.store_port import StorePort

logger = logging.getLogger(__name__)

# Track which embedder objects have had a warmup thread started.
# Keyed by id(embedder) so we don't spam threads across calls/hot-reloads.
_warmup_started: set[int] = set()


def _ensure_warmup(embedder: EmbeddingPort) -> None:
    """Start a background thread to load the embedding model if not already loading."""
    eid = id(embedder)
    if eid in _warmup_started:
        return
    _warmup_started.add(eid)
    # _load_model() is safe to call from multiple threads (double-checked lock),
    # so starting a thread here is idempotent even across hot-reloads.
    t = threading.Thread(
        target=embedder.embed_query,
        args=("warmup",),
        daemon=True,
        name="rag-model-warmup",
    )
    t.start()
    logger.info("Started background model warmup thread (id=%d)", eid)

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

    # Guard: if the model hasn't finished loading yet, kick off a warmup thread
    # (idempotent) and return immediately — never block on _load_lock for minutes.
    if not embedder.is_loaded:
        _ensure_warmup(embedder)
        return {
            "results": [],
            "total_found": 0,
            "query_time_ms": 0,
            "error": (
                "Embedding model loading — retry in 30-60 seconds."
            ),
        }

    try:
        query_embedding = embedder.embed_query(query)
    except Exception as e:
        logger.error("Embedding failed: %s", e)
        return {"results": [], "total_found": 0, "query_time_ms": 0, "error": f"Embedding failed: {e}"}

    all_results = []

    warnings: list[str] = []
    _graph_augmented = False
    _community_summaries: dict[str, str] = {}  # source_file -> community summary text

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

        # Wait if a project reindex is in progress
        if not (project_store.collection_exists(collection) and project_store.count(collection) > 0):
            from rag_server.core.locking import is_write_locked
            _lock_path = idx_dir / "index.lock"
            if is_write_locked(_lock_path):
                logger.info("Project reindex in progress — waiting up to 30s")
                _deadline = time.time() + 30
                while is_write_locked(_lock_path) and time.time() < _deadline:
                    time.sleep(0.5)

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

            # Annotate results with cached community summaries when available
            _csum_db = idx_dir / "graph.db"
            if _csum_db.exists() and all_results:
                try:
                    from rag_server.adapters.sqlite_graph_store import SQLiteGraphStore
                    _csum_gs = SQLiteGraphStore(_csum_db)
                    if _csum_gs.has_graph():
                        for _r in all_results:
                            _src = _r.metadata.get("source_file", "").replace("\\", "/")
                            if not _src or _src in _community_summaries:
                                continue
                            _cid = _csum_gs.get_community_for_file(_src)
                            if _cid is None:
                                continue
                            _row = _csum_gs.get_community_summary(_cid)
                            if _row and _row.get("summary"):
                                _community_summaries[_src] = _row["summary"]
                except Exception:
                    logger.debug("Community summary lookup failed", exc_info=True)

        elif project_store.collection_exists(collection) and project_store.count(collection) == 0:
            warnings.append("Codebase collection exists but is empty — run rag_index_project first.")
        else:
            warnings.append("Codebase collection not found — run rag_index_project first.")
        project_store.close()
    else:
        # Standard scopes: knowledge, agents, or all
        if scope == "all":
            collections = [s["collection"] for s in SCOPES.values()]
        else:
            collections = [scope]

        # If all collections are empty and a reindex is in progress, wait up to
        # 30s for the writer to finish rather than returning 0 results silently.
        _any_live = any(
            store.collection_exists(c) and store.count(c) > 0 for c in collections
        )
        if not _any_live:
            from rag_server.core.locking import is_write_locked
            _lock_path = RAG_INDEX_DIR / "index.lock"
            if is_write_locked(_lock_path):
                logger.info("RAG reindex in progress — waiting up to 30s for it to complete")
                _deadline = time.time() + 30
                while is_write_locked(_lock_path) and time.time() < _deadline:
                    time.sleep(0.5)

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

    _results_out = []
    for r in all_results:
        _src = r.metadata.get("source_file", "unknown").replace("\\", "/")
        _item: dict = {
            "content": r.content,
            "source": _src,
            "section": r.metadata.get("section", ""),
            "scope": r.metadata.get("scope", ""),
            "score": r.score,
            "line_start": r.metadata.get("line_start", 0),
        }
        if _src in _community_summaries:
            _item["community_summary"] = _community_summaries[_src]
        _results_out.append(_item)

    result = {
        "results": _results_out,
        "total_found": len(all_results),
        "query_time_ms": elapsed_ms,
        "mode": mode,
        "graph_augmented": _graph_augmented,
    }

    if warnings:
        result["warnings"] = warnings

    return result


_RRF_K = 60  # standard constant from Cormack et al. 2009


def _augment_with_graph(
    seed_results: list,
    idx_dir: "Path",
    project_store,
    limit: int,
) -> "tuple[list, bool, str | None]":
    """Expand seed results with structural neighbours from the graph store.

    Merges vector results and graph neighbours using reciprocal rank fusion (RRF).
    Each list is ranked independently; the combined RRF score is 1/(k+rank) summed
    across lists. This gives graph neighbours a fair shot without the brittle
    score-nudge heuristic.

    Returns (results, was_augmented, warning_or_none).
    was_augmented=True means graph neighbours were found and merged.
    warning_or_none is set when graph mode was requested but failed.
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

        # Reciprocal rank fusion: rank each list independently, score = 1/(k+rank).
        # Disjoint lists means each item contributes exactly one rank term.
        # Re-emit SearchResult objects with RRF scores so the caller's sort is correct.
        from rag_server.ports.store_port import SearchResult as _SR

        rrf_scores: dict[int, float] = {}
        rrf_items: dict[int, object] = {}

        for rank, r in enumerate(seed_results, 1):
            uid = id(r)
            rrf_items[uid] = r
            rrf_scores[uid] = 1.0 / (_RRF_K + rank)

        graph_sorted = sorted(extra, key=lambda r: r.score, reverse=True)
        for rank, r in enumerate(graph_sorted, 1):
            uid = id(r)
            rrf_items[uid] = r
            rrf_scores[uid] = rrf_scores.get(uid, 0.0) + 1.0 / (_RRF_K + rank)

        ordered = sorted(rrf_items.keys(), key=lambda u: rrf_scores[u], reverse=True)
        merged = [
            _SR(content=rrf_items[u].content, metadata=rrf_items[u].metadata,
                score=round(rrf_scores[u], 6))
            for u in ordered[:limit]
        ]
        return merged, True, None
    except Exception as e:
        logger.error("Graph augmentation failed: %s", e)
        return seed_results, False, f"graph augmentation failed: {e}"
