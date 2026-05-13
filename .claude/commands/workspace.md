---
argument-hint: <description of what you want to build or accomplish>
description: Create a workspace and generate a ClaudeBoost-aware implementation plan with optimal skill/agent routing
allowed-tools: Read, Write, Bash, Glob, Grep, Agent, AskUserQuestion, mcp__rag-server__rag_context, mcp__rag-server__rag_search
---

# /workspace — ClaudeBoost Workspace Planner

Input: **$ARGUMENTS**

Creates a workspace for your goal and produces a step-by-step implementation plan that routes to the right ClaudeBoost agents, skills, and knowledge bases — no guessing required.

---

## Phase 0: RAG Context

Call `rag_context(agent="architect-agent", task_description="workspace planning: $ARGUMENTS", max_tokens=5000)` as your FIRST action.

This loads architecture, workflow, orchestration, and model-selection knowledge so the plan is grounded in real ClaudeBoost capabilities.

---

## Phase 1: Create the Workspace

### 1a — Generate a slug

Derive a slug from `$ARGUMENTS`:
- Strip filler words: `fix`, `add`, `update`, `build`, `create`, `make`, `implement`, `the`, `a`, `an`, `for`, `to`, `of`, `in`, `on`, `it`, `this`, `that`, `i`, `want`
- Take up to 4 remaining content words, lowercase, hyphenated
- Append today's date: `YYYY-MM-DD`
- Examples: "build a RAG-powered ticket bot" → `rag-ticket-bot-2026-05-12`; "I want to add dark mode" → `dark-mode-2026-05-12`

Set `WORKSPACE_ID = [slug]`.

Check for collision — if that slug already exists, append `-2`, `-3`, etc.:
```bash
ls "$CLAUDEBOOST_HOME/workspace/" 2>/dev/null
```

### 1b — Create workspace

```bash
mkdir -p "$CLAUDEBOOST_HOME/workspace/$WORKSPACE_ID"
```

Report: "Created workspace `$WORKSPACE_ID`."

### 1c — Save the goal verbatim

Write `workspace/$WORKSPACE_ID/goal.md`:

```markdown
# Goal: $WORKSPACE_ID

**Input**: $ARGUMENTS
**Date**: [today]
**Status**: PLANNING
```

---

## Phase 2: Classify the Work

Examine `$ARGUMENTS` and assign one or more work types. A task can match several.

| Work Type | Detection Signals |
|-----------|------------------|
| **Feature** | "add", "build", "new", "implement", "create", "I want X to do Y" |
| **Bug Fix** | "fix", "broken", "wrong", "not working", "error", "failing", "crash" |
| **Refactor** | "clean up", "simplify", "restructure", "rename", "move", "reorganize" |
| **Architecture** | "design", "architecture", "system", "how should", "new module", "structure" |
| **Research** | "investigate", "understand", "figure out", "what is", "how does", "compare" |
| **Code Review** | "review", "check this", "look over", "is this right" |
| **Security** | "security", "vulnerability", "safe", "audit", "pentest", "OWASP", "injection" |
| **Testing** | "tests", "spec", "coverage", "unit test", "integration", "e2e" |
| **UI/Frontend** | "UI", "component", "page", "frontend", "design", "visual", "style" |
| **Database** | "database", "schema", "migration", "query", "model", "index" |
| **DevOps/CI** | "deploy", "CI", "pipeline", "Docker", "infra", "build system" |
| **Performance** | "slow", "optimize", "performance", "memory", "latency", "bottleneck" |
| **Observability** | "logging", "tracing", "metrics", "monitoring", "alerts" |
| **Documentation** | "docs", "document", "README", "explain", "write up" |
| **ClaudeBoost Meta** | "skill", "agent", "command", "knowledge base", "ClaudeBoost", "improve boost" |

Set `WORK_TYPES = [matched types]`. If ambiguous, include all plausible matches — the plan will filter.

---

## Phase 3: Capability Mapping

Search for the right tools. Do NOT skip — this is the core of the plan.

### 3a — RAG searches

```
rag_search(scope="agents", query="[primary work type] [key goal words]", limit=5)
rag_search(scope="knowledge", query="[primary work type] workflow best practices", limit=5)
```

If multiple work types: run a second search for the secondary type.

### 3b — Full ClaudeBoost capability catalog

Use this catalog to map work types to tools. Select only what the work actually needs — don't pad the plan.

#### Agents
| Agent | Best For | Model |
|-------|---------|-------|
| `architect-agent` | New system/module design, SOLID review, architectural decisions requiring Opus reasoning | **Opus** |
| `reviewer-agent` | Code review, PR review, verify-gate evaluation, quality judgment | **Opus** |
| `ticket-analyst-agent` | Ticket analysis, requirements extraction, definition of done, open-question surfacing | **Opus** |
| `debug-agent` | Bug diagnosis, error tracing, root cause analysis, reproduction steps | Sonnet |
| `refactor-agent` | Code restructuring, cleanup, rename campaigns, simplification | Sonnet |
| `test-agent` | Writing unit/integration tests, coverage analysis, test strategy design | Sonnet |
| `e2e-agent` | End-to-end browser test authoring and execution with Playwright | Sonnet |
| `browser-agent` | Browser automation, UI testing, DOM inspection, web scraping | Sonnet |
| `ui-agent` | Frontend components, HTML/CSS/JS, React, design systems, accessibility | Sonnet |
| `security-agent` | Security review, OWASP top 10, auth/authz, injection, secret detection | Sonnet |
| `performance-agent` | Performance profiling, N+1 detection, caching strategy, bottleneck analysis | Sonnet |
| `database-agent` | Schema design, migrations, query optimization, indexing, ORMs | Sonnet |
| `devops-agent` | CI/CD pipelines, Docker, infrastructure, deployment scripts | Sonnet |
| `observability-agent` | Logging strategy, tracing, metrics, error handling, alerting | Sonnet |
| `docs-agent` | Documentation, README, API docs, changelogs, inline comments | Sonnet |
| `research-agent` | Web research, library comparison, technical investigation, fact-checking | Sonnet |
| `research-rag-agent` | Build a persistent research RAG from URLs/PDFs, then query during implementation | Sonnet |
| `explore-agent` | Codebase discovery, file mapping, dependency tracing, usage search | Sonnet |
| `workflow-agent` | Multi-step task orchestration, process design, coordination | Sonnet |
| `compliance-agent` | Standards compliance, rule enforcement, policy and convention checks | Sonnet |
| `standards-validator-agent` | Coding standards validation, pattern enforcement, lint-like structural review | Sonnet |
| `estimator-agent` | Story pointing, complexity estimation, effort breakdown | Sonnet |
| `evaluator-agent` | Verify-gate evaluation — validates findings from other agents, anti-hallucination | Sonnet |
| `rag-indexing-agent` | RAG index management, knowledge base updates, re-indexing after changes | Sonnet |

#### Skills / Commands
| Skill | When to Use It |
|-------|---------------|
| `/boost` | Start of session — loads RAG + Gas Town; use if session isn't already boosted |
| `/explore <ticket-or-description>` | Full ticket deep-dive: ticket analysis → project indexing → code exploration → plan |
| `/plan-task <id> <desc>` | Planning phase only (no execution) — produces checklist + subtasks + agent list |
| `/audit <input>` | Parallel audit of code, config, URL, claim, or document with Opus verdict |
| `/code-review` | 15-pass parallel code review of the current branch changes |
| `/security-review` | Security-focused review of pending branch changes |
| `/end-to-end-test` | Browser-based E2E test execution with screenshot evidence |
| `/research-rag <topic>` | Build a research RAG from URLs/PDFs/docs, then query it during implementation |
| `/index-project <path>` | Index project codebase for semantic search via `rag_search(scope="codebase")` |
| `/visualize` | Interactive architecture board — self-map for ClaudeBoost, project-map for others |
| `/spawn-agent <agent>` | Spawn a specific agent with RAG knowledge loaded |
| `/self-improve` | ClaudeBoost self-improvement audit cycle (meta-work only) |
| `/done` | Submit completed work to merge queue |
| `/handoff` | Hand off to a fresh session when context is getting full |
| `/clear-safe` | Pre-flight save before /clear — preserves active workspace state |
| `/gate` | Compliance gate check |
| `/changes` | Interactive change explorer — review everything changed on this branch |

#### Knowledge Bases (always accessed via RAG — never read directly)
| Area | File | When Relevant |
|------|------|--------------|
| Architecture | `knowledge/architecture.xml` | New systems, modules, design decisions |
| Testing | `knowledge/testing.xml` | Any code changes, coverage, test strategy |
| Security | `knowledge/security.xml` | Auth, input validation, data, HTTP endpoints |
| Performance | `knowledge/performance.xml` | Queries, loops, caching, hot paths |
| Database | `knowledge/database.xml` | Schema, migrations, queries, indexing |
| DevOps | `knowledge/devops.xml` | CI/CD, Docker, deployment |
| UI Implementation | `knowledge/ui-implementation.xml` | Frontend components, accessibility |
| E2E Testing | `knowledge/e2e-testing.xml` | Browser-level test strategy |
| Playwright | `knowledge/playwright.xml` | Browser automation specifics |
| Observability | `knowledge/observability.xml` | Logging, tracing, metrics |
| Refactoring | `knowledge/refactoring.xml` | Code restructuring patterns |
| Debugging | `knowledge/debugging.xml` | Root cause analysis, error tracing |
| Documentation | `knowledge/documentation.xml` | Doc strategy, README, API docs |
| Research | `knowledge/research.xml` | Investigation methodology |
| Research RAG | `knowledge/research-rag.xml` | Persistent research index workflows |
| Code Exploration | `knowledge/code-exploration.xml` | Codebase navigation strategy |
| Workflow | `knowledge/workflow.xml` | Multi-step orchestration |
| API Design | `knowledge/api-design.xml` | REST/GraphQL API conventions |
| Coding Standards | `knowledge/coding-standards.xml` | Language/framework conventions |
| Verify Gate | `knowledge/verify-gate.xml` | Anti-hallucination, finding validation |
| Consult Mode | `knowledge/consult-mode.xml` | When to consult vs auto-proceed |
| Ticket Understanding | `knowledge/ticket-understanding.xml` | Requirements parsing, ambiguity resolution |
| Completion Verification | `knowledge/completion-verification.xml` | Definition of done, exit criteria |
| Multi-Agent Failures | `knowledge/multi-agent-failures.xml` | Common agent failure modes, recovery |
| Scope Governance | `knowledge/scope-governance.xml` | Scope creep, change management |
| Model Selection | `knowledge/model-selection.xml` | When to use Opus vs Sonnet |
| PR Review | `knowledge/pr-review.xml` | Code review standards |
| Branching Strategy | `knowledge/branching-strategy.xml` | Git branching, PR workflow |

### 3c — Produce a tool mapping

For each work type, select:
- **Primary agents** (core work) — with model
- **Supporting agents** (validation, evaluation) — always include `evaluator-agent` for findings
- **Skills to invoke** (exact commands)
- **Knowledge bases** (which to load via `rag_context`)

Prune ruthlessly — only include what the work genuinely needs.

---

## Phase 4: Ask About Project (if needed)

If WORK_TYPES includes Feature / Bug Fix / Refactor / Testing / UI / Database / Performance / DevOps / Security and no project path was mentioned in `$ARGUMENTS`:

Ask exactly this:
```
AskUserQuestion: "Does this involve a specific project codebase? Provide the full path (e.g., C:/Development/MyApp) or say 'none' if this is ClaudeBoost meta-work or codebase-independent."
```

Set `PROJECT_PATH` from the answer. If 'none' or ClaudeBoost meta-work: `PROJECT_PATH = none`.

If the input already implies a path or clearly describes ClaudeBoost-internal work: skip this question and set accordingly.

---

## Phase 5: Write the Plan

Write `workspace/$WORKSPACE_ID/plan.md` using this template:

```markdown
# Workspace Plan — $WORKSPACE_ID

**Goal**: [one-line description]
**Date**: [today]
**Work Types**: [WORK_TYPES]
**Project**: [PROJECT_PATH or "N/A — ClaudeBoost meta / codebase-independent"]
**Status**: PLAN_READY

---

## Recommended Approach

[2-4 sentences: what the work is, why the chosen approach, which ClaudeBoost capabilities are the key leverage points]

---

## Step-by-Step Implementation

### Step 1: [Step Name]
**What**: [what this step accomplishes]
**Command**: `[exact skill or agent action — e.g., /explore my-workspace-id or /spawn-agent security-agent]`
**Agent**: [agent-name (Model)]
**Knowledge loaded via RAG**: [list knowledge files]
**Output artifact**: [e.g., workspace/$WORKSPACE_ID/plan.md, tests/feature.spec.ts]
**Depends on**: [Step N, or "none — run first"]
**Execution**: [sequential | parallel with Step N]

[Repeat for each step]

---

## Execution Strategy

[Sequential / Parallel / Hybrid]

[If parallel, name the groups:]
- **Group 1** (run together): Steps X, Y
- **Group 2** (after Group 1 completes): Steps Z

[Rationale: why this order / grouping]

---

## Agent Roster

| Agent | Role in This Plan | Model | Step(s) |
|-------|------------------|-------|---------|
| [agent] | [specific role] | Opus/Sonnet | [N] |

---

## Knowledge Bases Engaged

| File | Why Relevant to This Work |
|------|--------------------------|
| [knowledge/X.xml] | [specific reason] |

---

## Skills Sequence

In order — copy-paste these to execute:
```
[Step 1 command]
[Step 2 command]
...
```

---

## Definition of Done

- [ ] [each concrete, testable completion criterion]
- [ ] Evaluator-agent has validated all findings (verify gate)
- [ ] No open questions remain
- [ ] context.md Status updated to COMPLETE

---

## Risks

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| [risk] | low/med/high | [concrete mitigation] |
```

Write `workspace/$WORKSPACE_ID/context.md`:
```markdown
# Workspace: $WORKSPACE_ID

## Status
PLAN_READY

## Goal
[one-line from goal.md]

## Next Step
[Step 1 exact command from plan.md]

## Key Decisions
[architectural or approach decisions embedded in the plan]

Last updated: [today]
```

---

## Phase 6: Present to User

Print the full `plan.md`.

Then output this block:

```
Workspace ready: workspace/$WORKSPACE_ID/

  goal.md     — your goal (verbatim)
  plan.md     — step-by-step ClaudeBoost implementation plan
  context.md  — session state (restored after /clear via handoff)

To start executing:
  [Step 1 exact command]

Agents queued  : [comma-separated agent list]
Skills involved: [comma-separated skill list]
Context budget : [sequential/parallel note based on current context level]
```

If any critical ambiguity remains (you genuinely cannot determine work type or scope): ask ONE focused question before presenting the plan. Do not ask about details that the plan itself can accommodate.
