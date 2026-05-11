# ClaudeBoost

Multi-agent orchestration toolkit for Claude Code. 24 specialist agents, 45 knowledge
bases, semantic RAG search, and Gas Town integration — all installable globally.

## What's Inside

```
ClaudeBoost/
├── agents/              24 specialist agent definitions (XML)
├── knowledge/           44 domain knowledge bases (XML)
├── mcp-rag-server/      Semantic search MCP server (Python)
├── .claude/commands/    24 slash commands
├── scripts/             Setup and maintenance scripts
├── gastown/             Gas Town multi-agent framework
├── CLAUDE.md            Orchestration rules
├── HOW-IT-WORKS.md      Architecture documentation
└── SETUP-GUIDE.md       Windows installation guide
```

## Quick Start

### 1. Install Gas Town (optional but recommended)

See [SETUP-GUIDE.md](SETUP-GUIDE.md) for full Windows installation including Go, Dolt, and GT.

### 2. Install ClaudeBoost Extensions

```powershell
cd <path-to-ClaudeBoost>
powershell -ExecutionPolicy Bypass -File scripts/setup.ps1
```

This registers everything globally:
- RAG MCP server (semantic search in every project)
- Hooks (SessionStart, PreToolUse, PostToolUse, PreCompact, UserPromptSubmit, Stop)
- CLAUDEBOOST_HOME environment variable
- Agent/knowledge files in GT directives (if GT installed)

### 3. Use It

Open any project in Claude Code. You now have:
- `rag_search` — semantic search across all knowledge bases
- `rag_context` — curated context packages for agent tasks
- `rag_index` — index new content
- `rag_status` — check server health
- `/boost` — activate ClaudeBoost (RAG + GT primed)
- 24 slash commands for task management

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

44 domain expertise files covering: coding standards, security, architecture, debugging,
testing, observability, performance, refactoring, UI implementation, API design,
context engineering, verify gate, scope governance, rule enforcement, and more.

## How It Works

See [HOW-IT-WORKS.md](HOW-IT-WORKS.md) for the full architecture, directives,
formulas, plugins, and Gas Town integration details.

## Works Standalone

ClaudeBoost works without Gas Town. You get agents, knowledge, RAG search, and
slash commands in any Claude Code project.

With Gas Town, you additionally get: multi-agent coordination, persistent identity,
work tracking (beads), message passing, and automated supervision.
