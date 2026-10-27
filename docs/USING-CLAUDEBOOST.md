# Using ClaudeBoost

A practical guide to everything ClaudeBoost gives you and how to use it daily.

---

## 1. What ClaudeBoost gives you

ClaudeBoost turns Claude Code into a structured engineering team. You get six pipeline agents (researcher, swiper, research-agent, bad-cop, good-cop, quick-cop), a RAG search layer over the projects you index, and slash commands covering your full development workflow. In CONSULT mode (the default), Claude proposes before making architectural decisions and waits for your approval — so you stay in control of the big calls while the agents handle the ground work.

The core idea is that most engineering tasks benefit from a specialist rather than a generalist. A security audit done by an agent that knows OWASP Top 10 and has the right knowledge pre-loaded is more reliable than asking the same question in open chat. A code review that runs 15 parallel passes is more thorough than a single pass. ClaudeBoost wires all of that up so you get it automatically — you don't have to think about which agent to use, which knowledge file to read, or whether a finding is verified. The system handles the routing; you handle the decisions.

---

## 2. Getting started

Install: see [SETUP-GUIDE.md](SETUP-GUIDE.md). The installer sets up the RAG server, links all slash commands, hardlinks `CLAUDE.md` globally, and builds the initial vector index. It takes a few minutes the first time.

Then run `/boost` at the start of every session. That's the one mandatory step — it loads RAG and primes Claude with your project context. Without it, RAG isn't connected and the agents can't search your indexed projects.

If you're working on a specific project and want semantic search over your codebase (not just the ClaudeBoost knowledge), run `/index-project <path>` once. That indexes your source files and builds the graph index. After that, Claude can find relevant files in your project by description rather than guessing file names.

---

## 3. Daily workflow

A typical session looks like this:

1. **Start the session** — run `/boost`. Don't skip it; RAG won't be connected without it.
2. **Kick off a task** — for simple things (a bug fix, a quick rename, a typo), just describe it. Claude will handle it directly. For anything complex — multi-file feature, ticket, architecture decision — run `/workspace <description>` first. That creates a tracked workspace folder and generates an implementation plan with agent routing.
3. **Review and approve** — in CONSULT mode, Claude pauses before adding new endpoints, tables, modules, or dependencies. It presents you with 2–3 options and their trade-offs. You pick one, add constraints if needed, then it proceeds. Approvals are logged so Claude won't re-ask about the same decision in the same session.
4. **Wrap up** — run `/done` when the work is ready to merge.

**If context fills up mid-task:** run `/clear-safe` before `/clear`. `/clear-safe` saves your workspace state so the next session can pick up exactly where you left off. In the new session, run `/boost` — the SessionStart hook restores your workspace context automatically.

**Complexity tiers matter.** There are three thresholds:
- **5–10 files changed (FEATURE)**: workspace + agent delegation
- **More than 10 files (COMPLEX)**: workspace + implementation plan + multiple agents
- **More than 15 source files or a new subsystem (COMPLEX+)**: `/create-prd` first, then the above

For a one-line fix or a doc update, none of that applies. The system doesn't add ceremony unless the task warrants it.

**You don't need to manage agents manually.** Claude routes to the right ones based on what you're asking for. If you want a specific agent, just tell Claude — for example, "have bad-cop look at this." They search with `POST http://127.0.0.1:8613/search` against your indexed projects. You'll see it in the output; it's expected behavior, not overhead.

---

## 4. Slash commands

Most slash commands are used internally by agents — you rarely call them directly. The ones you'll reach for in day-to-day work are:

| Command | When to use it |
|---------|---------------|
| `/boost` | Start of every session |
| `/workspace` | Any complex task, multi-file feature, or ticket |
| `/xray` | Quick A-F grade; add `--deep` for the full 16-pass parallel review |
| `/audit` | Verify a plan, a config, a document, or agent output |
| `/index-project` | Once per project, then after major structural changes |
| `/qa` | Full QA session — browser testing with screenshot evidence (auto-detects server), or general code/artifact QA with `--code` / file path / workspace ID. Both modes write a report with explicit coverage gaps. |

Everything else in the tables below is available, but most of it runs automatically — you won't need to invoke it by name unless you have a specific reason.

---

### Session Management

| Command | What it does | Example |
|---------|-------------|---------|
| `/boost` | Connects RAG, primes the session, and restores workspace context automatically if you ran `/clear-safe` in the last session. Run this first every time. | `/boost` |
| `/rag-health [target]` | Health check on the clean-rag server and one indexed project. Every check produces PASS, WARN, or FAIL. Targets: `project` (the default, the current directory), an absolute path, `boost`, `task`, `all`. | `/rag-health project` |
| `/clear-safe` | Saves current workspace context before you clear. Prevents losing mid-task state. | `/clear-safe` |
| `/handoff` | Saves session state and prepares for a fresh context. Good for long-running tasks that need a clean start. | `/handoff` |

### Planning & Workspace

| Command | What it does | Example |
|---------|-------------|---------|
| `/workspace` | Creates a `workspace/[task-id]/` folder and produces a step-by-step implementation plan with agent routing. | `/workspace add OAuth login to the API` |
| `/explore` | Full ticket deep-dive: reads the ticket, explores the codebase, and builds an implementation plan. | `/explore` (paste ticket first) |
| `/create-prd` | Generates a PRD and task checklist for large features or new subsystems (>15 source files or a new subsystem). | `/create-prd new notifications system` |
| `/ws [id]` | Shows all workspaces for the current project with status and last-edited time. Pass a workspace ID or partial name to switch the active workspace. Pass `off` to clear the active workspace. | `/ws` or `/ws add-auth` |
| `/graph [task-id]` | Builds a "Files in Scope" map by running both vector and graph RAG seeded from ticket entities. Vector search finds semantically similar files; graph search finds structural neighbors. Use at task start to get a navigation map before agents begin. | `/graph add-auth-2026-06-01` |


### Code Quality

| Command | What it does | Example |
|---------|-------------|---------|
| `/xray` | Quick A-F grade by default. Add `--deep` for the full 16-pass parallel review: logic, security, performance, tests, patterns, and more. Supports `--staged`, `--branch`, `--pr <url>`. | `/xray --deep` |
| `/security-review` | Security-focused review of pending branch changes, or a full project audit with `--full`. | `/security-review --full` |
| `/audit` | Breaks input into dimensions, spawns parallel auditors, synthesizes a verdict. Good for reviewing docs, architecture, or requirements. | `/audit` |
| `/self-improve` | Runs ClaudeBoost's own self-improvement audit — finds gaps in the config, agents, or knowledge files. | `/self-improve` |
| `/simplify` | Built into Claude Code, not shipped by this repo. Cleans up the changed code for reuse, simplification, and efficiency, and applies the fixes. It does not hunt for bugs; `/code-review` does that. | `/simplify` |

### Debugging

| Command | What it does | Example |
|---------|-------------|---------|
| `/debug [target]` | Full debugging session in one command. Pass an error message, a `file:line`, or describe what's broken. It classifies the mode automatically: static analysis for logic issues, live step-through with mcp-debugger for runtime failures. Supports Python, .NET/ASP.NET, Go, Node.js, TypeScript, Java, and Rust. Also handles test-runner attach workflows (xUnit, pytest, Jest, JUnit). Outputs a Bug Analysis Report. | `/debug "NullReferenceException in OrdersController"` or `/debug app.py:42` |

### Testing

| Command | What it does | Example |
|---------|-------------|---------|
| `/qa` | Dual-mode QA session. **Browser mode** (default): auto-detects or starts the dev server, builds a full app inventory via RAG + graph traversal, writes a risk-prioritized test plan, and executes browser tests with screenshot evidence. **General mode**: charter-based code/artifact QA — runs the existing test suite, writes edge case tests, and produces a session report with findings. | `/qa` or `/qa http://localhost:3000 auth` or `/qa --code` or `/qa scripts/my-hook.py` |
| `/test-hooks` | Runs the ClaudeBoost hook test suite to verify all hook scripts behave correctly. Run this after any hook change, after setup, or any time you pull ClaudeBoost updates that touch scripts. | `/test-hooks` |

### RAG & Indexing

| Command | What it does | Example |
|---------|-------------|---------|
| `/index-project` | Indexes your project's source code for semantic search. Run once per project, then again after major structural changes. | `/index-project /path/to/myapp` |

### Documentation

| Command | What it does | Example |
|---------|-------------|---------|
| `/init` | Built into Claude Code, not shipped by this repo. Creates a `CLAUDE.md` with codebase documentation for the current project. | `/init` |
| `/visualize` | Generates an interactive architecture board and opens it in the browser. | `/visualize` |
| `/walkthrough` | Generates a step by step tutorial with annotated screenshots. Drives a live app through Playwright, injects visual highlights, numbered callouts, arrows, and popovers, then assembles a polished markdown doc. | `/walkthrough http://localhost:3000 login flow` |

### Git & Workflow

| Command | What it does | Example |
|---------|-------------|---------|
| `/done` | Submits completed work to the merge queue. | `/done` |
| `/pr-description` | Generates a PR title and description following project conventions. | `/pr-description` |
| `/changes` | Opens an interactive explorer showing what changed and why. | `/changes` |
| `/ticket-handoff [ticket-id] [handoff-to]` | Generates a filled handoff document using the team Confluence template and copies it to the clipboard as rich HTML so it pastes correctly into Confluence. Includes current status, branch, next steps, and outstanding blockers. | `/ticket-handoff ASC-1175 sarah` |

### Configuration

| Command | What it does | Example |
|---------|-------------|---------|
| `/auto` | Switches to AUTO mode — Claude acts without consulting on architectural decisions. | `/auto prototyping a new feature` |
| `/consult` | Returns to CONSULT mode (the default). Claude will propose before acting on architectural changes. | `/consult` |
| `/speak` | Toggles text-to-speech on or off. | `/speak on` |
| `/bash-guard [on\|off\|status]` | Toggles the Bash safety guard. The guard blocks command shapes that trip Claude Code's permission prompts (compound `cd &&`, multiline `python -c`, heredocs, bare `$VAR` expansion). Turn it off when those blocks get in the way; turn it back on to restore the safety net. | `/bash-guard off` |
| `/boost verify` | Health check. Among other things it reports hook events missing from `~/.claude/settings.json` and offers to repair them by re-running `scripts/setup.py`, which is idempotent. For a per hook check that every registered script exists and compiles, run `python scripts/audit-hooks.py`. Run after pulling updates or if hooks seem to not be firing. | `/boost verify` |
| `/edit-state [key] [value]` | Shows all ClaudeBoost state values (mode, RAG enforcement, TTS, active workspace, intent override). Pass a key and value to update one. Useful for debugging unexpected behavior or manually overriding state. | `/edit-state` or `/edit-state mode auto` |
| `/telemetry` | Shows per-session telemetry stats for the active workspace: tool calls by type, RAG search calls, DB breakdown, and latency percentiles. Useful for understanding what Claude spent time on during a session. | `/telemetry` |
| `/uninstall [--purge] [--dry-run]` | Reverses everything the installer (`scripts/setup.py`) installed: hooks, env vars, statusLine, symlinks, and the RAG server MCP registration. Always shows a dry-run preview first and asks for confirmation. Add `--purge` to also pip-uninstall the RAG server, delete indexes, and strip PATH edits. | `/uninstall --dry-run` |


---

## 5. Agents

Six agents run the pipeline. Claude spawns them for you; you can also ask for one
by name.

| Agent | What it does | Best for | Model |
|-------|-------------|----------|-------|
| researcher | Reads the codebase through clean-rag's index and import graph, and researches the general engineering standard for the change | Understanding an unfamiliar codebase, or working out how this kind of change is normally built | Sonnet |
| swiper | Checks whether the thing already exists, in your project, the stdlib, a dependency, GitHub or StackOverflow, and hands back the exact lines to take | Before writing anything from scratch | Sonnet |
| research-agent | Web research on untrusted pages. Cannot write files, and its Bash only reaches the local clean-rag server | Comparing two libraries before picking one | Sonnet |
| bad-cop | Writes tests aimed at breaking your change, runs them, and reports the real failures with output attached. Never fixes anything | After any real code change | Sonnet |
| good-cop | Reproduces each of bad-cop's findings, researches the fix, applies it, gets the suite green | Only when bad-cop found something Critical or High | Opus |
| quick-cop | Reads the code and says whether a single "it is done" claim is true. Non blocking, stamps nothing | Any time something is declared finished | Sonnet |

Claude Code's own built-ins (`Explore`, `Plan`, `general-purpose`) are available
alongside these.

This table used to list 24 agents. Twenty-two of them, including
architect-agent, reviewer-agent, ticket-analyst-agent, debug-agent and
security-agent, do not exist and cannot be spawned. Read any older reference to
one of those names as aspirational.

### How agents are routed

Two sequences, and the order inside each one matters.

Before an edit: `researcher`, then `swiper`. swiper runs second because it needs
researcher's findings to avoid recommending a swipe for something your project
already has.

After an edit: `bad-cop`. If it finds nothing it stamps `VERIFIED:` and you are
done. If everything it found is a nit it says `NITS:`, you fix those yourself,
and you re-run bad-cop. Only if it says `HANDOFF:`, meaning Critical or High, do
you spawn `good-cop`, and then bad-cop again to re-check the fix. The loop ends
when bad-cop stamps `VERIFIED:` itself, never when good-cop says it is done.

Agents run in parallel when context allows:

- **Context below 50%**: up to 3 agents at once
- **Context 50 to 75%**: up to 2 agents at once
- **Context above 75%**: one at a time

Split parallel reviewers by dimension (correctness, security, concurrency, error
handling, test quality) and hand every one the full diff. Never split them by
file: a reviewer that sees only file B cannot see that a signature change in
file A broke it.

### When to use Opus vs Sonnet

`good-cop` runs on Opus. It is the one applying a fix to code that already
failed an adversarial test, so the reasoning quality shows. Everything else runs
on Sonnet.

---

## 6. RAG tools

One server, clean-rag, runs on `http://127.0.0.1:8613`. It searches projects you have indexed, plus live web search. There is no separate agents or knowledge base index any more. ClaudeBoost itself is just another indexed project.

A project is searchable once you run `/index-project <path>`. After that it reindexes itself after every edit, with a full sweep every 10 minutes.

### HTTP API endpoints

Claude calls these directly. `clean-rag/CLAUDE.md` has the full table.

**`POST /search`** takes `sources`, a list of `project:<absolute path>`, and a `mode`. Use `mode: "both"` for code search: vector finds semantically similar code, and graph finds files that import from or are inherited by the matches. If the response lists a project under `stale_projects` with `served: false`, that index was refused, and the `reason` field says why.

**`POST /index-project`** indexes a project. It takes `project_path`.

**`GET /status`** reports whether the server is ready, which embedding model is loaded, and each indexed project's file, chunk and graph edge counts.

**`POST /web-search`** is a ranked DuckDuckGo search, with GitHub and StackOverflow first.

### When to reindex

- A project was never indexed: `/index-project <path>`
- `/search` lists the project under `stale_projects`: `/index-project <path>` with force. That can take a long time on a large project.
- The server is not answering: `/clean-rag-server start`, or `/fix-rag` if it will not stay up.

---

## 7. CONSULT vs AUTO mode

### CONSULT (default)

Claude researches and proposes before taking any architectural action, then waits for your input. The full loop is:

1. Claude searches RAG and reads 2–3 relevant files
2. Spawns `researcher`, then `swiper`, to produce options grounded in your actual codebase
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

ClaudeBoost prevents unverified findings from reaching you. When an agent reports a security issue, a bug, or a high-severity finding, that finding has to be backed by actual code evidence — a specific file path and line number — before it shows up in your results. If it isn't, `quick-cop` is spawned to independently check it.

This matters because an LLM that found a bug and is then asked "is this bug real?" will often say yes, using the same flawed reasoning that produced the finding in the first place. `quick-cop` runs in a completely fresh context with no knowledge of the original finding — it reads only the cited file:line evidence and gives an independent verdict. If it can't confirm the finding from the evidence, the finding is dropped.

From your perspective, this means two things. First, findings you see have been verified against actual code. Second, "no issues found" is always a valid outcome. The agents aren't trying to find something impressive — they're trying to find something real. A clean result is a good result.

Every finding in a review, audit, or security scan must include a `file:line` citation before the orchestrator accepts it. Agents that report BLOCKER or HIGH severity findings without citations are blocked — the finding is marked `NEEDS_VERIFICATION` and escalated to `quick-cop` before it reaches you.

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

`context.md` is what keeps tasks resumable across sessions. It's designed to survive a `/clear` — everything that would otherwise live only in context gets written here. When you run `/boost` in a new session after a `/clear-safe`, Claude reads `context.md` and picks up exactly where you left off, without you re-explaining the task history.

For tasks involving UI work, `snapshots/` is where before/after screenshots go. For tasks that produce files (a generated config, a migration, a report), those land in `outputs/`. The folder structure is consistent across all tasks, so it's easy to navigate even if you haven't touched a workspace in weeks.

---

## 10. Common task patterns

### 1. Fix a bug

Describe the bug and what you expected to happen. Run `/debug`, which works through a systematic process: reproduce the issue, read the relevant files, identify the root cause, and propose a fix. After the fix, spawn `bad-cop` to add a regression test that actually fails on the old code, so the same bug can't come back undetected.

For simple bugs where the cause is obvious, Claude handles it directly without spinning up agents. The decision is automatic — don't second-guess it.

### 2. Review code or a PR

```
/xray
/xray --deep
/xray --staged
/xray --branch feature-branch
/xray --pr https://github.com/org/repo/pull/42
```

`/xray` gives you a quick A-F grade by default. Add `--deep` for the full 16-pass parallel review: 15 agents run in parallel batches, each covering a specific dimension — simplicity, dead code, debug leftovers, project patterns, common-pattern violations, fresh eyes, ticket alignment, spec precision, schema migrations, platform footguns, banned dependencies, and test coverage/logging. A 16th evaluator agent (Opus) classifies every finding: BLOCKER, WARNING, NIT, or FALSE POSITIVE.

**Grade scale:**
- A: no blockers, no warnings
- B: no blockers, warnings or nits only
- C: meaningful warnings, no blockers
- D: 1–2 blockers
- F: 3+ blockers or any test failure

Every BLOCKER and WARNING needs a specific `file:line` citation before it reaches you. The evaluator discards anything without one — so "no issues found" is a valid and clean result.

For a security-only pass, use `/security-review`.

### 3. Start a complex task or feature

```
/workspace add payment plan support to the subscription API
/workspace ASC-1175 <paste ticket text>
```

Creates `workspace/[task-id]/` with:
- `ticket.md` — verbatim ticket text (immutable after creation)
- `plan.md` — step-by-step implementation plan, each step mapped to an agent and knowledge base
- `context.md` — living state record: what was found, what's next, open questions

The planner searches your project's codebase via RAG to build the plan — it knows which files are in scope before any agent spawns. If your project isn't indexed yet, it warns you and offers to index it first.

**What it detects from your description:**
- Work type: Feature, Bug Fix, Refactor, Architecture, Research, Security, Database, etc.
- Complexity tier: 5–10 files (FEATURE), 10+ files (COMPLEX), 15+ source files or new subsystem (COMPLEX+ — recommends `/create-prd` first)

In CONSULT mode, any new endpoints, tables, dependencies, modules, or auth strategies trigger a proposal before code is written. You get options with trade-offs, pick one, and implementation proceeds.

`context.md` is updated after every significant finding. It's how tasks survive `/clear` — run `/clear-safe` before clearing, then `/boost` in the new session to pick up exactly where you left off.

For large features (15+ source files or a new subsystem), use `/create-prd` first to generate a requirements document and task breakdown.

### 4. Write tests

For unit and integration tests: describe what needs testing. Claude spawns `bad-cop`, which reads the code being tested, identifies the important cases (happy path, edge cases, error conditions), and writes tests that actually fail when the behavior breaks — not just tests that exist on paper.

For browser QA sessions:
```
/qa http://localhost:3000
/qa http://localhost:5173 auth
/qa http://localhost:3000 all
```

What happens:
1. **Discovery** — crawls the app via browser + codebase RAG to map all routes, forms, and entities. Builds an App Map and component registry.
2. **Flow map** — identifies the 5–10 highest-risk user journeys (not just pages). Scores each by risk: auth, data writes, revenue paths, prior bugs.
3. **Test plan** — generates test cases from journeys and writes them to `workspace/e2e-.../plan.md` before any test runs. The plan predates execution — this prevents fabricated results.
4. **Execution** — runs each test using only browser tools. No direct DB queries, no API shortcuts. Each passing test gets a screenshot with a red annotation box on the verified element.
5. **Debugger step-through** — after each passing UI test, attaches to the running server process and steps through the code path to confirm the server actually hit. Works for .NET (requires `netcoredbg`) and Node.js (built-in inspector). If the server can't be found, tests run UI-only.
6. **Screenshot audit** — bad-cop with MODE: evidence-judge independently checks every screenshot for annotation presence, correct placement, and post-action state. Flags any that need a retake.

Scope options: `auth`, `crud`, `nav`, `errors`, `responsive`, or `all` (default).

**Hard safety rules:** refuses to run against staging or production URLs. Checks the URL statically and again after navigation (catches OAuth redirects to non-local environments).

Requires a running local server — it will not test against external URLs under any circumstances.

### 5. Audit code, configs, documents, or agent output

```
/audit workspace/my-feature/plan.md
/audit src/auth/login.ts
/audit https://some-local-page
/audit "claim or statement to verify"
```

Works on any input: a file path, a block of code, a config, a URL, a claim, a document, or pasted text. It detects the input type automatically and picks 3–6 relevant audit dimensions.

**Dimensions by input type:**
- Code/file: logic & correctness, security, error handling, performance, completeness, conventions
- Config: schema validity, security, completeness, best practices
- URL: content accuracy, credibility signals, red flags, security signals
- Document/claim: factual accuracy, internal consistency, completeness, logical validity
- Process or agent output: completion coverage, evidence quality, goal alignment, internal consistency, specificity

Each dimension runs as a separate parallel agent. A final Opus verdict agent synthesizes the results into: **LEGIT / MOSTLY LEGIT / SUSPICIOUS / INVALID / INCOMPLETE**.

Any finding without a specific quote, line number, or field name is discarded as a false positive by the verdict agent.

**Most useful for:**
- Auditing a `plan.md` or `prd.md` before you start executing it (checks goal alignment, specificity, ClaudeBoost protocol compliance)
- Verifying an agent's findings before acting on them
- Quick security pass on a new config or an untrusted code snippet

For a dedicated security pass on your current branch changes, use `/security-review` instead. Add `--full` for a whole-project audit covering OWASP Top 10, auth/authz, injection, secrets, and headers.

### 6. Research an external API or library before implementing

There's nothing to run. The research gate handles this for you. When an agent is about to edit code, the gate nudges toward research, and `researcher` or `swiper` digs into the relevant APIs, libraries, and patterns before the edit. Only you decide an edit is trivial enough to skip that, by running `/ps`.

For quick, one-off research (comparing two libraries, answering a specific question), just ask, or use the `/research` skill. That goes to `research-agent`, which does a web lookup and synthesizes an answer.

### 7. Index your project for semantic search

```
/index-project
/index-project C:/Development/MyApp
/index-project litware
/index-project MyApp typescript,csharp
```

Scans your project, embeds all source files into a per-project vector index, and builds a structural graph index (imports, inheritance chains). After indexing, Claude can find relevant files by description rather than guessing names.

**What you get:**
- Vector search — "find the payment processing logic", "where is auth handled?"
- Graph search — "what imports this module?", "what changes if I modify class Foo?"

**Path resolution:** pass a full path, a short project name (fuzzy matching works — "litware" finds "LitwareBenefits"), or nothing to use the current directory.

**Quality checks after indexing (7 checks, auto-fixed where possible):**
- Coverage: detects file types excluded from the index (`.vue`, `.razor`, etc.)
- Graph liveness: verifies graph edges are activating in search results
- Relevance quality: checks top search scores with a language-specific query
- Manifest integrity: confirms the index was written correctly
- Search smoke test: `POST /search` returns results and no refused `stale_projects` entry
- .ragignore compliance: verifies excluded directories are actually excluded
- Community summaries: checks that all knowledge communities have LLM summaries

**When to run:**
- Once when you start working on a new project
- After major structural changes (new modules, large refactors)
- If RAG search results seem off (`GET /status` will show a stale index)

You don't need to pass `force` unless you see a health warning — incremental mode skips unchanged files automatically.

---

### 8. Refactor messy code

Describe what needs cleaning up — a function that's grown too large, a module with unclear responsibilities, a naming convention that got inconsistent across the codebase. `researcher` maps what depends on the code first, then Claude restructures and renames while keeping behavior the same, and `bad-cop` checks the result.

For rename campaigns that touch many files, Claude searches all occurrences first and lists every match before changing anything. That's intentional — the rule is to grep before touching, then update all occurrences in one pass. No silent partial updates.

### 9. See the architecture

```
/visualize
```
Generates an interactive board of your project's architecture and opens it in the browser. Shows the layers of the system, how components connect, and where decisions were made. Useful for onboarding a new team member, planning a large change, or just getting reoriented in a codebase you haven't touched in a while.

### 10. Generate a feature walkthrough

```
/walkthrough http://localhost:3000 login flow
/walkthrough http://localhost:5173 creating a new project --output docs/tutorials
```

Creates a step by step tutorial document with annotated screenshots. Claude drives the app through Playwright in headed mode, injects visual annotations (numbered badges, highlight boxes, arrows, Driver.js popovers) onto each step, captures a screenshot, then assembles a polished markdown file with all the images embedded.

**How it works:**
1. You provide a URL (localhost only) and describe the feature or workflow
2. Claude writes a step plan and shows it to you for approval
3. For each step, it navigates, waits for the page to settle, injects annotations, takes a screenshot, cleans up, then performs the action to advance
4. The output is a markdown doc in `docs/walkthroughs/` (or your `--output` path) with one section per step, each containing instructions and an annotated screenshot

**Annotation types available:**
- Numbered callout badges (red circles with step numbers)
- Highlight boxes (colored outlines around target elements)
- Directional arrows with text labels
- Driver.js popovers (spotlight + tooltip with title and description)

The skill falls back to pure DOM injection if the CDN is unreachable (air gapped environments). All annotations are cleaned up between steps so they don't accumulate.

### 11. Context window full mid-task

This happens on long sessions. The fix is:

```
/clear-safe
```
Then `/clear` to clear the context. In the new session, run `/boost`. The SessionStart
hook reads the saved state automatically and resumes from where you left off — you don't
re-explain the task.

`/clear-safe` saves your workspace state: what task you were on, what was found, what's
next, which files are relevant. Run it *before* `/clear`, not after.

The key is running `/clear-safe` *before* `/clear`, not after. Once you clear the context, that information is gone if you didn't save it.

### 12. Review what changed

```
/changes
```
Interactive explorer of recent changes with context. Good for writing a commit message, doing a final pre-merge pass, or confirming that every file you meant to change actually changed (and nothing extra snuck in). It shows the diff with the reasoning behind each change, not just the raw diff.


---

## 12. How hooks work

ClaudeBoost installs several hooks that run automatically in the background. You will see their effects but usually do not interact with them directly.

**Session start hook** - runs when Claude Code starts. It checks whether `/boost` has been run this session and injects the CONSULT/AUTO mode protocol into context. If the sentinel is missing (meaning `/boost` has not run), it blocks task spawning until you run `/boost`.

**Pre-task hook** - `agent-spawn-gate.py` is registered before any agent spawn, but on this branch it is a stub that exits 0 and checks nothing. Research is enforced at the edit instead, by the research gate, which nudges rather than blocks.

**Post-task hook** - fires after every agent completes. It nudges the orchestrator to check agent output for unverified BLOCKER/HIGH findings and spawn `quick-cop` if needed. It is an LLM nudge, not a mechanical block - the orchestrator has to act on it.

**Pre-write hook** - fires before Edit or Write tool calls. It checks whether the change qualifies as an architectural decision and reminds the orchestrator to go through the CONSULT protocol if so.

**Context nudge hook** - fires every 5 file reads as a reminder to update `context.md` with recent findings. The workspace update protocol says to update proactively, not wait for this trigger - but it is a fallback in case Claude gets deep in exploration mode and forgets.

**Reindex check hook** - runs at session start and warns if the RAG index is stale based on the last-modified timestamps of indexed files. If it fires, run `/index-project <path>` before starting work.

You will not see most of these. They run silently unless there is a problem, in which case they surface a clear message explaining what to fix and how. If a hook error blocks something unexpected, the message will tell you the exact command to run to unblock it.

---


---

## Tips

**Do not over-describe tasks.** A clear one-sentence description works better than a paragraph. Claude searches for context it needs - you do not have to pre-explain every file involved.

**Let the CONSULT proposals happen.** It is tempting to switch to AUTO to move faster, but the proposal step catches assumptions you would otherwise miss. Most proposals take under a minute. If a specific axis keeps coming up unnecessarily, note it - that is feedback that the trigger logic could be tuned.

**Use `/changes` before committing.** It gives you a clean view of everything that changed and why, which makes commit messages easier and catches any unintended edits.

**If something seems slow or wrong with RAG**, run `GET /status` (or `/boost` to reconnect) before anything else. Most search quality problems are stale index problems, and they are easy to fix.

**For big tasks, start with `/explore` not `/workspace`.** `/explore` does a deeper ticket analysis and codebase exploration pass before generating the plan. `/workspace` is faster but assumes less investigation is needed. Use `/explore` when you have a ticket with real complexity.

**Keep your project indexed.** `/index-project` runs in a few minutes for most projects. After that, every agent working on that project gets codebase-aware search at no extra cost. The index persists - you only need to rerun it after significant structural changes.

---

## Appendix: What RAG searches

There is no knowledge base. RAG searches the projects you have indexed with `/index-project`, and nothing else. To see what it would surface for a task before starting, run:

```
POST http://127.0.0.1:8613/search
{"query": "<describe your task>", "sources": ["project:<absolute path>"], "mode": "both", "limit": 8}
```

`mode: "both"` runs vector similarity and the import graph together. A path that was never indexed returns nothing, so check `GET /status` when a search comes back empty.

---

