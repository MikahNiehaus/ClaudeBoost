# ClaudeBoost

**Created by Mikah Niehaus**

Claude knows how to code. ClaudeBoost knows how to do it right.

It loads security standards and testing methodology into every session, searches your
own indexed code before anything is written, and researches what is missing with cited
sources. Whatever you're building, whatever stack you're on — ClaudeBoost makes sure
Claude behaves like a senior engineer who already knows your domain.

## What It Does

AI can write code fast. That's never been the bottleneck. The bottleneck is what the code looks like six months later — unapproved tables, inconsistent patterns, security gaps, zero tests. Most AI tools make this worse by making the same low-quality code arrive faster.

ClaudeBoost fixes that by making Claude an instant expert on whatever you're working on. A custom RAG system, designed by Mikah Niehaus and running entirely on your CPU, loads exactly the right knowledge before a single line is written — security, testing, your stack, your project's own patterns. When domain knowledge is missing, it researches it and cites the source. When code changes, it maps the blast radius first. Every finding requires a `file:line` citation or it gets dropped. The goal isn't faster code — it's production-ready, thoroughly tested, maintainable code delivered correctly the first time.

The RAG server runs entirely locally. No external vector service. No API calls to embed
your code. Your codebase stays on your machine. Microsoft's GraphRAG costs around
$30,000 to index 5 GB of data. ClaudeBoost indexes the same on a CPU, for free.

### Built like infrastructure, not a script

| | |
|---|---|
| Retrieval server | 12,220 lines across 19 modules |
| Test suite | **606 tests, 15,339 lines, 57 files** |
| Test to source ratio | **1.25 to 1** |
| Adversarial suites | 10, covering resource limits, race conditions, provenance, metrics |
| Total Python | 39,109 lines |

More test code than production code. The largest single test file, 1,699 lines of
adversarial resource-limiting cases, is bigger than every source module in the server.
Search correctness here is not asserted, it is measured against external benchmarks and
defended by tests written to break it.

## What Makes the RAG Unique

Code retrieval that reaches roughly 93% of a model fine-tuned on millions of labeled
pairs, on a CPU, with no fine-tuning, no training data, and no cloud cost. Four
techniques get it there, and one of them is a result that does not appear in any
published retrieval paper.

The headline finding is not a leaderboard position. It is that document augmentation
and asymmetric encoding are structurally complementary, and siginj proves it with a
controlled sign flip: the same technique that lifts an asymmetric model measurably
*hurts* a symmetric one.

### Signature Injection (siginj)

Before embedding a code document at index time, the method signature is deterministically extracted and prepended to the full document text:

```
// what gets embedded — signature prepended to body
decimal CalculateTax(Order order, decimal rate)
public decimal CalculateTax(Order order, decimal rate) {
    return order.Subtotal * rate;
}
```

Cost: ~1ms per function at index time. Zero milliseconds at query time. No LLM, no inference, no hallucination risk.

**Results (CodeSearchNet 1K-pool):**
- C#: MRR 0.950, R@1 91.7% (BAAI/bge-base-en-v1.5 + siginj)
- Python: MRR 0.931, R@1 90.0% (BAAI/bge-base-en-v1.5 + siginj)

**Why this works — the asymmetric insight:** BGE-style models (BAAI/bge-base-en-v1.5) encode queries and documents using different instruction prefixes, placing them in different geometric subspaces. Enriching the document does not corrupt the query signal — they don't share a subspace. Document augmentation and asymmetric encoding are structurally complementary, not competing.

Confirmation: st-codesearch-distilroberta-base (symmetric model) scores 0.8928 with siginj — slightly *worse* than baseline (0.8979). The same technique that boosts bge-base by +3.3% hurts a symmetric model. This validates the subspace explanation empirically.

This observation does not appear in any published retrieval paper.

**How siginj differs from related techniques:**

| Technique | Mechanism | Cost |
|-----------|-----------|------|
| **Siginj** (this work) | Deterministic extraction + prepend at index time | ~1ms/function, zero query latency |
| HyDE / LLM-Augmented Retrieval | LLM generates synthetic queries or doc titles | LLM inference per document, can hallucinate |
| RouterRetriever (2409.02685) | Routes queries to expert retrievers at runtime | Requires router training, adds query latency |
| CodeXEmbed (2411.12644) | Trains one large multilingual model end-to-end | Requires GPU training on labeled pairs |
| MigGPT / HEF (2603.06593) | Signature extraction for LLM prompting or soft tokens | Different task: generation/soft-prompts, not dense retrieval |

### Per-Language Model Routing

A self-improving benchmark loop selects the best embedding model per language empirically, stores the winner in `best_model_config.json`, and routes all indexing and queries accordingly. No training, no router model — selection happens once at benchmark time, routing is free at runtime.

This is different from RouterRetriever, which selects models at query time using a trained router. ClaudeBoost selects at configuration time using empirical benchmarks — zero query overhead, no training required.

### Real Code Structure Graph (not LLM-synthesized)

ClaudeBoost builds an import and inheritance graph from tree-sitter AST parsing during indexing — the same single pass that produces chunks. No LLM, no synthesized edges, no hallucinated relationships. Graph search expands vector results to all structurally connected files via reciprocal rank fusion with PageRank weighting.

Microsoft's full GraphRAG synthesizes graph edges from unstructured text using LLMs (~$33K for 5 GB in 2024). ClaudeBoost's graph is free, deterministic, and zero-hallucination.

### Provenance-Checked Vectors

A vector index only means anything to the model that produced it. Two different
embedding models can both emit 768 dimensions and still place the same code in
completely different regions of space, so querying one model's index with another
model's vectors returns confident nonsense with no error and no warning.

ClaudeBoost records which embedder produced each project's vectors and refuses to serve
a search when the current embedder does not match, rather than returning results that
look fine and are meaningless. Most retrieval stacks have no answer for this failure at
all, because nothing about it looks like a bug.

### Rank Fusion Across Two Incompatible Scales

Vector search returns cosine similarity. The graph walk returns edge strength. The two
numbers are not comparable, so ClaudeBoost fuses them by rank rather than by score,
using reciprocal rank fusion at k=60.

The graph side is a personalized PageRank seeded by the vector hits themselves, not by
chat history the way standard GraphRAG does it. On deep traversals the frontier is
ranked by PageRank before expanding, which keeps a hub file with 400 importers from
swallowing the entire result set.

---

## What's Inside

```
ClaudeBoost/
├── clean-rag/               Search server on port 8613, hooks, installer
│   ├── server/              HTTP routes, indexing, vector and graph search
│   ├── hooks/               Research gate, verifier gate, auto test gate
│   └── portable/            What the installer ships
│       ├── agents/          Agent definitions (markdown)
│       ├── skills/          Skills
│       └── CLAUDE.md        Orchestration rules, installed to ~/.claude/CLAUDE.md
├── .claude/commands/        Slash commands
├── scripts/                 Setup, hooks, and maintenance scripts
├── benchmarks/              CodeSearchNet results
└── docs/                    Reference documentation
```

## Quick Start

### 1. Install

**macOS / Linux:**

```bash
cd <path-to-ClaudeBoost>
./install.sh
```

**Windows:**

```powershell
cd <path-to-ClaudeBoost>
.\install.bat
```

`scripts/setup.py` handles the rest — registers hooks globally, sets CLAUDEBOOST_HOME,
starts the RAG server, and links all slash commands.

**The install builds clean-rag its own virtualenv, and you need it.** The
embedding stack (torch, transformers, sentence-transformers) goes into
`clean-rag/clean-rag-venv/`, never onto your global interpreter, and the server
is launched with that venv's Python. Expect the download to be a few hundred
megabytes and to be the slowest part of the install. The venv is built per
machine and is gitignored, so a fresh clone has to run the installer before
search or indexing will work.

Two consequences worth knowing:

- If you see `[warn] clean-rag-venv not found`, the venv is missing and the
  server has fallen back to whatever interpreter launched it. Run
  `python clean-rag/install.py` to build it.
- The three embedding packages are pinned exactly in
  `clean-rag/requirements.txt`, not ranged. They have to agree on versions with
  each other, and a range let them drift apart until every embedding load failed.
  Bump them together or not at all.

### Uninstall

`uninstall.sh` / `uninstall.bat` (or the `/uninstall` slash command) reverse `setup.py`.
Preview first, it changes nothing:

```bash
./uninstall.sh --dry-run        # macOS / Linux  (.\uninstall.bat --dry-run on Windows)
```

Then remove. The default scope touches only ClaudeBoost's own footprint and is fully
reversible by re-running `install.sh`:

```bash
./uninstall.sh                  # removes CB hooks, env, statusLine, permission entries,
                                # the ~/.claude symlinks/helpers, the rag-server MCP
                                # entry; stops the RAG server. Asks before applying.
```

Add `--purge` to also pip-uninstall `rag-server`, delete the RAG index, strip the
netcoredbg PATH line, and deregister the shared MCP servers (mcp-debugger, playwright):

```bash
./uninstall.sh --purge
```

It never deletes the repo folder, a `~/.claude/CLAUDE.md` you wrote, slash commands you
added yourself, or shared ML deps. Restart open Claude Code sessions afterward so they
drop the removed hooks and commands.

### 2. Use It

Open any project in Claude Code and run `/boost`. That starts the RAG server, primes
the session, and shows recent workspaces. From there:

```
/boost                   Start a session
/ws                      Show all workspaces for this project — description + last edited
/index-project           Index your codebase for semantic search
/workspace <task>        Create a workspace + implementation plan
/xray                    Quick A-F grade by default; add --deep for full 16-pass parallel review
/qa                      Full QA session — app inventory, risk-based test plan, screenshot evidence
/security-review         OWASP-grounded security audit
```

The search server, clean-rag, exposes an HTTP API at `http://127.0.0.1:8613`.
Start it with `/clean-rag-server start`.

| Endpoint | What it does |
|----------|-------------|
| `POST /search` | Vector and graph search over indexed projects. `sources: ["project:<abs path>"]`, `mode: "both"` |
| `POST /index-project` | Index a project. `{"project_path": "<abs path>"}` |
| `GET /status` | Server health and every registered project |
| `POST /web-search` | Live web search, GitHub and StackOverflow ranked first |

`clean-rag/CLAUDE.md` has the full route table.

## Features

### Local RAG + GraphRAG

Two search modes, both running on your machine:

**Vector search** (`mode=vector`, default) finds semantically similar content. Use it
to find similar patterns in your codebase or seed an agent's context.

**Graph search** (`mode=graph`) builds a structural code graph from your project's
import chains and inheritance relationships. When you query in graph mode, it finds
vector-matched seed files and then expands to all files that import, inherit from, or
are imported by those seeds. Code review and E2E test planning use this to map the full
blast radius of a change — not just what the query matches, but everything connected to it.

The graph index lives in `graph.db` alongside each project's vector index. It's built
automatically when you run `/index-project`. No configuration needed.

### Multi-Agent Orchestration

Simple tasks run directly. Complex tasks get decomposed and delegated to specialist
agents:

**Model routing** — good-cop runs on Opus. bad-cop, quick-cop, research-agent,
researcher and swiper run on Sonnet. The agent table below says what each does.

**Weight routing** — full ceremony (verify gate + evaluator verification) for review,
security, and performance agents; standard for implementation work; lightweight for
exploration and research.

**Parallel limits** — up to 3 agents in parallel below 50% context; 2 from 50–75%; 1
above 75%.

### Agent RAG Usage

Agents search the project index themselves with `POST /search`. No hook forces it.
The research gate checks that `researcher` or `swiper` covered a file before it is
edited, and it nudges rather than blocks. The search rules:

**Vector search (`mode=vector`)** — called before writing any code to find existing
patterns, utilities, or similar implementations. Prevents duplication.

**Graph search (`mode=graph`)** — called before changing any file to map its callers
and importers. Every agent that touches code knows the blast radius before touching
anything.

`bad-cop` runs a Caller Impact pass: it graph-searches every changed file and
checks each caller for silent breakage. A change that looks clean in isolation
but breaks a caller is flagged Critical.

### Code Review

`/xray` gives you a quick A–F grade by default. Add `--deep` for the full 16-pass
parallel review: a deterministic pre-scan (grep patterns for closure-scope timers, template
secret rendering, and loading states with no exit) runs first, then 15 passes run in parallel
(logic, security, performance, test coverage, dead code, debug artifacts, banned patterns,
project pattern consistency, caller impact, ticket alignment, async pattern audit, and template
rendering security), then quick-cop runs last in a fresh context.
Every finding needs a `file:line` citation or it gets dropped.

Scope flags: `--staged`, `--branch`, `--pr <url>`.

`/security-review` focuses the full depth of the security pass on just security findings,
with `--full` for a whole-project audit.

### QA Sessions

`/qa <url>` runs a full QA session against a localhost app:

1. **App discovery** — Playwright snapshot crawl + RAG codebase search to build a
   component registry and app map
2. **Test plan generation** — equivalence partitioning and boundary values; quick-cop
   removes unverified test cases; you approve the plan before execution starts
3. **Test execution** — browser-only tools only (no DB queries, no API bypasses);
   annotated screenshots saved for every PASS; honest FAIL written for every failure
4. **Report** — written to `workspace/<task>/report.md` with screenshots in `snapshots/`

Anti-cheat: the skill blocks itself from fabricating PASS results. If a UI assertion
fails, the output says FAIL. Playwright is localhost-only — staging and production URLs
hard-stop the skill.

### Debugging

For step-through debugging, Claude uses the built-in MCP debugger integration (not
`print()` statements):

```
"set a breakpoint at line 42"
"step through this function"
"what's the value of X when it hits the auth check"
```

This maps to `mcp-debugger` tools — create session, set breakpoint, continue, inspect
variables, step over/into/out. Works for Python, Node.js, TypeScript, Go, Rust, Java,
and C#. Run `/debug` for a complex debugging session, and invoke the
`debugging-methodology` skill when one technique stops producing new
information.

### Verify Gate (Anti-Hallucination)

Every finding from a review or audit agent must be proven from actual code before it
reaches you. The protocol:

- Each finding needs a `file:line` citation
- A fresh quick-cop reads only that citation — no session context — and returns
  CONFIRMED or UNVERIFIED
- UNVERIFIED findings are dropped before the report is written
- Hooks nudge the orchestrator to spawn quick-cop; agents self-report confidence
  levels (HIGH / MEDIUM / LOW) and the orchestrator escalates on LOW
- Every gate here nudges. None of them refuses the work. The one exception is
  `auto-test-gate.py`, which blocks on a real test failure, because a failing
  test is an objective fact and a review verdict is a judgement call

"No issues found" is always a valid outcome. Finding something is not the goal.
Finding real things is.

### CONSULT / AUTO Mode

Default mode is **CONSULT**. Before any architectural decision (new endpoint, new table,
new dependency, new module), Claude researches and proposes options — grounded in your
actual codebase — then waits for your input. You approve, adjust, or write in a new
option. The decision is logged so Claude doesn't re-ask about the same axis in the
same session.

`/auto` disables consultation and lets Claude proceed autonomously. `/consult` restores
the default.

### There is no topic knowledge base, and that was deliberate

An earlier version of this project shipped a scraped topic knowledge base: dozens
of documentation sets searchable as one corpus. It was deleted, along with the
second server that hosted it. Do not rebuild it.

It went because **it confidently returned wrong answers and no score threshold
caught them.** Measured, not guessed:

| Query | What came back | Score |
|---|---|---|
| "is it done" | Azure Functions `context.done()` docs | 0.82 |
| "duck duck go" | react-query docs, then PCMag browser reviews | 0.80 |
| a function containing a SQL injection | Go stack trace docs | 0.86 |
| `MAX_RETRIES = 5` | PowerShell retry docs | 0.86 |

`min_score: 0.5` caught none of it. Two things follow, and both were believed
false until measured. Vector search does not degrade gracefully: a keyword soup
query embeds into something, and something is always nearby. And embedding
search retrieves text resembling your query, never a critique of it, so feeding
it SQL-injecting code returns more SQL code rather than the vulnerability
warning.

Retrieval therefore moved to the only thing that can write a decent query: a
reasoning agent. The project index stayed, because a hit there is a real file
you can open and check.

Full reasoning in `clean-rag/CLAUDE.md`, under "Why the KB is gone".

### Project research notes

A project can accumulate research notes under `.claudeboost/knowledge/`, written
by the research agents as markdown, one file per source they read.

These are **notes to read, not a search corpus.** They are not a registered
project, so a `project:` source naming that directory returns nothing. The
session primer injects the path for exactly this reason: open the files, do not
search them.

Two claims that used to appear here and are not true. `research-agent` cannot
write them: its tools are `WebSearch, WebFetch, Bash, Grep, Glob, Read`, with no
`Write` and no `Edit`, which is the deliberate defence against a prompt
injection in the web content it reads. And there is no `triage-agent` deciding
whether a change needs research; that agent was removed because it made that
call without reading the code. Skipping research on a genuinely trivial turn is
the human's call, made with `/ps`.

## Agents

Six pipeline agents, installed into `~/.claude/agents/` from
`clean-rag/portable/agents/`. The installer copies every file in that directory, so
a helper agent that a skill ships lands there too. Check with `ls ~/.claude/agents`.

| Agent | Specialty | Model |
|-------|-----------|-------|
| researcher | Understands the codebase and the general engineering standard for a change. Runs the project index, vector search and the import graph. No `Write`, no `Edit` | Sonnet |
| swiper | Finds working code to take instead of writing it: the project, the stdlib, a dependency, GitHub, StackOverflow. Reports it, never writes it | Sonnet |
| research-agent | Web and codebase investigation. Tools are `WebSearch, WebFetch, Bash, Grep, Glob, Read`; its Bash is caged to the local clean-rag server | Sonnet |
| bad-cop | Adversarial QA. Writes tests aimed at breaking a change and runs them. Reports only, fixes nothing. Also judges a finished QA session's artifacts with `MODE: evidence-judge` | Sonnet |
| good-cop | Runs only on a Critical or High from bad-cop. Researches the root cause, applies the fix, gets everything green | Opus |
| quick-cop | Claim checker. Reads the code and says whether a finding or an "it is done" claim is true. Non blocking, stamps nothing | Sonnet |

Claude Code's own built-ins (`Explore`, `Plan`, `general-purpose`) are available
alongside these.

**This table used to list 23 agents.** Eighteen of them, including
`architect-agent`, `reviewer-agent`, `debug-agent`, `security-agent` and
`evaluator-agent`, have never existed in this repo and cannot be spawned. Read
any older reference to one of those names as aspirational, not as a feature.
There is no `agents/` directory at the root and no agent defined in XML.

## Slash Commands

Commands organized by workflow:

**Session & Setup**
`/boost` `/clean-rag-server` `/rag-health` `/uninstall` `/index-project`

**Planning & Workspace**
`/ws` `/workspace` `/create-prd` `/explore` `/graph`

**Code Quality**
`/xray` `/security-review` `/audit` `/self-improve`

**Debugging**
`/debug`

**Testing**
`/qa` `/test-hooks`

**Git & Workflow**
`/done` `/pr-description` `/changes` `/handoff` `/clear-safe` `/ticket-handoff`

**Configuration**
`/auto` `/consult` `/bash-guard` `/speak` `/edit-state` `/telemetry`

**Documentation & Visualization**
`/visualize`

**Built into Claude Code, not shipped by this repo**
`/init` `/simplify`

## Benchmarks

Two test suites evaluate the RAG system. One uses the actual CodeSearchNet dataset.
The other tests ClaudeBoost's domain-specific retrieval.

### CodeSearchNet Benchmark (external dataset)

Both tests use real data from the CodeSearchNet Python test set (Husain et al. 2019,
arxiv:1909.09436) — the same dataset used to evaluate CodeBERT, GraphCodeBERT, and
other code retrieval systems.

#### Official 1K-pool protocol

`test_codesearchnet_multilang.py` — full corpus per language, all queries,
1 correct + 999 random distractors per query. Uses the same 1K-pool evaluation
protocol (Husain et al. 2019). Docstrings are stripped before embedding so the
model retrieves on function semantics, not text overlap.

Per-language model routing: a self-improving benchmark loop selects the best embedding
model and preprocessing strategy per language automatically. Models run on CPU with GPU
acceleration when available (CUDA auto-detected).

#### Multi-language benchmark

Seven languages. No per-language fine-tuning in the base model.

> **Read the protocol before reading the numbers.** The MRR column below is the 1K-pool
> protocol: one correct answer against 999 random distractors. The CodeBERT and
> GraphCodeBERT columns are their published figures, which come from the harder
> full-corpus setting where the answer is retrieved from the entire test corpus. The two
> protocols are not directly comparable, and the larger the candidate pool the harder the
> task, so a "+0.162" here is not a like-for-like win.
>
> For the honest apples-to-apples number, see
> `benchmarks/codesearchnet/results/full_benchmark.json`: on the full 22,176 function
> Python corpus this system scores **MRR 0.6438**, against GraphCodeBERT's published
> 0.692. It does not beat a fine-tuned model on equal footing. It reaches roughly 93% of
> one, on a CPU, with zero training. That is the result worth quoting.

| Language | N (corpus) | MRR (1K-pool) | R@1 | R@5 | CodeBERT (full corpus) | GraphCodeBERT (full corpus) | Note |
|----------|-----------|-----|-----|-----|----------|----------------|--------|
| Python | 21,544 | **0.931** | 90.0% | 97.0% | 0.713 | 0.769 | higher on 1K-pool, not comparable |
| JavaScript | 6,483 | **0.748** | 68.8% | 81.7% | 0.629 | 0.674 | higher on 1K-pool, not comparable |
| Java | 26,909 | **0.850** | 81.6% | 88.9% | 0.719 | 0.769 | higher on 1K-pool, not comparable |
| Go | 14,291 | **0.839** | 81.1% | 86.5% | 0.921 | 0.897 | below fine-tuned models |
| Ruby | 2,279 | **0.738** | 66.2% | 83.2% | 0.678 | 0.703 | higher on 1K-pool, not comparable |
| PHP | 28,391 | **0.850** | 81.7% | 88.7% | 0.630 | 0.649 | higher on 1K-pool, not comparable |
| C# | 5,261 | **0.950** | 91.7% | — | N/A | N/A | synthetic corpus; bge-base + siginj |

Python, JavaScript, Java, Ruby, and PHP all score higher than GraphCodeBERT's published
figures, on an easier protocol, so treat that as encouraging rather than as a win. Go is competitive — 0.839 vs GraphCodeBERT's 0.897 with no
language-specific fine-tuning.

C# uses a synthetic corpus from open-source GitHub repos (Newtonsoft.Json, AutoMapper,
Polly, etc.) since CodeSearchNet has no official C# split. BAAI/bge-base-en-v1.5 with
signature injection (siginj) reaches MRR 0.950 and R@1 91.7% — the method signature
is deterministically extracted and prepended to the document at index time, taking
~1ms per function with zero query overhead.

Preprocessing: function name prepended before code for all non-Python languages (S6
strategy); Python and C# use siginj — the full `def name(params) -> return:` signature
is AST-extracted and prepended to the stripped function body at index time. Siginj works
on asymmetric models (BGE family) where instruction prefixes place queries and documents
in separate geometric subspaces; document enrichment improves retrieval without
corrupting query signals. All strategies were found by an automated improvement loop.

#### Multi-domain documentation benchmark (BEIR)

`test_beir_documentation.py` — six documentation domains from the BEIR suite
(Thakur et al. 2021). Tests whether the same model works on non-code text.

| Dataset | Domain | N passages | NDCG@10 | BM25 | TAS-B | Status |
|---------|--------|-----------|---------|------|-------|--------|
| FIQA | Financial Q&A | 57,600 | **0.369** | 0.236 | 0.300 | BEATS TAS-B +0.069 |
| SciFact | Scientific claims | 5,183 | **0.645** | 0.665 | 0.643 | BEATS TAS-B +0.002 |
| NFCorpus | Medical / nutrition | 3,633 | **0.317** | 0.325 | 0.321 | near BM25 |
| ArguAna | Argumentation | 8,674 | **0.370** | 0.315 | 0.429 | beats BM25 +0.055 |
| TREC-COVID | Biomedical research | 171,331 | **0.454** | 0.656 | 0.481 | below BM25 (expected) |
| HotpotQA | Multi-hop Wikipedia | 5.2M | (run with -m slow) | 0.603 | 0.584 | large corpus |

First run downloads each dataset from HuggingFace and caches embeddings. Subsequent
runs complete in seconds. TREC-COVID and HotpotQA are large; use `-k "not hotpotqa"`
to skip the 5M-passage dataset for routine runs.

#### Quick smoke-test

`test_codesearchnet_benchmark.py` — 200 Python functions from the real test set indexed,
queries are the actual natural-language docstrings. Docstrings stripped before indexing
(same clean eval protocol as the 1K-pool test). Runs in ~5 minutes, good for CI.

| Metric | Score |
|--------|-------|
| Recall@1 | 69.5% |
| Recall@5 | 91.5% |
| MRR | 0.789 |

Scores are lower than the 1K-pool numbers: the 200-function corpus is a coherent cluster
of video-download and pipeline functions with many similar docstrings, making retrieval
harder than a pool with random distractors. Use the 1K-pool test for leaderboard comparison.

### Domain Quality Tests (ClaudeBoost-specific)

These figures were measured on the retired 8612 server by a 64 test suite that was
deleted with it, so nothing in the tree reproduces them today. It checked the old
knowledge base and codebase retrieval using domain-specific ground-truth pairs.
Metric formulas follow BEIR (Recall@k), MTEB (nDCG@5, MRR), and GraphRAG-Bench
(structural neighbour retrieval). The query/source pairs are ClaudeBoost-specific,
not from the original benchmark datasets.

**Results (64/64 passing):**

| Metric | Score |
|--------|-------|
| Recall@1 | 79% |
| Recall@3 | **97%** |
| Recall@5 | **100%** |
| nDCG@5 | **0.899** |
| MRR | 0.865 |

### Three tiers

The retired domain test suite checked each layer of the RAG stack:

**Tier 1 — Vector only**: 34 queries across knowledge files, agent definitions, and codebase.
Embedding similarity alone. Recall@5 = 100%.

**Tier 2 — Normal indexing (vector + graph)**: `/index-project` builds both the vector
index and the import-chain graph in one pass. Tests confirm the embedding pipeline and
edge extraction are both healthy: seed file + structural import-chain neighbour retrieved
at 100% hit rate.

**Tier 3 — `/graph` skill**: Entity extraction from a task description + multi-hop graph
traversal. Surfaces files the basic search misses. The skill added files beyond
single-entity vector search in 3/3 cases (100% gap-fill rate).

### Run it yourself

You cannot, as things stand. Every benchmark test named in this section lived under
`mcp-rag-server/tests/`, which was deleted with the 8612 server. The recorded
results are in `benchmarks/codesearchnet/results/`. The harness in
`benchmarks/codesearchnet/` still defaults to the retired 8612 server and needs
porting to clean-rag on 8613 before it runs again.

### How the 1K-pool numbers were produced

The official protocol: CodeSearchNet test splits from HuggingFace
(`code-search-net/code_search_net`, CC BY-4.0), one correct answer against 999
random distractors per query. The recorded Python run is below.

**Recorded output (Python, with model routing active):**

```
CODESEARCHNET 1K-POOL BENCHMARK (Python)
Official protocol — Husain et al. 2019 (arxiv:1909.09436)
================================================================
  Model:    flax-sentence-embeddings/st-codesearch-distilroberta-base
  Corpus:   21,544 Python functions (full test set)
  Queries:  21,544 (full corpus)
  Pool:     1000 per query (1 correct + 999 random distractors)

  Metric        ClaudeBoost        NBOW    CodeBERT   GraphCodeBERT   UniXcoder
  --------------------------------------------------------------------------
  Recall@1         83.0%           ~38%       ~59%           ~68%       ~72%
  Recall@5         94.1%           ~65%       ~85%           ~90%       ~92%
  Recall@10        96.2%           ~75%       ~90%           ~94%       ~95%
  MRR              0.898          0.510      0.713          0.769      0.791
```

**What makes this fair:** Docstrings are stripped from the code before
embedding. The model retrieves on function semantics, not literal text overlap.
The 1K random distractor pool matches the protocol used to produce the published
CodeBERT/GraphCodeBERT numbers.

**How model routing works:** A self-improving benchmark loop evaluates multiple
models and preprocessing strategies per language, then writes the best
configuration to `best_model_config.json`. All models run on CPU with no per-language fine-tuning beyond
the pre-trained weights.

## How It Works

See [CLAUDEBOOST-REFERENCE.md](docs/CLAUDEBOOST-REFERENCE.md) for the full architecture, hook registration,
RAG pipeline, and session flow.

> **TTS:** `/speak` works on Windows and macOS. Linux is not supported.
