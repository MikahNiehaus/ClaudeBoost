"""
ClaudeBoost  —  CodeSearchNet Benchmark
========================================
Protocol: self-supervised MRR evaluation matching Husain et al. 2019.
Pool    : full Python test set (~22,176 functions).
Metrics : R@1, R@5, R@10, MRR  (same as published baselines).

Published Python baselines (same protocol):
  GraphCodeBERT (Microsoft): MRR=0.769  R@1=0.723  R@5=0.852
  CodeBERT:                  MRR=0.713  R@1=0.661  R@5=0.806

Prerequisites
-------------
1. ClaudeBoost RAG server running on localhost:8612
   Start it: python scripts/rag-server-start.py
2. pip install -r requirements.txt

Usage
-----
  # Full benchmark (~40 min):
  python benchmark.py

  # Faster smoke-test (500-function pool, ~3 min):
  python benchmark.py --pool 500 --queries 100

  # Custom RAG URL:
  python benchmark.py --rag-url http://127.0.0.1:8612

Results are saved to results/full_benchmark.json (or results/bench_<pool>.json for custom pool).
"""
import argparse
import ast
import json
import pathlib
import random
import shutil
import sys
import tempfile
import time
import urllib.error
import urllib.request
import warnings

SCRIPT_DIR   = pathlib.Path(__file__).parent
DATA_DIR     = SCRIPT_DIR / "data"
RESULTS_DIR  = SCRIPT_DIR / "results"
HF_PARQUET   = (
    "https://huggingface.co/datasets/code_search_net/resolve/main"
    "/python/test-00000-of-00001.parquet"
)

RESULTS_DIR.mkdir(exist_ok=True)
DATA_DIR.mkdir(exist_ok=True)


# ── Arg parsing ───────────────────────────────────────────────────────────────
def parse_args():
    p = argparse.ArgumentParser(description="ClaudeBoost CodeSearchNet benchmark")
    p.add_argument("--rag-url",  default="http://127.0.0.1:8612",
                   help="ClaudeBoost RAG server URL (default: http://127.0.0.1:8612)")
    p.add_argument("--pool",     type=int, default=0,
                   help="Candidate pool size. 0 = use full test set (default)")
    p.add_argument("--queries",  type=int, default=500,
                   help="Number of random queries to evaluate (default: 500)")
    p.add_argument("--seed",     type=int, default=42,
                   help="Random seed (default: 42)")
    p.add_argument("--limit",     type=int,   default=10,
                   help="Results per search query — determines max rank tracked (default: 10)")
    p.add_argument("--min-score", type=float, default=0.0,
                   help="Minimum similarity score to include result (default: 0.0 for benchmark). "
                        "Set to 0.5 to match production default.")
    p.add_argument("--query-prefix", type=str, default="",
                   help="Prefix to prepend to every docstring query, e.g. 'python function that'")
    p.add_argument("--keep-dir", action="store_true",
                   help="Keep the temp index directory after the run (for debugging)")
    return p.parse_args()


# ── RAG helpers ───────────────────────────────────────────────────────────────
def rag_check(base_url):
    try:
        with urllib.request.urlopen(f"{base_url}/status", timeout=5) as r:
            data = json.loads(r.read())
            return data.get("status") == "ready"
    except Exception:
        return False


def rag_model_name(base_url):
    """Return the code embedding model the server is currently using."""
    try:
        with urllib.request.urlopen(f"{base_url}/status", timeout=5) as r:
            data = json.loads(r.read())
            # code_model may differ from the default knowledge model
            return data.get("code_model") or data.get("model", "unknown")
    except Exception:
        return "unknown"


def rag_index(base_url, project_path, force=True):
    body = json.dumps({"project_path": str(project_path), "force": force}).encode()
    req  = urllib.request.Request(
        f"{base_url}/index", data=body,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=7200) as r:
        return json.loads(r.read())


def rag_search(base_url, query, project_path, limit=10, min_score=0.0):
    payload = {
        "query":        query,
        "scope":        "codebase",
        "project_path": str(project_path),
        "mode":         "vector",
        "limit":        limit,
        "min_score":    min_score,
    }
    body = json.dumps(payload).encode()
    req  = urllib.request.Request(
        f"{base_url}/search", data=body,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read()).get("results", [])


# ── Data helpers ──────────────────────────────────────────────────────────────
def download_data():
    parquet_path = DATA_DIR / "csn_python_test.parquet"
    jsonl_path   = DATA_DIR / "csn_python_full.jsonl"

    if not parquet_path.exists():
        print("Downloading CodeSearchNet Python test set from HuggingFace...")
        urllib.request.urlretrieve(HF_PARQUET, parquet_path)
        print(f"  Saved to {parquet_path}")

    if not jsonl_path.exists():
        print("Converting parquet to JSONL...")
        import pandas as pd
        df = pd.read_parquet(parquet_path)
        count = 0
        with open(jsonl_path, "w", encoding="utf-8") as f:
            for _, row in df.iterrows():
                rec = {
                    "func_name": row.get("func_name", ""),
                    "code":      row.get("whole_func_string", row.get("code", "")),
                    "docstring": row.get("func_documentation_string",
                                        row.get("docstring", "")),
                }
                if rec["code"] and rec["docstring"]:
                    f.write(json.dumps(rec) + "\n")
                    count += 1
        print(f"  Wrote {count} examples")

    examples = []
    with open(jsonl_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                examples.append(json.loads(line))
    return examples


def strip_docstring(code):
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


def write_source_files(examples, dest_dir):
    print(f"Writing {len(examples)} stripped source files to {dest_dir}...")
    t = time.time()
    for i, ex in enumerate(examples):
        if i % 2000 == 0 and i > 0:
            print(f"  {i}/{len(examples)}...")
        raw   = ex.get("func_name", f"func{i}").split(".")[-1]
        safe  = "".join(c if c.isalnum() or c == "_" else "_" for c in raw)[:30]
        fname = f"func_{i:06d}_{safe}.py"
        (dest_dir / fname).write_text(strip_docstring(ex["code"]), encoding="utf-8")
    print(f"  Done in {time.time()-t:.1f}s")


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    args = parse_args()
    rag_url = args.rag_url

    # 1. Health check
    print(f"Checking RAG server at {rag_url}...")
    if not rag_check(rag_url):
        print("ERROR: RAG server not ready. Start it with: python scripts/rag-server-start.py")
        sys.exit(1)
    model_name = rag_model_name(rag_url)
    print(f"  Server ready. Code embedding model: {model_name}")

    # 2. Load data
    print("\nLoading CodeSearchNet Python test set...")
    all_examples = download_data()
    print(f"  Total examples: {len(all_examples)}")

    # 3. Sample pool
    random.seed(args.seed)
    pool_size = args.pool if args.pool > 0 else len(all_examples)
    pool_size = min(pool_size, len(all_examples))
    pool_indices = random.sample(range(len(all_examples)), pool_size)
    pool = [all_examples[i] for i in pool_indices]
    # Remap so pool[i] gets tag func_{i:06d}_
    print(f"  Pool size: {pool_size} functions")

    # 4. Write source files
    index_dir = pathlib.Path(tempfile.mkdtemp(prefix="csn_bench_"))
    try:
        write_source_files(pool, index_dir)

        # 5. Index
        print(f"\nIndexing {pool_size} functions into RAG...")
        print("  Estimated time: ~90s per 1000 functions")
        t_idx = time.time()
        result = rag_index(rag_url, index_dir, force=True)
        idx_elapsed = time.time() - t_idx
        files_indexed = result.get("files_indexed", 0)
        print(f"  Indexed {files_indexed} files in {idx_elapsed:.1f}s ({idx_elapsed/60:.1f} min)")

        # 6. Evaluate
        n_queries = min(args.queries, pool_size)
        query_indices = random.sample(range(pool_size), n_queries)
        print(f"\nEvaluating {n_queries} queries against {pool_size}-function pool...")

        hits = {1: 0, 5: 0, 10: 0}
        rr_sum = 0.0
        t_bench = time.time()

        for q_num, pool_idx in enumerate(query_indices):
            if q_num % 50 == 0:
                elapsed = time.time() - t_bench
                eta = (elapsed / (q_num + 1)) * (n_queries - q_num - 1) if q_num > 0 else 0
                print(f"  {q_num}/{n_queries}  ETA: {eta/60:.1f} min")

            ex      = pool[pool_idx]
            tag     = f"func_{pool_idx:06d}_"
            query   = (args.query_prefix + " " + ex["docstring"]).strip() if args.query_prefix else ex["docstring"]
            results = rag_search(rag_url, query, index_dir, limit=args.limit, min_score=args.min_score)

            for rank, r in enumerate(results, 1):
                if tag in r.get("source", ""):
                    for k in (1, 5, 10):
                        if rank <= k:
                            hits[k] += 1
                    rr_sum += 1.0 / rank
                    break

        bench_elapsed = time.time() - t_bench

        # 7. Results
        r1  = hits[1]  / n_queries
        r5  = hits[5]  / n_queries
        r10 = hits[10] / n_queries
        mrr = rr_sum   / n_queries

        print(f"\n{'='*65}")
        print(f"CODESEARCHNET BENCHMARK  —  Python, {pool_size}-function pool")
        print(f"Queries: {n_queries}  |  Seed: {args.seed}  |  Limit: {args.limit}")
        print(f"{'='*65}")
        print(f"  ClaudeBoost RAG  ({model_name}):")
        print(f"    R@1   = {hits[1]}/{n_queries}  =  {r1:.3f}  ({r1:.1%})")
        print(f"    R@5   = {hits[5]}/{n_queries}  =  {r5:.3f}  ({r5:.1%})")
        print(f"    R@10  = {hits[10]}/{n_queries}  =  {r10:.3f}  ({r10:.1%})")
        print(f"    MRR   = {mrr:.3f}")
        print()
        print(f"  Published baselines (Python, ~22K pool, Husain et al. 2019):")
        print(f"    GraphCodeBERT (Microsoft):  MRR=0.769  R@1=0.723  R@5=0.852")
        print(f"    CodeBERT:                   MRR=0.713  R@1=0.661  R@5=0.806")
        print(f"    SelfAtt:                    MRR=0.690")
        print(f"    NBOW:                       MRR=0.510")
        print(f"{'='*65}")
        print(f"Note: pool_size={pool_size} vs published ~22,176")
        print(f"      Smaller pool = higher absolute scores. Results are comparable")
        print(f"      when pool_size >= 10,000.")

        # 8. Save JSON
        out_name = "full_benchmark.json" if args.pool == 0 else f"bench_{pool_size}.json"
        out_path = RESULTS_DIR / out_name
        out_data = {
            "method":       "ClaudeBoost RAG",
            "model":        model_name,
            "dataset":      "CodeSearchNet Python test set (Husain et al. 2019)",
            "pool_size":    pool_size,
            "n_queries":    n_queries,
            "seed":         args.seed,
            "limit":        args.limit,
            "metrics": {
                "MRR":   round(mrr, 4),
                "R@1":   round(r1,  4),
                "R@5":   round(r5,  4),
                "R@10":  round(r10, 4),
            },
            "published_baselines": {
                "GraphCodeBERT": {"MRR": 0.769, "R@1": 0.723, "R@5": 0.852},
                "CodeBERT":      {"MRR": 0.713, "R@1": 0.661, "R@5": 0.806},
            },
            "timing": {
                "index_seconds": round(idx_elapsed, 1),
                "query_seconds": round(bench_elapsed, 1),
            },
        }
        out_path.write_text(json.dumps(out_data, indent=2))
        print(f"\nResults saved to {out_path}")

    finally:
        if not args.keep_dir:
            shutil.rmtree(index_dir, ignore_errors=True)
        else:
            print(f"Index dir kept at: {index_dir}")


if __name__ == "__main__":
    main()
