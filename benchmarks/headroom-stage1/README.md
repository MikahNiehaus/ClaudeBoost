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
python3 capture.py                    # needs clean-rag up on 127.0.0.1:8613
/tmp/hr-venv/bin/python measure.py    # savings + field retention per payload
/tmp/hr-venv/bin/python control.py    # the control: compaction vs headroom, swept over its presets
/tmp/hr-venv/bin/python hookblock.py  # §7.1: the hook-injection side
python3 -m pytest tests/test_headroom_stage1_metrics.py   # from the repo root
```

`capture.py` writes real wire bytes to `payloads_wire/` (not re-serialized —
clean-rag already sends `indent=2`, and re-indenting would fake the baseline).
`measure.py` and `control.py` both read that one directory, so their numbers
describe the same 18 payloads.

`payloads_wire/` is gitignored: a real capture is verbatim source code from
whatever projects you had indexed. The scripts and the recorded measurements are
the committed artifact, the inputs are not — same split as
`benchmarks/codesearchnet`.

### Choosing which projects to capture

`capture.py` hardcodes no project path — absolute paths are local to whoever ran
the capture, and this is a public repo. By default it asks the running server for
its indexed projects and takes the best-indexed `STAGE1_N_PROJECTS` (default 3).

To pin an exact set — needed to reproduce the recorded numbers, since
auto-discovery follows whatever is largest *now* — pass absolute paths:

```bash
STAGE1_PROJECTS=/abs/one,/abs/two,/abs/three python3 capture.py
CLEAN_RAG_URL=http://127.0.0.1:8613 python3 capture.py   # non-default server
```

The recorded run used three projects whose short names appear in
`stage1_results.json`: `assets-backend`, `assets-messages` and
`reputation-ontology`. All five `lossless:table` payloads came from the last of
those, so a capture without it will not reproduce §7.3's split.

Importing `capture.py` is inert: discovery and the capture loop both run only
under `__main__`, so no import can hit the network or overwrite a recorded
capture.

## Files

| File | Role |
|---|---|
| `capture.py` | Captures real `/search` responses, exact wire bytes |
| `metrics.py` | The percentage arithmetic and the wire-byte split. Stdlib-only, so it is testable |
| `retention.py` | Field-retention checker + its own 10-case self-test |
| `measure.py` | Per-payload savings, safe ceilings and retention, both compression paths |
| `control.py` | **The decisive one** — isolates headroom's contribution from plain JSON compaction, and sweeps its three named presets |
| `hookblock.py` | §7.1 — runs the real `rag-enforce.py` and measures the block it injects |
| `stage1_results.json`, `control_results.json`, `hookblock_results.json` | Recorded output from the 2026-09-12 run |

`tests/test_headroom_stage1_metrics.py` (in the repo's own suite, no headroom
needed) covers `metrics.py` and `retention.py` and pins the figures quoted in §7
to the recorded output, so a number that drifts from the harness fails the suite.

## Caveats baked into every number

Token counts come from headroom's `AnthropicTokenCounter`, which uses tiktoken
`cl100k_base` × 1.1 for a bare string — **not** a real Anthropic tokenizer. The
numbers are approximations, consistent with each other, and must not be quoted
as exact. Real counts need a live `Anthropic()` client passed to the provider.

`hookblock.py` builds its input from live search results, so its token counts
move with the index. Its byte count does not: `rag-enforce.py` caps the block at
3 results × 250 characters. It also opens a research-turn record under a
synthetic session id in clean-rag's gitignored `state/research/`, which expires
after an hour.
