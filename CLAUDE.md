# ClaudeBoost

Multi-agent orchestration toolkit for Claude Code. Agents, knowledge bases, and
semantic search — works standalone or with Gas Town.

## How It Works

You have 24 specialist agents (`agents/*.xml`) and 38 knowledge bases (`knowledge/*.xml`).
A RAG server indexes all of them for semantic search.

**RAG powers agent knowledge (MANDATORY):**
- Spawned agents MUST call `rag_context` as their FIRST action — no exceptions, no skipping
- When unsure which knowledge file applies: MUST call `rag_search` with a natural language query
- When reviewing code: MUST `rag_search` for the relevant standards (e.g., "SQL security", "logging requirements")
- NEVER guess which file to read — search for it
- A PreToolUse hook enforces `rag_context` on every agent spawn — if you skip it, the hook will catch you

## Decision Flow

Two paths, not five mandatory steps:

**Simple task?** Just do it. No workspace, no ceremony.

**Complex task?** (ticket attached, multi-agent, multi-session, user says "plan this")
1. Create `workspace/[task-id]/` — announce with one line
2. Sweep-then-verify across domains (testing, docs, security, architecture, performance, review, clarity)
3. Spawn the right agent(s)

Sweep-then-verify: scan all domains, but for every flag you raise, **prove it from actual code**.
If you can't cite specific lines — drop the flag. "Nothing found" is always valid.

## Agent Spawning

Spawn agents when they add value: parallelism, isolation, deep specialization.
Do the work directly when they don't. A one-line fix doesn't need an agent.

**Agent knowledge loading (ENFORCED BY HOOK)**: Spawned agents MUST call `rag_context` as
their FIRST action. Include the agent name and task description in the spawn prompt
so the agent knows what to query. You do NOT need to pre-fetch knowledge.
A PreToolUse hook on `Task` verifies every spawn includes `rag_context` instructions.

### Model Routing
- **Opus**: architect-agent, reviewer-agent, ticket-analyst-agent
- **Sonnet**: all others

### Parallel Limits
- Context below 50%: up to 3 agents
- Context 50-75%: up to 2 agents
- Context above 75%: 1 agent, sequential

## Verify Gate (Anti-Hallucination)

Applies everywhere: reviews, planning, bug diagnosis, security audits, test planning.

- Every finding must be **proven from actual code** before acting on it
- Cite specific file + line for every flag
- "No issues found" is always a valid outcome
- Reviewers: finding something is NOT the goal. Finding REAL things is.

**Structural Enforcement** (hooks, not just instructions):
- **PreToolUse on Task**: Injects verify gate instructions into every agent spawn prompt
- **PostToolUse on Task**: Intercepts agent output — unverified BLOCKER/HIGH findings are dropped or verified
- **Output format**: Evidence column and Verification Status make gaps structurally visible
- **Evaluator escalation**: NEEDS_VERIFICATION status triggers mandatory evaluator-agent spawn

## Hard Rules (Non-Negotiable)

### jQuery Ban
jQuery is BANNED unless user explicitly requests it.
Detect: `$()`, `jQuery`, `import/require jquery`, CDN script tags.
Use instead: React hooks, vanilla JS, native fetch.

### Security Standards
- Parameterized queries always (never string concatenation in SQL)
- SQL transactions for multi-step database operations
- OWASP top 10 awareness — see `knowledge/security.xml`
- No secrets in logs, URLs, or source code
- Input validation at system boundaries
- Auth/authz checks on endpoints

### Logging Standards
- **BLOCKER**: Missing `logger.error` in catch/error blocks
- **BLOCKER**: Sensitive data in log output
- **Suggestion**: Missing INFO-level on service methods
- **Suggestion**: Missing before/after on external calls

## When to Use What

| Trigger | Action |
|---------|--------|
| Simple question | Answer directly |
| Simple code change | Do it, no agent needed |
| Ticket pasted | Save verbatim to `workspace/[task-id]/ticket.md`, plan, then delegate |
| Complex feature | Workspace + sweep-then-verify + agents |
| Code review | Spawn reviewer-agent (Opus) with verify gate |
| New architecture | Spawn architect-agent (Opus) with SOLID review |

### SOLID Review
Only when designing new classes, modules, interfaces, or systems.
Not on bug fixes, config changes, styling, or docs.

### Self-Critique + Teaching
Only on workspace tasks (complex work). Simple tasks: just deliver.

### Alternatives Analysis
Ask: "Would a reasonable person pick a different approach?"
Yes: document alternatives and rationale. No: just do it.

## Gas Town Compatibility

Works with: `gt prime`, `gt hook`, `gt sling`, `gt mail`, `gt nudge`, `gt handoff`, beads.
Workspace convention is compatible with bead attachment.
Agent spawning is compatible with `gt sling` to polecats.

## RAG Server

MCP server for semantic search over agents, knowledge, workspaces, and codebases.
Register globally so every project has access:

```json
{
  "mcpServers": {
    "rag-server": {
      "command": "python",
      "args": ["-m", "rag_server"],
      "cwd": "<path-to-ClaudeBoost>/mcp-rag-server"
    }
  }
}
```

Tools: `rag_search`, `rag_index`, `rag_context`, `rag_status`.

## Agent Roster

| Agent | Specialty | Model |
|-------|-----------|-------|
| architect-agent | System design, patterns | Opus |
| reviewer-agent | Code review, SOLID validation | Opus |
| ticket-analyst-agent | Requirements analysis | Opus |
| test-agent | Testing, TDD | Sonnet |
| debug-agent | Root cause analysis | Sonnet |
| security-agent | Security auditing | Sonnet |
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
| devops-agent | CI/CD, Docker, deployment | Sonnet |
| database-agent | Schema design, queries, migrations | Sonnet |
| observability-agent | Logging, metrics, alerting | Sonnet |

## Browser Testing Safety

Playwright/browser automation is **localhost only**.
Allowed: localhost, 127.0.0.1, 0.0.0.0, *.local, *.test.
If unsure whether a URL is local, ask before navigating.
