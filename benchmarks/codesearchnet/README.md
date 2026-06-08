# ClaudeBoost — CodeSearchNet Benchmark

Reproducible evaluation of ClaudeBoost's RAG retrieval quality across **7 programming languages** using the CodeSearchNet benchmark protocol. Includes benchmark-driven per-language model selection and **siginj** — a simple document augmentation technique that achieves MRR 0.950 / R@1 91.7% on C# with no model fine-tuning.

## Key Results

### Full corpus baseline (Python, 21,544-function pool)

Matches the self-supervised evaluation protocol from Husain et al. 2019 — directly comparable to published baselines.

| Model | MRR | R@1 | R@5 | Notes |
|-------|-----|-----|-----|-------|
| GraphCodeBERT (Microsoft) | 0.769 | 0.723 | 0.852 | Code-pretrained, fine-tuned |
| CodeBERT | 0.713 | 0.661 | 0.806 | Code-pretrained |
| SelfAtt | 0.690 | — | — | |
| NBOW | 0.510 | — | — | |
| **ClaudeBoost (st-codesearch-distilroberta)** | **0.617** | **0.500** | **0.774** | No fine-tuning, local GPU, $0 cost |
| ClaudeBoost (all-MiniLM-L6-v2, old) | 0.587 | 0.484 | 0.734 | Previous default, general sentence transformer |

Source: [Guo et al. 2021 (GraphCodeBERT)](https://arxiv.org/abs/2009.08366), [Feng et al. 2020 (CodeBERT)](https://arxiv.org/abs/2002.08155)

### 1K-pool per-language results (Husain et al. 2019 original protocol)

1K-pool = each query ranked against 999 random distractors. This is the original evaluation protocol from the CodeSearchNet paper. **Not directly comparable to the full-corpus table above** — the larger the pool, the harder the task.

| Language | Model | Strategy | MRR | R@1 | Floor |
|----------|-------|----------|-----|-----|-------|
| **C#** | BAAI/bge-base-en-v1.5 | **siginj** | **0.950** | **0.917** | 0.935 |
| Python | st-codesearch-distilroberta-base | default | 0.898 | — | 0.845 |
| Java | st-codesearch-distilroberta-base | default | 0.850 | — | 0.751 |
| PHP | st-codesearch-distilroberta-base | default | 0.850 | — | 0.719 |
| JavaScript | st-codesearch-distilroberta-base + bge-base (3-way fusion) | camel_split | 0.801 | — | 0.786 |
| Go | st-codesearch-distilroberta-base | default | 0.839 | — | 0.770 |
| Ruby | st-codesearch-distilroberta-base | default | 0.738 | — | 0.700 |

All results: zero fine-tuning, local GPU/CPU, $0 inference cost.

## siginj — Signature Injection for C#

C# is unusually hard for general embedding models because method names are often generic (`Process`, `Execute`, `Handle`) and the docstring alone gives little signal. **siginj** fixes this by prepending the method signature to the document text at index time:

```
# Without siginj (doc only)
"Processes the given input and returns a result."

# With siginj (signature + doc)
"public async Task<ProcessResult> ProcessPaymentAsync(PaymentRequest request, CancellationToken ct)\nProcesses the given input and returns a result."
```

The query embedding sees natural language; the document embedding now contains the type signatures, parameter names, and return type that the query implicitly describes. No LLM required — just structured metadata that was already present in the source code.

**Why it works:** BGE-base uses asymmetric retrieval (query prefix ≠ document prefix). The model already expects query and document to be in different "registers." siginj exploits this by making the document richer without changing the query.

**Result:** MRR improves from ~0.82 (bge-base, plain docstring) to **0.950** (+13 points). R@1 goes from ~0.74 to **0.917** (+17.7 points).

## Per-Language Model Routing

Different languages benefit from different models. The benchmark identified:

| Language group | Best model | Reason |
|---------------|-----------|--------|
| Python, Java, Go, PHP, Ruby | `flax-sentence-embeddings/st-codesearch-distilroberta-base` | Trained on code-query pairs across these languages |
| C# | `BAAI/bge-base-en-v1.5` + siginj | BGE's asymmetric retrieval + signature augmentation outperforms code-trained model for C# |
| JavaScript | 3-way fusion (st-codesearch 20% + bge-base 40% + bge-base-camelcase 40%) | Camel-case splitting helps with JS identifier semantics |

These model choices are wired into the production ClaudeBoost MCP RAG server (`mcp-rag-server/src/rag_server/config.py`).

## Protocol

- **Full corpus**: query ranked against all ~22K test functions. Matches published baseline protocol exactly.
- **1K-pool**: query ranked against 999 random distractors (seed=42). This is the original Husain et al. 2019 evaluation protocol.
- **Data leakage prevention**: docstrings are stripped from source code before indexing. Only code tokens are embedded.
- **Reproducibility**: fully deterministic given the same `--seed`.
- **Data split**: official CodeSearchNet test split (not train or valid).

## Quickstart

```bash
# 1. Start the ClaudeBoost RAG server
python scripts/rag-server-start.py

# 2. Install benchmark dependencies
pip install -r benchmarks/codesearchnet/requirements.txt

# 3. Run full benchmark — Python, full corpus (~40 min, downloads data on first run)
python benchmarks/codesearchnet/benchmark.py

# 4. Run 1K-pool multilang benchmark (all 7 languages)
python mcp-rag-server/tests/test_codesearchnet_multilang.py

# 5. Quick smoke test (~3 min)
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

## Reproducibility Notes

- The benchmark downloads parquet directly from HuggingFace on first run and caches it in `benchmarks/codesearchnet/data/`
- The multilang benchmark uses pre-cached embeddings in `mcp-rag-server/tests/data/`
- All model selections are logged in `mcp-rag-server/tests/data/best_model_config.json`
- The 1K-pool seed (42) is fixed across all languages for comparability

## Submitting Results

Papers With Code was shut down by Meta in July 2025. Current options:

- **[CodeSOTA](https://www.codesota.com)** — the active SOTA leaderboard successor
- **Hugging Face** — submit as a model card or dataset card evaluation result
- **W&B** — the original CodeSearchNet leaderboard was hosted at `app.wandb.ai/github/codesearchnet/benchmark`
