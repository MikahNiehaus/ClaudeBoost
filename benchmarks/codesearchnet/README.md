# ClaudeBoost — CodeSearchNet Benchmark

Reproducible evaluation of ClaudeBoost's RAG retrieval quality on the CodeSearchNet Python test set.

## Protocol

Matches the self-supervised evaluation in **Husain et al. 2019** — the same protocol used to benchmark Microsoft's GraphCodeBERT and CodeBERT:

- **Dataset**: CodeSearchNet Python test set (~22,176 functions)
- **Task**: given a natural language docstring, retrieve the correct function from the full candidate pool
- **Metrics**: MRR, R@1, R@5, R@10

No fine-tuning on code. ClaudeBoost uses `sentence-transformers/all-MiniLM-L6-v2` (a general sentence transformer) plus graph-augmented retrieval — zero cloud cost, runs on local CPU.

## Quickstart

```bash
# 1. Start the ClaudeBoost RAG server
python scripts/rag-server-start.py

# 2. Install benchmark dependencies
pip install -r benchmarks/codesearchnet/requirements.txt

# 3. Run full benchmark (~40 min — downloads data on first run)
python benchmarks/codesearchnet/benchmark.py

# 4. Quick smoke test (~3 min, smaller pool)
python benchmarks/codesearchnet/benchmark.py --pool 500 --queries 100
```

Results are saved to `benchmarks/codesearchnet/results/full_benchmark.json`.

## CLI Options

| Flag | Default | Description |
|------|---------|-------------|
| `--rag-url` | `http://127.0.0.1:8612` | RAG server URL |
| `--pool` | 0 (full test set) | Candidate pool size. 0 = all ~22K functions |
| `--queries` | 500 | Number of random queries to evaluate |
| `--seed` | 42 | Random seed for reproducibility |
| `--limit` | 10 | Search result limit (max rank tracked) |
| `--keep-dir` | false | Keep temp index dir after run |

## Published Baselines (Python, ~22K pool)

| Model | MRR | R@1 | R@5 |
|-------|-----|-----|-----|
| GraphCodeBERT (Microsoft) | 0.769 | 0.723 | 0.852 |
| CodeBERT | 0.713 | 0.661 | 0.806 |
| SelfAtt | 0.690 | — | — |
| NBOW | 0.510 | — | — |
| **ClaudeBoost RAG** | **see results/** | | |

Source: [Guo et al. 2021 (GraphCodeBERT)](https://arxiv.org/abs/2009.08366), [Feng et al. 2020 (CodeBERT)](https://arxiv.org/abs/2002.08155)

## Reproducibility Notes

- The benchmark downloads the parquet directly from HuggingFace on first run and caches it in `benchmarks/codesearchnet/data/`
- Docstrings are stripped from source code before indexing to prevent data leakage
- Results are fully deterministic given the same `--seed`
- The data split used is the official CodeSearchNet Python **test** split (not train or valid)

## Submitting to Papers With Code

Once you have results in `results/full_benchmark.json`:

1. Go to [CodeSearchNet leaderboard](https://paperswithcode.com/sota/code-search-on-codesearchnet)
2. Click **Submit result**
3. Link to this repository
4. Fill in the metrics from `results/full_benchmark.json`
5. Note in the method description: "general sentence transformer + graph augmentation, no code-specific fine-tuning, CPU-only"
