# ClaudeBoost — How It Works

ClaudeBoost is a multi-agent orchestration layer for Claude Code. It adds 25 specialist
agents, 106 knowledge files, a local semantic RAG + GraphRAG server, and 27 slash
commands — all wired together through hooks.

## Directory Layout

```
ClaudeBoost/
├── agents/              25 specialist agent definitions (XML)
├── knowledge/           106 knowledge files (XML)
│   ├── lang-*.xml       21 language guides
│   └── fw-*.xml         33 framework guides
├── mcp-rag-server/      HTTP RAG server on port 8612 (Python)
├── .claude/commands/    27 slash commands
├── scripts/             Setup, hooks, and maintenance scripts
├── docs/                Reference documentation
└── CLAUDE.md            Orchestration rules loaded globally
```

## The RAG Server

The RAG server is a Python HTTP service on port 8612. It runs as a subprocess
when Claude Code starts, and exposes a REST API used by Claude, hooks, and agents.
It holds two separate indexes:

| Index | What it holds | Location |
|-------|--------------|----------|
| **ClaudeBoost RAG** | `agents/*.xml` + `knowledge/*.xml` | `mcp-rag-server/.rag-index/` |
| **Project RAG** | A specific project's source code | `<project>/workspace/.rag-index/` |
| **Graph DB** | Code structure graph (imports, inheritance) | alongside Project RAG |

`POST /context` combines all of them — ClaudeBoost RAG supplies knowledge and agent
definitions, Project RAG supplies codebase context. Every spawned agent calls this
as its first action.

## RAG Modes

**Vector search** (`POST /search`, default `mode=vector`) uses sentence embeddings to
find semantically similar content. Use it to find the right knowledge file, locate
similar patterns in your codebase, or seed an agent's context package.

**Graph search** (`POST /search`, `mode=graph`) builds on vector search by expanding
structurally. It starts with vector-matched seed files, then follows import chains and
inheritance edges in `graph.db` to return every file connected to the seeds. This is
how code review and E2E test planning map the full scope of a change — not just what
semantically matches the query, but everything the matched code actually depends on
or is depended on by.

The graph index (`graph.db`) is built automatically alongside the vector index when
you run `/index-project` or `POST /index`. It degrades gracefully — if no `graph.db`
exists, graph mode falls back to vector results.

## Agents

25 specialist agents, each defined as an XML file in `agents/`. They are not scripts —
they are prompt definitions that the RAG server loads and injects via `POST /context`
when an agent is spawned.

**Model routing:**
- **Opus**: architect-agent, reviewer-agent, ticket-analyst-agent
- **Sonnet**: all others (escalation to Opus available mid-task on LOW confidence or BLOCKED)

**Weight routing:**
- **Full** (reviewer, security, performance): verify gate + evaluator-agent verification
- **Standard** (workflow, debug, test, refactor, ui, etc.): no verify gate overhead
- **Lightweight** (explore, research, docs, estimator, rag-indexing): minimal ceremony

## Knowledge Files

106 XML files in `knowledge/`, organized as:
- **Domain bases** (52): coding standards, security, architecture, debugging, testing,
  observability, performance, refactoring, UI implementation, API design, context
  engineering, verify gate, scope governance, rule enforcement, human voice standard,
  and more
- **Language guides** (`lang-*.xml`, 21): Python, TypeScript, C#, Go, SQL, Rust, Swift,
  Kotlin, Java, PHP, Ruby, and others
- **Framework guides** (`fw-*.xml`, 33): React, Next.js, ASP.NET Core, FastAPI, Django,
  Flask, Spring Boot, Rails, Flutter, and others

Language and framework files load automatically when their name appears in a spawn
prompt's task description — `"fix bug in TypeScript React component"` pulls both
`lang-typescript.xml` and `fw-react.xml`.

## Hooks

Six hook types, each implemented as one or more Python scripts in `scripts/`:

| Hook | Scripts | Purpose |
|------|---------|---------|
| **SessionStart** | `rag-session-reset.py`, `compaction-restore.py` | Clear RAG sentinel, restore handoff state after clear/compact |
| **PreToolUse** | `rag-read-guard.py`, `agent-spawn-gate.py`, `session-primer.py` | RAG gate before file reads, agent spawn enforcement, RAG sentinel check |
| **PostToolUse** | `context-nudge.py`, `spawn-nudge.py` | Nudge context.md updates, remind orchestrator to spawn evaluator |
| **PreCompact** | `pre-compact-save.py` | Save workspace state before compaction |
| **UserPromptSubmit** | `session-primer.py` | Inject HARD STOP if RAG sentinel is missing |
| **Stop** | `stop-hook.py` | Status line update on stop |

`agent-spawn-gate.py` enforces that every agent spawn prompt includes a `POST /context`
call. Spawns without it are blocked (exit 2). `rag-read-guard.py` blocks direct file
reads if RAG hasn't been called recently — it enforces the pattern of searching before
reading, not reading blindly.

## Slash Commands

27 commands in `.claude/commands/`. Key ones:

| Command | Purpose |
|---------|---------|
| `/boost` | Start a session — RAG up, hooks verified, mode set, workspaces restored |
| `/rag` | Start or reconnect the RAG server |
| `/index-project <path>` | Index a project's codebase for vector + graph search |
| `/index-boost` | Reindex ClaudeBoost agents and knowledge |
| `/graph <task>` | Build a Files in Scope map using vector + graph RAG |
| `/workspace <task>` | Create a workspace and implementation plan |
| `/review` | Quick A-F grade by default; add `--deep` for full 15-pass parallel review |
| `/end-to-end-test <url>` | Browser E2E tests with screenshot evidence |
| `/security-review` | OWASP-grounded security audit |
| `/self-improve` | ClaudeBoost self-audit — finds config, agent, and knowledge gaps |
| `/done` | Push completed work to remote |
| `/handoff` | Save session state for a fresh context |
| `/clear-safe` | Save state before clearing context (restored automatically on next `/boost`) |

## Session Flow

A typical session:

1. User runs `/boost` — RAG server starts, session is primed, active workspaces discovered
2. User pastes a ticket or describes a task
3. CLAUDE.md rules apply: simple tasks are done directly; complex tasks go through
   the workspace flow (workspace + sweep + agent delegation)
4. Agents spawn as needed; each calls `POST /context` first to load relevant knowledge
5. Findings are written to `workspace/<task>/context.md` as they accumulate
6. When done, user runs `/done` to push to remote

## Verify Gate (Anti-Hallucination)

Every finding from a review or audit must be proven from actual code before it reaches
the user. The protocol:

- Each finding needs a `file:line` citation
- A fresh evaluator-agent (Opus) reads only that citation — no session context
- UNVERIFIED findings are dropped; only CONFIRMED findings appear in the final report
- Hooks remind agents and the orchestrator to follow this protocol at every step

## Code Metrics Thresholds

Enforced by agent directives:

| Metric | Threshold |
|--------|-----------|
| Cyclomatic complexity | 10 max per method |
| Method length | 40 lines max |
| Class length | 300 lines max |
| Parameter count | 4 max |
| Nesting depth | 3 max |
