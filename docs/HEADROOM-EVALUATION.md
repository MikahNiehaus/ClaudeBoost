# Headroom evaluation for ClaudeBoost

**Subject:** [headroomlabs-ai/headroom](https://github.com/headroomlabs-ai/headroom) — local
context-compression layer for LLM agents. Library, proxy, MCP server.
**Evaluated:** 2026-09-12, against `headroom-ai` v0.37.0 (commit `fix(litellm)` 2026-09-12).
**Verdict:** **Do not adopt.** The proxy is unsafe for our gates (§3); the library
path was plausible but measured out at +0.4 pts over a one-line change (§7).
Take the 11.8% available from compacting our own JSON instead.

---

## 1. What it is

Compresses everything an agent reads — tool outputs, logs, RAG chunks, files,
history — before it reaches the model. Compression runs locally; no content is
sent out to be compressed. Four delivery shapes:

| Shape | Mechanism |
|---|---|
| Library | `from headroom import compress` |
| Proxy | `headroom proxy --port 8787`, sets `ANTHROPIC_BASE_URL` |
| Agent wrap | `headroom wrap claude` — proxy + config mutation + Serena |
| MCP server | `headroom_compress`, `headroom_retrieve`, `headroom_stats` |

Internals that matter to us: **SmartCrusher** (JSON — arrays of dicts, keeps
error items and outliers by field-variance statistics), **CodeCompressor**
(AST-aware slicing, tree-sitter), **Kompress-v2-base** (HF model, prose),
**CacheAligner** (flags KV-cache-busting volatility, never rewrites),
**CCR** (originals cached locally, retrievable on demand).

### Project health

Apache-2.0. 71.7k stars, 5.5k forks, 637 open issues, created 2026-01-07, pushed
the day of this evaluation. Releases roughly weekly (v0.37.0 on 2026-08-27).
Commit log shows real outside contributors and real bug-fix churn, not a
promo repo. Healthy, but eight months old and `Development Status :: 4 - Beta` in
its own metadata.

Their published numbers, reproducible offline via
`benchmarks/index_proof_table.py --seed 20260902`: code search 21%, codebase
exploration 42%, SRE log debugging 57%. Accuracy at tier 1: GSM8K ±0.000,
SQuAD v2 97% at 19% compression, BFCL (tools) 97% at 32% compression. Compression
cost 0.21 ms p50 at 10K tokens. Taken at face value these are credible and
self-consistent — savings scale with payload repetitiveness, and they say so.

---

## 2. Why this is relevant to ClaudeBoost specifically

Not a generic "save tokens" pitch. It lands on three measured problems we already have:

1. **The injection budget is quadratic.** Recorded in project memory:
   per-prompt hook context grows quadratically, and the standing mitigation is
   "keep it delta-only and measure it." Compression is the orthogonal lever —
   it shrinks the block rather than restricting what goes in it.
2. **clean-rag results are SmartCrusher's best case.** `/search` with
   `mode: "both"` returns arrays of dicts with repeated keys, per-result
   metadata, `relation` and `seed_file` fields. Repeated JSON arrays are where
   headroom claims 60–95%, and that shape is exactly what we inject every turn.
3. **Our architecture is tool-output-heavy by design.** A single real change
   fans out researcher, swiper, bad-cop, good-cop and quick-cop, each re-reading
   files, test output and search results. Long sessions with heavy tool output
   are headroom's stated sweet spot, and they are our normal operating mode.

---

## 3. Why the proxy path is the wrong shape for us

ClaudeBoost's enforcement layer is not built on prose. It is built on **exact
literal marker lines and byte-verbatim quotes**, parsed mechanically:

- `hooks/verifier_state.py` — `VERIFIED:`, `HANDOFF:`, `NITS:`, and the
  Mode-B judge stamps `FULLY VERIFIED:` / `TEST AGAIN:`.
- `hooks/research-record.py` — `_COVERS_LINE_RE` (`^COVERS:.*$`), plus a rule
  that a GitHub citation with no accompanying verbatim quote gets the entire
  `COVERS:` line **stripped**.
- `CLAUDE.md` — `MATCH_STRATEGY: clone-and-patch` makes the verbatim quoted
  reference a *hard ceiling on the diff*, not a suggestion.

Four concrete collisions follow.

### 3.1 Compression breaks the verbatim-quote contract (sharpest risk)

CodeCompressor is an AST slicer. If a fetched GitHub source file is compressed
before swiper reads it, the snippet swiper quotes back is a quote of *compressed*
text while still being presented as verbatim. `clone-and-patch` then clamps the
diff to a reference that was silently altered. CCR's `headroom_retrieve` is an
escape hatch, but it only helps if the model chooses to call it — and nothing in
our prompt contract tells it to.

### 3.2 Terseness steering vs. a machine-parsed report format

`HEADROOM_OUTPUT_SHAPER=1` appends "be terse, don't restate context" to the end
of the system prompt. Our agent reports are required to restate context: the
literal stamp line, the covered file list, cited sources. Terseness pressure on a
format parsed by exact literal is a direct hazard.

The failure is **silent**. Both gates are fail-open by design — `research-gate.py`
exits 0 on every payload shape, `verifier-gate.py` exits 0 always and writes to
stderr. So a dropped `COVERS:` line does not raise an error; it produces an
under-covered audit trail. That is the one thing the design explicitly says must
not be fakeable: *"What can't be faked is the record, not a refusal."*

### 3.3 Effort routing dials down exactly the wrong turn

Effort routing reduces thinking budget "when a turn is only the model resuming
after a tool result — a file read, a passing test." In ClaudeBoost, resuming
after a tool result is precisely when bad-cop reads test output and decides
whether a failure is real, and when the auto-test-gate hands back a real
assertion diff to reason about. Those are the highest-judgment turns we have, and
this heuristic classifies them as routine.

### 3.4 It rewrites `~/.claude/settings.json`

`headroom/providers/claude/install.py` read-modify-writes the whole settings file
(`json.loads` → mutate `env` → `json.dumps(payload, indent=2)`) to set
`ANTHROPIC_BASE_URL` and force the tool-search default. It does preserve
unrelated keys, so it is not destructive by design — but it is a non-atomic
whole-file rewrite of the file holding 20 ClaudeBoost hook registrations
(counted 2026-09-12). Project memory already records this exact failure class:
*"clean-rag install race — installing from a live session silently loses its
hook registrations."*

Scope limit worth stating: `headroom/install/paths.py::claude_settings_path()`
resolves to `~/.claude/settings.json` only. This repo's own
`.claude/settings.json` carries 10 further ClaudeBoost hook entries
(`rag-session-reset.py`, `compaction-restore.py`, `session-primer.py`,
`rag-read-guard.py`, `stop-context-guard.py` and others) that headroom never
touches. So the blast radius is the 20 user-scope entries, not all 30.

Two further notes from their own code and docs:

- Their comment on the tool-search env is a warning, not a footnote: without it,
  pointing Claude Code at a custom `ANTHROPIC_BASE_URL` "materializes every
  schema into its context window (GH #746) — **breaking sub-agents** and forcing
  compaction." We are a subagent-first architecture.
- `headroom wrap` also installs **Serena** at user scope into `~/.claude.json`.
  We do not need it — clean-rag already has indexed vector + import-graph search.
  Suppress with `--code-memory none`.
- `headroom learn` writes to `CLAUDE.md` / `CLAUDE.local.md`. Our `CLAUDE.md` is
  26KB of hand-tuned operative rules under a measured injection budget. An
  automated writer into that file is a bad fit; if ever used, pin it to
  `CLAUDE.local.md` (its default) and never `--target CLAUDE.md`.
- Telemetry beacon is **on by default**. Requires `HEADROOM_BEACON=off` or
  `DO_NOT_TRACK=1`.

---

## 4. Verified install blocker: do not install into `clean-rag-venv`

Measured on this host (arm64, macOS 26.6.2):

```
clean-rag-venv          Python 3.14.5
  sentence-transformers 3.4.1   requires  transformers<5.0.0,>=4.41.0
  transformers          4.57.6
  torch                 2.13.0
headroom-ai[proxy]              requires  transformers>=5.5.0,<6.0
```

`headroom-ai[proxy]` and `[all]` are **mutually unsatisfiable** with clean-rag's
embedding stack. Installing either into `clean-rag-venv` would either fail
resolution or upgrade `transformers` out from under `sentence-transformers 3.4.1`
and break embedding. This is the same shared-environment hoisting failure already
in project memory as *"test-coverage MCP zod pin — run it from the pinned
install, not npx."*

Secondary, non-blocking: headroom excludes `litellm` on Python 3.14
(`python_version < '3.14'`), and clean-rag's venv is 3.14.5. Core compression
still works there; the model registry and the dashboard's dollar figure do not.
`python3.13` is available on this host if the pricing layer is ever wanted.

**Therefore:** headroom goes in its own isolated environment
(`uv tool install --python 3.13 "headroom-ai[core]"` or a dedicated venv), and
clean-rag talks to it across a process boundary — never in-process in
`clean-rag-venv`.

---

## 5. Recommendation

**Adopt narrowly, where ClaudeBoost owns both ends of the pipe.**

The asymmetry is the whole argument. Compressing clean-rag's own search payload
before injection is safe because we control the producer and the consumer, the
content is machine-generated JSON, and no gate artifact passes through it.
Compressing the entire prompt stream via the proxy puts a rewriter between the
model and the exact-literal artifacts our enforcement is built on — and the
resulting failure is a silently weakened audit trail, not an error.

### Stage 1 — measure, commit to nothing

Isolated env. Capture real `/search` responses and real injected hook blocks,
run `compress()` over them offline, report token delta and — non-negotiable —
whether the compressed form still contains every file path, `relation` and
`seed_file` the injection consumers read. No wiring, no config mutation.

### Stage 2 — compress clean-rag's injected payload

Only if Stage 1 shows real savings with zero field loss. Compress inside the 8613
server / the injecting hooks, behind an env flag defaulting **off**, with a
byte-for-byte passthrough fallback on any compression error. Touches no Claude
Code config and no agent report.

### Stage 3 — explicitly out of scope

`headroom wrap claude`, the proxy, `HEADROOM_OUTPUT_SHAPER`, effort routing,
`headroom learn`, and the Serena install. Revisit only if the verbatim-quote and
stamp-line hazards in §3 can be excluded by a *test*, not by an argument.

### Gates that must hold for any stage

- Compression must never touch agent report text. Stamp lines and cited
  verbatim snippets stay byte-exact.
- `research-record.py`'s GitHub-quote check must still pass on a compressed run.
- Off by default, single env flag, passthrough on error.
- `HEADROOM_BEACON=off`.
- A test proving a compressed injection still yields the same gate coverage as an
  uncompressed one. Per CLAUDE.md, that test runs once with a **scrubbed
  environment**, not the inherited one.

---

## 7. Stage 1 result (measured 2026-09-12)

Ran against real data. Harness and recorded output: `benchmarks/headroom-stage1/`.

**Setup.** `headroom-ai` 0.37.0 in its own Python 3.13 venv, base + `[code]`
extras only — no torch, transformers, magika or onnxruntime, confirming §4's
conclusion that core JSON compression needs none of them. Inputs: 18 real
`/search` responses (exact wire bytes, `mode: "both"`, 180 results, 200,059
bytes) across three indexed projects, plus 3 real `rag-enforce.py` injection
blocks.

**All numbers are approximations.** headroom's `AnthropicTokenCounter` counts a
bare string with tiktoken `cl100k_base` × 1.1, not a real Anthropic tokenizer.

### 7.1 The hook-injection side is already finished

`rag-enforce.py` emits **1,248 bytes (~310 tokens)**, constant across three
different prompts, and already internally truncated. That is below every
headroom threshold (`min_tokens_to_crush` 200 on an array, `min_tokens_to_compress`
250 per message) and far too small to be worth compressing. The injection-budget
work already took this win — `session-primer.py` went 5,751 → 729 chars. There is
nothing left here for compression to get.

So the target is narrower than §2 assumed: only the `/search` tool-result
payloads, 5–22KB each.

### 7.2 Savings and risk live in the same field

Across all 180 results:

| Part of payload | Bytes | Share |
|---|---:|---:|
| `content` (the source code) | 145,025 | **78.8%** |
| all metadata fields | 39,122 | 21.2% |

Compression that must not touch `content` has a hard ceiling around a fifth of
the payload. Everything beyond that is bought by altering the code an agent
quotes — exactly the §3.1 hazard.

### 7.3 The control experiment is the whole answer

clean-rag serves `indent=2` pretty-printed JSON over the wire. Compacting it
(`json.dumps(separators=(",", ":"))`) is lossless, structure-preserving, one
line, and needs no dependency. Measured against headroom on identical inputs:

| | median | min | max |
|---|---:|---:|---:|
| Compact JSON only, no headroom | **11.8%** | 5.4% | 20.0% |
| SmartCrusher on wire bytes | 14.9% | 7.4% | 88.2% |
| SmartCrusher *after* compacting | **0.6%** | 0.0% | 87.5% |

The payloads split cleanly into two populations:

| Population | n | headroom saving | compaction alone | headroom's own contribution |
|---|---:|---:|---:|---:|
| `none:adaptive_at_limit` | **13** | 14.0% | 13.6% | **+0.4 pts** |
| `lossless:table` | 5 | 86.2% | 6.6% | +79.6 pts |

On **72% of real payloads headroom adds 0.4 points** over a one-line change we
can make ourselves. The mechanism is `SmartCrusherConfig.lossless_min_savings_ratio
= 0.15`: the table transform is only applied when it would clear 15%, and
otherwise the payload passes through with nothing but JSON compaction. Raising
`bias` from 1.0 to 50.0 does not change the decision.

### 7.4 Where it does win, it fails the retention gate

The 5 `lossless:table` payloads compress 86% — by rewriting `results` from a JSON
array of dicts into a **single string** holding a schema header plus CSV rows,
with every `content` value replaced by a CCR pointer:

```
{"results":"[10]{content:string,file:string,line_end:int,...}
<<ccr:974c31ec70ff,string,1.9KB>>,reputation/schemas/visit.waiting_set/1-0-0.json,206,134,...
```

Two consequences:

- **Structure is gone.** Any consumer doing `payload["results"][i]["file"]`
  breaks. Metadata *values* survive — distinctive strings matched 100% — so the
  transform is honestly named lossless, but it is lossless in the way a CSV is
  lossless, not in the way a parseable field is.
- **The code is gone**, replaced by a retrieval pointer that only resolves if the
  model calls `headroom_retrieve` through the MCP server (`[mcp]`/`[proxy]`, which
  we deliberately did not install) and chooses to do so.

Against Stage 1's stated non-negotiable gate — every consumer field must survive
— the result is **FAIL on 5/18, PASS on 13/18**, and the 13 pass only because
nothing happened to them beyond compaction.

### 7.5 Verdict: Stage 2 as written is not justified

Take the free win, drop the dependency:

1. **Do — serve compact JSON from clean-rag.** Median 11.8% (up to 20%) off every
   search payload. Lossless, structure-preserving, one line, no third-party code,
   no new environment, nothing to gate behind a flag.
2. **Do not — wire headroom into the injection path.** On 72% of real payloads it
   contributes 0.4 points over item 1. On the 28% where it wins big it destroys
   the JSON structure and swaps the source code for pointers requiring a component
   we excluded on security grounds.
3. **Revisit only** if a measured need appears for late-session pressure relief on
   payloads much larger than these, where an 86% reduction with CCR retrieval
   would beat truncation. That is a different problem from the injection budget,
   and it should be measured on that problem's own payloads.

This supersedes the Stage 2 recommendation in §5. §5's reasoning was sound —
compress where we own both ends — but it assumed headroom would do meaningful
work on these payloads. Measured, it mostly does not, and the part it does do
costs the structure.

---

## 6. One-line summary

Real tool, healthy project. The proxy is the wrong shape for us outright: it
would compress the very artifacts our gates parse literally, and both gates fail
open, so that damage would arrive as a quietly weaker audit trail rather than a
visible failure.

And measured (§7), the library path we did like turns out not to earn its keep
either. On 72% of real clean-rag search payloads headroom adds 0.4 points over
compacting our own JSON, a one-line change with no dependency; where it does win
it rewrites `results` into a CSV string and replaces the source code with
retrieval pointers, failing Stage 1's own retention gate. **Take the 11.8% from
compact JSON. Do not adopt headroom.**
