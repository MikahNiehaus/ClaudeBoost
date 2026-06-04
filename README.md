# ClaudeBoost

Multi-agent orchestration toolkit for Claude Code. 25 specialist agents, 96 knowledge
files, and semantic RAG search — all installable globally.

## What's Inside

```
ClaudeBoost/
├── agents/              25 specialist agent definitions (XML)
├── knowledge/           96 knowledge files (46 domain, 17 lang, 33 framework) (XML)
├── mcp-rag-server/      Semantic search MCP server (Python)
├── .claude/commands/    41 slash commands
├── scripts/             Setup and maintenance scripts
├── CLAUDE.md            Orchestration rules
└── docs/                Reference documentation
```

## Quick Start

### 1. Install ClaudeBoost

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

Either path runs `scripts/setup.py`, the cross-platform installer. It registers everything globally:

- RAG MCP server (semantic search in every project)
- Hooks (SessionStart, PreToolUse, PostToolUse, PreCompact, UserPromptSubmit, Stop)
- CLAUDEBOOST_HOME environment variable

> **TTS support:** `/speak` works on Windows and macOS. Linux is not supported (no `afplay` / Windows API equivalent wired in) — the rest of ClaudeBoost runs fine.

### 3. Use It

Open any project in Claude Code. You now have:
- `rag_search` — semantic search across all knowledge bases
- `rag_context` — curated context packages for agent tasks
- `rag_index` — index new content
- `rag_status` — check server health
- `/boost` — activate ClaudeBoost (RAG primed)
- 41 slash commands for task management

## Features

### Quality-First Token Routing

Every agent spawn is routed to the right weight — full ceremony where quality demands
it, lightweight where it doesn't:

- **Full** (reviewer, security, performance): verify gate + evaluator-agent verification
- **Standard** (workflow, refactor, debug, test, ui, etc.): no verify gate overhead
- **Lightweight** (explore, research, docs, estimator, rag-indexing): minimal ceremony

### Verify Gate (Anti-Hallucination)

Every finding must be proven from actual code. 4 hooks remind agents and the orchestrator to follow the protocol:

- **PreToolUse on Task**: Nudges spawn prompt to include `rag_context` and architect contract
- **PostToolUse on Task**: Reminds orchestrator to spawn evaluator-agent for unverified findings
- **SessionStart**: Loads quality-first routing mindset
- **PreCompact**: Preserves routing rules across context compaction

Evaluator-agent always runs in a fresh context to prevent confirmation bias.

### RAG-Powered Knowledge

Agents load their identity and relevant knowledge via `rag_context` on every spawn.
A PreToolUse hook reminds the orchestrator to include `rag_context` in spawn prompts — it is a nudge, not a gate.

## Agents

| Agent | Specialty | Model |
|-------|-----------|-------|
| architect-agent | System design, patterns, DDD | Opus |
| reviewer-agent | Code review, SOLID validation | Opus |
| ticket-analyst-agent | Requirements analysis | Opus |
| test-agent | Testing, TDD | Sonnet |
| debug-agent | Root cause analysis | Sonnet |
| security-agent | Security auditing, OWASP | Sonnet |
| performance-agent | Performance optimization | Sonnet |
| refactor-agent | Code refactoring | Sonnet |
| ui-agent | Frontend, accessibility | Sonnet |
| docs-agent | Documentation | Sonnet |
| research-agent | Investigation | Sonnet |
| research-rag-agent | Build persistent research RAG from URLs/PDFs | Sonnet |
| explore-agent | Code exploration | Sonnet |
| browser-agent | Playwright testing | Sonnet |
| workflow-agent | Complex multi-step workflows | Sonnet |
| compliance-agent | Compliance auditing | Sonnet |
| evaluator-agent | Output verification | Sonnet |
| standards-validator-agent | Standards validation | Sonnet |
| estimator-agent | Story pointing | Sonnet |
| devops-agent | CI/CD, Docker, deployment | Sonnet |
| database-agent | Schema design, queries, migrations | Sonnet |
| observability-agent | Logging, metrics, alerting | Sonnet |
| rag-indexing-agent | RAG index advisor — scans scope, recommends filters | Sonnet |
| e2e-agent | End-to-end UI testing, structured test plans | Sonnet |

## Knowledge Bases

96 knowledge files covering: coding standards, security, architecture, debugging,
testing, observability, performance, refactoring, UI implementation, API design,
context engineering, verify gate, scope governance, rule enforcement, and more.

## How It Works

See [HOW-IT-WORKS.md](docs/HOW-IT-WORKS.md) for the full architecture, agents, knowledge bases, and RAG details.
