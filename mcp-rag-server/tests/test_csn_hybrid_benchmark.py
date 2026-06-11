"""CodeSearchNet 1K-Pool Benchmark with BM25+Embedding Hybrid Retrieval

Extends test_codesearchnet_1k_pool.py with:
1. BM25 scoring over the candidate pool (fused via RRF)
2. Code-aware tokenization (snake_case/camelCase splitting)
3. Query preprocessing (first sentence extraction)

Goal: improve MRR from 0.587 toward GraphCodeBERT's 0.769.

Run:
    pytest mcp-rag-server/tests/test_csn_hybrid_benchmark.py -v -s
"""

import ast
import json
import math
import random
import re
import time
import warnings
from pathlib import Path

import numpy as np
import pytest

try:
    from rank_bm25 import BM25Okapi
    HAS_BM25 = True
except ImportError:
    HAS_BM25 = False

try:
    from sentence_transformers import SentenceTransformer
    HAS_ST = True
except ImportError:
    HAS_ST = False

FULL_DATA = Path(__file__).parent / "data" / "codesearchnet_python_full.jsonl"
CACHE_DIR = Path(__file__).parent / "data"
CODE_CACHE = CACHE_DIR / "csn_code_embeddings_stripped.npy"
DOC_CACHE = CACHE_DIR / "csn_doc_embeddings.npy"
# New: preprocessed doc embeddings cache
DOC_CACHE_PREPROCESSED = CACHE_DIR / "csn_doc_embeddings_preprocessed.npy"

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
N_EVAL = 500
N_POOL = 1000
RANDOM_SEED = 42

# RRF fusion constant (k=60 is standard, lower k weighs high ranks more)
RRF_K = 60


# ---------------------------------------------------------------------------
# Tokenizers
# ---------------------------------------------------------------------------

def _split_camel(s: str) -> list[str]:
    """Split camelCase and snake_case identifiers into word tokens."""
    # snake_case: split on underscores
    parts = s.split("_")
    result = []
    for p in parts:
        # camelCase: split on uppercase letter followed by lowercase
        sub = re.sub(r"([A-Z])([A-Z][a-z])", r"\1 \2", p)
        sub = re.sub(r"([a-z\d])([A-Z])", r"\1 \2", sub)
        result.extend(sub.lower().split())
    return [t for t in result if t]


def tokenize_code(code: str) -> list[str]:
    """Code-aware tokenizer: splits on whitespace, then splits identifiers."""
    tokens = []
    for raw in re.split(r"[\s\(\)\[\]\{\},:;=+\-*/\\\"'\.@<>!&|^~%]+", code):
        if not raw or len(raw) < 2:
            continue
        # Skip pure numbers
        if raw.isdigit():
            continue
        tokens.extend(_split_camel(raw))
    return tokens


def tokenize_query(query: str) -> list[str]:
    """Simple tokenizer for natural language queries."""
    # Lowercase, split on non-alphanumeric
    return [t for t in re.split(r"\W+", query.lower()) if len(t) >= 2]


def preprocess_docstring(doc: str) -> str:
    """Extract the most informative part of a docstring for querying.

    For multi-sentence docstrings, the first sentence is usually the most
    concise description of what the function does. Long docstrings get
    truncated by MiniLM's 256-token limit anyway, so extracting the key
    part improves retrieval quality.
    """
    doc = doc.strip()
    if not doc:
        return doc

    # Split on first period that's followed by whitespace or end-of-string
    # (avoids splitting on "e.g." or file extensions)
    match = re.search(r"\.\s+|\.\s*$", doc)
    if match and match.start() > 20:
        first_sent = doc[: match.start() + 1].strip()
        # Only use first sentence if it's reasonably informative (>15 chars)
        if len(first_sent) >= 15:
            return first_sent

    # Fall back to first line (handles newline-separated descriptions)
    first_line = doc.split("\n")[0].strip()
    if len(first_line) >= 15 and len(first_line) < len(doc):
        return first_line

    return doc


def _strip_docstring(code: str) -> str:
    """Remove the docstring from a Python function before embedding."""
    try:
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=SyntaxWarning)
            tree = ast.parse(code)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if (
                    node.body
                    and isinstance(node.body[0], ast.Expr)
                    and isinstance(node.body[0].value, ast.Constant)
                    and isinstance(node.body[0].value.value, str)
                ):
                    node.body.pop(0)
                    if not node.body:
                        node.body.append(ast.Pass())
        return ast.unparse(tree)
    except SyntaxError:
        return code


# ---------------------------------------------------------------------------
# RRF fusion
# ---------------------------------------------------------------------------

def rrf_rank(scores_list: list[np.ndarray], k: int = RRF_K) -> np.ndarray:
    """Reciprocal Rank Fusion over multiple score arrays.

    Args:
        scores_list: list of score arrays (higher = better). All same length.
        k: RRF constant (default 60 from original paper)

    Returns:
        Fused score array (higher = better).
    """
    n = len(scores_list[0])
    fused = np.zeros(n, dtype=np.float32)
    for scores in scores_list:
        # Convert scores to ranks (0-indexed, 0 = best)
        rank_order = np.argsort(-scores)
        ranks = np.empty(n, dtype=np.float32)
        ranks[rank_order] = np.arange(n, dtype=np.float32)
        fused += 1.0 / (k + ranks)
    return fused


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session", autouse=True)
def require_deps():
    if not HAS_ST:
        pytest.skip("sentence-transformers not installed")
    if not HAS_BM25:
        pytest.skip("rank_bm25 not installed — pip install rank_bm25")


@pytest.fixture(scope="session")
def corpus() -> list[dict]:
    if not FULL_DATA.exists():
        pytest.skip(f"Full CodeSearchNet data not found at {FULL_DATA}.")
    examples = []
    with open(FULL_DATA, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                examples.append(json.loads(line))
    assert len(examples) >= 1000, f"Corpus too small: {len(examples)}"
    print(f"\n[CSN-Hybrid] Loaded {len(examples):,} Python functions.")
    return examples


@pytest.fixture(scope="session")
def embeddings(corpus) -> tuple[np.ndarray, np.ndarray]:
    """Load or build code/doc embeddings. Reuses existing MiniLM cache."""
    n = len(corpus)

    if CODE_CACHE.exists() and DOC_CACHE.exists():
        code_embs = np.load(CODE_CACHE)
        doc_embs = np.load(DOC_CACHE)
        if code_embs.shape[0] == n and doc_embs.shape[0] == n:
            print(f"[CSN-Hybrid] Loaded cached embeddings ({n:,} × {code_embs.shape[1]}d).")
            return code_embs, doc_embs

    # If cache missing, build it
    print(f"[CSN-Hybrid] Encoding {n:,} functions with {MODEL_NAME} ...")
    model = SentenceTransformer(MODEL_NAME)
    code_texts = [_strip_docstring(ex["code"]) for ex in corpus]
    code_embs = model.encode(
        code_texts, batch_size=256, show_progress_bar=True,
        normalize_embeddings=True, convert_to_numpy=True,
    )
    doc_texts = [ex["docstring"] for ex in corpus]
    doc_embs = model.encode(
        doc_texts, batch_size=256, show_progress_bar=True,
        normalize_embeddings=True, convert_to_numpy=True,
    )
    CACHE_DIR.mkdir(exist_ok=True)
    np.save(CODE_CACHE, code_embs)
    np.save(DOC_CACHE, doc_embs)
    return code_embs, doc_embs


@pytest.fixture(scope="session")
def preprocessed_doc_embeddings(corpus) -> np.ndarray:
    """Doc embeddings using preprocessed (first-sentence) docstrings.

    Only the docstring side needs re-encoding; code embeddings are unchanged.
    """
    n = len(corpus)

    if DOC_CACHE_PREPROCESSED.exists():
        cached = np.load(DOC_CACHE_PREPROCESSED)
        if cached.shape[0] == n:
            print(f"[CSN-Hybrid] Loaded preprocessed doc embeddings ({n:,} × {cached.shape[1]}d).")
            return cached

    print(f"[CSN-Hybrid] Encoding preprocessed docstrings ({n:,}) ...")
    model = SentenceTransformer(MODEL_NAME)
    doc_texts = [preprocess_docstring(ex["docstring"]) for ex in corpus]
    doc_embs = model.encode(
        doc_texts, batch_size=256, show_progress_bar=True,
        normalize_embeddings=True, convert_to_numpy=True,
    )
    np.save(DOC_CACHE_PREPROCESSED, doc_embs)
    print(f"[CSN-Hybrid] Preprocessed doc embeddings cached.")
    return doc_embs


@pytest.fixture(scope="session")
def bm25_index(corpus):
    """BM25 index over stripped code functions."""
    print(f"\n[CSN-Hybrid] Building BM25 index ({len(corpus):,} documents) ...")
    t0 = time.time()
    tokenized = [tokenize_code(_strip_docstring(ex["code"])) for ex in corpus]
    bm25 = BM25Okapi(tokenized)
    print(f"[CSN-Hybrid] BM25 index built in {time.time() - t0:.1f}s.")
    return bm25, tokenized



# ---------------------------------------------------------------------------
# Evaluation core
# ---------------------------------------------------------------------------

def _pool_mrr_recall(
    query_vecs: np.ndarray,
    code_vecs: np.ndarray,
    correct_indices: list[int],
    pool_size: int,
    rng: random.Random,
    n: int,
    bm25_model=None,
    queries_raw: list[str] | None = None,
    label: str = "",
) -> dict:
    """1K-pool evaluation with optional BM25 fusion via RRF."""
    total = len(correct_indices)
    indices_to_eval = list(range(total))
    rng.shuffle(indices_to_eval)
    indices_to_eval = indices_to_eval[:n]
    all_idxs = list(range(len(code_vecs)))

    hits_1 = hits_5 = hits_10 = 0
    rr_sum = 0.0

    for qi in indices_to_eval:
        correct_idx = correct_indices[qi]
        distractors = rng.sample([x for x in all_idxs if x != correct_idx], k=pool_size - 1)
        pool = [correct_idx] + distractors

        pool_vecs = code_vecs[pool]
        dense_scores = pool_vecs @ query_vecs[qi]  # cosine sim (normalized)

        if bm25_model is not None and queries_raw is not None:
            # BM25 scores using the full-corpus index (proper IDF)
            query_tokens = tokenize_query(queries_raw[qi])
            all_bm25 = bm25_model.get_scores(query_tokens)  # shape (N_corpus,)
            bm25_scores = np.array(all_bm25[pool], dtype=np.float32)

            # Fuse dense + BM25 via RRF
            final_scores = rrf_rank([dense_scores, bm25_scores])
        else:
            final_scores = dense_scores

        ranked = np.argsort(-final_scores)
        rank = int(np.where(ranked == 0)[0][0]) + 1

        if rank == 1:
            hits_1 += 1
        if rank <= 5:
            hits_5 += 1
        if rank <= 10:
            hits_10 += 1
        rr_sum += 1.0 / rank

    return {
        "n": n,
        "recall_1": hits_1 / n,
        "recall_5": hits_5 / n,
        "recall_10": hits_10 / n,
        "mrr": rr_sum / n,
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_baseline_dense_only(corpus, embeddings):
    """Baseline: pure embedding similarity (reproduces test_codesearchnet_1k_pool.py)."""
    code_embs, doc_embs = embeddings
    rng = random.Random(RANDOM_SEED)

    t0 = time.time()
    results = _pool_mrr_recall(
        query_vecs=doc_embs,
        code_vecs=code_embs,
        correct_indices=list(range(len(corpus))),
        pool_size=N_POOL,
        rng=rng,
        n=N_EVAL,
    )
    elapsed = time.time() - t0

    r1, r5, r10, mrr = results["recall_1"], results["recall_5"], results["recall_10"], results["mrr"]
    _print_results("BASELINE: Dense only (MiniLM)", r1, r5, r10, mrr, elapsed, N_EVAL, N_POOL)

    assert mrr >= 0.20, f"MRR floor failure: {mrr:.3f}"


def test_preprocessed_query(corpus, embeddings, preprocessed_doc_embeddings):
    """Improvement 1: preprocessed docstrings (first-sentence extraction)."""
    code_embs, _ = embeddings
    rng = random.Random(RANDOM_SEED)

    t0 = time.time()
    results = _pool_mrr_recall(
        query_vecs=preprocessed_doc_embeddings,
        code_vecs=code_embs,
        correct_indices=list(range(len(corpus))),
        pool_size=N_POOL,
        rng=rng,
        n=N_EVAL,
    )
    elapsed = time.time() - t0

    r1, r5, r10, mrr = results["recall_1"], results["recall_5"], results["recall_10"], results["mrr"]
    _print_results("IMPROVED: Preprocessed docstrings", r1, r5, r10, mrr, elapsed, N_EVAL, N_POOL)
    assert mrr >= 0.20


def test_hybrid_bm25_dense(corpus, embeddings, bm25_index):
    """Improvement 2: BM25 + dense RRF fusion (original docstrings)."""
    code_embs, doc_embs = embeddings
    bm25_model, _ = bm25_index
    rng = random.Random(RANDOM_SEED)
    raw_queries = [ex["docstring"] for ex in corpus]

    t0 = time.time()
    results = _pool_mrr_recall(
        query_vecs=doc_embs,
        code_vecs=code_embs,
        correct_indices=list(range(len(corpus))),
        pool_size=N_POOL,
        rng=rng,
        n=N_EVAL,
        bm25_model=bm25_model,
        queries_raw=raw_queries,
    )
    elapsed = time.time() - t0

    r1, r5, r10, mrr = results["recall_1"], results["recall_5"], results["recall_10"], results["mrr"]
    _print_results("IMPROVED: Dense + BM25 RRF", r1, r5, r10, mrr, elapsed, N_EVAL, N_POOL)
    assert mrr >= 0.20


def test_hybrid_preprocessed_bm25(corpus, embeddings, preprocessed_doc_embeddings, bm25_index):
    """Improvement 3: BM25 + preprocessed-docstring dense RRF (best combo)."""
    code_embs, _ = embeddings
    bm25_model, _ = bm25_index
    rng = random.Random(RANDOM_SEED)
    raw_queries = [preprocess_docstring(ex["docstring"]) for ex in corpus]

    t0 = time.time()
    results = _pool_mrr_recall(
        query_vecs=preprocessed_doc_embeddings,
        code_vecs=code_embs,
        correct_indices=list(range(len(corpus))),
        pool_size=N_POOL,
        rng=rng,
        n=N_EVAL,
        bm25_model=bm25_model,
        queries_raw=raw_queries,
    )
    elapsed = time.time() - t0

    r1, r5, r10, mrr = results["recall_1"], results["recall_5"], results["recall_10"], results["mrr"]
    _print_results("BEST COMBO: Preprocessed + BM25 RRF", r1, r5, r10, mrr, elapsed, N_EVAL, N_POOL)
    assert mrr >= 0.20


# ---------------------------------------------------------------------------
# Reporter
# ---------------------------------------------------------------------------

def _print_results(label, r1, r5, r10, mrr, elapsed, n, pool):
    print(f"\n{'='*68}")
    print(f"  {label}")
    print(f"{'='*68}")
    print(f"  Model:    {MODEL_NAME}")
    print(f"  Queries:  {n}  |  Pool: {pool} per query  |  Time: {elapsed:.1f}s")
    print()
    print(f"  {'Metric':<12} {'Result':>10}  {'NBOW':>8}  {'CodeBERT':>10}  {'GraphCodeBERT':>14}")
    print(f"  {'-'*56}")
    print(f"  {'Recall@1':<12} {r1:>9.1%}  {'~38%':>8}  {'~59%':>10}  {'~68%':>14}")
    print(f"  {'Recall@5':<12} {r5:>9.1%}  {'~65%':>8}  {'~85%':>10}  {'~90%':>14}")
    print(f"  {'Recall@10':<12} {r10:>9.1%}  {'~75%':>8}  {'~90%':>10}  {'~94%':>14}")
    print(f"  {'MRR':<12} {mrr:>10.3f}  {'0.510':>8}  {'0.713':>10}  {'0.769':>14}")
    print(f"{'='*68}")
