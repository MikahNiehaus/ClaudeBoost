# ClaudeBoost

Multi-agent orchestration toolkit for Claude Code: agents, knowledge bases, semantic search.

## How It Works

You have 25 agents (`agents/*.xml`) and 45 knowledge bases (`knowledge/*.xml`).
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

**Complex task?** (ticket attached, multi-agent, multi-session, user says "plan this", or touches >5 files)

Scope tiers:
- **5–10 files (FEATURE)**: workspace + subtasks
- **>10 files (COMPLEX)**: workspace + plan + agent delegation
- **>15 source files or new subsystem (COMPLEX+)**: create a PRD first (`/create-prd`)

Steps:
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

### Language & Framework Guides
Language and framework knowledge files (`knowledge/lang-*.xml`, `knowledge/fw-*.xml`) are indexed in RAG and load automatically when relevant. Including the language or framework name in a spawn prompt's `task_description` improves match quality — e.g. `"fix bug in TypeScript React component"` will pull in both the TypeScript and React guides.

### Agent Return Format
Every agent response **MUST** end with a `## Summary` block (≤300 words) containing:
- Findings with `file:line` citations
- Decision made or action taken
- Specific next step

The orchestrator reads the `## Summary` block. It does **NOT** re-read the full response body.
This keeps agent output from bloating the main context window (multi-agent overhead can reach 15× chat tokens — Anthropic research finding).
Include this instruction in every agent spawn prompt: `"End your response with ## Summary (≤300 words): findings with file:line, action taken, next step."`

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

### Label / String Consistency Fix Rule
When fixing a label, field name, or string inconsistency:
1. Grep for ALL occurrences of the old value across the entire repo before touching anything.
2. List every match found — HTML labels, [DisplayName] attributes, export column .Name() calls, validation ErrorMessage strings, constants, comments.
3. Default: update ALL of them in one commit.
4. Exception: if a location is genuinely out of scope (e.g. a migration filename, a historical comment), state it explicitly and justify the skip.
Never silently leave occurrences untouched because the bug report only mentioned a subset of surfaces.

## Human Voice Standard

Every word Claude produces — responses, code comments, explanations, labels, error messages — must sound like a human wrote it. This is not optional.

### Banned vocabulary (replace with plain English)
`delve` `delving` `underscore` `pivotal` `robust` `seamless` `comprehensive` `nuanced` `leverage` `utilize` `facilitate` `harness` `illuminate` `bolster` `tapestry` `realm` `beacon` `cacophony` `foster` `intricate` `palpable` `transformative` `revolutionary` `game-changing` `paradigm` `synergy` `holistic` `empower`

### Banned openers and filler phrases
- "Certainly!" / "Great question!" / "Absolutely!" / "Of course!" / "I'd be happy to"
- "In today's rapidly evolving landscape…" / "It's worth noting that…" / "It is important to note that…"
- "Furthermore," / "Moreover," / "Additionally," / "Consequently," → use "Also", "And", or a new sentence
- "In conclusion" / "To summarize" → just say the thing
- "It's not just X, it's Y" → sounds like insight, contains none; cut it
- "As an AI" → never

### Structural rules
- **Vary sentence length.** Short sentences exist. Mix them with longer ones.
- **Use contractions** — "don't", "it's", "we'll", not "do not", "it is", "we will"
- **No uniform lists** — "Bold term: explanation" repeated 6 times reads like a machine; use prose or vary the structure
- **One em-dash per response max** — Claude overuses em-dashes; rewrite as separate sentences
- **No hedging clusters** — "might potentially perhaps" in one breath is not caution, it's noise; pick one or cut it
- **Concrete over abstract** — "the build broke on line 42" not "there were issues"
- **No throat-clearing** — start with the substance, not "Let's explore…" or "This section will cover…"

### Code comments
Same rules. Comments are output too.
- Write like a note to a colleague, not a spec document
- Say WHY, not WHAT — the code shows what; the comment explains why
- Skip obvious comments; short beats long
- No: `// This function facilitates the seamless authentication flow`
- Yes: `// Throws if the token is expired`

Full framework with examples: `knowledge/human-voice.xml`

## When to Use What

| Trigger | Action |
|---------|--------|
| Ticket pasted | Save verbatim to `[project]/workspace/[task-id]/ticket.md` (project-scoped; ClaudeBoost meta-work uses `$CLAUDEBOOST_HOME/workspace/[task-id]/ticket.md`), plan, then delegate |
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

### Per-Folder CLAUDE.md
Create a `CLAUDE.md` in any significant subdirectory with:
- Purpose of the folder
- Conventions specific to that folder
- Key patterns or constraints
Claude Code auto-loads these when working in subdirectories.

## Gas Town Compatibility

Compatible: `gt prime`, `gt hook`, `gt sling` (polecats), `gt mail`, `gt nudge`, `gt handoff`, beads.

## RAG Unavailable Protocol

When RAG tools are missing from your tool list OR return a connection/server error:

1. **STOP immediately** — no investigation, no agent spawning, no file reading as a substitute
2. Tell the user exactly: *"RAG is not connected. Run `/boost` to reconnect, then retry."*
3. Do NOT attempt to recover by grepping, reading files, or proceeding with degraded context
4. Do NOT rationalize past this — "I can be helpful anyway" is the wrong call

When RAG errors mid-task: `rag-error-guard.py` surfaces the error automatically. Still stop and report; do not continue.

The `session-primer.py` UserPromptSubmit hook injects a HARD STOP directive when the sentinel is missing — treat it as a hard requirement, not a soft suggestion.

## RAG Health Check Protocol

At the start of any investigation or multi-step codebase task:
1. Call `rag_context(agent="...", task_description="...", project_path="...")`
2. **Also call `rag_status`** — check for unresolved graph edges, index errors, or stale collections
3. If `rag_status` shows errors: stop and fix before continuing (reindex if stale, report if server error)
4. If index is stale (`reindex-check.py` warned at session start): call `rag_index_project(force=true)` before searching

Do not skip the health check because "RAG seemed to work earlier" — indexes degrade silently.

## Workspace Update Protocol

Update `workspace/[task-id]/context.md` **after every significant finding** — not at fixed intervals:
- After a RAG search that surfaces relevant files: write what you found and why it matters
- After reading a file that confirms or refutes a hypothesis: record the evidence
- After identifying root cause of a bug: write it down before fixing
- After any architectural decision or user constraint: capture it
- Format: current status → what was found → next step → open questions

The `context-nudge.py` PostToolUse hook fires after every 5 reads as a fallback reminder. Don't wait for it — update proactively. Findings in `context.md` survive compaction; findings only in context do not.

## RAG Server

Two distinct RAG indexes — always distinguish between them:

| Term | What it is | Tools |
|------|-----------|-------|
| **ClaudeBoost RAG** | Agents (`agents/`) + knowledge bases (`knowledge/`) indexed at `mcp-rag-server/.rag-index/` | `rag_search scope=agents/knowledge/all`, `rag_index`, `rag_context` |
| **Project RAG** | A specific project's source code, indexed per-project at `<project>/workspace/.rag-index/` | `rag_index_project`, `rag_search scope=codebase`, `/index-project` |
| **GraphRAG** | Structural code graph (imports, inherits) stored in `graph.db` alongside Project RAG | `rag_search scope=codebase mode=graph` — auto-built at index time, auto-augments `rag_context` Tier 4b |

When the user says "ClaudeBoost RAG" → they mean agents/knowledge.
When the user says "Project RAG" or "project index" → they mean the codebase index for whatever project they're working on.
`rag_context` combines both: tiers 0-3 pull from ClaudeBoost RAG, tier 4 pulls from Project RAG (vector), tier 4b pulls structural graph neighbours when a graph index exists.

**GraphRAG usage:**
- `rag_search scope=codebase mode=graph` — vector seed + structural neighbours (files that import/inherit from seed files)
- `rag_search scope=codebase mode=vector` — semantic only (default, backwards compatible)
- Graph index is built automatically during `rag_index_project` — no extra step needed
- Graph index degrades gracefully: if no `graph.db` exists, mode=graph falls back to vector results

## TTS (Text-to-Speech)

Hook auto-speaks responses when enabled. **NEVER run edge-tts, speak-play.py, or `start` via Bash** — triggers permission prompts. Just respond normally.

- `/speak on|off` — toggle TTS
- `/speak voice <name>` — change voice
- `/speak voices` — list voices
