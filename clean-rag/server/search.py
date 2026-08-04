"""Search logic for clean-rag. Searches project codebase indexes."""

import logging
import re
from pathlib import Path

from .config import DATABASES_DIR, DEFAULT_MIN_SCORE, DEFAULT_SEARCH_LIMIT
from .project_id import resolve_project_dir
from .store import ChromaStore

logger = logging.getLogger(__name__)


#: Relation strength, the primary ranking signal for a graph neighbour.
#: Module level so the tiebreaker invariant below can be asserted against the
#: real numbers instead of a copy of them.
EDGE_WEIGHTS = {
    "imports": 0.9,
    "inherits": 0.85,
    "implements": 0.85,
    "calls": 0.8,
}

#: Applied to any edge type not named above.
DEFAULT_EDGE_WEIGHT = 0.7

#: Distance has to cost something. Without the decay a file 5 hops out scored
#: identically to a direct neighbour of the same edge type, so with depth>1 and
#: a 200 node frontier per hop, distant noise could outrank a direct neighbour
#: of a slightly weaker seed. 1 hop is unchanged (0.7**0 == 1.0).
DEPTH_DECAY = 0.7

#: How much the centrality ranking counts against the structural one when the
#: two are fused. Below 1.0 on purpose: structural proximity is measured
#: evidence, centrality is a hint. At 0.1 the hint can move a file past its
#: immediate neighbours, which is what it is for, but cannot carry one from the
#: bottom of the list to the top, which is what it did at parity.
CENTRALITY_WEIGHT = 0.1


def _personalized_ranks(graph, seed_files) -> dict[str, float]:
    """Personalized PageRank for this query, or {} if it cannot be computed.

    Never raises: ranking must degrade to the previous edge weighted behaviour
    rather than losing the search.
    """
    try:
        from .graph_store import compute_personalized_pagerank

        return compute_personalized_pagerank(graph, list(seed_files or ()))
    except Exception:
        logger.debug("Personalized PageRank unavailable", exc_info=True)
        return {}


def reciprocal_rank_fusion(
    *ranked_lists: list[dict], k: int = 60, key=None, weights=None,
) -> list[dict]:
    """Merge ranked result lists by RANK rather than by score.

    Vector search returns a cosine similarity; the graph walk returns an edge
    weighted product. Those are different scales, so the previous merge (keep
    whichever number is larger) was comparing quantities that were never
    comparable, and whichever scoring scheme happened to produce bigger floats
    won regardless of which result was better.

    RRF sidesteps that entirely by throwing the scores away and using only
    position: score(d) = sum over lists of 1 / (k + rank(d)). Cormack et al.
    2009, and the same formula Elasticsearch, OpenSearch and Qdrant use for
    hybrid search. k=60 is their shared default; it damps the difference
    between the top few positions so one list cannot dominate purely by being
    confident.

    Each input list must already be sorted best first. The returned dicts are
    the originals with an added ``rrf_score``, ordered by it.

    *weights* optionally scales each list's contribution, so
    ``score(d) = sum over lists of wi / (k + rank_i(d))``. Elasticsearch and
    Qdrant both expose the same per retriever weight, and it is needed for the
    same reason they expose it: unweighted, every list is equally authoritative,
    so a list that is only a hint can outvote the one carrying the evidence. A
    file ranked LAST on structure but first on centrality won outright before
    this existed. Defaults to 1.0 per list, which is plain RRF.
    """
    if key is None:
        def key(r):
            return f"{r.get('file', '')}:{r.get('line_start', 0)}"

    if weights is None:
        weights = [1.0] * len(ranked_lists)
    if len(weights) != len(ranked_lists):
        raise ValueError(
            f"weights has {len(weights)} entries for {len(ranked_lists)} lists"
        )

    scores: dict[str, float] = {}
    best: dict[str, dict] = {}

    for weight, results in zip(weights, ranked_lists):
        for rank, result in enumerate(results):
            identity = key(result)
            scores[identity] = scores.get(identity, 0.0) + weight / (k + rank + 1)
            # Keep the richer record when the same chunk appears in both lists.
            # Graph results carry relation/seed_file that vector results lack,
            # and losing those would drop the explanation of why a file is here.
            if identity not in best or len(result) > len(best[identity]):
                best[identity] = result

    fused = []
    for identity, score in sorted(scores.items(), key=lambda kv: kv[1], reverse=True):
        record = dict(best[identity])
        record["rrf_score"] = round(score, 6)
        fused.append(record)
    return fused


_TOKEN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def _tokenize(text: str) -> list[str]:
    """Identifier aware tokens, lowercased.

    Splits camelCase and snake_case as well as keeping the whole identifier, so
    a query for ``sweepProject`` matches ``_sweep_project`` and vice versa.
    BM25 scores on exact token overlap, so the tokenizer decides what "exact"
    even means here.
    """
    out: list[str] = []
    for word in _TOKEN.findall(text or ""):
        lowered = word.lower()
        out.append(lowered)
        parts = [p for p in word.split("_") if p]
        for part in parts:
            for piece in re.findall(r"[A-Z]+(?![a-z])|[A-Z][a-z0-9]*|[a-z0-9]+", part):
                piece = piece.lower()
                if piece and piece != lowered:
                    out.append(piece)
    return out


def _search_project_keyword(query: str, candidates: list[dict], limit: int) -> list[dict]:
    """Rank *candidates* by BM25 over their own text.

    Reranks what vector and graph already found rather than scanning the whole
    project. That keeps it cheap and needs no second index, and it still fixes
    the failure it exists for: a chunk containing the literal identifier being
    ranked below one that is merely semantically close.

    Returns [] when rank_bm25 is missing or there is nothing to rank, which
    makes it inert rather than a hard dependency.
    """
    if not candidates:
        return []
    try:
        from rank_bm25 import BM25Okapi
    except ImportError:
        logger.debug("rank_bm25 not installed, skipping the keyword leg")
        return []

    tokenized_query = _tokenize(query)
    if not tokenized_query:
        return []

    # Deduplicate on the same identity the fusion uses, or one chunk appearing
    # in both input lists would get two BM25 ranks and count twice.
    seen: dict[str, dict] = {}
    for r in candidates:
        seen.setdefault(f"{r.get('file', '')}:{r.get('line_start', 0)}", r)
    unique = list(seen.values())

    corpus = [
        _tokenize(f"{r.get('file', '')} {r.get('content', '')}") for r in unique
    ]
    if not any(corpus):
        return []

    try:
        scores = BM25Okapi(corpus).get_scores(tokenized_query)
    except Exception:
        logger.debug("BM25 scoring failed", exc_info=True)
        return []

    # Membership is decided by token overlap, NOT by score > 0.
    #
    # BM25's IDF term goes negative for anything appearing in more than half
    # the documents, which is normal and harmless over a whole corpus and
    # completely wrong here: this reranks a handful of candidates, so with two
    # documents EVERY score came out negative and a `score > 0` filter threw
    # away all of them, including the exact identifier match it existed to
    # promote. Measured: the literal `_sweep_project` chunk scored -0.084.
    #
    # Overlap answers the actual question ("does this chunk contain a token
    # the user typed") and does not move with corpus size. The score then only
    # has to order the survivors, which is what it is good at.
    wanted = set(tokenized_query)
    scored = [
        (r, s) for r, s, toks in zip(unique, scores, corpus) if wanted & set(toks)
    ]
    scored.sort(key=lambda pair: pair[1], reverse=True)
    return [r for r, _s in scored][:limit]


def _provenance_mismatch(project_path: str, code_embedder) -> str | None:
    """Return a reason string if this project's index cannot be trusted.

    A vector index only means anything to the model that produced it. Two
    different models of the same width (CodeRankEmbed and
    st-codesearch-distilroberta-base are both 768) produce vectors that are
    dimensionally compatible and semantically unrelated, so every width check in
    the stack passes and the results come back confidently wrong rather than
    empty. The recorded model id is the only thing that catches it.

    Returns None when the index is safe to query.
    """
    from .indexing import read_project_provenance

    current = getattr(code_embedder, "model_name", None)
    if current is None:
        return None  # not a model-identifying embedder, nothing to compare

    recorded = read_project_provenance(project_path).get("model_id")
    if recorded is None:
        return (
            f"index has no recorded embedding model, so it cannot be confirmed to "
            f"match the current model ({current}); reindex to make it searchable"
        )
    if recorded != current:
        return (
            f"index was built with {recorded} but queries now use {current}; "
            f"reindex to make it searchable"
        )
    return None


def _embedder_for_project(project_path: str, default_embedder, embedder_for):
    """The embedder that actually produced this project's vectors.

    `lang_router` picks an embedding model per project at index time, from the
    project's dominant language. The query side did not: every search embedded
    with the one global CODE_EMBEDDING_MODEL, so `_provenance_mismatch` refused
    every project the router had routed anywhere else. Measured, that was 12,758
    files across 5 projects returning zero results, with the index itself
    perfectly good. The vectors were never the problem; querying them with the
    wrong model was.

    So resolve the model from the index's own provenance and load that one. This
    is a query side fix on purpose: nothing is reindexed, because nothing about
    the stored vectors is wrong.

    Falls back to *default_embedder* whenever the recorded model cannot be
    determined or cannot be loaded. Failing that way keeps the old behaviour,
    which means `_provenance_mismatch` still refuses the search rather than
    silently answering from the wrong embedding space.

    Returns (embedder, model_id_switched_to_or_None).
    """
    if embedder_for is None:
        return default_embedder, None

    from .indexing import read_project_provenance

    try:
        recorded = read_project_provenance(project_path).get("model_id")
    except Exception:
        logger.debug("Could not read provenance for %s", project_path, exc_info=True)
        return default_embedder, None

    # No recorded model is not a routing question, it is an unverifiable index.
    # Leave it to _provenance_mismatch, which refuses it with that reason.
    if not recorded:
        return default_embedder, None

    if recorded == getattr(default_embedder, "model_name", None):
        return default_embedder, None

    try:
        return embedder_for(recorded), recorded
    except Exception as e:
        logger.warning(
            "Index for %s was built with %s, which failed to load (%s); "
            "falling back to the default embedder, which will refuse the search",
            project_path, recorded, e,
        )
        return default_embedder, None


def _incomplete_index_warning(project_path: str) -> str | None:
    """Return a warning if this project's index covers only part of the tree.

    An indexing run that hit the pressure guard, or a server that went down
    mid sweep, leaves a manifest marked ``__incomplete__`` listing a real
    subset of the project. Every chunk in it was produced by the current model
    from a real file, so the hits are genuine; what is missing is coverage.

    Returns None when the index covers the whole project.
    """
    from .indexing import index_is_incomplete

    if not index_is_incomplete(project_path):
        return None
    return (
        "index is incomplete: an indexing run stopped before it reached every "
        "file, so these results cover only part of the project and a missing "
        "hit does not mean the code is absent; reindex to complete it"
    )


def _check_index_before_search(project_path: str, code_embedder, meta_out: dict | None) -> bool:
    """Record anything the caller must know about this project's index.

    Returns False when the index must not be queried at all, True when it is
    safe to query, which may still leave a warning recorded in *meta_out*.

    Two ways an index can be untrustworthy, and they get opposite answers,
    because one makes the results WRONG and the other only makes them PARTIAL.

    Wrong: an index built in a different embedding space. Every score is
    confident nonsense and nothing downstream can tell those hits from real
    ones, so refuse and state the reason. Returning nothing with a reason is
    recoverable; returning plausible wrong files is not.

    Partial: an indexing run stopped early. The chunks that made it in are real
    and correctly embedded, there are just fewer of them than the project has
    files. Served with a warning rather than refused, deliberately. Refusing
    would throw away correct results to avoid a coverage gap, and would make
    any interrupted sweep un-searchable until it finishes, which is open ended
    on the machine that interrupted it in the first place, exactly when search
    matters. This is the call Elasticsearch makes for the same shape of
    problem: when shards fail it returns what the surviving shards found and
    sets ``_shards.failed`` / ``timed_out`` on the response rather than
    erroring the whole search
    (https://www.elastic.co/docs/solutions/search/the-search-api).

    The risk of a warning is that the caller ignores it, so noticing a thin
    result set is not left to the caller: the entry rides the same
    ``stale_projects`` channel /search already surfaces for a refusal, and
    ``served`` is what tells the two apart, so "results plus a stale_projects
    entry" can never be misread as "refused".
    """
    def note(reason: str, served: bool) -> None:
        if meta_out is not None:
            meta_out.setdefault("stale_projects", []).append({
                "project": project_path,
                "reason": reason,
                "served": served,
            })

    stale_reason = _provenance_mismatch(project_path, code_embedder)
    if stale_reason is not None:
        logger.warning("Skipping stale index for %s: %s", project_path, stale_reason)
        note(stale_reason, served=False)
        return False

    incomplete_reason = _incomplete_index_warning(project_path)
    if incomplete_reason is not None:
        logger.warning("Partial index for %s: %s", project_path, incomplete_reason)
        note(incomplete_reason, served=True)

    return True


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
    doc_embedder=None,
    embedder_for=None,
) -> list[dict]:
    """Search across project codebase indexes and persistent docs topics.

    Args:
        query: The search query text.
        sources: List of source specifiers:
            - "project:<path>" to search a project's codebase index
            - "docs:<topic>" to search a persistent official documents topic
        code_embedder: Code embedder (st-codesearch-distilroberta-base).
        doc_embedder: General prose embedder for docs: sources. Required only
            when a docs: source is present; project: sources ignore it.
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
        embedder_for: Optional callable model_id -> embedder, used to query
              each project with the model its own index was built with rather
              than with `code_embedder`. Without it every project is queried
              with `code_embedder`, which is what made router-routed projects
              unsearchable. Per project source, so one request naming projects
              on different models works.

    Returns:
        List of result dicts sorted by score (highest first).
    """
    all_results: list[dict] = []

    for source in sources:
        if source.startswith("project:"):
            project_path = source[8:]

            # Resolved per source, not once per request: two projects in one
            # search can legitimately sit on different models.
            project_embedder, switched_to = _embedder_for_project(
                project_path, code_embedder, embedder_for,
            )
            if switched_to:
                logger.info(
                    "Querying %s with its own index model %s", project_path, switched_to,
                )

            if not _check_index_before_search(project_path, project_embedder, meta_out):
                continue

            if mode == "both":
                # Run vector and graph, then fuse by rank.
                #
                # This used to dedupe on file+line and keep whichever score was
                # numerically larger, which silently compared a cosine
                # similarity against an edge weighted graph product. Those have
                # no common scale, so the merge was decided by which formula
                # emitted bigger floats rather than which hit was better.
                vec = _search_project(query, project_path, project_embedder, limit, min_score)
                graph = _search_project_graph(
                    query, project_path, project_embedder, limit, min_score,
                    meta_out, depth, direction,
                )
                # Keyword is the third leg, and it covers the one thing
                # embeddings are worst at: an exact identifier. A query for
                # `_sweep_project` should find the literal token, and cosine
                # similarity will happily return something that merely reads
                # like it instead.
                keyword = _search_project_keyword(
                    query, vec + graph, limit,
                )
                all_results.extend(
                    reciprocal_rank_fusion(vec, graph, keyword)
                )
            elif mode == "graph":
                results = _search_project_graph(
                    query, project_path, project_embedder, limit, min_score,
                    meta_out, depth, direction,
                )
                all_results.extend(results)
            else:
                results = _search_project(query, project_path, project_embedder, limit, min_score)
                all_results.extend(results)
        elif source.startswith("docs:"):
            topic = source[5:]
            if doc_embedder is None:
                logger.warning("docs: source requested but no doc_embedder provided: %s", source)
                continue
            from .docs_store import search_topic
            all_results.extend(search_topic(query, topic, doc_embedder, limit, min_score))
        else:
            logger.warning("Unknown source specifier: %s", source)

    # Sort by score descending, trim to limit
    # Sort on the fused rank where there is one, otherwise the raw score.
    #
    # Sorting purely on "score" here would have thrown away the fusion the
    # moment it was computed: RRF deliberately ignores the raw scores because
    # they are not comparable across sources, so re-sorting by exactly those
    # scores puts the incomparable ordering right back. Results from a single
    # source have no rrf_score and keep their own ordering, and a mixed list
    # (project: fused, docs: not) puts the fused ones first, which is correct:
    # a result corroborated by two retrieval methods outranks one seen by one.
    all_results.sort(
        key=lambda r: (r.get("rrf_score") is not None, r.get("rrf_score", 0.0), r["score"]),
        reverse=True,
    )
    return all_results[:limit]


def _search_project(
    query: str, project_path: str, code_embedder, limit: int, min_score: float,
) -> list[dict]:
    """Search a project's codebase index (vector mode)."""
    project_root = Path(project_path).resolve()
    pid = resolve_project_dir(DATABASES_DIR / "_projects", project_root).name

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
    4. Rank neighbours two ways and fuse by rank: structurally (edge type and
       hop distance) and by personalized PageRank, then prune to the top
       `limit`*3.

    This function backs both mode="graph" and mode="both". `score` on each
    result stays the pure structural number, so it is comparable with what
    this function has always returned; the PageRank signal affects the ORDER
    and which neighbours survive the prune, not the score value.

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
    index_dir = resolve_project_dir(DATABASES_DIR / "_projects", project_root)
    pid = index_dir.name

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
        hop_of: dict[str, int] = {}
        try:
            neighbors = graph.get_neighbours(
                seed_file, depth=depth, direction=direction, depths_out=hop_of,
            )
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
                    # 1 if the traversal never reported a hop for this file,
                    # which keeps the decay a no-op rather than a KeyError.
                    "depth": hop_of.get(neighbor, 1),
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

    # Two orderings, fused by rank.
    #
    # Structural: edge type times hop decay times how good the seed was. This
    # is the evidence, and on its own it is what this function always used.
    #
    # Centrality: personalized PageRank, which answers "important relative to
    # THESE seeds" rather than the global "utils.py is central to the repo",
    # which is equally true for every query and therefore worthless for
    # ranking.
    #
    # They are fused rather than multiplied together. Multiplying was the
    # original attempt and it was the exact mistake reciprocal_rank_fusion
    # exists to prevent, stated in its own docstring twenty lines up: a
    # PageRank value and an edge weight product share no scale, so combining
    # them by arithmetic means whichever happens to produce bigger floats wins.
    # That was not theoretical. It put a 2 hop hub at 0.8505 above a direct
    # neighbour at 0.7902. Capping the multiplier below the smallest structural
    # gap did fix the inversion, but it took a bespoke derivation to prove a
    # bound that RRF gets for free by never touching the raw numbers at all.
    #
    # Consequence worth naming: RRF is rank based, so centrality can now break
    # a tie between two files that differ structurally but land adjacent in the
    # ordering, not only between exactly equal scores. That is a slightly
    # stronger tiebreak than the capped multiplier allowed, and it is the
    # intended trade for deleting the derivation.
    for nfile, info in neighbor_files.items():
        weight = EDGE_WEIGHTS.get(info["edge_type"], DEFAULT_EDGE_WEIGHT)
        decay = DEPTH_DECAY ** (max(info["depth"], 1) - 1)
        info["graph_score"] = round(info["seed_score"] * weight * decay, 4)

    by_structure = sorted(
        neighbor_files, key=lambda f: neighbor_files[f]["graph_score"], reverse=True,
    )
    ppr = _personalized_ranks(graph, seed_files)
    by_centrality = (
        sorted(neighbor_files, key=lambda f: ppr.get(f, 0.0), reverse=True)
        if ppr else []
    )

    # Same fusion the vector and graph lists get in search(), so there is one
    # answer to "these scores are not comparable" in this file rather than two.
    #
    # Weighted, because these two lists are not equally authoritative.
    # Structure is the evidence: this file really is one import hop from
    # something the query matched. Centrality is a hint about the shape of the
    # neighbourhood. Unweighted, the hint outvoted the evidence outright, and a
    # file ranked LAST on structure but first on centrality came back first.
    fused_order = [
        r["file"] for r in reciprocal_rank_fusion(
            [{"file": f} for f in by_structure],
            [{"file": f} for f in by_centrality],
            key=lambda r: r["file"],
            weights=(1.0, CENTRALITY_WEIGHT),
        )
    ]

    # Prune before the chunk-fetch loop (each fetch is a ChromaDB call) --
    # depth up to 5 with a 200-node frontier budget per hop can still surface
    # far more neighbors than any caller wants results for.
    ranked_neighbors = [
        (f, neighbor_files[f]) for f in fused_order[: max(limit * 3, 15)]
    ]

    # Step 3: fetch chunks for neighbor files from ChromaDB
    results: list[dict] = []

    for nfile, info in ranked_neighbors:
        # Get chunks for this file from ChromaDB
        try:
            file_chunks = store.get_by_source("codebase", nfile)
        except Exception as e:
            logger.warning(
                "graph search: failed to fetch chunks for %s: %s: %s",
                nfile, type(e).__name__, e,
            )
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
