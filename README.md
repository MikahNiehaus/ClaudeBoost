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
| e2e-agent | End-to-end UI testing, structured test plans | Sonnet |

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

## How It Works

See [HOW-IT-WORKS.md](docs/HOW-IT-WORKS.md) for the full architecture, hook registration,
RAG pipeline, and session flow.

> **TTS:** `/speak` works on Windows and macOS. Linux is not supported.
