# Headroom Stage 1 measurement

Reproduces the numbers in `docs/HEADROOM-EVALUATION.md` §7. Measures what
headroom compression actually does to real clean-rag `/search` payloads.

## Setup

Headroom must be installed in its **own** environment — never in
`clean-rag-venv`, which pins `transformers<5.0.0` via `sentence-transformers`
while headroom's `[proxy]` extra wants `>=5.5.0` (see §4 of the evaluation).

```bash
python3.13 -m venv /tmp/hr-venv
/tmp/hr-venv/bin/pip install "headroom-ai" "headroom-ai[code]"   # core only: no torch, no transformers
```

## Run

```bash
python3 capture.py                  # needs clean-rag up on 127.0.0.1:8613
/tmp/hr-venv/bin/python measure.py  # savings + field retention per payload
/tmp/hr-venv/bin/python control.py  # the control: compaction vs headroom
/tmp/hr-venv/bin/python retention.py  # self-test of the retention checker
```

`capture.py` writes real wire bytes to `payloads_wire/` (not re-serialized —
clean-rag already sends `indent=2`, and re-indenting would fake the baseline).

## Files

| File | Role |
|---|---|
| `capture.py` | Captures real `/search` responses, exact wire bytes |
| `retention.py` | Field-retention checker + its own 8-case self-test |
| `measure.py` | Per-payload savings and retention, both compression paths |
| `control.py` | **The decisive one** — isolates headroom's contribution from plain JSON compaction |
| `stage1_results.json`, `control_results.json` | Recorded output from the 2026-09-12 run |

## Caveat baked into every number

Token counts come from headroom's `AnthropicTokenCounter`, which uses tiktoken
`cl100k_base` × 1.1 for a bare string — **not** a real Anthropic tokenizer. The
numbers are approximations, consistent with each other, and must not be quoted
as exact. Real counts need a live `Anthropic()` client passed to the provider.
