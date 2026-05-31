# Using ClaudeBoost

A practical guide to everything ClaudeBoost gives you and how to use it daily.

---

## 1. What ClaudeBoost gives you

ClaudeBoost turns Claude Code into a structured engineering team. You get 25 specialist agents (architect, security, performance, test, debug, and more), 96 knowledge files covering languages, frameworks, and engineering domains, a RAG search layer that routes the right knowledge to each agent automatically, and 41 slash commands covering your full development workflow. In CONSULT mode (the default), Claude proposes before making architectural decisions and waits for your approval — so you stay in control of the big calls while the agents handle the ground work. Gas Town, if installed, adds multi-agent coordination, persistent identity, and cross-session work tracking on top of all that.

The core idea is that most engineering tasks benefit from a specialist rather than a generalist. A security audit done by an agent that knows OWASP Top 10 and has the right knowledge pre-loaded is more reliable than asking the same question in open chat. A code review that runs 15 parallel passes is more thorough than a single pass. ClaudeBoost wires all of that up so you get it automatically — you don't have to think about which agent to use, which knowledge file to read, or whether a finding is verified. The system handles the routing; you handle the decisions.

---

## 2. Getting started

Install: see [SETUP-GUIDE.md](SETUP-GUIDE.md). The installer sets up the RAG server, links all 41 slash commands, hardlinks `CLAUDE.md` globally, and builds the initial vector index. It takes a few minutes the first time.

Then run `/boost` at the start of every session. That's the one mandatory step — it loads RAG, activates Gas Town if installed, and primes Claude with your project context. Without it, RAG isn't connected and the agents won't have access to the knowledge bases.

If you're working on a specific project and want semantic search over your codebase (not just the ClaudeBoost knowledge), run `/index-project <path>` once. That indexes your source files and builds the graph index. After that, Claude can find relevant files in your project by description rather than guessing file names.

---

## 3. Daily workflow

A typical session looks like this:

1. **Start the session** — run `/boost`. Don't skip it; RAG won't be connected without it.
2. **Kick off a task** — for simple things (a bug fix, a quick rename, a typo), just describe it. Claude will handle it directly. For anything complex — multi-file feature, ticket, architecture decision — run `/workspace <description>` first. That creates a tracked workspace folder and generates an implementation plan with agent routing.
3. **Review and approve** — in CONSULT mode, Claude pauses before adding new endpoints, tables, modules, or dependencies. It presents you with 2–3 options and their trade-offs. You pick one, add constraints if needed, then it proceeds. Approvals are logged so Claude won't re-ask about the same decision in the same session.
4. **Wrap up** — run `/done` when the work is ready to merge.

**If context fills up mid-task:** run `/clear-safe` before `/clear`. `/clear-safe` saves your workspace state so the next session can pick up exactly where you left off. In the new session, run `/boost` then `/restore`.

**Complexity tiers matter.** There are three thresholds:
- **5–10 files changed (FEATURE)**: workspace + agent delegation
- **More than 10 files (COMPLEX)**: workspace + implementation plan + multiple agents
- **More than 15 source files or a new subsystem (COMPLEX+)**: `/create-prd` first, then the above

For a one-line fix or a doc update, none of that applies. The system doesn't add ceremony unless the task warrants it.

**You don't need to manage agents manually.** Claude routes to the right ones based on what you're asking for. If you want a specific agent, use `/spawn-agent` or just say "have security-agent look at this." The agents always call `rag_context` as their first action — that's how they know what domain knowledge applies to the task. You'll see it in the output; it's expected behavior, not overhead.

---

## 4. Slash commands

### Session Management

| Command | What it does | Example |
|---------|-------------|---------|
| `/boost` | Connects RAG, loads Gas Town, primes the session. Run this first every time. | `/boost` |
| `/restore` | Reloads workspace state saved by your last `/clear-safe`. Use in a fresh session after `/clear`. | `/restore` |
| `/clear-safe` | Saves current workspace context before you clear. Prevents losing mid-task state. | `/clear-safe` |
| `/handoff` | Hands off to a fresh Gas Town session. Good for long-running tasks that need a clean context. | `/handoff` |
| `/compact-review` | Shows the critical state Claude will preserve during compaction. Run before compaction to verify nothing important gets lost. | `/compact-review` |

### Planning & Workspace

| Command | What it does | Example |
|---------|-------------|---------|
| `/workspace` | Creates a `workspace/[task-id]/` folder and produces a step-by-step implementation plan with agent routing. | `/workspace add OAuth login to the API` |
| `/explore` | Full ticket deep-dive: reads the ticket, explores the codebase, and builds an implementation plan. | `/explore` (paste ticket first) |
| `/plan-task` | Runs the planning phase without executing anything. Good when you want to review the plan before committing. | `/plan-task refactor the payment module` |
| `/create-prd` | Generates a PRD and task checklist for large features or new subsystems (>15 source files or a new subsystem). | `/create-prd new notifications system` |
| `/set-mode` | Sets the execution mode for a task to NORMAL or PERSISTENT. | `/set-mode PERSISTENT` |

### Agent Operations

| Command | What it does | Example |
|---------|-------------|---------|
| `/spawn-agent` | Spawns a named agent with RAG knowledge pre-loaded. | `/spawn-agent security-agent` |
| `/list-agents` | Lists all 25 agents with their expertise domains. | `/list-agents` |
| `/agent-status` | Shows current task status and what each agent has contributed. | `/agent-status` |

### Code Quality

| Command | What it does | Example |
|---------|-------------|---------|
| `/code-review` | 15-pass parallel review of the current branch: logic, security, performance, tests, patterns, and more. | `/code-review` |
| `/review` | Structured code review with a letter grade (A–F) and specific findings. | `/review` |
| `/security-review` | Security-focused review of pending branch changes, or a full project audit with `--full`. | `/security-review --full` |
| `/audit` | Breaks input into dimensions, spawns parallel auditors, synthesizes a verdict. Good for reviewing docs, architecture, or requirements. | `/audit` |
| `/self-improve` | Runs ClaudeBoost's own self-improvement audit — finds gaps in the config, agents, or knowledge files. | `/self-improve` |
| `/gate` | Compliance check before a task starts. Verifies standards, security rules, and required patterns are in place. | `/gate` |
| `/simplify` | Reviews recent code changes for reuse opportunities, quality issues, and efficiency. | `/simplify` |

### Testing

| Command | What it does | Example |
|---------|-------------|---------|
| `/end-to-end-test` | Runs browser E2E tests with Playwright and captures screenshot evidence. Discovers the app via RAG first, then writes and executes the test plan. | `/end-to-end-test` |

### RAG & Indexing

| Command | What it does | Example |
|---------|-------------|---------|
| `/index-project` | Indexes your project's source code for semantic search. Run once per project, then again after major structural changes. | `/index-project /path/to/myapp` |
| `/index-boost` | Reindexes ClaudeBoost's own agents and knowledge bases. Run after pulling a ClaudeBoost update. | `/index-boost` |
| `/research-rag` | Builds a workspace-scoped research index from URLs and PDFs, then queries it during implementation. | `/research-rag Stripe webhook integration` |

### Documentation

| Command | What it does | Example |
|---------|-------------|---------|
| `/update-docs` | Generates or refreshes project documentation in the `docs/` folder. | `/update-docs` |
| `/init` | Creates a `CLAUDE.md` with codebase documentation for the current project. | `/init` |
| `/generate-agents-md` | Generates an `AGENTS.md` from `CLAUDE.md` for cross-tool AI compatibility (Cursor, Copilot, etc.). | `/generate-agents-md` |
| `/visualize` | Generates an interactive architecture board and opens it in the browser. | `/visualize` |

### Git & Workflow

| Command | What it does | Example |
|---------|-------------|---------|
| `/commit-message` | Generates a conventional commit message from staged changes. | `/commit-message` |
| `/done` | Submits completed work to the merge queue. | `/done` |
| `/dependency-update` | Safe one-at-a-time dependency update with audit, license check, and rollback plan. | `/dependency-update` |
| `/changes` | Opens an interactive explorer showing what changed and why. | `/changes` |

### Configuration

| Command | What it does | Example |
|---------|-------------|---------|
| `/update-config` | Configures Claude Code settings, hooks, and permissions in `settings.json`. | `/update-config allow npm commands` |
| `/set-permissions` | Manages project-level Claude Code permissions. | `/set-permissions` |
| `/set-global-permissions` | Manages global Claude Code permissions in `~/.claude/settings.json`. | `/set-global-permissions` |
| `/keybindings-help` | Customizes keyboard shortcuts in `~/.claude/keybindings.json`. | `/keybindings-help` |
| `/statusline` | Configures the Claude Code status line display. | `/statusline` |
| `/speak` | Toggles text-to-speech on or off. | `/speak on` |

### Collaboration Modes

| Command | What it does | Example |
|---------|-------------|---------|
| `/auto` | Switches to AUTO mode — Claude acts without consulting on architectural decisions. | `/auto prototyping a new feature` |
| `/consult` | Returns to CONSULT mode (the default). Claude will propose before acting on architectural changes. | `/consult` |

### Utilities

| Command | What it does | Example |
|---------|-------------|---------|
| `/check-task` | Validates a task folder's structure and completeness. | `/check-task` |
| `/check-completion` | Verifies whether a task's completion criteria are met. | `/check-completion` |
| `/mcp-builder` | Step-by-step guide for building a high-quality MCP server in TypeScript or Python. | `/mcp-builder` |
| `/insights` | Generates a report analyzing your Claude Code session patterns and usage. | `/insights` |
| `/team-onboarding` | Creates an onboarding guide for teammates ramping up on Claude Code. | `/team-onboarding` |

---

## 5. Agents

All 25 agents are spawned automatically based on task type, or you can call them directly with `/spawn-agent`. Opus agents run on Claude's most capable model and are used for tasks that need deep reasoning or high-stakes judgment. Sonnet handles everything else — it's fast, strong at code, and handles the bulk of the work.

| Agent | What it does | Best for | Model |
|-------|-------------|----------|-------|
| architect-agent | Designs systems, reviews SOLID principles, produces grounded architectural proposals | Designing a new module or deciding between two approaches | Opus |
| reviewer-agent | Code review, PR review, verify-gate evaluation | Pre-merge review or confirming findings from other agents | Opus |
| ticket-analyst-agent | Parses tickets, extracts requirements, defines done criteria | Turning a vague ticket into a clear implementation plan | Opus |
| debug-agent | Bug diagnosis, root cause analysis | Tracking down a regression or a crash that only reproduces in production | Sonnet |
| refactor-agent | Code restructuring, cleanup, rename campaigns | Paying down technical debt across multiple files | Sonnet |
| test-agent | Unit/integration tests, TDD, coverage analysis | Adding tests to untested code or writing tests first | Sonnet |
| e2e-agent | End-to-end browser testing with Playwright | Verifying a user flow works from login to checkout | Sonnet |
| browser-agent | Browser automation, DOM inspection, UI verification | Checking that a UI element renders correctly across states | Sonnet |
| ui-agent | Frontend components, React, accessibility | Building a new component or auditing for a11y issues | Sonnet |
| security-agent | OWASP Top 10, auth/authz, injection detection | Auditing a new endpoint or reviewing a login flow | Sonnet |
| performance-agent | Profiling, N+1 detection, caching strategy | Diagnosing slow page loads or database query bottlenecks | Sonnet |
| database-agent | Schema design, migrations, query optimization | Designing a new table or reviewing a slow query plan | Sonnet |
| devops-agent | CI/CD, Docker, deployment scripts | Writing a GitHub Actions workflow or Dockerizing an app | Sonnet |
| observability-agent | Logging strategy, tracing, metrics setup | Adding structured logging to a service or setting up distributed tracing | Sonnet |
| docs-agent | Documentation, README, API docs | Writing a README, API reference, or inline documentation | Sonnet |
| research-agent | Web research, library comparison, investigation | Comparing two libraries before picking one | Sonnet |
| research-rag-agent | Builds a persistent research RAG from URLs and PDFs | Deep research into an external API's docs before implementing | Sonnet |
| explore-agent | Codebase discovery, file mapping, dependency tracing | Mapping an unfamiliar codebase before starting work | Sonnet |
| workflow-agent | Multi-step task orchestration | Coordinating a sequence of dependent sub-tasks | Sonnet |
| compliance-agent | Standards compliance, rule enforcement | Verifying a feature against regulatory or internal standards | Sonnet |
| standards-validator-agent | Coding standards validation, pattern enforcement | Checking whether new code follows project conventions | Sonnet |
| estimator-agent | Story pointing, complexity estimation | Estimating effort for a sprint backlog | Sonnet |
| evaluator-agent | Verify-gate — validates findings from other agents | Confirming a security or bug finding is real before it reaches you | Sonnet |
| rag-indexing-agent | RAG index management, re-indexing advice | Diagnosing stale or broken index state | Sonnet |

The `_orchestrator` meta-agent is internal — it coordinates agent spawning and doesn't appear in `/list-agents`.

### How agents are routed

Claude decides which agents to spawn based on what you're asking for. A bug report goes to debug-agent. A "please review this PR" goes to reviewer-agent (Opus). A new feature with database changes gets architect-agent for the design, then database-agent for the schema, then test-agent for coverage. You don't pick them manually unless you want to.

Agents run in parallel when context allows it:

- **Context below 50%**: up to 3 agents at once
- **Context 50–75%**: up to 2 agents at once
- **Context above 75%**: sequential only — one at a time

If a task needs more than 3 agents, they run in batches with a compact step between batches. This prevents the context from exploding, which would cause a "conversation too long" error mid-task. Each batch completes, its findings get written to `context.md`, then the next batch starts.

Spawning with `run_in_background: true` is sometimes used for agents that don't need to block the main flow — Claude can continue with other work and check in on the background agent when it finishes.

### When to use Opus vs Sonnet

Three agents always run on Opus regardless of context: `architect-agent`, `reviewer-agent`, and `ticket-analyst-agent`. These are the ones doing deep architectural reasoning, high-stakes evaluation, and requirements interpretation — tasks where the quality difference between Opus and Sonnet is most visible.

Opus can also be escalated for other agents when stakes are high: production-critical code, auth systems, payment flows, or when a Sonnet agent reports it's blocked and needs more reasoning depth.

Everything else runs on Sonnet. It handles code generation, testing, debugging, documentation, and most implementation work well, and it's significantly faster.

---

## 6. RAG tools

ClaudeBoost runs two separate indexes. Knowing which is which saves confusion.

### Two indexes

**ClaudeBoost RAG** — the agents and knowledge base index. Built from `agents/*.xml` and `knowledge/*.xml`, stored at `mcp-rag-server/.rag-index/`. This is what Claude searches when it needs to know how to apply a coding standard, which agent to use, or how to handle a specific domain. You rebuild it with `/index-boost` after pulling a ClaudeBoost update.

**Project RAG** — your project's source code, indexed per-project at `<project>/workspace/.rag-index/`. This is what Claude searches when it needs to find a specific file, function, or pattern in *your* codebase. It doesn't exist until you run `/index-project <path>`. After that, it's automatically available during any work on that project.

### MCP tools

These run behind the scenes. You won't usually call them directly, but they're available if you want to query manually, and understanding what they do explains why the system behaves the way it does.

**`rag_search`** — semantic search across either index. Key scope options:
- `scope=agents` — search agent definitions only
- `scope=knowledge` — search knowledge bases only
- `scope=all` — search both ClaudeBoost indexes
- `scope=codebase` — search your project's source code (requires `/index-project` first)
- Add `mode=graph` to `scope=codebase` for structural neighbors — files that import from or are inherited by the seed files. Falls back to vector if no graph index exists.

The graph mode is useful when you need to understand ripple effects: "what files import this module?", "what changes if I modify class Foo?". The vector mode (default) is better for semantic questions: "where is payment processing handled?", "find the auth middleware."

**`rag_context`** — the tool every agent calls as its first action. It assembles a curated context package: the right agent definition, relevant knowledge chunks, and (if available) matching codebase results. It works in tiers: agent definition first, then relevant knowledge, then project code. This is what makes each agent smart about its domain without loading the entire knowledge base into context every time. If you see an agent getting started and it calls `rag_context` first, that's expected and required — it's the mandatory first step for every agent.

**`rag_index`** — reindexes the ClaudeBoost knowledge and agent files. Called by `/index-boost`. Run manually if you've added or edited knowledge files directly and want the changes picked up immediately.

**`rag_status`** — health check for the RAG server. Shows unresolved graph edges, index errors, stale collections, and whether the server is running. If search results seem wrong or incomplete, or if an agent seems to be missing obvious knowledge, run this first. Stale indexes fail silently — they return results, just not the right ones.

### When to reindex

- After pulling a ClaudeBoost update: `/index-boost`
- After adding or significantly changing project source files: `/index-project <path>`
- If `rag_status` shows a stale index: `/index-project <path>` (force mode)
- If RAG isn't connected at all: run `/boost` to reconnect — don't try to work around it by reading files manually

The RAG unavailability protocol is strict: if RAG is down, stop, run `/boost`, and retry. Don't substitute grep or file reads for RAG when it's offline. The system is designed to use RAG as the entry point for knowledge — bypassing it produces degraded results and skips guardrails.

---

## 7. CONSULT vs AUTO mode

### CONSULT (default)

Claude researches and proposes before taking any architectural action, then waits for your input. The full loop is:

1. Claude searches RAG and reads 2–3 relevant files
2. Spawns `architect-agent` (Opus) to produce options grounded in your actual codebase
3. Presents you with 2–3 options, each with a one-sentence trade-off
4. You pick, adjust, or write in a new option
5. Claude implements the approved choice plus any constraints you added
6. The decision is logged to `state/session-approvals.json` so Claude won't re-ask about the same axis later in the session

CONSULT kicks in for:

- New API endpoints or routes
- New database tables or schema changes
- New modules, packages, or significant dependencies
- New middleware or auth strategies
- New config keys that affect runtime behavior
- Any new concurrency pattern or external API integration

It doesn't kick in for: bug fixes, test changes, documentation, config tweaks, file renames, or edits inside `workspace/`, `.claude/`, `knowledge/`, or `plans/`.

Security standards (parameterized queries, `logger.error` in catch blocks, input validation, auth checks) are always applied automatically — they're not part of the proposal. They're not up for debate.

One practical note: once you approve a decision for a given architectural axis in a session, Claude logs it to `state/session-approvals.json` and won't re-consult on the same axis. If you approved "use Zod for input validation" earlier in the session, the next endpoint doesn't trigger another proposal for that same question. The approval persists until the session ends.

### AUTO mode

Claude proceeds without consulting. Good for prototyping, solo sessions where you know exactly what you want, or when CONSULT is slowing you down on work that's clearly low-risk.

```
/auto building a quick prototype
```

To return to CONSULT:

```
/consult
```

The mode persists for the current session. Every new session starts in CONSULT by default. If you find yourself running `/auto` at the start of every session, that's worth examining — it might mean CONSULT is triggering on things it shouldn't, which is something to feed back.

Note that non-negotiable standards still apply in AUTO mode. Parameterized queries, error logging, input validation — those aren't gated on CONSULT. They're applied regardless of mode.

---

## 8. The verify gate

ClaudeBoost prevents unverified findings from reaching you. When an agent reports a security issue, a bug, or a high-severity finding, that finding has to be backed by actual code evidence — a specific file path and line number — before it shows up in your results. If it isn't, `evaluator-agent` is spawned to independently check it.

This matters because an LLM that found a bug and is then asked "is this bug real?" will often say yes, using the same flawed reasoning that produced the finding in the first place. `evaluator-agent` runs in a completely fresh context with no knowledge of the original finding — it reads only the cited file:line evidence and gives an independent verdict. If it can't confirm the finding from the evidence, the finding is dropped.

From your perspective, this means two things. First, findings you see have been verified against actual code. Second, "no issues found" is always a valid outcome. The agents aren't trying to find something impressive — they're trying to find something real. A clean result is a good result.

Every finding in a review, audit, or security scan must include a `file:line` citation before the orchestrator accepts it. Agents that report BLOCKER or HIGH severity findings without citations are blocked — the finding is marked `NEEDS_VERIFICATION` and escalated to `evaluator-agent` before it reaches you.

---

## 9. Workspace internals

When you run `/workspace` or `/explore`, ClaudeBoost creates a `workspace/[task-id]/` folder with this structure:

```
workspace/
└── my-feature-2024-01-15/
    ├── ticket.md      # Verbatim original ticket — never modified after creation
    ├── context.md     # Living task state: findings, agent contributions, next steps
    ├── mockups/       # Design references, specs, input images
    ├── outputs/       # Generated artifacts, final deliverables
    └── snapshots/     # Screenshots, progress captures, before/after comparisons
```

`ticket.md` is immutable after creation. All agents reference it as the single source of truth for what was asked. If the requirements change, that's a conversation — not an edit to `ticket.md`.

`context.md` is the living record of everything that's happened on the task. It's updated after every significant finding — not on a schedule, but whenever something worth capturing happens: a RAG search that turns up a relevant file, a root cause identified, an architectural decision made. The sections Claude maintains are: current status, what was found and why it matters, next step, and open questions.

`context.md` is what keeps tasks resumable across sessions. It's designed to survive a `/clear` — everything that would otherwise live only in context gets written here. When you run `/restore` in a new session, Claude reads `context.md` and picks up exactly where you left off, without you re-explaining the task history.

For tasks involving UI work, `snapshots/` is where before/after screenshots go. For tasks that produce files (a generated config, a migration, a report), those land in `outputs/`. The folder structure is consistent across all tasks, so it's easy to navigate even if you haven't touched a workspace in weeks.

---

## 10. Gas Town (if installed)

Gas Town adds a coordination layer on top of ClaudeBoost. Without it, ClaudeBoost still works fully — you get all the agents, knowledge, RAG, and slash commands. Gas Town is optional infrastructure for teams or for long-running work that spans many sessions.

What it adds:

- **Persistent identity** — agents have a stable identity across sessions, not just a task description
- **Work tracking (beads)** — each unit of work is tracked and can be handed off cleanly
- **Cross-session handoffs** — `gt handoff` passes a live session to a fresh context without losing state
- **Directives** — structured role definitions that shape how agents in a group behave

Key commands:

| Command | What it does |
|---------|-------------|
| `gt prime` | Prime the current session with Gas Town context and active work state |
| `gt sling` | Dispatch a task to an agent (polecat dispatch) |
| `gt handoff` | Hand off the current session cleanly to a new context |
| `gt mail` | Send a message to another agent or session |
| `gt nudge` | Nudge a stalled session back into motion |

Gas Town uses three directive types: `mayor.md` (town-wide rules that apply to all agents), `polecat.md` (individual agent roles and responsibilities), and `witness.md` (observer role for recording decisions without acting on them).

For install instructions, see [SETUP-GUIDE.md](SETUP-GUIDE.md).

---

## 11. Common task patterns

### 1. Fix a bug

Describe the bug and what you expected to happen. Claude spawns `debug-agent`, which works through a systematic process: reproduce the issue, read the relevant files, identify the root cause, and propose a fix. After the fix, it spawns `test-agent` to add a regression test so the same bug can't come back undetected.

For simple bugs where the cause is obvious, Claude handles it directly without spinning up agents. The decision is automatic — don't second-guess it.

### 2. Review code or a PR

```
/code-review
```
or for a lighter structured pass:
```
/review
```
Both spawn `reviewer-agent` (Opus). `/code-review` runs 15 parallel passes covering security, performance, patterns, test coverage, logic, and clarity. `/review` gives you a structured A–F grade with specific findings and a recommended action for each. All findings from both commands go through the verify gate — every flag needs a `file:line` citation before it reaches you.

### 3. Add a new feature

```
/workspace add payment plan support to the subscription API
```
This creates a workspace folder, runs a planning sweep across testing, security, architecture, performance, and other domains, and identifies which agents to use for each phase. In CONSULT mode, any new endpoints, tables, or dependencies will trigger a proposal before Claude writes any code. You get the architectural options with trade-offs, pick one, and implementation proceeds.

For large features (more than 15 source files, or a new subsystem), use `/create-prd` first. That generates a proper requirements document and task breakdown before any code is written.

### 4. Write tests

For unit and integration tests: describe what needs testing. Claude spawns `test-agent`, which reads the code being tested, identifies the important cases (happy path, edge cases, error conditions), and writes tests that actually fail when the behavior breaks — not just tests that exist on paper.

For browser E2E tests:
```
/end-to-end-test
```
`e2e-agent` uses Playwright, discovers the running app via RAG, writes a test plan, executes it against localhost, and captures screenshots at each step as evidence. Requires a running local server — it won't test against external URLs.

### 5. Security audit

```
/security-review
```
Reviews the current branch by default. Add `--full` for a whole-project audit. Covers OWASP Top 10, auth/authz patterns, injection vectors, hardcoded secrets, insecure defaults, and misconfigured headers. All findings are independently verified by `evaluator-agent` before they reach you — no unverified flags.

### 6. Research a library or API

```
/research-rag Stripe Connect integration patterns
```
`research-rag-agent` fetches the relevant docs (URLs or PDFs you point it at), builds a workspace-scoped index, and makes that knowledge searchable during implementation. The index is persistent for the task — not global. After the task is done, it's not maintained, so don't reuse it across tasks.

For lighter research (quick library comparison, answering a specific question), just ask. `research-agent` does web lookups and synthesizes results without building a persistent index.

### 7. Refactor messy code

Describe what needs cleaning up — a function that's grown too large, a module with unclear responsibilities, a naming convention that got inconsistent across the codebase. Claude spawns `refactor-agent`, which restructures and renames while keeping behavior the same.

For rename campaigns that touch many files, `refactor-agent` searches all occurrences first and lists every match before changing anything. That's intentional — the rule is to grep before touching, then update all occurrences in one pass. No silent partial updates.

### 8. See the architecture

```
/visualize
```
Generates an interactive board of your project's architecture and opens it in the browser. Shows the layers of the system, how components connect, and where decisions were made. Useful for onboarding a new team member, planning a large change, or just getting reoriented in a codebase you haven't touched in a while.

### 9. Context window full mid-task

This happens on long sessions. The fix is:

```
/clear-safe
```
Then `/clear` to clear the context. In the new session:
```
/boost
/restore
```
`/clear-safe` saves your workspace state: what task you were on, what was found, what's next, which files are relevant. `/restore` reads that state in the new session and resumes from where you left off. You don't re-explain the task.

The key is running `/clear-safe` *before* `/clear`, not after. Once you clear the context, that information is gone if you didn't save it.

### 10. Review what changed

```
/changes
```
Interactive explorer of recent changes with context. Good for writing a commit message, doing a final pre-merge pass, or confirming that every file you meant to change actually changed (and nothing extra snuck in). It shows the diff with the reasoning behind each change, not just the raw diff.


---

## 12. How hooks work

ClaudeBoost installs several hooks that run automatically in the background. You will see their effects but usually do not interact with them directly.

**Session start hook** - runs when Claude Code starts. It checks whether `/boost` has been run this session and injects the CONSULT/AUTO mode protocol into context. If the sentinel is missing (meaning `/boost` has not run), it blocks task spawning until you run `/boost`.

**Pre-task hook** - fires before any agent is spawned via the Task tool. It checks that `rag_context` is included in the spawn prompt. If it is not, the spawn is blocked (exit code 2). This enforces the "RAG first" contract that keeps agents from running with empty context.

**Post-task hook** - fires after every agent completes. It nudges the orchestrator to check agent output for unverified BLOCKER/HIGH findings and spawn `evaluator-agent` if needed. It is an LLM nudge, not a mechanical block - the orchestrator has to act on it.

**Pre-write hook** - fires before Edit or Write tool calls. It checks whether the change qualifies as an architectural decision and reminds the orchestrator to go through the CONSULT protocol if so.

**Context nudge hook** - fires every 5 file reads as a reminder to update `context.md` with recent findings. The workspace update protocol says to update proactively, not wait for this trigger - but it is a fallback in case Claude gets deep in exploration mode and forgets.

**Reindex check hook** - runs at session start and warns if the RAG index is stale based on the last-modified timestamps of indexed files. If it fires, run `/index-boost` before starting work.

You will not see most of these. They run silently unless there is a problem, in which case they surface a clear message explaining what to fix and how. If a hook error blocks something unexpected, the message will tell you the exact command to run to unblock it.

---


---

## Tips

**Do not over-describe tasks.** A clear one-sentence description works better than a paragraph. Claude searches for context it needs - you do not have to pre-explain every file involved.

**Let the CONSULT proposals happen.** It is tempting to switch to AUTO to move faster, but the proposal step catches assumptions you would otherwise miss. Most proposals take under a minute. If a specific axis keeps coming up unnecessarily, note it - that is feedback that the trigger logic could be tuned.

**Use `/changes` before committing.** It gives you a clean view of everything that changed and why, which makes commit messages easier and catches any unintended edits.

**If something seems slow or wrong with RAG**, run `rag_status` before anything else. Most search quality problems are stale index problems, and they are easy to fix.

**For big tasks, start with `/explore` not `/workspace`.** `/explore` does a deeper ticket analysis and codebase exploration pass before generating the plan. `/workspace` is faster but assumes less investigation is needed. Use `/explore` when you have a ticket with real complexity.

**Keep your project indexed.** `/index-project` runs in a few minutes for most projects. After that, every agent working on that project gets codebase-aware search at no extra cost. The index persists - you only need to rerun it after significant structural changes.

---

## Appendix: Knowledge base coverage

The 96 knowledge files are loaded automatically by RAG — you don't pick them manually. RAG matches them based on what you're working on.

**Domain bases (46 files)** cover: api-design, architecture, branching-strategy, code-critique, code-exploration, coding-standards, consult-mode, context-engineering, database, debugging, devops, documentation, e2e-testing, error-handling, human-voice, memory-management, model-selection, observability, performance, playwright, pr-review, refactoring, research, security, testing, ticket-understanding, tool-design, ui-implementation, verify-gate, workflow, and more.

**Language guides (17 files, `lang-*.xml`)** cover C#, Go, Java, JavaScript, Kotlin, Python, Rust, Swift, TypeScript, and others — each with idioms, common pitfalls, and language-specific standards. These load when the language appears in the task description or in the files being edited.

**Framework guides (33 files, `fw-*.xml`)** cover ASP.NET Core, React, Vue, Angular, Next.js, Django, FastAPI, Spring Boot, Android Compose, iOS SwiftUI, and more. Including the framework name in your task description (e.g., "fix bug in React component") pulls in the right guide automatically. Both the language and framework guides can load at the same time — a TypeScript React task gets both.

If you want to see which knowledge files would be relevant to a specific task before starting, run:

```
rag_search(scope="all", query="<describe your task>")
```

That shows you exactly what RAG would surface for that work.

---

