"""BEIR Multi-Dataset Documentation Benchmark

Tests retrieval quality across many different documentation types using the
BEIR benchmark suite (Thakur et al. 2021, arxiv:2104.08663).

Datasets (auto-downloaded from HuggingFace on first run, cached locally):
  FIQA        Financial Q&A from StackExchange        57,638 passages   648 queries
  SciFact     Scientific claim verification            5,183 abstracts   300 queries
  NFCorpus    Medical / nutritional facts              3,633 abstracts   323 queries
  ArguAna     Counter-argument retrieval               8,674 arguments  1,406 queries
  TREC-COVID  COVID-19 biomedical research            171,332 articles   50 queries
  HotpotQA    Multi-hop Wikipedia reasoning           5,233,329 passages 7,405 queries

Documentation domains covered:
  Finance         FIQA        (StackExchange financial Q&A)
  Science/medical SciFact     (claim verification from academic papers)
  Medical         NFCorpus    (nutritional epidemiology / MedLine)
  Argumentation   ArguAna     (counter-argument retrieval)
  Biomedical      TREC-COVID  (COVID-19 scientific literature)
  General/facts   HotpotQA    (Wikipedia multi-hop)

Published baselines (NDCG@10) from the BEIR paper:
  Dataset      BM25   TAS-B  SPECTER  Notes
  FIQA         0.236  0.300  0.314    StackExchange financial
  SciFact      0.665  0.643  0.707    scientific claims
  NFCorpus     0.325  0.321  0.268    medical literature
  ArguAna      0.315  0.429  0.347    argumentation pairs
  TREC-COVID   0.656  0.481  0.514    biomedical COVID (BM25 wins)
  HotpotQA     0.603  0.584  0.441    Wikipedia multi-hop

Note: TREC-COVID and HotpotQA are large. First run for each downloads and encodes
the full corpus (can take 5-30 min on CPU). Cached after first run.

Supports per-language model routing via ModelRouter when available. Falls back
to all-MiniLM-L6-v2 as the default.

Run:
    pytest mcp-rag-server/tests/test_beir_documentation.py -v -s
    pytest mcp-rag-server/tests/test_beir_documentation.py -v -s -k "fiqa or scifact"
    pytest mcp-rag-server/tests/test_beir_documentation.py -v -s -k "not hotpotqa"
"""

import json
import math
import time
from pathlib import Path

import numpy as np
import pytest

try:
    from sentence_transformers import SentenceTransformer
    HAS_ST = True
except ImportError:
    HAS_ST = False

try:
    from datasets import load_dataset
    HAS_DS = True
except ImportError:
    HAS_DS = False

try:
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from model_router import get_router
    HAS_ROUTER = True
except Exception:
    HAS_ROUTER = False


DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
DATA_DIR = Path(__file__).parent / "data" / "beir"

# Published BEIR baselines (NDCG@10) — Thakur et al. 2021
BEIR_BASELINES = {
    "fiqa":      {"bm25": 0.236, "tas_b": 0.300, "specter": 0.314},
    "scifact":   {"bm25": 0.665, "tas_b": 0.643, "specter": 0.707},
    "nfcorpus":  {"bm25": 0.325, "tas_b": 0.321, "specter": 0.268},
    "arguana":   {"bm25": 0.315, "tas_b": 0.429, "specter": 0.347},
    "trec-covid":{"bm25": 0.656, "tas_b": 0.481, "specter": 0.514},
    "hotpotqa":  {"bm25": 0.603, "tas_b": 0.584, "specter": 0.441},
}

# Regression floors — confirmed NDCG@10 scores, set ~0.025 below to absorb variance
NDCG_FLOOR = {
    "fiqa":      0.340,   # confirmed 0.369 (BEATS TAS-B 0.300 +0.069)
    "scifact":   0.610,   # confirmed 0.645 (BEATS TAS-B 0.643 +0.002)
    "nfcorpus":  0.290,   # confirmed 0.317 (near BM25 0.325)
    "arguana":   0.340,   # confirmed 0.370 (beats BM25 0.315 +0.055)
    "trec-covid":0.420,   # confirmed 0.454 (BM25=0.656 dominates; dense models lag)
    "hotpotqa":  0.450,   # not yet run (BM25=0.603); placeholder
}

# Domain label for reporting
DOMAIN = {
    "fiqa":      "Financial Q&A",
    "scifact":   "Scientific claims",
    "nfcorpus":  "Medical / nutrition",
    "arguana":   "Argumentation",
    "trec-covid":"Biomedical COVID-19",
    "hotpotqa":  "Multi-hop Wikipedia",
}

# Datasets that have large corpora — skip by default unless --run-large passed
LARGE_DATASETS = {"hotpotqa"}


# ---------------------------------------------------------------------------
# BEIR loader
# ---------------------------------------------------------------------------

class BEIRDataset:
    # mteb/* namespace has corpus, queries, and qrels (as "default" config)
    # BeIR/* dropped the qrels config in 2024; mteb/* is the current source
    HF_IDS = {
        "fiqa":      "mteb/fiqa",
        "scifact":   "mteb/scifact",
        "nfcorpus":  "mteb/nfcorpus",
        "arguana":   "mteb/arguana",
        "trec-covid":"mteb/trec-covid",
        "hotpotqa":  "mteb/hotpotqa",
    }

    def __init__(self, name: str, model):
        self.name = name
        self.model = model
        self.cache_dir = DATA_DIR / name
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def load(self) -> tuple:
        ce = self.cache_dir / "corpus_embs.npy"
        ci = self.cache_dir / "corpus_ids.json"
        qe = self.cache_dir / "query_embs.npy"
        qq = self.cache_dir / "queries.json"
        ql = self.cache_dir / "qrels.json"

        if all(p.exists() for p in [ce, ci, qe, qq, ql]):
            print(f"  [{self.name}] Cache hit.", flush=True)
            corpus_embs = np.load(ce)
            corpus_ids  = json.loads(ci.read_text("utf-8"))
            qrels       = json.loads(ql.read_text("utf-8"))
            queries     = json.loads(qq.read_text("utf-8"))
            query_embs  = np.load(qe)
            print(f"  [{self.name}] {len(corpus_ids):,} passages, {len(queries):,} queries", flush=True)
            return corpus_embs, corpus_ids, query_embs, queries, qrels

        hf_id = self.HF_IDS[self.name]
        print(f"  [{self.name}] Downloading {hf_id} from HuggingFace ...", flush=True)

        corpus_ds  = load_dataset(hf_id, "corpus",  split="corpus")
        queries_ds = load_dataset(hf_id, "queries", split="queries")
        qrels_ds   = load_dataset(hf_id, "default", split="test")

        qrels = {}
        test_qids = set()
        for ex in qrels_ds:
            qid = str(ex["query-id"])
            cid = str(ex["corpus-id"])
            rel = int(ex.get("score", 1))
            if rel > 0:
                qrels.setdefault(qid, {})[cid] = rel
                test_qids.add(qid)

        corpus_ids, corpus_texts = [], []
        for ex in corpus_ds:
            cid  = str(ex["_id"])
            text = ((ex.get("title") or "") + " " + (ex.get("text") or "")).strip()
            if text:
                corpus_ids.append(cid)
                corpus_texts.append(text)

        queries = {}
        for ex in queries_ds:
            qid = str(ex["_id"])
            if qid in test_qids:
                queries[qid] = ex["text"]

        print(f"  [{self.name}] Corpus: {len(corpus_ids):,}  Queries: {len(queries):,}", flush=True)
        print(f"  [{self.name}] Encoding corpus ...", flush=True)
        t0 = time.time()
        corpus_embs = self.model.encode(
            corpus_texts, batch_size=256, normalize_embeddings=True,
            show_progress_bar=True, convert_to_numpy=True,
        )
        print(f"  [{self.name}] Corpus done {time.time()-t0:.1f}s. Encoding queries ...", flush=True)
        query_list = [(qid, queries[qid]) for qid in queries]
        query_embs = self.model.encode(
            [q for _, q in query_list], batch_size=256,
            normalize_embeddings=True, show_progress_bar=True, convert_to_numpy=True,
        )
        queries_ordered = {qid: text for qid, text in query_list}

        np.save(ce, corpus_embs)
        np.save(qe, query_embs)
        ci.write_text(json.dumps(corpus_ids), "utf-8")
        ql.write_text(json.dumps(qrels), "utf-8")
        qq.write_text(json.dumps(queries_ordered), "utf-8")
        print(f"  [{self.name}] Cached.")
        return corpus_embs, corpus_ids, query_embs, queries_ordered, qrels


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

def ndcg_at_k(ranked: list, relevant: dict, k: int) -> float:
    dcg  = sum((2**relevant.get(c, 0) - 1) / math.log2(i+2) for i, c in enumerate(ranked[:k]))
    idcg = sum((2**r - 1) / math.log2(i+2) for i, r in enumerate(sorted(relevant.values(), reverse=True)[:k]))
    return dcg / idcg if idcg > 0 else 0.0


def recall_at_k(ranked: list, relevant: dict, k: int) -> float:
    hits = sum(1 for c in ranked[:k] if relevant.get(c, 0) > 0)
    return hits / len(relevant) if relevant else 0.0


def mrr(ranked: list, relevant: dict) -> float:
    for i, c in enumerate(ranked):
        if relevant.get(c, 0) > 0:
            return 1.0 / (i + 1)
    return 0.0


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session", autouse=True)
def check_deps():
    if not HAS_ST:
        pytest.skip("sentence-transformers not installed.")
    if not HAS_DS:
        pytest.skip("datasets not installed — pip install datasets")


@pytest.fixture(scope="session")
def st_model():
    if HAS_ROUTER:
        # Use model router's "docs" slot if configured, else default
        router = get_router()
        model_name = router.model_for_lang("docs")
    else:
        model_name = DEFAULT_MODEL
    try:
        import torch
        _device = "cuda" if torch.cuda.is_available() else "cpu"
    except ImportError:
        _device = "cpu"
    return SentenceTransformer(model_name, device=_device)


# ---------------------------------------------------------------------------
# Evaluation helper
# ---------------------------------------------------------------------------

def _run_dataset(name: str, model) -> dict:
    ds = BEIRDataset(name, model)
    corpus_embs, corpus_ids, query_embs, queries, qrels = ds.load()

    query_ids = list(queries.keys())
    t0 = time.time()
    ndcg10 = mrr_ = rec5 = 0.0
    n = 0

    for i, qid in enumerate(query_ids):
        if qid not in qrels:
            continue
        scores = corpus_embs @ query_embs[i]
        ranked = [corpus_ids[j] for j in np.argsort(-scores)[:100]]
        rel    = qrels[qid]
        ndcg10 += ndcg_at_k(ranked, rel, 10)
        mrr_   += mrr(ranked, rel)
        rec5   += recall_at_k(ranked, rel, 5)
        n      += 1

    return {
        "ndcg10": ndcg10 / n,
        "mrr":    mrr_   / n,
        "rec5":   rec5   / n,
        "n":      n,
        "corpus": len(corpus_ids),
        "elapsed": time.time() - t0,
    }


# ---------------------------------------------------------------------------
# Per-dataset parametrized test
# ---------------------------------------------------------------------------

SMALL_DATASETS = [d for d in BEIR_BASELINES if d not in LARGE_DATASETS]
ALL_DATASETS   = list(BEIR_BASELINES.keys())


@pytest.mark.parametrize("dataset", SMALL_DATASETS)
def test_beir_dataset(dataset, st_model):
    """BEIR documentation retrieval — one documentation domain at a time."""
    r   = _run_dataset(dataset, st_model)
    pub = BEIR_BASELINES[dataset]
    floor = NDCG_FLOOR[dataset]

    print(f"\n{'='*68}")
    print(f"BEIR: {dataset.upper()} — {DOMAIN[dataset]}")
    print(f"Corpus: {r['corpus']:,} passages   Queries: {r['n']:,}")
    print(f"{'='*68}")
    print(f"  {'Metric':<12} {'Score':>8}  {'BM25':>8}  {'TAS-B':>8}  {'SPECTER':>10}")
    print(f"  {'-'*52}")
    print(f"  {'NDCG@10':<12} {r['ndcg10']:>8.3f}  "
          f"{pub['bm25']:>8.3f}  {pub['tas_b']:>8.3f}  {pub['specter']:>10.3f}")
    print(f"  {'MRR':<12} {r['mrr']:>8.3f}")
    print(f"  {'Recall@5':<12} {r['rec5']:>7.1%}")
    print(f"  {'Time':<12} {r['elapsed']:>7.1f}s")
    print(f"{'='*68}")

    if r["ndcg10"] > pub["tas_b"]:
        print(f"  BEATS TAS-B (heavy fine-tuned) +{r['ndcg10']-pub['tas_b']:.3f}")
    elif r["ndcg10"] > pub["bm25"]:
        print(f"  Beats BM25 keyword baseline +{r['ndcg10']-pub['bm25']:.3f}")
    else:
        print(f"  Below BM25 by {r['ndcg10']-pub['bm25']:.3f} (expected for this domain)")

    assert r["ndcg10"] >= floor, (
        f"{dataset} NDCG@10 {r['ndcg10']:.3f} below floor {floor:.3f}. Retrieval broken."
    )


@pytest.mark.slow
@pytest.mark.parametrize("dataset", list(LARGE_DATASETS))
def test_beir_large_dataset(dataset, st_model):
    """Large BEIR datasets — marked slow, skipped by default.
    Run with: pytest -v -s -m slow
    """
    r   = _run_dataset(dataset, st_model)
    pub = BEIR_BASELINES[dataset]
    floor = NDCG_FLOOR[dataset]

    print(f"\n[{dataset.upper()}] {DOMAIN[dataset]}: NDCG@10={r['ndcg10']:.3f} "
          f"(BM25={pub['bm25']:.3f}, TAS-B={pub['tas_b']:.3f})")

    assert r["ndcg10"] >= floor, (
        f"{dataset} NDCG@10 {r['ndcg10']:.3f} below floor {floor:.3f}"
    )


# ---------------------------------------------------------------------------
# Model improvement loop
# ---------------------------------------------------------------------------

BEIR_IMPROVE_DATASETS = ["fiqa", "scifact", "nfcorpus", "arguana"]

# Confirmed baseline (all-MiniLM-L6-v2)
BEIR_IMPROVE_BASELINE = {
    "fiqa":     0.369,
    "scifact":  0.645,
    "nfcorpus": 0.317,
    "arguana":  0.370,
}

# (model_name, model_key, query_prefix, doc_prefix)
# e5-large-v2 uses asymmetric prefixes per model card.
# CPU speed note: bge-base/mpnet_base (~110M params) are CPU-fast.
# bge-large/e5-large (~335M params) are 3x slower — benchmarked for ceiling,
# deployed only if user explicitly enables high-quality mode.
BEIR_IMPROVE_CANDIDATES = [
    ("BAAI/bge-base-en-v1.5",                     "bge_base",   "",          ""),   # CPU-fast, already loaded for code
    ("sentence-transformers/all-mpnet-base-v2",   "mpnet_base", "",          ""),   # CPU-fast, strong classic baseline
    ("BAAI/bge-large-en-v1.5",                    "bge_large",  "",          ""),   # 335M, benchmark ceiling
    ("intfloat/e5-large-v2",                       "e5_large",   "query: ",  "passage: "),  # 335M, MTEB top-tier
]


class BEIRDatasetWithKey:
    """BEIRDataset variant with per-model-key embedding cache.

    Raw text data (corpus_texts.json, qrels.json, queries.json) is shared in the
    base beir/<dataset> directory to avoid redundant HuggingFace downloads.
    Embeddings (corpus_embs.npy, query_embs.npy) are stored per model key.
    """

    HF_IDS = BEIRDataset.HF_IDS

    def __init__(self, name, model, model_key, query_prefix="", doc_prefix=""):
        self.name = name
        self.model = model
        self.model_key = model_key
        self.query_prefix = query_prefix
        self.doc_prefix = doc_prefix
        # Shared raw-text cache (download once)
        self.base_cache = DATA_DIR / name
        self.base_cache.mkdir(parents=True, exist_ok=True)
        # Per-model embedding cache
        self.emb_cache = DATA_DIR.parent / "beir_improve" / model_key / name
        self.emb_cache.mkdir(parents=True, exist_ok=True)

    def _get_raw_data(self):
        """Return (corpus_ids, corpus_texts, queries, qrels) — download once, cache raw texts."""
        ct = self.base_cache / "corpus_texts.json"
        ci = self.base_cache / "corpus_ids.json"
        qq = self.base_cache / "queries.json"
        ql = self.base_cache / "qrels.json"

        if all(p.exists() for p in [ct, ci, qq, ql]):
            print(f"  [{self.name}] Raw-text cache hit.", flush=True)
            corpus_ids   = json.loads(ci.read_text("utf-8"))
            corpus_texts = json.loads(ct.read_text("utf-8"))
            queries      = json.loads(qq.read_text("utf-8"))
            qrels        = json.loads(ql.read_text("utf-8"))
            print(f"  [{self.name}] {len(corpus_ids):,} docs, {len(queries):,} queries", flush=True)
            return corpus_ids, corpus_texts, queries, qrels

        hf_id = self.HF_IDS[self.name]
        print(f"  [{self.name}] Downloading {hf_id} ...", flush=True)

        corpus_ds  = load_dataset(hf_id, "corpus",  split="corpus")
        queries_ds = load_dataset(hf_id, "queries", split="queries")
        qrels_ds   = load_dataset(hf_id, "default", split="test")

        qrels = {}
        test_qids = set()
        for ex in qrels_ds:
            qid = str(ex["query-id"])
            cid = str(ex["corpus-id"])
            rel = int(ex.get("score", 1))
            if rel > 0:
                qrels.setdefault(qid, {})[cid] = rel
                test_qids.add(qid)

        corpus_ids, corpus_texts = [], []
        for ex in corpus_ds:
            cid  = str(ex["_id"])
            text = ((ex.get("title") or "") + " " + (ex.get("text") or "")).strip()
            if text:
                corpus_ids.append(cid)
                corpus_texts.append(text)

        queries = {}
        for ex in queries_ds:
            qid = str(ex["_id"])
            if qid in test_qids:
                queries[qid] = ex["text"]

        ci.write_text(json.dumps(corpus_ids), "utf-8")
        ct.write_text(json.dumps(corpus_texts), "utf-8")
        ql.write_text(json.dumps(qrels), "utf-8")
        qq.write_text(json.dumps(queries), "utf-8")
        print(f"  [{self.name}] Raw texts cached. {len(corpus_ids):,} docs.", flush=True)
        return corpus_ids, corpus_texts, queries, qrels

    def load(self):
        ce = self.emb_cache / "corpus_embs.npy"
        qe = self.emb_cache / "query_embs.npy"

        corpus_ids, corpus_texts, queries, qrels = self._get_raw_data()

        if ce.exists() and qe.exists():
            print(f"  [{self.name}] Embedding cache hit ({self.model_key}).", flush=True)
            return np.load(ce), corpus_ids, np.load(qe), queries, qrels

        doc_texts = [self.doc_prefix + t for t in corpus_texts] if self.doc_prefix else corpus_texts
        print(f"  [{self.name}] Encoding {len(corpus_ids):,} docs ({self.model_key}) ...", flush=True)
        t0 = time.time()
        # batch_size=128 with fp16: safe VRAM even with 16K-char FIQA outliers; 2x GPU throughput
        # History: bs=256 fp32 → 4 docs/s (VRAM overflow); bs=64 fp32 → 40 docs/s; bs=128 fp16 → target 80+ docs/s
        corpus_embs = self.model.encode(
            doc_texts, batch_size=128, normalize_embeddings=True,
            show_progress_bar=True, convert_to_numpy=True,
        )
        print(f"  Corpus done {time.time()-t0:.1f}s. Encoding queries ...", flush=True)
        query_ids = list(queries.keys())
        q_texts = (
            [self.query_prefix + queries[qid] for qid in query_ids]
            if self.query_prefix else
            [queries[qid] for qid in query_ids]
        )
        query_embs = self.model.encode(
            q_texts, batch_size=128, normalize_embeddings=True,
            show_progress_bar=True, convert_to_numpy=True,
        )
        np.save(ce, corpus_embs)
        np.save(qe, query_embs)
        print(f"  [{self.name}] Embeddings cached.", flush=True)
        return corpus_embs, corpus_ids, query_embs, queries, qrels


def _eval_beir_model(model_name, model_key, query_prefix="", doc_prefix=""):
    """Evaluate one model across BEIR_IMPROVE_DATASETS. Returns per-dataset metrics dict."""
    try:
        import torch
        _device = "cuda" if torch.cuda.is_available() else "cpu"
    except ImportError:
        _device = "cpu"
    model = SentenceTransformer(model_name, device=_device)
    # fp16 on GPU: 2x throughput + half VRAM → batch_size=128 safe even with long FIQA outliers
    if _device == "cuda":
        model.half()
    print(f"  Device: {_device} ({'GPU fp16' if _device == 'cuda' else 'CPU fp32 fallback'})", flush=True)
    results = {}
    for ds_name in BEIR_IMPROVE_DATASETS:
        ds = BEIRDatasetWithKey(ds_name, model, model_key, query_prefix, doc_prefix)
        corpus_embs, corpus_ids, query_embs, queries, qrels = ds.load()
        query_ids = list(queries.keys())
        ndcg10 = mrr_ = rec5 = 0.0
        n = 0
        for i, qid in enumerate(query_ids):
            if qid not in qrels:
                continue
            scores = corpus_embs @ query_embs[i]
            ranked = [corpus_ids[j] for j in np.argsort(-scores)[:100]]
            rel = qrels[qid]
            ndcg10 += ndcg_at_k(ranked, rel, 10)
            mrr_   += mrr(ranked, rel)
            rec5   += recall_at_k(ranked, rel, 5)
            n += 1
        results[ds_name] = {"ndcg10": ndcg10 / n, "mrr": mrr_ / n, "rec5": rec5 / n, "n": n}
        print(f"  [{ds_name}] NDCG@10={ndcg10/n:.3f}  MRR={mrr_/n:.3f}", flush=True)
    return results


@pytest.mark.parametrize("model_name,model_key,query_prefix,doc_prefix", BEIR_IMPROVE_CANDIDATES)
def test_beir_improve(model_name, model_key, query_prefix, doc_prefix):
    """BEIR doc model improvement loop — compare candidates vs all-MiniLM-L6-v2 baseline.

    Baseline (all-MiniLM-L6-v2): FIQA=0.369, SciFact=0.645, NFCorpus=0.317, ArguAna=0.370
    Avg baseline: 0.425
    Win threshold: avg NDCG@10 > baseline avg + 0.020

    To update best_model_config.json after a win:
        python update_beir_best.py --model '<model_name>' --key '<model_key>'
    """
    if not HAS_ST:
        pytest.skip("sentence-transformers not installed")
    if not HAS_DS:
        pytest.skip("datasets not installed")

    baseline_avg = sum(BEIR_IMPROVE_BASELINE.values()) / len(BEIR_IMPROVE_BASELINE)
    print(f"\nBEIR IMPROVE: {model_key} ({model_name})", flush=True)
    if query_prefix:
        print(f"  query_prefix='{query_prefix}'  doc_prefix='{doc_prefix}'", flush=True)

    results = _eval_beir_model(model_name, model_key, query_prefix, doc_prefix)
    scores = {ds: results[ds]["ndcg10"] for ds in BEIR_IMPROVE_DATASETS}
    current_avg = sum(scores.values()) / len(scores)

    print(f"\n{'='*72}")
    print(f"BEIR IMPROVE RESULT — {model_key} ({model_name})")
    print(f"{'='*72}")
    print(f"  {'Dataset':<12} {'Baseline':>10}  {'This':>10}  {'Delta':>8}  Status")
    print(f"  {'-'*58}")
    for ds_name in BEIR_IMPROVE_DATASETS:
        base  = BEIR_IMPROVE_BASELINE[ds_name]
        score = scores[ds_name]
        delta = score - base
        tag = "BETTER" if delta > 0.005 else ("~same" if abs(delta) <= 0.005 else "worse")
        print(f"  {ds_name:<12} {base:>10.3f}  {score:>10.3f}  {delta:>+8.3f}  {tag}")
    print(f"  {'-'*58}")
    print(f"  {'AVG':<12} {baseline_avg:>10.3f}  {current_avg:>10.3f}  "
          f"{current_avg-baseline_avg:>+8.3f}")
    print(f"{'='*72}")

    cpu_flag = " [CPU-fast OK]" if model_key in ("bge_base", "mpnet_base") else " [3x slower on CPU -- benchmark only]"
    if current_avg >= baseline_avg + 0.02:
        print(f"  BEATS BASELINE by avg +{current_avg-baseline_avg:.3f}  "
              f"(threshold 0.020){cpu_flag}")
        if model_key in ("bge_base", "mpnet_base"):
            print(f"  DEPLOYABLE - CPU-friendly, update best_model_config.json['docs']!")
        else:
            print(f"  Large model ceiling - note score gap but keep bge_base unless user opts in.")
    else:
        gap = baseline_avg + 0.02 - current_avg
        print(f"  Does NOT beat baseline by 0.020 avg "
              f"(got {current_avg-baseline_avg:+.3f}, need {gap:.3f} more){cpu_flag}")


def test_beir_summary(st_model):
    """Run all standard (non-large) datasets and print a comprehensive table."""
    datasets = SMALL_DATASETS
    results  = {}
    for ds_name in datasets:
        print(f"  Running {ds_name} ({DOMAIN[ds_name]}) ...", flush=True)
        results[ds_name] = _run_dataset(ds_name, st_model)

    W = 102
    print(f"\n{'='*W}")
    print("BEIR MULTI-DOMAIN DOCUMENTATION BENCHMARK")
    print(f"Domains: Finance | Scientific | Medical | Argumentation | Biomedical | General")
    print(f"{'='*W}")
    print(f"  {'Dataset':<12} {'Domain':<22} {'N':>5}  {'NDCG@10':>8}  "
          f"{'BM25':>6}  {'TAS-B':>7}  {'SPECTER':>9}  Status")
    print(f"  {'-'*(W-2)}")

    for ds_name in datasets:
        r   = results[ds_name]
        pub = BEIR_BASELINES[ds_name]
        s   = r["ndcg10"]
        dom = DOMAIN[ds_name]

        if s > pub["tas_b"]:
            status = f"BEATS TAS-B +{s-pub['tas_b']:.3f}"
        elif s > pub["specter"]:
            status = f"beats SPECTER +{s-pub['specter']:.3f}"
        elif s > pub["bm25"]:
            status = f"beats BM25 +{s-pub['bm25']:.3f}"
        else:
            status = f"below BM25 {s-pub['bm25']:+.3f} (expected)"

        print(f"  {ds_name:<12} {dom:<22} {r['n']:>5,}  {s:>8.3f}  "
              f"{pub['bm25']:>6.3f}  {pub['tas_b']:>7.3f}  {pub['specter']:>9.3f}  {status}")

    print(f"{'='*W}")
    print()
    print("  BM25: keyword search baseline (no ML).")
    print("  TAS-B, SPECTER: heavy domain-specialized bi-encoders (hundreds of MB).")
    print("  Same model that retrieves code across 7 languages retrieves all doc types.")
    print()
    print("  Note on TREC-COVID: BM25 is unusually strong on this dataset (0.656).")
    print("  All dense embedding models underperform BM25 on TREC-COVID; this is known.")
    print("  Note on HotpotQA: multi-hop queries by design require cross-passage reasoning.")
    print("  Run large datasets with: pytest -v -s -m slow")

    all_scores = [r["ndcg10"] for r in results.values()]
    assert all(s >= 0.15 for s in all_scores), "One or more datasets below absolute minimum."
