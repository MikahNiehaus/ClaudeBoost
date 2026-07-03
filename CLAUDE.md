# ClaudeBoost

Multi-agent orchestration toolkit for Claude Code: agents, knowledge bases, semantic search.

## How It Works

You have 24 agents (`agents/*.xml`) and 108 knowledge files (`knowledge/*.xml`) — 54 domain bases, 21 language guides (`lang-*.xml`), 33 framework guides (`fw-*.xml`).
A RAG server indexes all of them for semantic search.

**RAG powers agent knowledge (REQUIRED — PreToolUse hook reminds you):**
- Spawned agents MUST call `POST http://127.0.0.1:8612/context` as their FIRST action
- Use `POST http://127.0.0.1:8612/search` when unsure which knowledge file applies or when reviewing code for standards
- NEVER guess which file to read — search for it
- Include agent name + task description in spawn prompt; no need to pre-fetch knowledge
- PreToolUse hook on `Task` enforces a RAG context call in the spawn prompt — spawns without it are blocked (exit 2); include `POST http://127.0.0.1:8612/context` as the first action in every spawn prompt

**Use all three RAG modes when they apply:**
- `POST /context` — knowledge and agent context (always first, via HTTP REST)
- `POST /search` with `scope=codebase` — semantic code search
- `POST /search` with `scope=codebase&mode=graph` — dependency and import chains

**Dual-mode mandate (MANDATORY):** Every codebase search MUST cover BOTH modes. Use `mode=both` in a single `POST /search scope=codebase` call — it runs vector and graph concurrently server-side and returns `{"vector": {...}, "graph": {...}}`. If mode=both is unavailable, fall back to two sequential calls (`mode=vector` then `mode=graph`). They surface different files — never run only one.

**If RAG errors mid-task, fix it — never skip it.** Run `/rag` to restart the server. Do not proceed with degraded context or substitute grep/file reads.

## Decision Flow

Two paths, not five mandatory steps:

**Simple task?** Just do it. No workspace, no ceremony — but `POST /search` still applies when you need to find something in the codebase.

**Complex task?** (ticket attached, multi-agent, multi-session, user says "plan this", or touches >5 files)

Scope tiers:
- **5–10 files (FEATURE)**: workspace + subtasks
- **>10 files (COMPLEX)**: workspace + plan + agent delegation
- **>15 source files or new subsystem (COMPLEX+)**: create a PRD first (`/create-prd`)

Steps:
1. Create `workspace/[task-id]/` — announce with one line
2. Sweep-then-verify across domains (testing, docs, security, architecture, performance, review, clarity, browser testing, observability)
2b. Scope graph — after ticket analysis, run BOTH `POST /search mode=vector` AND `POST /search mode=graph` seeded from ticket entities (file names, service names, endpoints mentioned). Merge results and write to `context.md` as "Files in Scope". This is your starting navigation map for the task.
3. Spawn the right agent(s)

Sweep-then-verify across domains — every flag must cite file:line or be dropped (see Verify Gate).

## Agent Spawning

**CRITICAL:** Always use the **Task tool** to spawn agents, never the Agent tool.
The enforcement gate (PreToolUse hook on Task) blocks unresearched agent spawns.
Agent tool bypasses enforcement — it will be blocked by agent-spawn-gate.py.

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

Hooks remind you of this: PreToolUse nudges agents to call POST http://127.0.0.1:8612/context in spawn prompts, PostToolUse reminds the orchestrator to spawn evaluator-agent for unverified findings (it is an LLM nudge, not a mechanical gate — mark findings correctly yourself), NEEDS_VERIFICATION status flags a finding for evaluator-agent escalation.

## Collaborative Mode (CONSULT / AUTO)

Default: **CONSULT**. Before touching any file, produce a spec sheet: a plain-language summary of what the task does, then a table listing every file and the specific change planned. The user approves the spec. Claude can only edit files listed in the approved spec. Anything outside the spec requires a new spec sheet first.

This is a per-file gate, not a one-time task-level check. The hook (`consult-gate.py`) enforces it mechanically: every Edit, Write, and MultiEdit is checked against `state/spec-sheet.json`. If no spec exists, or the target file isn't listed in `approved_files`, the hook blocks with a dialog explaining what to do.

**Spec sheet format:**

```
## Spec Sheet: [task name]

### What This Does
[2-3 sentences. What the user will see or experience. Concrete, not technical.]

### Approved Changes
| # | File | Operation | What Changes |
|---|------|-----------|--------------|
| 1 | path/to/file.py | modify | Specific function and exactly what changes |
| 2 | path/to/new.py  | create | New file — what it contains and why |

### Out of Scope
[files explicitly excluded from this spec]
```

Stop after producing the spec. Don't write code or files. Wait for the user's approval before writing `state/spec-sheet.json` and starting work. If you discover a new file needs changing during implementation, stop, tell the user why, wait for approval, then update the spec before proceeding.

**What fires the gate**: any Edit, Write, or MultiEdit on a file not in `approved_files`.
**What doesn't**: reads, Bash, Glob, Grep; files under `workspace/`, `state/`, `.claudeboost/`, `plans/`, `docs/`; AUTO mode bypasses everything.

**Bugfix exemption boundary**: "bugfix" means the user said fix/repair/correct this — not a bug Claude diagnosed on its own. If Claude identifies a bug the user didn't name, describe the finding and proposed fix and wait for confirmation before editing.

Standards (parameterized queries, `logger.error`, input validation, auth) apply automatically throughout — never listed in the spec, never up for debate.
Approvals logged to `state/session-approvals.json` (session-scoped).
Approved file list logged to `state/spec-sheet.json` (overwritten per task).
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

### No Multiline python -c or cat heredocs
Never write `python -c "..."` or `python3 -c "..."` with multi-line code, and never use `cat > file << 'EOF'` to create files. Both trigger Claude Code's built-in safety scanner regardless of the allow list.

Use the Write tool to create the file, then run it:
1. Write tool → `$TEMP/cb_script.py` with your Python content
2. `Bash: python "$TEMP/cb_script.py"`

bash-guard.py enforces both — multiline `-c` strings and cat heredocs are blocked at the hook level.

### No Hardcoded Paths in ClaudeBoost Code
Never write literal paths like `C:/Development/ClaudeBoost/...` or `C:/Users/mniehaus/...` inside any ClaudeBoost source file (scripts, server code, hooks, agents). Always derive paths from:
- `os.environ.get("CLAUDEBOOST_HOME")` or the `BOOST_HOME` constant
- `Path(__file__).resolve().parent...` to traverse relative to the file
- `os.environ.get("LOCALAPPDATA")` / `Path.home()` for user-scoped paths
- Temp files: use `tempfile.mkstemp()` or `os.environ.get("TEMP")`, never a hardcoded drive path

This applies equally to debug code, one-off scripts, and test helpers. Hardcoded paths break on other machines and other users.

### Branch Creation (Non-Negotiable)
Before creating any new git branch — including during workspace creation — STOP and ask the user for permission using AskUserQuestion. State the proposed branch name and purpose. Do not create the branch until the user confirms.

After creating a workspace, explicitly tell the user: "I created branch `[branch-name]` for this workspace."

This applies in every context — workspace setup, agent spawns, scripts, and direct git commands.

### Irreversible Actions (Non-Negotiable)
Before doing ANYTHING that cannot be undone — deleting files, dropping tables, force-pushing, overwriting data, sending messages, publishing to external services, running destructive shell commands — STOP.

Tell the user exactly what you are about to do and why it cannot be undone. Use AskUserQuestion to get explicit YES confirmation before proceeding. If uncertain whether an action is reversible, treat it as irreversible and ask.

Always prefer safe reversible alternatives when one exists: soft deletes over hard deletes, backups before overwrites, dry-runs before destructive commands.

This applies in every context — not just agent spawns.

### Label / String Consistency Fix Rule
When fixing a label, field name, or string inconsistency:
1. Grep for ALL occurrences of the old value across the entire repo before touching anything.
2. List every match found — HTML labels, [DisplayName] attributes, export column .Name() calls, validation ErrorMessage strings, constants, comments.
3. Default: update ALL of them in one commit.
4. Exception: if a location is genuinely out of scope (e.g. a migration filename, a historical comment), state it explicitly and justify the skip.
Never silently leave occurrences untouched because the bug report only mentioned a subset of surfaces.

### Research Grounded Decisions (not negotiable)
When working on a task that has a workspace KB (Tier 3c exists), every implementation decision, pattern choice, and architecture recommendation must be grounded in indexed research — not in training-data recall.

Before answering "which approach should I use", "what pattern fits here", or "how should this be structured", query the workspace KB first:

```bash
POST http://127.0.0.1:8612/search
  scope="codebase"
  project_path="[WORKSPACE_ABS]/knowledge"
  query="[the specific decision question]"
  limit=3
```

If a result comes back with score ≥ 0.55: base the decision on what the indexed docs say. Cite the source.
If score < 0.55 or no results: flag it explicitly — "no research coverage for this decision" — then proceed from code context. Never silently answer from memory.

Log every grounded decision: `Decision: [what] — grounded by [source title] (score N)`

This applies to spawned agents too. Include this mandate in every agent spawn prompt when a workspace_path is set.

**Decision points that require a query:**
- Choosing between two implementation approaches
- Picking a library API method not already used in the codebase
- Recommending a security pattern or auth flow
- Handling an edge case the ticket leaves open
- Any architectural choice where multiple valid options exist

**Not required for:**
- Reading or explaining existing code
- Trivial one-line fixes with no approach choice
- Tasks with no workspace KB (Tier 3c not built)

## Human Voice Standard

Every word Claude produces — responses, code comments, explanations, labels, error messages — must sound like a human wrote it. This is not optional.

### Banned vocabulary (replace with plain English)
`delve` `delving` `underscore` `pivotal` `robust` `seamless` `comprehensive` `nuanced` `leverage` `utilize` `facilitate` `harness` `illuminate` `bolster` `tapestry` `realm` `beacon` `cacophony` `foster` `intricate` `palpable` `transformative` `revolutionary` `game-changing` `paradigm` `synergy` `holistic` `empower` `embark` `spearhead`

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
- **No em-dashes at all.** Rewrite as separate sentences instead.
- **No hyphenated compound jargon.** "no-go", "hard-block", "soft-fail", "non-trivial" used as standalone terms are AI-speak. Say what you mean: "not allowed", "blocks the task", "fails gracefully", "takes some work".
- **No hedging clusters** — "might potentially perhaps" in one breath is not caution, it's noise; pick one or cut it
- **Concrete over abstract** — "the build broke on line 42" not "there were issues"
- **No throat-clearing** — start with the substance, not "Let's explore…" or "This section will cover…"

### Code comments
Same rules. Comments are output too.
- Write like a note to a colleague, not a spec document
- Say WHY, not WHAT — the code shows what; the comment explains why
- Skip obvious comments; short beats long
- Informal but professional, conversational not corporate
- No dashes of any kind (no hyphens as separators, no em dashes, no double dashes)
- No hyphenated compound words: "non-blocking" → "not blocking", "hard-coded" → "hardcoded", "step-by-step" → "step by step". Exception: dashes inside actual code identifiers (filenames, flags, variable names) are fine
- No: `// This function facilitates the seamless authentication flow`
- Yes: `// Throws if the token is expired`

Full framework with examples: `knowledge/human-voice.xml`

## MCP Debugging Tools

When a user asks for breakpoint debugging, step-through execution, or wants to inspect
runtime variable values, use `mcp-debugger` MCP tools — not print statements.

**Trigger phrases:** "set a breakpoint", "step through", "step into/over/out", "what's the
value of X at line Y", "debug this", "walk through execution", "trace this call"

**Tool sequence:**
1. `mcp__mcp-debugger__create_debug_session` — start session, pass language + name, returns sessionId
2. `mcp__mcp-debugger__set_breakpoint` — set breakpoint at file:line
3. `mcp__mcp-debugger__continue_execution` — run until breakpoint hits
4. `mcp__mcp-debugger__get_variables` — inspect locals, call stack, scope
5. `mcp__mcp-debugger__step_over` / `step_into` / `step_out` — navigate execution
6. `mcp__mcp-debugger__evaluate_expression` — evaluate expression in current scope
7. `mcp__mcp-debugger__close_debug_session` — always close when done

**Languages:** Python, Node.js, TypeScript, browser JS, Go, Rust, Java, C#/.NET

**Anti-pattern:** Never add `print()` / `console.log()` to inspect runtime state when
mcp-debugger is available. Use `get_variables` instead.

**For complex debugging sessions:** Spawn `debug-agent` — it has this workflow built in.
Run `/boost` — Step 4c will confirm whether `mcp-debugger` is connected.

## Task Creation

For any multi-step or non-trivial work, call `TaskCreate` before starting. Mark the task `in_progress` when you begin it and `completed` when you finish. Don't batch completions — update each task as you go.

When in doubt, create the tasks first. It keeps the user informed and preserves progress through compaction.

## When to Use What

| Trigger | Action |
|---------|--------|
| Ticket pasted | Save verbatim to `[project]/workspace/[task-id]/ticket.md` (project-scoped; ClaudeBoost meta-work uses `$CLAUDEBOOST_HOME/workspace/[task-id]/ticket.md`), plan, then delegate |
| Complex feature (>5 files) | `/workspace` — creates plan, workspace, and agent routing |
| Before delegating agents | Run `/research-task [task-id]` to build Tier 3c workspace research — agents get task-specific docs auto-loaded via `/context`. Add URLs as arguments to curate sources manually; add `--approve` for the approval gate. |
| New codebase / first time in repo | `/index-project <path>` to enable semantic search, then `/research-project` for stack overview |
| New subsystem or >15 files | `/create-prd` before `/workspace` — locks down scope and acceptance criteria |
| Explaining architecture or flow | `/visualize` — interactive board in browser |
| Code just changed | `/xray` to check quality, then `/qa --code` to run tests + edge cases, then `/qa <url>` for browser verification if there's a UI |
| Security concern | `/security-review` — OWASP-aware review of pending branch changes |
| Something feels off after changes | `/audit` — parallel multi-angle assessment with Opus verdict |
| Code review | Spawn reviewer-agent (Opus) with verify gate |
| New architecture | Spawn architect-agent (Opus) with SOLID review |
| Ready to ship | `/done` — pre-push checklist then push |
| Context window filling up | `/clear-safe` to save state, then `/handoff` to document progress |
| Want to see what changed | `/changes` — interactive branch change explorer |
| Performance bottleneck | Spawn performance-agent |
| Logging / metrics gaps | Spawn observability-agent |
| After indexing a project | `/research-project` — builds domain expertise from the indexed codebase |

## Proactive Skill Suggestions

When a response naturally completes a phase or the user's message matches a trigger pattern, append a short "What's next?" suggestion. Use `knowledge/skill-routing.xml` (loaded via RAG) for the full trigger-to-skill catalog.

**Four rules — apply all before suggesting:**
1. One suggestion per response max. Don't stack hints.
2. Phrase it as an option: "Consider running /review to..." not "Run /review now."
3. Skip if the user is already mid-skill (they know what they're doing).
4. Skip for trivial one-liners where a suggestion would feel patronizing.

**Format — two surfaces, two styles:**
- **Mid-conversation hint** (proactive, inline): one or two sentences — `What's next: /skill-name — [one-line reason].`
- **Post-skill completion** (at the end of a command): the "What's Next After /skill" table in each command file — rows are `If X | Run Y`, placed after the final output block of the skill.

These are distinct. Don't use the table format for inline hints, and don't use the sentence format inside command files.

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

## RAG HTTP API

The RAG server exposes an HTTP REST API on port 8612. All RAG access — from Claude Code, scripts, agents, and external tools — uses this API directly. No MCP required. See `knowledge/rag-http-api.xml` for full docs.

## RAG Unavailable Protocol

When RAG tools are missing from your tool list OR return a connection/server error:

1. **STOP immediately** — no investigation, no agent spawning, no file reading as a substitute
2. Tell the user exactly: *"RAG is not connected. Run `/rag` to reconnect, then retry."*
3. Do NOT attempt to recover by grepping, reading files, or proceeding with degraded context
4. Do NOT rationalize past this — "I can be helpful anyway" is the wrong call

When RAG errors mid-task: `rag-error-guard.py` surfaces the error automatically. Still stop and report; do not continue.

The `session-primer.py` UserPromptSubmit hook injects a HARD STOP directive when the sentinel is missing — treat it as a hard requirement, not a soft suggestion.

**Agent spawn blocked by sentinel guard?** Run `/rag` immediately. Do not investigate the sentinel file, do not try to set it manually, do not look for workarounds. The block means `/rag` hasn't run this session — that's the fix, full stop.

## RAG Health Check Protocol

At the start of any investigation or multi-step codebase task:

1. **Call `GET http://127.0.0.1:8612/status` FIRST** — before loading context, before spawning agents.
   - Returns in under 1 second if the server is up.
   - If it fails: **STOP. Do not proceed.** Tell the user: "RAG server is not responding. Run `/rag` to start it."
2. **Then call `POST http://127.0.0.1:8612/context`** with `{"agent":"...","task_description":"...","project_path":"...","workspace_path":"..."}`
   - `project_path` = absolute path to the project being worked on (enables Tier 4 codebase search and stack detection for Tier 3 boost)
   - `workspace_path` = absolute path to the active workspace, e.g. `$CLAUDEBOOST_HOME/workspace/[task-id]` (enables Tier 3c task research). Omit only when no workspace exists for this task.
   - If the response contains an `"error"` key: **STOP. Do not proceed.** Report the error and tell the user to run `/rag`.
3. **Check the status response** for collection counts and indexed projects to spot stale indexes.
4. If index is stale (`reindex-check.py` warned at session start): POST /index with `{"project_path":"<path>","force":true}` before searching.

**Any RAG tool returning an error is a hard stop** — do not continue with degraded or missing context. Do not rationalize past it ("I can grep instead"). Stop and tell the user to fix RAG.

Do not skip the health check because "RAG seemed to work earlier" — indexes degrade silently and the server can disconnect between calls.

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
| **ClaudeBoost RAG** | Agents (`agents/`) + knowledge bases (`knowledge/`) indexed at `mcp-rag-server/.rag-index/` | `POST /search scope=agents/knowledge/all`, `POST /index`, `POST /context` |
| **Project RAG** | A specific project's source code, indexed per-project at `<project>/workspace/.rag-index/` | `POST /index`, `POST /search scope=codebase`, `/index-project` |
| **GraphRAG** | Structural code graph (imports, inherits) stored in `graph.db` alongside Project RAG | `POST /search scope=codebase mode=graph` — auto-built at index time, auto-augments `/context` Tier 4b |

When the user says "ClaudeBoost RAG" → they mean agents/knowledge.
When the user says "Project RAG" or "project index" → they mean the codebase index for whatever project they're working on.
`POST /context` combines both: tiers 0-3 pull from ClaudeBoost RAG, tier 4 pulls from Project RAG (vector), tier 4b pulls structural graph neighbours when a graph index exists.

**GraphRAG usage (always run both):**
- `POST /search` with `scope=codebase mode=vector` — semantic matches (required first call)
- `POST /search` with `scope=codebase mode=graph` — structural neighbours: imports, callers, inheritance (required second call)
- Run BOTH on every codebase query — vector and graph find different files; omitting either leaves a gap
- Graph index is built automatically during project indexing (POST /index) — no extra step needed
- Graph index degrades gracefully: if no `graph.db` exists, mode=graph falls back to vector results

**Parallel reindex pattern** (use when reindexing a project while doing other work):

Spawn a lightweight agent to run the reindex. The main agent stays unblocked.

Spawn prompt must include:
1. Call `POST http://127.0.0.1:8612/context` with `{"agent":"rag-indexing-agent","task_description":"reindex project at <path>"}` as first action
2. Call `POST http://127.0.0.1:8612/index` with `{"project_path":"<path>","force":true}`
3. Read the result: if `files_failed > 0`, log each entry in `errors[]` (file, type, message)
4. If `errors[]` contains `embed_error` entries: retry once with `force=True`; if still failing, report the specific files
5. Call `GET http://127.0.0.1:8612/status` and confirm graph shows `graph_active: true` for the project
6. Return summary: files_indexed, chunks_created, files_failed, elapsed_s, graph edges/resolved, any unresolved errors

**Reading reindex results** — POST /index returns:
- `files_indexed` — successfully embedded and stored
- `files_unchanged` — skipped (hash match, no change needed)
- `files_failed` — errored; check `errors[]` for details
- `errors[]` — `[{file, type: "read_error|embed_error", message}]` — only present if failures occurred
- `elapsed_s` — total time
- `graph.edges` / `graph.resolved` — graph index health

`files_failed > 0` is the signal that something went wrong. Zero failures = healthy index.

## TTS (Text-to-Speech)

Hook auto-speaks responses when enabled. **NEVER run edge-tts, speak-play.py, or `start` via Bash** — triggers permission prompts. Just respond normally.

- `/speak on|off` — toggle TTS
- `/speak voice <name>` — change voice
- `/speak voices` — list voices
