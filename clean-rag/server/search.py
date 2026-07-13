"""Search logic for clean-rag. Searches project codebase indexes."""

import hashlib
import logging
from pathlib import Path

from .config import DATABASES_DIR, DEFAULT_MIN_SCORE, DEFAULT_SEARCH_LIMIT
from .store import ChromaStore

logger = logging.getLogger(__name__)


def search(
    query: str,
    sources: list[str],
    code_embedder,
    limit: int = DEFAULT_SEARCH_LIMIT,
    min_score: float = DEFAULT_MIN_SCORE,
    mode: str = "vector",
    meta_out: dict | None = None,
    depth: int = 2,
    direction: str = "both",
) -> list[dict]:
    """Search across project codebase indexes.

    Args:
        query: The search query text.
        sources: List of source specifiers:
            - "project:<path>" to search a project's codebase index
        code_embedder: Code embedder (st-codesearch-distilroberta-base).
        limit: Max results per source.
        min_score: Minimum similarity score.
        mode: Search mode for project sources. "vector" (default), "graph",
              or "both". Graph mode finds structural neighbors (imports,
              callers, inheritance) of vector-matched files.
        meta_out: Optional dict the caller passes in to receive graph
              traversal metadata (graph_status: "hit"/"empty"/"absent",
              graph_hit_count, caller_count) that can't be reliably inferred
              from `results` alone -- zero graph hits is ambiguous between
              "no graph.db for this project" and "graph exists but nothing
              connects here" without this. Only populated for project
              sources using mode="graph"/"both"; untouched otherwise.
        depth: Graph traversal depth for mode="graph"/"both" (1-5, default
              2). Only applies to project sources; ignored otherwise.
        direction: Graph traversal direction for mode="graph"/"both":
              "both" (default), "callers" (blast-radius direction -- files
              that depend on/call/import the seed), or "dependencies"
              (files the seed itself depends on).

    Returns:
        List of result dicts sorted by score (highest first).
    """
    all_results: list[dict] = []

    for source in sources:
        if source.startswith("project:"):
            project_path = source[8:]
            if mode == "both":
                # Run vector and graph, merge results
                vec = _search_project(query, project_path, code_embedder, limit, min_score)
                graph = _search_project_graph(
                    query, project_path, code_embedder, limit, min_score,
                    meta_out, depth, direction,
                )
                # Deduplicate by file+line_start, keeping higher score
                seen: dict[str, dict] = {}
                for r in vec + graph:
                    key = f"{r['file']}:{r.get('line_start', 0)}"
                    if key not in seen or r["score"] > seen[key]["score"]:
                        seen[key] = r
                all_results.extend(seen.values())
            elif mode == "graph":
                results = _search_project_graph(
                    query, project_path, code_embedder, limit, min_score,
                    meta_out, depth, direction,
                )
                all_results.extend(results)
            else:
                results = _search_project(query, project_path, code_embedder, limit, min_score)
                all_results.extend(results)
        else:
            logger.warning("Unknown source specifier: %s", source)

    # Sort by score descending, trim to limit
    all_results.sort(key=lambda r: r["score"], reverse=True)
    return all_results[:limit]


def _search_project(
    query: str, project_path: str, code_embedder, limit: int, min_score: float,
) -> list[dict]:
    """Search a project's codebase index (vector mode)."""
    project_root = Path(project_path).resolve()
    pid = hashlib.sha256(str(project_root).encode("utf-8")).hexdigest()[:12]

    chroma_dir = DATABASES_DIR / "_projects" / pid / "chroma"
    if not chroma_dir.exists():
        logger.warning("Project index not found for: %s (pid=%s)", project_path, pid)
        return []

    store = ChromaStore(persist_dir=str(chroma_dir))
    if not store.collection_exists("codebase"):
        return []

    query_embedding = code_embedder.embed_query(query)
    results = store.search("codebase", query_embedding, limit=limit, min_score=min_score)

    return [
        {
            "content": r.content,
            "score": r.score,
            "source_type": "project",
            "file": r.metadata.get("source_file", ""),
            "tree_path": r.metadata.get("tree_path", ""),
            "section": r.metadata.get("section", ""),
            "line_start": r.metadata.get("line_start", 0),
            "line_end": r.metadata.get("line_end", 0),
        }
        for r in results
    ]


def _search_project_graph(
    query: str, project_path: str, code_embedder, limit: int, min_score: float,
    meta_out: dict | None = None, depth: int = 2, direction: str = "both",
) -> list[dict]:
    """Search a project using structural graph traversal.

    Flow:
    1. Small vector search to find seed files (top 3 matches)
    2. Graph traversal from each seed to find structural neighbors
       (imports, callers, inheritance, out to `depth` hops)
    3. Fetch chunks for neighbor files from ChromaDB
    4. Score neighbors based on edge type and depth from seed, prune to
       the top `limit`*3 by that score (edge-weight/relation-strength to
       the seed is the primary pruning signal here -- PageRank is only
       used inside get_neighbours() as a frontier tiebreaker during
       traversal itself, not for ranking final results)

    Returns results tagged with source_type="project" and
    relation metadata showing the graph edge that surfaced them.

    If meta_out is passed, it's populated with graph_status
    ("absent" if the project has no graph.db/no edges, "empty" if the
    graph exists but this specific query's seeds have no neighbors,
    "hit" if real graph neighbors were found), graph_hit_count, and
    caller_count (neighbors reached via an edge that targets the seed,
    i.e. something that depends on the seed -- see edge direction note
    below).
    """
    if meta_out is not None:
        meta_out["graph_status"] = "absent"
        meta_out["graph_hit_count"] = 0
        meta_out["caller_count"] = 0

    project_root = Path(project_path).resolve()
    pid = hashlib.sha256(str(project_root).encode("utf-8")).hexdigest()[:12]
    index_dir = DATABASES_DIR / "_projects" / pid

    graph_db_path = index_dir / "graph.db"
    chroma_dir = index_dir / "chroma"

    if not graph_db_path.exists():
        logger.info("No graph.db for project %s, falling back to vector search", pid)
        return _search_project(query, project_path, code_embedder, limit, min_score)

    if not chroma_dir.exists():
        return []

    try:
        from .graph_store import SQLiteGraphStore, _EXTERNAL_SENTINEL
    except ImportError:
        logger.warning("graph_store not available, falling back to vector")
        return _search_project(query, project_path, code_embedder, limit, min_score)

    store = ChromaStore(persist_dir=str(chroma_dir))
    if not store.collection_exists("codebase"):
        return []

    graph = SQLiteGraphStore(str(graph_db_path))
    if not graph.has_graph():
        logger.info("Graph is empty for project %s, falling back to vector", pid)
        return _search_project(query, project_path, code_embedder, limit, min_score)

    # Step 1: small vector search for seed files
    query_embedding = code_embedder.embed_query(query)
    seed_results = store.search("codebase", query_embedding, limit=3, min_score=0.1)

    if not seed_results:
        return []

    # Collect unique seed files
    seed_files: list[str] = []
    seed_scores: dict[str, float] = {}
    for r in seed_results:
        f = r.metadata.get("source_file", "")
        if f and f not in seed_scores:
            seed_files.append(f)
            seed_scores[f] = r.score

    # Step 2: traverse graph from each seed
    neighbor_files: dict[str, dict] = {}  # file -> {edge_type, seed, depth, is_caller}
    for seed_file in seed_files:
        try:
            neighbors = graph.get_neighbours(seed_file, depth=depth, direction=direction)
        except Exception as e:
            logger.warning("Graph traversal failed for %s: %s", seed_file, e)
            continue

        for edge in neighbors:
            # get_neighbours() does an undirected lookup (file may be either
            # source_file or target_file of the edge, graph_store.py:346-350),
            # so the neighbor is whichever side isn't the seed -- not always
            # target_file. For depth-2 edges that touch neither side of the
            # seed directly (a neighbor-of-neighbor edge), fall back to
            # target_file, matching this function's original (buggy but at
            # least non-crashing) intent for that case.
            #
            # Direction relative to the seed: GraphEdge is source -> target
            # (graph_store.py:26-37), so edge.target_file == seed_file means
            # the OTHER side (edge.source_file) has an edge pointing INTO the
            # seed -- i.e. that neighbor depends on / calls / imports the
            # seed, making it a caller of the seed (the blast-radius
            # direction). edge.source_file == seed_file means the seed
            # points at the neighbor, i.e. the neighbor is a dependency.
            if edge.source_file == seed_file:
                neighbor = edge.target_file
                is_caller = False
            elif edge.target_file == seed_file:
                neighbor = edge.source_file
                is_caller = True
            else:
                neighbor = edge.target_file
                is_caller = False

            if not neighbor or neighbor == _EXTERNAL_SENTINEL:
                continue
            if neighbor in seed_scores:
                continue  # skip files already found by vector
            if neighbor not in neighbor_files:
                neighbor_files[neighbor] = {
                    "edge_type": edge.edge_type,
                    "seed": seed_file,
                    "seed_score": seed_scores[seed_file],
                    "is_caller": is_caller,
                }

    if meta_out is not None:
        meta_out["graph_hit_count"] = len(neighbor_files)
        meta_out["caller_count"] = sum(1 for v in neighbor_files.values() if v["is_caller"])
        meta_out["graph_status"] = "hit" if neighbor_files else "empty"

    if not neighbor_files:
        # No graph neighbors found, return vector seeds as results
        return [
            {
                "content": r.content,
                "score": r.score,
                "source_type": "project",
                "file": r.metadata.get("source_file", ""),
                "tree_path": r.metadata.get("tree_path", ""),
                "section": r.metadata.get("section", ""),
                "line_start": r.metadata.get("line_start", 0),
                "line_end": r.metadata.get("line_end", 0),
            }
            for r in seed_results
            if r.score >= min_score
        ]

    # Score weighting by edge type -- this, not PageRank, is the primary
    # signal for how relevant a neighbor is to the seed. PageRank (used
    # inside get_neighbours()) only decides which frontier nodes are worth
    # expanding further during traversal; it doesn't rank final results,
    # since a globally-central file (e.g. a shared utils.py) isn't
    # necessarily more relevant to THIS seed than a weakly-global but
    # directly, strongly connected one.
    edge_weights = {
        "imports": 0.9,
        "inherits": 0.85,
        "implements": 0.85,
        "calls": 0.8,
    }
    for info in neighbor_files.values():
        weight = edge_weights.get(info["edge_type"], 0.7)
        info["graph_score"] = round(info["seed_score"] * weight, 4)

    # Prune by graph_score before the chunk-fetch loop (each fetch is a
    # ChromaDB call) -- depth up to 5 with a 200-node frontier budget per
    # hop can still surface far more neighbors than any caller wants
    # results for.
    ranked_neighbors = sorted(
        neighbor_files.items(), key=lambda kv: kv[1]["graph_score"], reverse=True,
    )[: max(limit * 3, 15)]

    # Step 3: fetch chunks for neighbor files from ChromaDB
    results: list[dict] = []

    for nfile, info in ranked_neighbors:
        # Get chunks for this file from ChromaDB
        try:
            file_chunks = store.get_by_source("codebase", nfile)
        except Exception:
            continue

        if not file_chunks:
            continue

        graph_score = info["graph_score"]

        if graph_score < min_score:
            continue

        # Take the first chunk as representative (usually the imports/header)
        chunk = file_chunks[0]
        results.append({
            "content": chunk.content,
            "score": graph_score,
            "source_type": "project",
            "search_mode": "graph",
            "file": nfile,
            "tree_path": "/".join(nfile.replace("\\", "/").split("/")[:-1]),
            "section": "",
            "line_start": 0,
            "line_end": 0,
            "relation": info["edge_type"],
            "seed_file": info["seed"],
            "is_caller": info["is_caller"],
        })

    # Also include vector seeds in the output
    for r in seed_results:
        if r.score >= min_score:
            results.append({
                "content": r.content,
                "score": r.score,
                "source_type": "project",
                "search_mode": "vector_seed",
                "file": r.metadata.get("source_file", ""),
                "tree_path": r.metadata.get("tree_path", ""),
                "section": r.metadata.get("section", ""),
                "line_start": r.metadata.get("line_start", 0),
                "line_end": r.metadata.get("line_end", 0),
            })

    results.sort(key=lambda r: r["score"], reverse=True)
    return results[:limit]
