# ClaudeBoost

Multi-agent orchestration toolkit for Claude Code. 21 specialist agents, 36 knowledge
bases, semantic RAG search, and Gas Town integration — all installable globally.

## What's Inside

```
ClaudeBoost/
├── agents/              21 specialist agent definitions (XML)
├── knowledge/           36 domain knowledge bases (XML)
├── mcp-rag-server/      Semantic search MCP server (Python)
├── .claude/commands/    13 slash commands
├── gastown/             Gas Town multi-agent framework
├── CLAUDE.md            Orchestration rules (slim v2)
├── install.bat          One-time global installer
├── gtstart.bat          GT project launcher
├── SETUP-GUIDE.md       Windows installation guide
└── HOW-IT-WORKS.md      Architecture documentation
```

## Quick Start

### 1. Install Gas Town (optional but recommended)

See [SETUP-GUIDE.md](SETUP-GUIDE.md) for full Windows installation including Go, Dolt, and GT.

### 2. Install ClaudeBoost Extensions

```batch
cd C:\Users\grayw\OneDrive\prj\ClaudeBoost
.\install.bat
```

This registers everything globally:
- RAG MCP server (semantic search in every project)
- Slash commands (global)
- Agent/knowledge files in GT directives (if GT installed)

### 3. Use It

Open any project in Claude Code. You now have:
- `rag_search` — semantic search across all knowledge bases
- `rag_context` — curated context packages for agent tasks
- `rag_index` — index new content
- `rag_status` — check server health
- 13 slash commands for task management

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
| teacher-agent | Teaching, explanation | Sonnet |

## Knowledge Bases

36 domain expertise files covering: coding standards, security, architecture, debugging,
testing, observability, performance, refactoring, UI implementation, API design,
context engineering, and more.

## How It Works

See [HOW-IT-WORKS.md](HOW-IT-WORKS.md) for the full architecture, directives,
formulas, plugins, and Gas Town integration details.

## Works Standalone

ClaudeBoost works without Gas Town. You get agents, knowledge, RAG search, and
slash commands in any Claude Code project.

With Gas Town, you additionally get: multi-agent coordination, persistent identity,
work tracking (beads), message passing, and automated supervision.
