---
description: List all available agents with their expertise domains
allowed-tools: Read, Glob
---

# Available Agents

## Instructions

List all agent files from `agents/` directory (excluding `_orchestrator.md`) and display:
- Agent name
- Primary expertise
- Knowledge base reference
- When to use

## Agent Summary Table

| Agent | Expertise | Knowledge Base | Spawn For |
|-------|-----------|----------------|-----------|
| `test-agent` | Testing, TDD, coverage | `knowledge/testing.md` | Writing tests, test strategy |
| `debug-agent` | Bug analysis, root cause | `knowledge/debugging.md` | Errors, debugging |
| `architect-agent` | Design, SOLID, patterns | `knowledge/architecture.md` | Architecture decisions |
| `reviewer-agent` | PR review, feedback | `knowledge/pr-review.md` | Code reviews |
| `docs-agent` | Documentation | `knowledge/documentation.md` | Writing docs |
| `estimator-agent` | Story points, estimation | `knowledge/story-pointing.md` | Ticket estimation |
| `ui-agent` | UI implementation | `knowledge/ui-implementation.md` | Frontend, mockups |
| `workflow-agent` | Execution, process | `knowledge/workflow.md` | Complex implementations |
| `research-agent` | Web research, verification | `knowledge/research.md` | Deep research, fact-checking |
| `security-agent` | Security review, OWASP | `knowledge/security.md` | Security audits, vulnerability review |
| `refactor-agent` | Code smells, refactoring | `knowledge/refactoring.md` | Code cleanup, technical debt |
| `explore-agent` | Codebase exploration | `knowledge/code-exploration.md` | Understanding codebases |
| `performance-agent` | Profiling, optimization | `knowledge/performance.md` | Performance issues, bottlenecks |
| `ticket-analyst-agent` | Requirements analysis | `knowledge/ticket-understanding.md` | Clarifying vague requests |
| `compliance-agent` | Rule auditing | `knowledge/rule-enforcement.md` | Checking rule adherence |
| `browser-agent` | Interactive browser testing | `knowledge/playwright.md` | Playwright MCP, e2e testing |

## Quick Decision Guide

```
Need to...                          → Use
─────────────────────────────────────────────
Write or review tests               → test-agent
Fix a bug or error                  → debug-agent
Design system architecture          → architect-agent
Review a pull request               → reviewer-agent
Write documentation                 → docs-agent
Estimate a ticket/story             → estimator-agent
Implement UI from mockup            → ui-agent
Plan complex implementation         → workflow-agent
Research external topics            → research-agent
Security audit or review            → security-agent
Clean up / refactor code            → refactor-agent
Understand a codebase               → explore-agent
Optimize performance                → performance-agent
Clarify requirements                → ticket-analyst-agent
Audit rule compliance               → compliance-agent
Interactive browser testing         → browser-agent
```

## Usage

To spawn an agent: `/spawn-agent <agent-name> <task-id>`
To check task status: `/agent-status <task-id>`
