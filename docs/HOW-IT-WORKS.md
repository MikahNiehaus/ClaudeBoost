# ClaudeBoost — How It Works

ClaudeBoost is a multi-agent orchestration layer for Claude Code. It adds 25 specialist
agents, 96 knowledge files, a semantic RAG server, and 41 slash commands — all wired
together through hooks.

## Directory Layout

```
ClaudeBoost/
├── agents/              25 specialist agent definitions (XML)
├── knowledge/           96 knowledge files (XML)
│   ├── lang-*.xml       17 language guides
│   └── fw-*.xml         33 framework guides
├── mcp-rag-server/      RAG HTTP server (Python, port 8612)
├── .claude/commands/    41 slash commands
├── scripts/             Setup and maintenance scripts
├── docs/                Reference documentation
└── CLAUDE.md            Orchestration rules loaded globally
```

## The RAG Server

The RAG server runs as an MCP subprocess on port 8612. It has two separate indexes:

| Index | What it holds | Location |
|-------|--------------|----------|
| **ClaudeBoost RAG** | `agents/*.xml` + `knowledge/*.xml` | `mcp-rag-server/.rag-index/` |
| **Project RAG** | A specific project's source code | `<project>/workspace/.rag-index/` |
| **Graph DB** | Code structure graph (imports, inheritance) | alongside Project RAG |

`POST /context` combines both — ClaudeBoost RAG for knowledge, Project RAG for codebase
context. This is the first call every spawned agent makes.

## Agents

25 specialist agents, each defined as an XML file in `agents/`. They are not
scripts — they are prompts loaded by the RAG server and injected via `POST /context`
when an agent is spawned.

Model routing:
- **Opus**: architect-agent, reviewer-agent, ticket-analyst-agent
- **Sonnet**: all others

Agent weight routing:
- **Full** (reviewer, security, performance): verify gate + evaluator-agent
- **Standard** (workflow, debug, test, refactor, ui, etc.): no verify gate
- **Lightweight** (explore, research, docs, estimator, rag-indexing): minimal ceremony

## Knowledge Files

96 XML files in `knowledge/`, organized as:
- **Domain bases** (46): coding standards, security, architecture, debugging, testing, etc.
- **Language guides** (`lang-*.xml`, 17): Python, TypeScript, C#, Go, SQL, etc.
- **Framework guides** (`fw-*.xml`, 33): React, Next.js, ASP.NET, FastAPI, etc.

Language and framework files load automatically when their name appears in a spawn
prompt's task description — e.g. `"fix bug in TypeScript React component"` pulls
both `lang-typescript.xml` and `fw-react.xml`.

## Hooks

Six hook types, each implemented as one or more Python scripts:

| Hook | Scripts | Purpose |
|------|---------|---------|
| **SessionStart** | `rag-session-reset.py`, `compaction-restore.py` | Clear RAG sentinel, restore handoff state after clear/compact |
| **PreToolUse** | `rag-read-guard.py`, `spawn-guard.py`, `session-primer.py` | RAG gate, agent spawn enforcement, RAG sentinel check |
| **PostToolUse** | `context-nudge.py`, `spawn-nudge.py` | Nudge context.md updates, remind orchestrator to spawn evaluator |
| **PreCompact** | `pre-compact-save.py` | Save workspace state before compaction |
| **UserPromptSubmit** | `session-primer.py` | Inject HARD STOP if RAG sentinel is missing |
| **Stop** | `stop-hook.py` | Status line update on stop |

## Slash Commands

41 commands in `.claude/commands/`. Key ones:

| Command | Purpose |
|---------|---------|
| `/boost` | Start a session — RAG up, hooks verified, mode set, workspaces discovered |
| `/rag` | Start or reconnect the RAG server |
| `/index-project <path>` | Index a project's codebase for semantic search |
| `/index-boost` | Reindex ClaudeBoost agents and knowledge |
| `/graph <task>` | Build a Files in Scope map using vector + graph RAG |
| `/workspace <task>` | Create a workspace and implementation plan |
| `/done` | Push completed work to remote |
| `/handoff` | Save session state for a fresh context |
| `/clear-safe` | Save state before clearing context |
| `/restore` | Restore state from last clear-safe |

## Session Flow

A typical session looks like this:

1. User runs `/boost` — RAG server starts, session is primed, active workspaces discovered
2. User pastes a ticket or describes a task
3. CLAUDE.md rules apply: simple tasks get done directly, complex tasks go through the workspace flow
4. Agents are spawned as needed; each calls `POST /context` first to load relevant knowledge
5. Findings are written to `workspace/<task>/context.md` as they accumulate
6. When done, user runs `/done` to push work to remote

## Code Metrics Thresholds

Enforced by agent directives:

| Metric | Threshold |
|--------|-----------|
| Cyclomatic complexity | 10 max per method |
| Method length | 40 lines max |
| Class length | 300 lines max |
| Parameter count | 4 max |
| Nesting depth | 3 max |
