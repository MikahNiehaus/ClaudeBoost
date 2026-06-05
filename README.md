# ClaudeBoost

Multi-agent orchestration layer for Claude Code. 25 specialist agents, 106 knowledge
files, a local semantic RAG + GraphRAG server, and 44 slash commands — all wired
together through hooks.

## What It Does

ClaudeBoost turns Claude Code into a production-grade engineering assistant. Instead of
one general-purpose model handling everything, it routes work to specialist agents,
loads the right knowledge for each task, and enforces anti-hallucination checks before
any finding reaches you.

The RAG server runs entirely locally. No external vector service. No API calls to embed
your code. Your codebase stays on your machine.

## What's Inside

```
ClaudeBoost/
├── agents/              25 specialist agent definitions (XML)
├── knowledge/           106 knowledge files (XML)
│   ├── lang-*.xml       21 language guides
│   └── fw-*.xml         33 framework guides
├── mcp-rag-server/      HTTP RAG server on port 8612 (Python)
├── .claude/commands/    44 slash commands
├── scripts/             Setup, hooks, and maintenance scripts
├── CLAUDE.md            Orchestration rules (loaded globally)
└── docs/                Reference documentation
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

### 2. Use It

Open any project in Claude Code and run `/boost`. That starts the RAG server, primes
the session, and shows active workspaces. From there:

```
/boost                   Start a session
/index-project           Index your codebase for semantic search
/workspace <task>        Create a workspace + implementation plan
/code-review             14-pass parallel code review
/end-to-end-test         Browser E2E tests with screenshot evidence
/security-review         OWASP-grounded security audit
```

The RAG server exposes an HTTP API at `http://127.0.0.1:8612`:

| Endpoint | What it does |
|----------|-------------|
| `POST /context` | Load agent identity + relevant knowledge + codebase context |
| `POST /search` | Semantic search (knowledge, agents, or codebase) |
| `POST /index` | Index a project's source code |
| `GET /status` | Server health + collection sizes |

Agents call `POST /context` as their first action on every spawn. That's what makes
knowledge loading automatic rather than manual.

## Features

### Local RAG + GraphRAG

Two search modes, both running on your machine:

**Vector search** (`mode=vector`, default) finds semantically similar content. Use it
to locate the right knowledge file, find similar patterns in your codebase, or seed an
agent's context.

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

**Model routing** — three agents always run on Opus (architect, reviewer,
ticket-analyst). Everything else runs on Sonnet. Opus can be escalated mid-task when
an agent reports low confidence or gets blocked.

**Weight routing** — full ceremony (verify gate + evaluator verification) for review,
security, and performance agents; standard for implementation work; lightweight for
exploration and research.

**Parallel limits** — up to 3 agents in parallel below 50% context; 2 from 50–75%; 1
above 75%.

### Code Review

`/code-review` runs 14 parallel passes against your staged changes or branch:

- Logic, edge cases, off-by-one errors
- Security (OWASP top 10, injection, auth bypass)
- Performance (N+1 queries, missing indexes, blocking I/O)
- Test coverage and missing assertions
- Dead code, debug artifacts, banned patterns
- Project pattern consistency
- Ticket alignment
- And more

Passes run in parallel, batched in groups of 3. The evaluator-agent (Opus) runs last in
a fresh context — no confirmation bias. Every finding needs a `file:line` citation or
it gets dropped. Output is a letter grade (A–F) with BLOCKERS, WARNINGS, and NITS.

`/review` gives a structured review of any code. `/security-review` focuses the full
depth of the security pass on just security findings, with `--full` for a whole-project
audit.

### E2E Testing

`/end-to-end-test <url>` runs structured browser testing against a localhost app:

1. **App discovery** — Playwright snapshot crawl + RAG codebase search to build a
   component registry and app map
2. **Test plan generation** — equivalence partitioning and boundary values; evaluator-agent
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
and C#. Spawn `debug-agent` for complex debugging sessions; it has the full workflow
built in.

### Verify Gate (Anti-Hallucination)

Every finding from a review or audit agent must be proven from actual code before it
reaches you. The protocol:

- Each finding needs a `file:line` citation
- A fresh evaluator-agent reads only that citation — no session context — and returns
  CONFIRMED or UNVERIFIED
- UNVERIFIED findings are dropped before the report is written
- Hooks nudge the orchestrator to spawn the evaluator; agents self-report confidence
  levels (HIGH / MEDIUM / LOW) and the orchestrator escalates on LOW

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

### Knowledge Bases

106 XML files loaded automatically by the RAG server:

- **52 domain bases**: coding standards, security (OWASP), architecture, debugging,
  testing, observability, performance, refactoring, API design, context engineering,
  scope governance, rule enforcement, and more
- **21 language guides**: Python, TypeScript, C#, Go, SQL, Rust, Swift, Kotlin, Java,
  PHP, Ruby, and others
- **33 framework guides**: React, Next.js, ASP.NET Core, FastAPI, Django, Flask,
  Spring Boot, Rails, Flutter, and others

Language and framework files load automatically when their name appears in a spawn
prompt. `"fix bug in TypeScript React component"` pulls both `lang-typescript.xml` and
`fw-react.xml`.

## Agents

| Agent | Specialty | Model |
|-------|-----------|-------|
| architect-agent | System design, SOLID principles, DDD | Opus |
| reviewer-agent | Code review, verify gate | Opus |
| ticket-analyst-agent | Requirements analysis | Opus |
| debug-agent | Root cause analysis, step-through debugging | Sonnet |
| test-agent | Testing strategy, TDD | Sonnet |
| security-agent | Security auditing, OWASP | Sonnet |
| performance-agent | Performance profiling, optimization | Sonnet |
| refactor-agent | Code refactoring | Sonnet |
| ui-agent | Frontend, accessibility | Sonnet |
| docs-agent | Documentation | Sonnet |
| research-agent | Web and codebase investigation | Sonnet |
| research-rag-agent | Build persistent research RAG from URLs/PDFs | Sonnet |
| explore-agent | Code exploration, fast file/symbol search | Sonnet |
| browser-agent | Playwright browser automation | Sonnet |
| e2e-agent | Structured E2E testing with screenshot evidence | Sonnet |
| workflow-agent | Complex multi-step workflows | Sonnet |
| compliance-agent | Compliance auditing | Sonnet |
| evaluator-agent | Independent output verification | Sonnet |
| standards-validator-agent | Standards validation | Sonnet |
| estimator-agent | Story pointing | Sonnet |
| devops-agent | CI/CD, Docker, deployment | Sonnet |
| database-agent | Schema design, queries, migrations | Sonnet |
| observability-agent | Logging, metrics, alerting | Sonnet |
| rag-indexing-agent | RAG index health and filtering | Sonnet |

## Slash Commands

44 commands organized by workflow:

**Session & Setup**
`/boost` `/rag` `/setup` `/index-project` `/index-boost` `/list-agents`

**Planning & Workspace**
`/workspace` `/create-prd` `/plan-task` `/explore` `/research-task` `/research-rag`
`/graph` `/agent-status`

**Code Quality**
`/code-review` `/review` `/security-review` `/audit` `/gate` `/simplify`

**Testing**
`/end-to-end-test` `/test-hooks`

**Git & Workflow**
`/done` `/pr-description` `/commit-message` `/changes` `/handoff` `/clear-safe`
`/restore` `/compact-review`

**Configuration**
`/auto` `/consult` `/set-mode` `/set-permissions` `/set-global-permissions`
`/speak` `/statusline`

**Debugging & Maintenance**
`/self-improve` `/dependency-update` `/visualize` `/check-task` `/check-completion`
`/spawn-agent` `/mcp-builder`

**Documentation**
`/update-docs` `/init` `/generate-agents-md`

## Benchmarks

Two test suites evaluate the RAG system. One uses the actual CodeSearchNet dataset.
The other tests ClaudeBoost's domain-specific retrieval.

### CodeSearchNet Benchmark (external dataset)

`mcp-rag-server/tests/test_codesearchnet_benchmark.py` runs against the actual
CodeSearchNet Python test set (Husain et al. 2019, arxiv:1909.09436) — the same
dataset used to evaluate CodeBERT, GraphCodeBERT, and other code retrieval systems.

200 Python functions from the real test set are indexed. Queries are the actual
natural-language docstrings from those functions. Metrics match the paper's protocol.

**Official 1K-pool protocol** (`test_codesearchnet_1k_pool.py`) — full 21,544-function
corpus, 500 queries, 1 correct + 999 random distractors per query. Directly comparable
to published leaderboard numbers.

| Metric | ClaudeBoost | NBOW | CodeBERT | GraphCodeBERT |
|--------|-------------|------|----------|---------------|
| Recall@1 | **96.8%** | ~38% | ~59% | ~68% |
| Recall@5 | **99.4%** | ~65% | ~85% | ~90% |
| Recall@10 | **99.8%** | ~75% | ~90% | ~94% |
| MRR | **0.981** | 0.510 | 0.713 | 0.769 |

Model: `sentence-transformers/all-MiniLM-L6-v2` (same model used for all RAG retrieval).
Baselines from Husain et al. 2019 and follow-up work. all-MiniLM-L6-v2 is a
general-purpose model; CodeBERT and GraphCodeBERT were fine-tuned specifically on
code-docstring pairs, so this comparison shows what a general-purpose embedding achieves.

**Quick smoke-test** (`test_codesearchnet_benchmark.py`) — 200-function corpus, runs in
~4 minutes, good for CI. Recall@1=95.0%, Recall@5=99.5%, MRR=0.972 (smaller pool means
higher absolute scores — use the 1K-pool test for leaderboard comparison).

### Domain Quality Tests (ClaudeBoost-specific)

`mcp-rag-server/tests/test_rag_quality.py` (64 tests) verifies ClaudeBoost's
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

The domain test suite checks each layer of the RAG stack:

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

```bash
# Domain quality tests (fast, ~90s):
pytest mcp-rag-server/tests/test_rag_quality.py -v -s

# CodeSearchNet quick smoke-test (200-function corpus, ~4 min):
pytest mcp-rag-server/tests/test_codesearchnet_benchmark.py -v -s

# CodeSearchNet official 1K-pool benchmark (first run ~10 min, cached runs ~30s):
pytest mcp-rag-server/tests/test_codesearchnet_1k_pool.py -v -s
```

## How It Works

See [HOW-IT-WORKS.md](docs/HOW-IT-WORKS.md) for the full architecture, hook registration,
RAG pipeline, and session flow.

> **TTS:** `/speak` works on Windows and macOS. Linux is not supported.
