# ClaudeBoost

Multi-agent orchestration toolkit for Claude Code. Agents, knowledge bases, and
semantic search — works standalone or with Gas Town.

## How It Works

You have 24 specialist agents (`agents/*.xml`) and 38 knowledge bases (`knowledge/*.xml`).
A RAG server indexes all of them for semantic search.

**RAG powers agent knowledge (ENFORCED BY HOOK):**
- Spawned agents MUST call `rag_context` as their FIRST action
- Use `rag_search` when unsure which knowledge file applies or when reviewing code for standards
- NEVER guess which file to read — search for it
- Include agent name + task description in spawn prompt; no need to pre-fetch knowledge
- PreToolUse hook on `Task` enforces this

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

Hooks enforce this: PreToolUse injects verify gate into spawns, PostToolUse drops unverified BLOCKER/HIGH findings, NEEDS_VERIFICATION triggers evaluator-agent.

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
- **Standard** (workflow, refactor, debug, test, ui): no verify gate
- **Lightweight** (explore, research, docs, estimator, teacher): minimal ceremony

Always spawn evaluator for findings — never self-verify. Evaluator only reads cited file:lines.

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

MCP tools: `rag_search`, `rag_index`, `rag_context`, `rag_status`.

## Agent Roster

Opus: architect-agent, reviewer-agent, ticket-analyst-agent. All others: Sonnet.
Use `rag_search` for agent details or `/list-agents`.

## TTS (Text-to-Speech)

The Stop hook at `$CLAUDEBOOST_HOME/scripts/speak-tts.py` handles TTS **automatically** after every response. When `speak-state.json` has `enabled: true`, the hook reads the response, strips markdown, and speaks it aloud via edge-tts.

**NEVER run edge-tts, speak-play.py, or `start` manually via Bash.** This triggers permission prompts. Just respond normally — the hook does the rest.

- `/speak on` → set `speak-state.json` to `enabled: true`, respond normally
- `/speak off` → set `speak-state.json` to `enabled: false`
- `/speak voice <name>` → update the voice field
- `/speak voices` → list available voices
