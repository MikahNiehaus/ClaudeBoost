# ClaudeBoost

Multi-agent orchestration toolkit for Claude Code: agents, knowledge bases, semantic search.

## How It Works

You have 24 agents (`agents/*.xml`) and 45 knowledge bases (`knowledge/*.xml`).
A RAG server indexes all of them for semantic search.

**RAG powers agent knowledge (REQUIRED — PreToolUse hook reminds you):**
- Spawned agents MUST call `rag_context` as their FIRST action
- Use `rag_search` when unsure which knowledge file applies or when reviewing code for standards
- NEVER guess which file to read — search for it
- Include agent name + task description in spawn prompt; no need to pre-fetch knowledge
- PreToolUse hook on `Task` reminds you to include `rag_context` in the spawn prompt — it is a nudge, not a gate; do not rely on it as a safety net

## Decision Flow

Two paths, not five mandatory steps:

**Simple task?** Just do it. No workspace, no ceremony.

**Complex task?** (ticket attached, multi-agent, multi-session, user says "plan this")
1. Create `workspace/[task-id]/` — announce with one line
2. Sweep-then-verify across domains (testing, docs, security, architecture, performance, review, clarity, browser testing, observability)
3. Spawn the right agent(s)

Sweep-then-verify across domains — every flag must cite file:line or be dropped (see Verify Gate).

## Agent Spawning

Spawn agents when they add value: parallelism, isolation, deep specialization.
Do the work directly when they don't. A one-line fix doesn't need an agent.

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

Hooks remind you of this: PreToolUse nudges agents to call rag_context in spawn prompts, PostToolUse reminds the orchestrator to spawn evaluator-agent for unverified findings (it is an LLM nudge, not a mechanical gate — mark findings correctly yourself), NEEDS_VERIFICATION status flags a finding for evaluator-agent escalation.

## Collaborative Mode (CONSULT / AUTO)

Default: **CONSULT**. Research project, spawn `architect-agent` (Opus) for proposal, present via `AskUserQuestion`. User adds constraints; you implement.

**Triggers**: new endpoint/table/dependency/module/middleware/auth-strategy/API/config/concurrency.
**Not triggers**: typos, bugfixes, tests, docs, config tweaks, renames, edits under `workspace/`/`.claude/`/`knowledge/`/`plans/`/`docs/`.

Standards (parameterized queries, `logger.error`, input validation, auth) apply automatically — not debatable.
`architect-agent` requires >=2 `file:line` citations in spawn prompt.
Approvals logged to `state/session-approvals.json` (session-scoped).
State: `$CLAUDEBOOST_HOME/state/claudeboost-mode.json` (missing = CONSULT).
`/auto [reason]` = AUTO. `/consult` = restore. Full protocol: `knowledge/consult-mode.xml`.

## Token Efficiency

**Agent weight routing**:
- **Full** (reviewer, security, performance): verify gate + evaluator-agent
- **Standard** (workflow, refactor, debug, test, ui, architect, ticket-analyst, browser, evaluator, observability, devops, database, compliance, standards-validator, e2e): no verify gate
- **Lightweight** (explore, research, docs, estimator, rag-indexing): minimal ceremony

Always spawn evaluator for findings — never self-verify. Evaluator only reads cited file:lines.

## Hard Rules
See global `~/.claude/CLAUDE.md` — jQuery Ban, Security Standards, Logging Standards apply here.

## When to Use What

| Trigger | Action |
|---------|--------|
| Ticket pasted | Save verbatim to `workspace/[task-id]/ticket.md`, plan, then delegate |
| Complex feature | Workspace + sweep-then-verify + agents |
| Code review | Spawn reviewer-agent (Opus) with verify gate |
| New architecture | Spawn architect-agent (Opus) with SOLID review |
| Visualize architecture | `/visualize` — interactive board in browser (self-map for ClaudeBoost, project-map for others) |

### SOLID Review
Only when designing new classes, modules, interfaces, or systems.
Not on bug fixes, config changes, styling, or docs.

### Self-Critique + Teaching
Only on workspace tasks (complex work). Simple tasks: just deliver.

### Alternatives Analysis
Ask: "Would a reasonable person pick a different approach?"
Yes: document alternatives and rationale. No: just do it.

## Gas Town Compatibility

Compatible: `gt prime`, `gt hook`, `gt sling` (polecats), `gt mail`, `gt nudge`, `gt handoff`, beads.

## RAG Server

Two distinct RAG indexes — always distinguish between them:

| Term | What it is | Tools |
|------|-----------|-------|
| **ClaudeBoost RAG** | Agents (`agents/`) + knowledge bases (`knowledge/`) indexed at `mcp-rag-server/.rag-index/` | `rag_search scope=agents/knowledge/all`, `rag_index`, `rag_context` |
| **Project RAG** | A specific project's source code, indexed per-project at `<project>/workspace/.rag-index/` | `rag_index_project`, `rag_search scope=codebase`, `/index-project` |

When the user says "ClaudeBoost RAG" → they mean agents/knowledge.
When the user says "Project RAG" or "project index" → they mean the codebase index for whatever project they're working on.
`rag_context` combines both: tiers 0-3 pull from ClaudeBoost RAG, tier 4 pulls from Project RAG.

## TTS (Text-to-Speech)

Hook auto-speaks responses when enabled. **NEVER run edge-tts, speak-play.py, or `start` via Bash** — triggers permission prompts. Just respond normally.

- `/speak on|off` — toggle TTS
- `/speak voice <name>` — change voice
- `/speak voices` — list voices
