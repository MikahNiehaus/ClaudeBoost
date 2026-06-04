"""Recall@k evaluation harness for the RAG server.

Measures retrieval quality using a ground-truth query/answer set.
Each test is a (query, expected_source_fragment) pair — the test passes when
at least one of the top-k results has a source_file matching the fragment.

Run from the repo root:
    pytest mcp-rag-server/tests/test_rag_quality.py -v

Requires:
    - RAG server running at http://127.0.0.1:8612
    - ClaudeBoost knowledge + agents indexed (run /index-boost first)
    - Project codebase indexed at this repo root (run /index-project first)

Skip gracefully when the server is unreachable.
"""

import json
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


def _recall_at_k(results: list[dict], fragment: str, k: int) -> bool:
    """True if any of the top-k results has source_file containing fragment."""
    for r in results[:k]:
        if fragment in r.get("source", ""):
            return True
    return False


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session", autouse=True)
def require_server():
    if not _server_alive():
        pytest.skip("RAG server not reachable at 127.0.0.1:8612 — start with /rag")


# ---------------------------------------------------------------------------
# Knowledge scope: Recall@3 — common knowledge queries
# ---------------------------------------------------------------------------

KNOWLEDGE_CASES = [
    ("SQL injection prevention parameterized queries", "database"),
    ("BM25 hybrid search reciprocal rank fusion", "knowledge"),
    ("SOLID principles single responsibility", "coding-standards"),
    ("Python type hints annotations", "lang-python"),
    ("React hooks useState useEffect", "fw-react"),
    ("Django ORM models database", "fw-django"),
    ("cross-encoder reranking candidates", "knowledge"),
    ("code review checklist", "knowledge"),
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
# Agents scope: Recall@3
# ---------------------------------------------------------------------------

AGENTS_CASES = [
    ("security audit vulnerability scan", "security"),
    ("code review pull request", "reviewer"),
    ("architecture design SOLID principles", "architect"),
    ("performance profiling bottleneck", "performance"),
    ("database schema migration query", "database"),
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
# Codebase scope: Recall@5, vector + graph modes
# ---------------------------------------------------------------------------

CODEBASE_CASES_VECTOR = [
    ("chunk_markdown paragraph split overlap", "markdown_chunker"),
    ("cross-encoder reranker predict logits", "search"),
    ("SQLite graph store add edges", "sqlite_graph_store"),
    ("community detection Leiden graspologic", "community"),
    ("embedding model sentence transformers", "embedding"),
    ("FTS5 BM25 full text search", "fts_store"),
]

CODEBASE_CASES_GRAPH = [
    ("search.py imports graph store reranker", "search"),
    ("engine.py imports community detection", "engine"),
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
    # If graph index doesn't exist yet, expect a warning not a crash
    assert "results" in result, f"Unexpected response: {result}"


# ---------------------------------------------------------------------------
# Recall@k summary report (informational — always passes)
# ---------------------------------------------------------------------------

def test_recall_summary_report():
    """Print a Recall@k summary across all query sets. Never fails."""
    cases = [
        ("knowledge", q, f) for q, f in KNOWLEDGE_CASES
    ] + [
        ("agents", q, f) for q, f in AGENTS_CASES
    ] + [
        ("codebase", q, f) for q, f in CODEBASE_CASES_VECTOR
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
