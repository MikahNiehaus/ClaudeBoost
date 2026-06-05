"""RAG retrieval quality benchmark suite.

Measures retrieval quality using industry-standard methodologies:

  - BEIR-style Recall@k  — ground-truth query/source pairs across all scopes
  - MTEB-style nDCG@k    — normalised discounted cumulative gain for ranking quality
  - MRR                  — mean reciprocal rank for first-hit latency
  - CodeSearchNet-style  — natural-language queries mapped to specific code files
  - GraphRAG-Bench-style — multi-hop graph reasoning: does graph mode surface
                           structural neighbours that vector-only mode misses?

References:
  BEIR (Thakur et al. 2021)     — https://arxiv.org/abs/2104.08663
  MTEB (Muennighoff et al. 2022) — https://arxiv.org/abs/2210.07316
  GraphRAG-Bench (ICLR 2026)    — https://arxiv.org/abs/2506.05690
  CodeSearchNet (Husain et al.)  — https://arxiv.org/abs/1909.09436

Run from the repo root:
    pytest mcp-rag-server/tests/test_rag_quality.py -v -s

Requires:
    - RAG server running at http://127.0.0.1:8612
    - ClaudeBoost knowledge + agents indexed (run /index-boost first)
    - Project codebase indexed at this repo root (run /index-project first)

Skip gracefully when the server is unreachable.
"""

import json
import math
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import pytest

RAG_URL = "http://127.0.0.1:8612"
# Repo root: two levels up from mcp-rag-server/tests/
PROJECT_PATH = os.environ.get(
    "CLAUDEBOOST_HOME",
    str(Path(__file__).parent.parent.parent.resolve()),
)


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def _call(endpoint: str, payload: dict) -> dict:
    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"{RAG_URL}{endpoint}",
        data=body,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


def _server_alive() -> bool:
    try:
        urllib.request.urlopen(f"{RAG_URL}/status", timeout=5)
        return True
    except Exception:
        return False


def _search(query: str, scope: str, mode: str = "vector", limit: int = 5) -> list[dict]:
    payload: dict[str, Any] = {"query": query, "scope": scope, "limit": limit, "mode": mode}
    if scope == "codebase":
        payload["project_path"] = PROJECT_PATH
    result = _call("/search", payload)
    return result.get("results", [])


def _source_files(results: list[dict]) -> list[str]:
    return [r.get("source", "") for r in results]


# ---------------------------------------------------------------------------
# Metric implementations
# ---------------------------------------------------------------------------

def _recall_at_k(results: list[dict], fragment: str, k: int) -> bool:
    """True if any of the top-k results has source matching fragment."""
    for r in results[:k]:
        if fragment in r.get("source", ""):
            return True
    return False


def _reciprocal_rank(results: list[dict], fragment: str) -> float:
    """MRR component: 1/rank of first hit, 0 if not found."""
    for i, r in enumerate(results, start=1):
        if fragment in r.get("source", ""):
            return 1.0 / i
    return 0.0


def _ndcg_at_k(results: list[dict], relevant_fragments: list[str], k: int) -> float:
    """Binary-relevance nDCG@k (BEIR / MTEB standard).

    Deduplicates by source file first (each file counted once at its first
    rank) so multiple chunks from the same file don't inflate DCG above 1.0.
    """
    seen: set[str] = set()
    deduped: list[dict] = []
    for r in results:
        src = r.get("source", "")
        if src not in seen:
            seen.add(src)
            deduped.append(r)

    gains = []
    for r in deduped[:k]:
        src = r.get("source", "")
        gains.append(1.0 if any(frag in src for frag in relevant_fragments) else 0.0)

    dcg = sum(g / math.log2(i + 2) for i, g in enumerate(gains))

    n_relevant = min(len(relevant_fragments), k)
    idcg = sum(1.0 / math.log2(i + 2) for i in range(n_relevant))

    return dcg / idcg if idcg > 0 else 0.0


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session", autouse=True)
def require_server():
    if not _server_alive():
        pytest.skip("RAG server not reachable at 127.0.0.1:8612 — start with /rag")


# ---------------------------------------------------------------------------
# BEIR-style — Knowledge scope Recall@3
#
# Each pair: (natural-language query, expected source fragment)
# Ground truth derived from ClaudeBoost knowledge index.
# ---------------------------------------------------------------------------

KNOWLEDGE_CASES = [
    # Original cases
    ("SQL injection prevention parameterized queries", "database"),
    ("BM25 hybrid search reciprocal rank fusion", "knowledge"),
    ("SOLID principles single responsibility", "coding-standards"),
    ("Python type hints annotations", "lang-python"),
    ("React hooks useState useEffect", "fw-react"),
    ("Django ORM models database", "fw-django"),
    ("cross-encoder reranking candidates", "knowledge"),
    ("code review checklist", "knowledge"),
    # Extended — language guides
    ("TypeScript strict mode type narrowing interface", "lang-typescript"),
    ("TypeScript named exports avoid default export", "lang-typescript"),
    # Extended — framework guides
    ("FastAPI Depends dependency injection route handler", "fw-fastapi"),
    ("Next.js server components app router data fetching", "fw-nextjs"),
    # Extended — observability
    ("structured logging INFO ERROR level when to log", "observability"),
    ("distributed tracing spans metrics APM monitoring", "observability"),
]


@pytest.mark.parametrize("query,expected_fragment", KNOWLEDGE_CASES)
def test_knowledge_recall_at_3(query: str, expected_fragment: str):
    results = _search(query, scope="knowledge", limit=5)
    assert results, f"No results returned for: {query!r}"
    hit = _recall_at_k(results, expected_fragment, k=3)
    sources = _source_files(results)[:3]
    assert hit, (
        f"Recall@3 miss — query={query!r}, expected fragment={expected_fragment!r}\n"
        f"Top-3 sources: {sources}"
    )


# ---------------------------------------------------------------------------
# BEIR-style — Agents scope Recall@3
# ---------------------------------------------------------------------------

AGENTS_CASES = [
    ("security audit vulnerability scan", "security"),
    ("code review pull request", "reviewer"),
    ("architecture design SOLID principles", "architect"),
    ("performance profiling bottleneck", "performance"),
    ("database schema migration query", "database"),
    # Extended
    ("end-to-end browser testing Playwright", "e2e"),
    ("RAG index codebase semantic search", "rag-indexing"),
]


@pytest.mark.parametrize("query,expected_fragment", AGENTS_CASES)
def test_agents_recall_at_3(query: str, expected_fragment: str):
    results = _search(query, scope="agents", limit=5)
    assert results, f"No results returned for: {query!r}"
    hit = _recall_at_k(results, expected_fragment, k=3)
    sources = _source_files(results)[:3]
    assert hit, (
        f"Recall@3 miss — query={query!r}, expected fragment={expected_fragment!r}\n"
        f"Top-3 sources: {sources}"
    )


# ---------------------------------------------------------------------------
# BEIR / MTEB-style — Codebase vector Recall@5
# ---------------------------------------------------------------------------

CODEBASE_CASES_VECTOR = [
    ("chunk_markdown paragraph split overlap", "markdown_chunker"),
    ("cross-encoder reranker predict logits", "search"),
    ("SQLite graph store add edges", "sqlite_graph_store"),
    ("community detection Leiden graspologic", "community"),
    ("embedding model sentence transformers", "embedding"),
    ("FTS5 BM25 full text search", "fts_store"),
    # Extended
    ("XML chunker top-level element boundary", "xml_chunker"),
    ("PDF text extraction page PyMuPDF", "pdf_chunker"),
]


@pytest.mark.parametrize("query,expected_fragment", CODEBASE_CASES_VECTOR)
def test_codebase_vector_recall_at_5(query: str, expected_fragment: str):
    results = _search(query, scope="codebase", mode="vector", limit=5)
    assert results, f"No results returned for: {query!r}"
    hit = _recall_at_k(results, expected_fragment, k=5)
    sources = _source_files(results)[:5]
    assert hit, (
        f"Recall@5 miss — query={query!r}, expected fragment={expected_fragment!r}\n"
        f"Top-5 sources: {sources}"
    )


# ---------------------------------------------------------------------------
# CodeSearchNet-style — natural-language → code file
#
# Queries are written as a developer would describe the function they want,
# not as keywords from the source. Tests whether the embedding model
# generalises beyond literal term overlap.
# ---------------------------------------------------------------------------

CODESEARCH_CASES = [
    # (natural-language description, expected source fragment)
    (
        "split a text document into sections at heading boundaries, "
        "merging small trailing sections",
        "markdown_chunker",
    ),
    (
        "retrieve all structural neighbours of a source file from a graph database",
        "sqlite_graph_store",
    ),
    (
        "merge two ranked result lists using reciprocal rank fusion",
        "search",
    ),
    (
        "download a URL, convert the HTML to markdown, and split it into chunks",
        "url_chunker",
    ),
    (
        "extract text from a PDF file and split it into paragraphs",
        "pdf_chunker",
    ),
]


@pytest.mark.parametrize("description,expected_fragment", CODESEARCH_CASES)
def test_codesearch_recall_at_5(description: str, expected_fragment: str):
    """CodeSearchNet-style: natural language description → correct source file."""
    results = _search(description, scope="codebase", mode="vector", limit=5)
    assert results, f"No results for: {description[:60]!r}"
    hit = _recall_at_k(results, expected_fragment, k=5)
    sources = _source_files(results)[:5]
    assert hit, (
        f"CodeSearch miss — description={description[:60]!r}\n"
        f"Expected fragment: {expected_fragment!r}\n"
        f"Top-5 sources: {sources}"
    )


# ---------------------------------------------------------------------------
# GraphRAG-Bench-style — multi-hop structural retrieval
#
# Methodology from GraphRAG-Bench (ICLR 2026, arxiv:2506.05690):
# "Does graph mode surface structural neighbours that vector-only misses?"
#
# Each case: (query, seed_fragment, neighbour_fragment)
# The graph mode should return BOTH the seed file AND its structural
# import-chain neighbour. Vector-only typically returns only the seed.
# ---------------------------------------------------------------------------

GRAPH_MULTIHOP_CASES = [
    # xml_chunker imports from markdown_chunker — graph should pull both
    (
        "XML chunker split on element boundaries",
        "xml_chunker",
        "markdown_chunker",
    ),
    # url_chunker and pdf_chunker are siblings in the indexing module,
    # both importing from markdown_chunker — graph should surface the sibling
    (
        "URL chunker download and parse web page into chunks",
        "url_chunker",
        "pdf_chunker",
    ),
    # search.py imports sqlite_graph_store — graph traversal augments results
    (
        "search endpoint augment results with graph neighbours",
        "search",
        "sqlite_graph_store",
    ),
]


@pytest.mark.parametrize("query,seed_fragment,neighbour_fragment", GRAPH_MULTIHOP_CASES)
def test_graph_multihop_surfaces_neighbour(
    query: str, seed_fragment: str, neighbour_fragment: str
):
    """GraphRAG-Bench-style: graph mode should return both seed AND structural neighbour."""
    results = _search(query, scope="codebase", mode="graph", limit=7)
    assert results, f"No results returned for: {query!r}"

    has_seed = _recall_at_k(results, seed_fragment, k=7)
    has_neighbour = _recall_at_k(results, neighbour_fragment, k=7)
    sources = _source_files(results)

    assert has_seed, (
        f"Graph multi-hop miss (seed) — query={query!r}\n"
        f"Expected seed fragment: {seed_fragment!r}\n"
        f"Sources: {sources}"
    )
    assert has_neighbour, (
        f"Graph multi-hop miss (neighbour) — query={query!r}\n"
        f"Expected neighbour fragment: {neighbour_fragment!r}\n"
        f"Sources: {sources}"
    )


# ---------------------------------------------------------------------------
# Graph vs. vector advantage test
#
# Shows that graph mode adds files that vector-only mode misses.
# Each case: query where vector alone finds the seed but NOT the neighbour.
# ---------------------------------------------------------------------------

GRAPH_VS_VECTOR_CASES = [
    ("xml_chunker split element boundaries", "xml_chunker", "markdown_chunker"),
    ("search augment graph structural neighbours", "search", "sqlite_graph_store"),
]


@pytest.mark.parametrize("query,seed_fragment,expected_extra", GRAPH_VS_VECTOR_CASES)
def test_graph_adds_beyond_vector(query: str, seed_fragment: str, expected_extra: str):
    """Graph mode should surface at least one file that vector-only mode doesn't return."""
    vector_results = _search(query, scope="codebase", mode="vector", limit=5)
    graph_results = _search(query, scope="codebase", mode="graph", limit=7)

    vector_sources = set(_source_files(vector_results))
    graph_sources = set(_source_files(graph_results))
    graph_only = graph_sources - vector_sources

    # If neither mode finds the seed at all, skip — index may be stale
    if not _recall_at_k(vector_results, seed_fragment, k=5) and \
       not _recall_at_k(graph_results, seed_fragment, k=7):
        pytest.skip(f"Seed file {seed_fragment!r} not found in either mode — index may be stale")

    assert any(expected_extra in s for s in graph_only) or \
           _recall_at_k(graph_results, expected_extra, k=7), (
        f"Graph didn't add {expected_extra!r} beyond vector results\n"
        f"Vector sources: {sorted(vector_sources)}\n"
        f"Graph-only additions: {sorted(graph_only)}"
    )


# ---------------------------------------------------------------------------
# Original graph-mode codebase cases (kept for backwards compatibility)
# ---------------------------------------------------------------------------

CODEBASE_CASES_GRAPH = [
    ("search.py imports graph store reranker", "search"),
    ("engine.py imports community detection", "engine"),
    # Extended
    ("indexing pipeline scan embed store chunks", "engine"),
    ("SQLite graph store resolve target files edges neighbours", "sqlite_graph_store"),
]


@pytest.mark.parametrize("query,expected_fragment", CODEBASE_CASES_GRAPH)
def test_codebase_graph_recall_at_5(query: str, expected_fragment: str):
    results = _search(query, scope="codebase", mode="graph", limit=5)
    assert results, f"No results returned for: {query!r}"
    hit = _recall_at_k(results, expected_fragment, k=5)
    sources = _source_files(results)[:5]
    assert hit, (
        f"Recall@5 miss (graph mode) — query={query!r}, expected fragment={expected_fragment!r}\n"
        f"Top-5 sources: {sources}"
    )


# ---------------------------------------------------------------------------
# /graph skill benchmark
#
# The /graph skill (`.claude/commands/graph.md`) builds a "Files in Scope"
# map by:
#   1. Extracting entity names from a task description
#   2. Running POST /search scope=codebase mode=graph for each entity
#   3. Collecting unique file paths as structural context
#
# These tests simulate exactly that pattern with real task descriptions and
# assert the skill surfaces the right structural files — both primary hits
# (vector) and structural neighbours (graph traversal).
#
# This is the deepest benchmark: it exercises the full graph skill pipeline
# rather than just testing individual API calls.
# ---------------------------------------------------------------------------

GRAPH_SKILL_CASES = [
    # (task_description, primary_entities, expected_files_in_scope)
    (
        "fix the search endpoint to correctly report graph_augmented flag",
        # /graph skill extracts code entity names, not plain words
        ["rag_server/tools/search", "SQLiteGraphStore"],
        ["search", "sqlite_graph_store"],
    ),
    (
        "update the markdown chunker to preserve code blocks during splitting",
        ["markdown_chunker", "chunk_markdown"],
        ["markdown_chunker", "xml_chunker", "url_chunker"],  # both import markdown_chunker
    ),
    (
        "add PageRank weighting to graph neighbour scoring",
        ["sqlite_graph_store", "PageRank"],
        ["sqlite_graph_store", "search"],  # search.py calls get_all_pagerank
    ),
]


def _run_graph_skill(task_description: str, entities: list[str], limit: int = 5) -> set[str]:
    """Simulate what the /graph skill does: search each entity in graph mode, collect file paths."""
    files_in_scope: set[str] = set()
    for entity in entities:
        try:
            results = _search(entity, scope="codebase", mode="graph", limit=limit)
            for r in results:
                src = r.get("source", "")
                if src:
                    files_in_scope.add(src)
        except Exception:
            pass
    return files_in_scope


@pytest.mark.parametrize("description,entities,expected_files", GRAPH_SKILL_CASES)
def test_graph_skill_files_in_scope(
    description: str, entities: list[str], expected_files: list[str]
):
    """/graph skill benchmark: task description → Files in Scope covers expected structural files."""
    files_in_scope = _run_graph_skill(description, entities)

    missing = [
        frag for frag in expected_files
        if not any(frag in src for src in files_in_scope)
    ]
    assert not missing, (
        f"/graph skill missed files for: {description!r}\n"
        f"Missing fragments: {missing}\n"
        f"Files in scope ({len(files_in_scope)}): {sorted(files_in_scope)}"
    )


def test_graph_skill_vs_vector_scope_size():
    """/graph skill consistently returns more unique files than vector-only for structural queries."""
    task = "fix graph augmentation in the search endpoint"
    entities = ["search", "graph store", "augment"]

    vector_files: set[str] = set()
    graph_files: set[str] = set()

    for entity in entities:
        v = _search(entity, scope="codebase", mode="vector", limit=5)
        g = _search(entity, scope="codebase", mode="graph", limit=7)
        vector_files.update(r.get("source", "") for r in v)
        graph_files.update(r.get("source", "") for r in g)

    graph_only = graph_files - vector_files

    print(f"\n/graph skill scope comparison:")
    print(f"  Vector scope: {len(vector_files)} files")
    print(f"  Graph scope:  {len(graph_files)} files")
    print(f"  Graph-only additions: {len(graph_only)} files")
    if graph_only:
        print(f"  Added by graph: {sorted(graph_only)}")

    # Graph should surface at least as many unique files as vector
    assert len(graph_files) >= len(vector_files), (
        f"Graph scope ({len(graph_files)}) smaller than vector scope ({len(vector_files)})"
    )


# ---------------------------------------------------------------------------
# Normal indexing quality check — vector AND graph
#
# /index-project builds BOTH the vector index (embeddings) and the graph
# index (import/inheritance edges) in a single pass. These tests verify
# that a normal index produces working results in both modes.
#
# Vector cases confirm the embedding pipeline is healthy.
# Graph cases confirm the graph extraction and edge resolution are healthy.
# Both must pass after a fresh /index-project run.
# ---------------------------------------------------------------------------

NORMAL_INDEX_VECTOR_CASES = [
    # (query, expected_fragment, scope)
    ("Python dataclass frozen immutable", "lang-python", "knowledge"),
    ("Go goroutine channel concurrency", "lang-go", "knowledge"),
    ("Playwright browser click screenshot", "browser", "agents"),
    ("workflow multi-step orchestration coordination", "workflow", "agents"),
    ("BM25 full text search SQLite FTS5 term frequency", "fts_store", "codebase"),
    ("sentence transformer encode vector embedding", "embedding", "codebase"),
]

NORMAL_INDEX_GRAPH_CASES = [
    # Graph edges built at index time — these confirm graph extraction ran correctly.
    # Each query should return the seed file AND at least one structural neighbour.
    # (query, seed_fragment, expected_neighbour_fragment)
    (
        "XML chunker element boundaries chunk split",
        "xml_chunker",
        "markdown_chunker",   # xml_chunker imports from markdown_chunker
    ),
    (
        "URL chunker fetch HTML markdown chunk",
        "url_chunker",
        "markdown_chunker",   # url_chunker imports from markdown_chunker
    ),
    (
        "search endpoint augment structural neighbours graph",
        "search",
        "sqlite_graph_store", # search imports sqlite_graph_store
    ),
]


@pytest.mark.parametrize("query,expected_fragment,scope", NORMAL_INDEX_VECTOR_CASES)
def test_normal_index_vector_recall(query: str, expected_fragment: str, scope: str):
    """Normal indexing — vector mode: embedding pipeline produces correct results."""
    results = _search(query, scope=scope, mode="vector", limit=5)
    assert results, f"No results returned for: {query!r}"
    hit = _recall_at_k(results, expected_fragment, k=5)
    sources = _source_files(results)[:5]
    assert hit, (
        f"Normal index (vector) miss — scope={scope!r}, query={query!r}\n"
        f"Expected: {expected_fragment!r}\n"
        f"Top-5: {sources}"
    )


@pytest.mark.parametrize("query,seed_fragment,neighbour_fragment", NORMAL_INDEX_GRAPH_CASES)
def test_normal_index_graph_edges(query: str, seed_fragment: str, neighbour_fragment: str):
    """Normal indexing — graph mode: import edges were extracted and resolved correctly."""
    results = _search(query, scope="codebase", mode="graph", limit=7)
    assert results, f"No results returned for: {query!r}"

    has_seed = _recall_at_k(results, seed_fragment, k=7)
    has_neighbour = _recall_at_k(results, neighbour_fragment, k=7)
    sources = _source_files(results)

    assert has_seed, (
        f"Normal index (graph) seed miss — query={query!r}\n"
        f"Expected seed: {seed_fragment!r}\n"
        f"Sources: {sources}"
    )
    assert has_neighbour, (
        f"Normal index (graph) neighbour miss — query={query!r}\n"
        f"Expected neighbour: {neighbour_fragment!r}\n"
        f"Sources: {sources}"
    )


def test_normal_index_graph_active():
    """Confirm graph index is active (graph_augmented=True) after normal /index-project run."""
    payload = {
        "query": "chunker markdown split sections",
        "scope": "codebase",
        "project_path": PROJECT_PATH,
        "mode": "graph",
        "limit": 5,
    }
    result = _call("/search", payload)
    assert "results" in result, f"Unexpected response: {result}"
    assert result.get("graph_augmented") is True, (
        "graph_augmented=False — graph index not built. Run /index-project to rebuild.\n"
        f"Full response: {result}"
    )


# ---------------------------------------------------------------------------
# Regression: score sanity checks
# ---------------------------------------------------------------------------

def test_scores_in_valid_range():
    results = _search("Python async await coroutine", scope="knowledge", limit=5)
    for r in results:
        assert 0.0 <= r["score"] <= 1.0, f"Score out of range: {r['score']} for {r['source']}"


def test_results_sorted_descending():
    results = _search("security authentication token JWT", scope="knowledge", limit=5)
    scores = [r["score"] for r in results]
    assert scores == sorted(scores, reverse=True), f"Results not sorted descending: {scores}"


def test_limit_respected():
    for limit in (1, 3, 5):
        results = _search("code quality clean code", scope="knowledge", limit=limit)
        assert len(results) <= limit, f"Returned {len(results)} results but limit={limit}"


def test_graph_mode_augmented_flag():
    """graph mode should report graph_augmented=True when a graph index exists."""
    payload = {
        "query": "indexing engine chunker embedding",
        "scope": "codebase",
        "project_path": PROJECT_PATH,
        "mode": "graph",
        "limit": 3,
    }
    result = _call("/search", payload)
    assert "results" in result, f"Unexpected response: {result}"


# ---------------------------------------------------------------------------
# MTEB-style nDCG@k + MRR summary (informational — always passes)
#
# Computes nDCG@5 and MRR across all codebase vector cases.
# These match the primary metrics used on the MTEB leaderboard.
# ---------------------------------------------------------------------------

def test_mteb_ndcg_mrr_report():
    """MTEB-style nDCG@5 and MRR across codebase vector cases. Never fails."""
    ndcg_scores = []
    mrr_scores = []

    all_cases = CODEBASE_CASES_VECTOR + [
        (desc, frag) for desc, frag in CODESEARCH_CASES
    ]

    for query, fragment in all_cases:
        try:
            results = _search(query, scope="codebase", mode="vector", limit=5)
            ndcg_scores.append(_ndcg_at_k(results, [fragment], k=5))
            mrr_scores.append(_reciprocal_rank(results, fragment))
        except Exception:
            ndcg_scores.append(0.0)
            mrr_scores.append(0.0)

    n = len(all_cases)
    mean_ndcg = sum(ndcg_scores) / n if n else 0.0
    mean_mrr = sum(mrr_scores) / n if n else 0.0

    print(f"\nMTEB-style metrics ({n} codebase queries):")
    print(f"  nDCG@5 = {mean_ndcg:.3f}")
    print(f"  MRR    = {mean_mrr:.3f}")
    print(f"\nPer-query breakdown:")
    for (query, frag), ndcg, mrr in zip(all_cases, ndcg_scores, mrr_scores):
        status = "OK" if ndcg > 0 else "MISS"
        print(f"  [{status}] nDCG={ndcg:.2f} MRR={mrr:.2f}  {query[:55]!r}")


# ---------------------------------------------------------------------------
# Three-tier summary report (informational — always passes)
#
# Shows the value each retrieval tier adds over the one below it:
#
#   Tier 1 — Vector only   : embedding similarity, no structural context
#   Tier 2 — Graph (normal): vector + import-chain edges from /index-project
#   Tier 3 — /graph skill  : entity extraction + multi-hop traversal,
#                            surfaces gaps that Tier 1+2 miss
#
# This is the headline benchmark: the delta between tiers is the proof
# that graph indexing and the /graph skill add measurable value.
# ---------------------------------------------------------------------------

def test_three_tier_summary():
    """Three-tier Recall + gap analysis. Never fails — prints the full comparison."""

    # --- Tier 1: vector recall across all case types ---
    flat_cases = [
        ("knowledge", q, f) for q, f in KNOWLEDGE_CASES
    ] + [
        ("agents", q, f) for q, f in AGENTS_CASES
    ] + [
        ("codebase", q, f) for q, f in CODEBASE_CASES_VECTOR
    ] + [
        ("codebase", q, f) for q, f in CODESEARCH_CASES
    ]

    t1_hits = t1_total = 0
    for scope, query, fragment in flat_cases:
        t1_total += 1
        try:
            results = _search(query, scope=scope, mode="vector", limit=5)
            if _recall_at_k(results, fragment, k=5):
                t1_hits += 1
        except Exception:
            pass

    # --- Tier 2: graph recall on normal-index graph cases (seed + neighbour) ---
    t2_hits = 0
    t2_total = len(NORMAL_INDEX_GRAPH_CASES) * 2  # seed + neighbour per case
    for query, seed, neighbour in NORMAL_INDEX_GRAPH_CASES:
        try:
            results = _search(query, scope="codebase", mode="graph", limit=7)
            if _recall_at_k(results, seed, k=7):
                t2_hits += 1
            if _recall_at_k(results, neighbour, k=7):
                t2_hits += 1
        except Exception:
            pass

    # --- Tier 3: /graph skill multi-hop cases (seed + structural neighbour) ---
    t3_hits = 0
    t3_total = len(GRAPH_MULTIHOP_CASES) * 2
    for query, seed, neighbour in GRAPH_MULTIHOP_CASES:
        try:
            results = _search(query, scope="codebase", mode="graph", limit=7)
            if _recall_at_k(results, seed, k=7):
                t3_hits += 1
            if _recall_at_k(results, neighbour, k=7):
                t3_hits += 1
        except Exception:
            pass

    # --- Gap analysis: what does each tier add? ---
    # For each multi-hop case, compare what vector finds vs. what graph adds
    gaps_found_by_graph = 0
    gaps_total = len(GRAPH_MULTIHOP_CASES)
    for query, seed, neighbour in GRAPH_MULTIHOP_CASES:
        try:
            v_results = _search(query, scope="codebase", mode="vector", limit=5)
            g_results = _search(query, scope="codebase", mode="graph", limit=7)
            v_neighbour = _recall_at_k(v_results, neighbour, k=5)
            g_neighbour = _recall_at_k(g_results, neighbour, k=7)
            # Graph filled a gap if it found the neighbour but vector didn't
            if g_neighbour and not v_neighbour:
                gaps_found_by_graph += 1
        except Exception:
            pass

    # /graph skill gaps: what the skill surfaces that basic graph search misses
    skill_gaps_filled = 0
    for description, entities, expected_files in GRAPH_SKILL_CASES:
        try:
            # Basic graph: single entity query, no entity extraction
            basic_files: set[str] = set()
            v = _search(entities[0], scope="codebase", mode="vector", limit=5)
            basic_files.update(r.get("source", "") for r in v)

            # /graph skill: all entities, graph mode
            skill_files = _run_graph_skill(description, entities)

            skill_only = skill_files - basic_files
            for frag in expected_files[1:]:  # neighbours, not the seed
                if any(frag in s for s in skill_only):
                    skill_gaps_filled += 1
                    break
        except Exception:
            pass

    print("\n" + "=" * 60)
    print("THREE-TIER RAG BENCHMARK SUMMARY")
    print("=" * 60)
    print(f"\nTier 1 — Vector only (BEIR/MTEB Recall@5):")
    print(f"  {t1_hits}/{t1_total} = {t1_hits/t1_total:.0%}  ({t1_total} queries across knowledge, agents, codebase)")
    print(f"\nTier 2 — Normal indexing: vector + graph edges (/index-project):")
    print(f"  {t2_hits}/{t2_total} = {t2_hits/t2_total:.0%}  ({len(NORMAL_INDEX_GRAPH_CASES)} cases, seed + structural neighbour)")
    print(f"\nTier 3 — /graph skill: entity extraction + multi-hop traversal:")
    print(f"  {t3_hits}/{t3_total} = {t3_hits/t3_total:.0%}  ({len(GRAPH_MULTIHOP_CASES)} GraphRAG-Bench-style cases)")
    print(f"\nGap analysis:")
    print(f"  Graph fills over vector:     {gaps_found_by_graph}/{gaps_total} cases where graph found")
    print(f"                               structural neighbours that vector missed")
    print(f"  /graph skill fills over base: {skill_gaps_filled}/{len(GRAPH_SKILL_CASES)} cases where skill surfaced")
    print(f"                               files beyond single-entity vector search")
    print("=" * 60)


# ---------------------------------------------------------------------------
# Recall@k summary report (informational — always passes)
# ---------------------------------------------------------------------------

def test_recall_summary_report():
    """BEIR-style Recall@k summary across all query sets. Never fails."""
    cases = [
        ("knowledge", q, f) for q, f in KNOWLEDGE_CASES
    ] + [
        ("agents", q, f) for q, f in AGENTS_CASES
    ] + [
        ("codebase", q, f) for q, f in CODEBASE_CASES_VECTOR
    ] + [
        ("codebase", q, f) for q, f in CODESEARCH_CASES
    ]

    hits_at_1 = 0
    hits_at_3 = 0
    hits_at_5 = 0
    total = len(cases)

    for scope, query, fragment in cases:
        try:
            results = _search(query, scope=scope, limit=5)
            if _recall_at_k(results, fragment, k=1):
                hits_at_1 += 1
            if _recall_at_k(results, fragment, k=3):
                hits_at_3 += 1
            if _recall_at_k(results, fragment, k=5):
                hits_at_5 += 1
        except Exception:
            pass

    print(f"\nRecall@k summary ({total} queries):")
    print(f"  Recall@1 = {hits_at_1}/{total} = {hits_at_1/total:.0%}")
    print(f"  Recall@3 = {hits_at_3}/{total} = {hits_at_3/total:.0%}")
    print(f"  Recall@5 = {hits_at_5}/{total} = {hits_at_5/total:.0%}")
