---
description: List all available agents with their expertise domains
allowed-tools: Read, Glob
---

# Available Agents

## Instructions

List all agent files from `agents/` directory (excluding `_orchestrator.xml`) and display:
- Agent name
- Primary expertise
- Knowledge base reference
- When to use

## Agent Summary Table

| Agent | Expertise | Knowledge Base | Spawn For |
|-------|-----------|----------------|-----------|
| `architect-agent` | Design, SOLID, patterns | `knowledge/architecture.xml` | Architecture decisions |
| `browser-agent` | Interactive browser testing | `knowledge/playwright.xml` | Playwright MCP, e2e testing |
| `compliance-agent` | Rule auditing | `knowledge/rule-enforcement.xml` | Checking rule adherence |
| `database-agent` | Schema design, query optimization, migrations | `knowledge/database.xml` | Database design, query optimization, schema changes |
| `debug-agent` | Bug analysis, root cause | `knowledge/debugging.xml` | Errors, debugging |
| `devops-agent` | CI/CD, containerization, deployment | `knowledge/devops.xml` | Deployment automation, infrastructure, pipelines |
| `docs-agent` | Documentation | `knowledge/documentation.xml` | Writing docs |
| `estimator-agent` | Story points, estimation | `knowledge/story-pointing.xml` | Ticket estimation |
| `evaluator-agent` | Quality verification, acceptance criteria | `knowledge/completion-verification.xml` | Verify outputs meet requirements |
| `explore-agent` | Codebase exploration | `knowledge/code-exploration.xml` | Understanding codebases |
| `observability-agent` | Logging, metrics, tracing, alerting | `knowledge/observability.xml` | Design monitoring, observability, incident response |
| `performance-agent` | Profiling, optimization | `knowledge/performance.xml` | Performance issues, bottlenecks |
| `e2e-agent` | End-to-end UI testing, structured test plans | `knowledge/e2e-testing.xml` | Full E2E test runs with screenshot evidence |
| `rag-indexing-agent` | Pre-index analysis, scope recommendation | — | Recommend codebase indexing scope and filters |
| `refactor-agent` | Code smells, refactoring | `knowledge/refactoring.xml` | Code cleanup, technical debt |
| `research-agent` | Web research, verification | `knowledge/research.xml` | Deep research, fact-checking |
| `reviewer-agent` | PR review, feedback | `knowledge/pr-review.xml` | Code reviews |
| `security-agent` | Security review, OWASP | `knowledge/security.xml` | Security audits, vulnerability review |
| `standards-validator-agent` | SOLID principles, design patterns | `knowledge/coding-standards.xml` | Validate code against standards |
| `test-agent` | Testing, TDD, coverage | `knowledge/testing.xml` | Writing tests, test strategy |
| `ticket-analyst-agent` | Requirements analysis | `knowledge/ticket-understanding.xml` | Clarifying vague requests |
| `ui-agent` | UI implementation | `knowledge/ui-implementation.xml` | Frontend, mockups |
| `workflow-agent` | Execution, process | `knowledge/workflow.xml` | Complex implementations |

## Quick Decision Guide

```
Need to...                          → Use
─────────────────────────────────────────────
Design system architecture          → architect-agent
Interactive browser testing         → browser-agent
Audit rule compliance               → compliance-agent
Database design or query work       → database-agent
Fix a bug or error                  → debug-agent
CI/CD, Docker, deployment           → devops-agent
Write documentation                 → docs-agent
Estimate a ticket/story             → estimator-agent
Verify outputs meet requirements    → evaluator-agent
Understand a codebase               → explore-agent
Design monitoring/observability     → observability-agent
Optimize performance                → performance-agent
Run structured E2E UI tests         → e2e-agent
Recommend RAG indexing scope        → rag-indexing-agent
Clean up / refactor code            → refactor-agent
Research external topics            → research-agent
Review a pull request               → reviewer-agent
Security audit or review            → security-agent
Validate code against standards     → standards-validator-agent
Write or review tests               → test-agent
Clarify requirements                → ticket-analyst-agent
Implement UI from mockup            → ui-agent
Plan complex implementation         → workflow-agent
```

## Usage

To spawn an agent: `/spawn-agent <agent-name> <task-id>`
To check task status: `/agent-status <task-id>`
