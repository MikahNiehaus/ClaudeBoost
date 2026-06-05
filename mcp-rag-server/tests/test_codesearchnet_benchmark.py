"""CodeSearchNet Benchmark — ClaudeBoost RAG

Evaluates code retrieval quality using the actual CodeSearchNet Python test set
(Husain et al. 2019, arxiv:1909.09436). This is the same dataset used by
CodeBERT, GraphCodeBERT, UniXcoder, and other code retrieval systems.

Evaluation setup
----------------
Corpus:    200 Python functions sampled from the CodeSearchNet test set, each
           written to an individual .py file and indexed via POST /index.
Queries:   The corresponding natural-language docstrings (not keywords — the
           actual function documentation).
Metrics:   Recall@1, Recall@5, MRR — same metrics reported in the original
           paper and on the CodeSearchNet leaderboard.

Difference from official evaluation
------------------------------------
The official CodeSearchNet leaderboard uses a 1,000-candidate pool per query
(999 distractors from a shared distractor set + 1 correct function). Our pool
is the full 200-function corpus, so absolute scores are not directly comparable
to leaderboard numbers. What IS directly comparable: whether the model retrieves
the correct function in rank 1 or top 5, and the relative MRR across systems
tested against the same 200-function corpus.

Published baselines from Husain et al. 2019 (Python, 1K pool):
    NBOW:          MRR = 0.51
    BiRNN:         MRR = 0.56
    SelfAtt:       MRR = 0.69
    CodeBERT:      MRR = 0.713
    GraphCodeBERT: MRR = 0.769

ClaudeBoost uses: sentence-transformers/all-MiniLM-L6-v2

Data source:  huggingface.co/datasets/code_search_net (CC BY-4.0)
Sample file:  tests/data/codesearchnet_python_sample.jsonl (200 examples)

Run:
    pytest mcp-rag-server/tests/test_codesearchnet_benchmark.py -v -s
"""

import json
import math
import os
import shutil
import tempfile
import time
import urllib.request
import urllib.error
from pathlib import Path
from typing import Any

import pytest

RAG_URL = "http://127.0.0.1:8612"
DATA_FILE = Path(__file__).parent / "data" / "codesearchnet_python_sample.jsonl"
HF_PARQUET_URL = (
    "https://huggingface.co/datasets/code_search_net/resolve/main"
    "/python/test-00000-of-00001.parquet"
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
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def _server_alive() -> bool:
    try:
        urllib.request.urlopen(f"{RAG_URL}/status", timeout=5)
        return True
    except Exception:
        return False


def _search(
    query: str,
    project_path: str,
    mode: str = "vector",
    limit: int = 10,
) -> list[dict]:
    payload: dict[str, Any] = {
        "query": query,
        "scope": "codebase",
        "project_path": project_path,
        "mode": mode,
        "limit": limit,
    }
    result = _call("/search", payload)
    return result.get("results", [])


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

def _recall_at_k(results: list[dict], expected_tag: str, k: int) -> bool:
    for r in results[:k]:
        if expected_tag in r.get("source", ""):
            return True
    return False


def _reciprocal_rank(results: list[dict], expected_tag: str) -> float:
    for i, r in enumerate(results, start=1):
        if expected_tag in r.get("source", ""):
            return 1.0 / i
    return 0.0


# ---------------------------------------------------------------------------
# Session fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session", autouse=True)
def require_server():
    if not _server_alive():
        pytest.skip("RAG server not reachable — start with /rag")


@pytest.fixture(scope="session")
def csn_examples() -> list[dict]:
    """Load CodeSearchNet examples from the bundled JSONL sample."""
    if not DATA_FILE.exists():
        pytest.skip(
            f"CodeSearchNet sample not found at {DATA_FILE}. "
            "Run scripts/download_codesearchnet.py to generate it."
        )
    examples = []
    with open(DATA_FILE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                examples.append(json.loads(line))
    if not examples:
        pytest.skip("CodeSearchNet sample file is empty.")
    return examples


@pytest.fixture(scope="session")
def csn_index(csn_examples, tmp_path_factory) -> str:
    """Write CodeSearchNet functions to temp files and index them via RAG.

    Each function is written as func_{i:04d}_{name}.py so the expected
    source tag for query i is exactly 'func_{i:04d}_'.
    Returns the temp project path for use in search calls.
    """
    tmpdir = str(tmp_path_factory.mktemp("csn_bench"))

    print(f"\n[CodeSearchNet] Writing {len(csn_examples)} functions to {tmpdir} ...")
    for i, ex in enumerate(csn_examples):
        # Sanitise function name: keep only alnum and underscore, max 30 chars
        raw_name = ex.get("func_name", f"func{i}").split(".")[-1]
        safe_name = "".join(c if c.isalnum() or c == "_" else "_" for c in raw_name)[:30]
        filename = f"func_{i:04d}_{safe_name}.py"
        path = Path(tmpdir) / filename
        path.write_text(ex["code"], encoding="utf-8")

    print("[CodeSearchNet] Indexing (this takes ~30-60 s for 200 functions) ...")
    t0 = time.time()
    result = _call("/index", {"project_path": tmpdir, "force": True})
    elapsed = time.time() - t0

    indexed = result.get("files_indexed", 0)
    failed = result.get("files_failed", 0)
    print(
        f"[CodeSearchNet] Indexed {indexed} files, {failed} failed, "
        f"{elapsed:.1f}s"
    )

    if indexed == 0:
        pytest.skip("RAG indexing returned 0 files — check server logs.")

    return tmpdir


# ---------------------------------------------------------------------------
# Main benchmark tests
# ---------------------------------------------------------------------------

def test_codesearchnet_recall(csn_examples, csn_index):
    """CodeSearchNet Recall@1, Recall@5, MRR using real test data.

    Uses the actual CodeSearchNet Python test set (Husain et al. 2019).
    200-function corpus; docstring as query; function file as ground truth.
    """
    hits_1 = 0
    hits_5 = 0
    rr_sum = 0.0
    total = len(csn_examples)
    missed: list[str] = []

    for i, ex in enumerate(csn_examples):
        query = ex["docstring"]
        tag = f"func_{i:04d}_"

        results = _search(query, project_path=csn_index, mode="vector", limit=10)

        if _recall_at_k(results, tag, k=1):
            hits_1 += 1
        if _recall_at_k(results, tag, k=5):
            hits_5 += 1
        else:
            missed.append(f"  [{i}] {ex.get('func_name','?')!r}: {query[:60]!r}")

        rr_sum += _reciprocal_rank(results, tag)

    recall_1 = hits_1 / total
    recall_5 = hits_5 / total
    mrr = rr_sum / total

    print(f"\n{'='*60}")
    print("CODESEARCHNET BENCHMARK (Python, 200-function pool)")
    print(f"{'='*60}")
    print(f"  Corpus:   {total} Python functions (CodeSearchNet test set)")
    print(f"  Queries:  natural-language docstrings")
    print()
    print(f"  Recall@1  = {hits_1}/{total} = {recall_1:.1%}")
    print(f"  Recall@5  = {hits_5}/{total} = {recall_5:.1%}")
    print(f"  MRR       = {mrr:.3f}")
    print()
    print("  Published baselines (1K pool, from Husain et al. 2019):")
    print("    NBOW:          MRR = 0.51")
    print("    BiRNN:         MRR = 0.56")
    print("    SelfAtt:       MRR = 0.69")
    print("    CodeBERT:      MRR = 0.713")
    print("    GraphCodeBERT: MRR = 0.769")
    print()
    print("  Note: 200-pool scores are not directly comparable to 1K-pool")
    print("        leaderboard numbers (smaller pool = higher absolute scores).")
    if missed[:5]:
        print(f"\n  First 5 misses (Recall@5 failures):")
        for m in missed[:5]:
            print(m)
    print(f"{'='*60}")

    # Soft threshold: any reasonable embedding model should hit >30% Recall@1
    # on a 200-function pool. Failure here means the embedding pipeline is broken.
    assert recall_1 >= 0.30, (
        f"Recall@1 = {recall_1:.1%} — expected >= 30% on 200-function pool. "
        "Embedding pipeline may be degraded."
    )
    assert recall_5 >= 0.60, (
        f"Recall@5 = {recall_5:.1%} — expected >= 60% on 200-function pool."
    )
    assert mrr >= 0.35, (
        f"MRR = {mrr:.3f} — expected >= 0.35 on 200-function pool."
    )


def test_codesearchnet_graph_vs_vector(csn_examples, csn_index):
    """Graph mode vs vector mode on CodeSearchNet queries.

    Both modes should perform similarly for NL→code retrieval (graph mode
    adds structural neighbours, which are neutral for isolated function files).
    This test confirms graph augmentation doesn't degrade code retrieval.
    """
    # Use first 50 examples for speed
    sample = csn_examples[:50]
    vector_hits = 0
    graph_hits = 0

    for i, ex in enumerate(sample):
        tag = f"func_{i:04d}_"
        query = ex["docstring"]

        v = _search(query, project_path=csn_index, mode="vector", limit=5)
        g = _search(query, project_path=csn_index, mode="graph", limit=5)

        if _recall_at_k(v, tag, k=5):
            vector_hits += 1
        if _recall_at_k(g, tag, k=5):
            graph_hits += 1

    total = len(sample)
    print(f"\nCodeSearchNet graph vs vector (first {total} queries):")
    print(f"  Vector Recall@5: {vector_hits}/{total} = {vector_hits/total:.1%}")
    print(f"  Graph  Recall@5: {graph_hits}/{total} = {graph_hits/total:.1%}")

    # Graph mode must not degrade recall vs vector (allow 1 miss tolerance)
    assert graph_hits >= vector_hits - 1, (
        f"Graph mode degraded Recall@5 vs vector: {graph_hits} vs {vector_hits}"
    )


@pytest.mark.parametrize("query,func_name,docstring_preview", [
    # A few spot-check cases from the CodeSearchNet sample for CI-friendliness.
    # These are real entries from the dataset; the function names are specific
    # enough that a working embedding model should retrieve them reliably.
    (
        "Extracts video ID from URL.",
        "YouTube.get_vid_from_url",
        "Extracts video ID from URL",
    ),
])
def test_codesearchnet_spot_check(query, func_name, docstring_preview, csn_examples, csn_index):
    """Spot-check a handful of known CodeSearchNet entries by exact match."""
    # Find the index of this function in the sample
    idx = next(
        (i for i, ex in enumerate(csn_examples) if ex.get("func_name") == func_name),
        None,
    )
    if idx is None:
        pytest.skip(f"Function {func_name!r} not in current sample.")

    tag = f"func_{idx:04d}_"
    results = _search(query, project_path=csn_index, mode="vector", limit=5)
    assert _recall_at_k(results, tag, k=5), (
        f"CodeSearchNet spot-check miss: query={query!r}\n"
        f"Expected tag {tag!r} in top-5\n"
        f"Top sources: {[r.get('source','') for r in results[:5]]}"
    )
