---
argument-hint: <description of what you want to build or accomplish>
description: Create a workspace and generate a ClaudeBoost-aware implementation plan with optimal skill/agent routing
allowed-tools: Read, Write, Bash, Glob, Grep, Agent, AskUserQuestion
---

# /workspace — ClaudeBoost Workspace Planner

Input: **$ARGUMENTS**

Creates a workspace for your goal and produces a step-by-step implementation plan that routes to the right ClaudeBoost agents, skills, and knowledge bases — no guessing required.

---

## Snippet conventions (read first)

Bash snippets in this file mix two kinds of `$NAMES` — treat them differently:

- **Placeholders** (`$ARGUMENTS`, `$WORKSPACE_ID`, `$WORKSPACE_ABS`, `$WORKSPACE_ROOT`, `$PROJECT_PATH`, `$TASK_ID`): values YOU resolve in earlier phases. Substitute the actual literal value into the command before running it. Never pass them to Bash as shell variables — they don't exist in the shell, and bash-guard blocks bare `$VAR` anyway.
- **Runtime shell variables** (`${SPRINT_BRANCH}`, `${BASE_BRANCH}`, `${BRANCH_NAME}`, `${TEMP}`, `${CLAUDEBOOST_HOME}`): assigned or exported in the shell itself. Always written in `${VAR}` brace form, which both bash-guard and Claude Code's expansion scanner accept.

---

## Phase 0: Session Readiness Check

**Workspace detection (run before any other action):**

Run `get-active-workspace.py` to get the active workspace for this Claude
instance — matches the blue "WS XXXX" status bar (per-instance, not the
stale shared global file):
```bash
"${CLAUDEBOOST_PYTHON}" "${CLAUDEBOOST_HOME}/scripts/get-active-workspace.py"
```

Store `project_path` as `PROJECT_PATH` and `workspace_path` as `WORKSPACE_PATH`.
If `PROJECT_PATH` is empty: fall back to current working directory (`pwd`).

**Collision check:** if your context or memory references a different workspace
than what the script returned, print:
`[workspace] Conflict: status bar shows <X>, context/memory says <Y>. Which workspace should I use?`
Wait for the user's answer — the user is always the source of truth.

If `WORKSPACE_PATH` is empty: note it and continue.

Include `workspace_path="<WORKSPACE_PATH>"` in ALL agent spawn prompts and `/context` calls.



Run the sentinel check **alone** (never in parallel with other Bash calls — a parallel failure cancels both):

```bash
ls "${TEMP}/claudeboost_active"
```

- BOOSTED (`ls` succeeds): proceed silently.
- NOT_BOOSTED (`ls` errors): note it but **do not emit a warning yet**. The RAG server often stays running across sessions after `/clear` even when the sentinel is gone. Phase 0.5 confirms the real state.

After Phase 0.5 completes:
- RAG responded `"status":"ready"` → proceed silently. No warning. RAG is the critical dependency; the sentinel is a proxy for it.
- RAG is also down → emit this warning once and ask the user to run `/boost`:
  > "⚠ Session not boosted and RAG is not responding. Run `/boost` then `/index-project <path>`, then retry."

---

## Phase 0.5: RAG Health Check + Context

**Step 1 — Health check (REQUIRED, runs first):**

Call `GET http://127.0.0.1:8612/status` before loading any context.

**If `GET http://127.0.0.1:8612/status` returns an error OR the tool is not available:**
> **STOP. Do not proceed.**
> Tell the user: "RAG server is not responding. Run `/rag` to start the server, then retry `/workspace $ARGUMENTS`."

**Step 2 — Load context (only if Step 1 passes):**

Call `POST http://127.0.0.1:8612/context with agent="architect-agent", task_description="workspace planning: $ARGUMENTS", max_tokens=5000`.

**If `POST http://127.0.0.1:8612/context` returns an "error" key:**
> **STOP. Do not proceed.**
> Tell the user: "RAG context load failed: [error message]. Run `/rag` to start the server."

This loads architecture, workflow, orchestration, and model-selection knowledge so the plan is grounded in real ClaudeBoost capabilities.

---

## Phase 0.75: New or Existing Workspace?

Before creating anything, check if the user wants to continue in an existing workspace.

```bash
"${CLAUDEBOOST_PYTHON}" "${CLAUDEBOOST_HOME}/scripts/recent-workspaces.py"
```

If the output is empty (no existing workspaces with a `context.md`): skip this phase and proceed to Phase 1.

If workspaces are listed, parse each `wid|wpath|ppath` line and ask the user:

> "New workspace or piggyback on an existing one?
>
> 0. New workspace
> 1. `[wid-1]` — [ppath-1]
> 2. `[wid-2]` — [ppath-2]
> ...
>
> Reply with the number or workspace name."

**If the user picks 0 or says "new":** proceed to Phase 1.

**If the user picks an existing workspace (any other answer):**
- Set `WORKSPACE_ID = [chosen wid]`, `WORKSPACE_ABS = [chosen wpath]`, `PROJECT_PATH = [chosen ppath]`, `WORKSPACE_ROOT = PROJECT_PATH`
- Re-register and update the status bar:
  ```bash
  "${CLAUDEBOOST_PYTHON}" "${CLAUDEBOOST_HOME}/scripts/register-workspace.py" "$WORKSPACE_ID" "$WORKSPACE_ABS" "$WORKSPACE_ROOT" --activate
  "${CLAUDEBOOST_PYTHON}" "${CLAUDEBOOST_HOME}/scripts/workspace-status.py" "$WORKSPACE_ID"
  ```
- Read and print `$WORKSPACE_ABS/context.md`
- If `$WORKSPACE_ABS/plan.md` exists, read and print it
- Report: "Using existing workspace `$WORKSPACE_ID` at `$WORKSPACE_ABS`."
- If `$ARGUMENTS` contains a substantive new goal (not just a workspace ID or empty): update `$WORKSPACE_ABS/goal.md` with the new goal, then continue to Phase 1.5 to produce a fresh plan within this workspace — skip Phase 1 (no mkdir, no branch, no registration)
- If `$ARGUMENTS` is empty or just a workspace ID with no new goal: skip directly to Phase 6 and present the existing plan as-is

---

## Phase 1: Create the Workspace

### 1a — Detect flags

Before generating the slug, check `$ARGUMENTS` for flags:

- `--auto`: Run the full automated pipeline after plan creation (see Phase 7). Strip `--auto` from arguments before slug generation.

Set `AUTO_MODE = true` if `--auto` was detected, `false` otherwise.

### 1b — Generate a slug

Derive a slug from `$ARGUMENTS` (with flags stripped):
- Strip filler words: `fix`, `add`, `update`, `build`, `create`, `make`, `implement`, `the`, `a`, `an`, `for`, `to`, `of`, `in`, `on`, `it`, `this`, `that`, `i`, `want`
- Take up to 4 remaining content words, lowercase, hyphenated
- Append today's date: `YYYY-MM-DD`
- Examples: "build a RAG-powered ticket bot" → `rag-ticket-bot-2026-05-12`; "I want to add dark mode" → `dark-mode-2026-05-12`

Set `WORKSPACE_ID = [slug]`.

Check for collision — read `state/workspaces.json` (under CLAUDEBOOST_HOME) with the **Read tool** and look at its keys. If that slug already exists, append `-2`, `-3`, etc. Do NOT use multiline `python3 -c` for this — bash-guard blocks it; the Read tool never prompts.

### 1c — Determine workspace root and create workspace

**Detect project path** — do NOT use CWD as a proxy. CWD is often the ClaudeBoost directory even when the work is for a different project. Use this priority order instead:

1. **Absolute path in `$ARGUMENTS`** — if the arguments contain a path like `C:/Development/...` or `/home/user/...`, use that as `PROJECT_PATH`.

2. **ClaudeBoost meta-work detection** — scan `$ARGUMENTS` for these keywords: `agent`, `skill`, `knowledge base`, `knowledge file`, `ClaudeBoost`, `rag server`, `hook`, `boost`. If two or more match, set `WORKSPACE_ROOT = $CLAUDEBOOST_HOME`. This handles tasks that are literally about improving ClaudeBoost itself.

3. **Most recent project from registry** — check for previously used projects. Read `state/workspaces.json` (under CLAUDEBOOST_HOME) with the **Read tool**; if you need the recency ordering, use the Write tool to save this as `/tmp/cb_recent_projects.py` and run it with `"${CLAUDEBOOST_PYTHON}" /tmp/cb_recent_projects.py` (multiline `python3 -c` is blocked by bash-guard; the brace-form interpreter resolves on every platform):
```python
import json
from pathlib import Path
import os
home = Path(os.environ.get('CLAUDEBOOST_HOME', ''))
try:
    reg = json.loads((home / 'state' / 'workspaces.json').read_text(encoding='utf-8'))
    projects = sorted(
        set(v['project_path'] for v in reg.values() if v.get('project_path') and v['project_path'] != str(home)),
        key=lambda p: max((Path(v['workspace_path']) / 'context.md').stat().st_mtime
                         for v in reg.values() if v.get('project_path') == p
                         and (Path(v['workspace_path']) / 'context.md').exists()),
        reverse=True
    )
    [print(p) for p in projects[:3]]
except Exception as e:
    pass
```

If this returns exactly one project path: use it as `PROJECT_PATH` and tell the user `"Using project: {PROJECT_PATH}"`.

If it returns multiple: ask `"Which project is this for? (recent: {list})"`. Wait for the user's answer before proceeding.

4. **Ask the user** — if none of the above resolved a path, ask: `"What project is this for? Paste the absolute path to the project directory."` Wait for the answer before continuing.

Set `WORKSPACE_ROOT = PROJECT_PATH` (the project directory, not its parent).
Set `WORKSPACE_ABS = $WORKSPACE_ROOT/workspace/$WORKSPACE_ID`.

```bash
mkdir -p "$WORKSPACE_ABS"
```

**Register, protect, and mark active:**
```bash
"${CLAUDEBOOST_PYTHON}" "${CLAUDEBOOST_HOME}/scripts/register-workspace.py" "$WORKSPACE_ID" "$WORKSPACE_ABS" "$WORKSPACE_ROOT" --activate

if [ "$WORKSPACE_ROOT" != "$CLAUDEBOOST_HOME" ]; then
  if ! grep -qxF 'workspace/' "$WORKSPACE_ROOT/.gitignore" 2>/dev/null; then
    echo 'workspace/' >> "$WORKSPACE_ROOT/.gitignore"
  fi
fi

```

**Switch active workspace (updates status line immediately):**
```bash
"${CLAUDEBOOST_PYTHON}" "${CLAUDEBOOST_HOME}/scripts/workspace-status.py" "$WORKSPACE_ID"
```

This writes to the per-instance CWD-keyed file so the status bar shows `WS $WORKSPACE_ID` right away.

**Initialize telemetry for this workspace:**
```bash
DISABLE_TELEMETRY="" "${CLAUDEBOOST_PYTHON}" "${CLAUDEBOOST_HOME}/scripts/telemetry-session.py"
```

This creates `$WORKSPACE_ABS/Telemetry/session.json` so tool-call tracking begins immediately.
If it errors, note it but do not block — the workspace was already created.

Report: "Created workspace `$WORKSPACE_ID` at `$WORKSPACE_ABS`."

### 1d — Save the goal verbatim

Detect input format:
- **Short description** (≤30 whitespace-delimited words, single-line): write as a one-liner under `**Input**:`
- **Full ticket** (multi-line, contains headings/bullets/acceptance criteria/Jira-style content): write the entire text verbatim under `## Ticket Input` — do NOT summarize, truncate, or paraphrase

Write `$WORKSPACE_ABS/goal.md`:

**Short description:**
```markdown
# Goal: $WORKSPACE_ID

**Input**: $ARGUMENTS
**Date**: [today]
**Status**: PLANNING
```

**Full ticket (multi-paragraph):**
```markdown
# Goal: $WORKSPACE_ID

**Date**: [today]
**Status**: PLANNING

## Ticket Input

$ARGUMENTS
```

Also write `$WORKSPACE_ABS/ticket.md` with the raw verbatim input when a full ticket is detected (per CLAUDE.md convention: "Ticket pasted → Save verbatim to `workspace/[task-id]/ticket.md`").

### 1e — Create feature branch

**First: check the branch-creation setting in state.**

Write `"${TEMP}/cb_branch_check.py"`:
```python
import json, os, pathlib, sys
home = os.environ.get("CLAUDEBOOST_HOME", "")
p = pathlib.Path(home) / "state" / "workspace-settings.json"
if not p.exists():
    # Key absent — default is to create. Write true so future runs are explicit.
    p.write_text(json.dumps({"create_branch": True}), encoding="utf-8")
    print("CREATE")
    sys.exit(0)
d = json.loads(p.read_text(encoding="utf-8"))
if "create_branch" not in d:
    # Key absent — same: default to create and persist the decision.
    d["create_branch"] = True
    p.write_text(json.dumps(d, indent=2), encoding="utf-8")
    print("CREATE")
    sys.exit(0)
print("CREATE" if d["create_branch"] else "SKIP")
```
```bash
"${CLAUDEBOOST_PYTHON}" "${TEMP}/cb_branch_check.py"
```

If the output is `SKIP`: skip this step silently. Record in `context.md` under **Key Decisions**: "Branch: skipped (create_branch=false in state)"

If the output is `CREATE`: continue below.

If `WORKSPACE_ROOT` is a git repo, create a feature branch for the task:

```bash
git -C "$WORKSPACE_ROOT" rev-parse --is-inside-work-tree
```

If it prints `true` → GIT_REPO; if it errors → NOT_GIT. (No `|| echo` fallback — bash-guard blocks it.)

If NOT_GIT or WORKSPACE_ROOT is CLAUDEBOOST_HOME: skip this step silently.

If GIT_REPO:

```bash
# 1. Look for the latest sprint branch (local or remote).
#    Sprint branches match: sprint/*, sprint-*, sprint_*
#    Pick the most recent by committer date so you always branch from the newest sprint.
SPRINT_BRANCH=$(git -C "$WORKSPACE_ROOT" branch -a --sort=-committerdate \
  | sed 's|^[* ]*||; s|^remotes/[^/]*/||' \
  | grep -E '^sprint[-/_]' \
  | head -1)

# 2. Fall back: use origin/HEAD → main/master if no sprint branch exists.
if [ -n "${SPRINT_BRANCH}" ]; then
  BASE_BRANCH="${SPRINT_BRANCH}"
else
  BASE_BRANCH=$(git -C "$WORKSPACE_ROOT" symbolic-ref refs/remotes/origin/HEAD 2>/dev/null | sed 's@^refs/remotes/origin/@@')
  BASE_BRANCH=${BASE_BRANCH:-main}
fi

BRANCH_NAME="feature/$WORKSPACE_ID"

git -C "$WORKSPACE_ROOT" checkout -b "${BRANCH_NAME}" "${BASE_BRANCH}" 2>&1
```

(Runtime shell variables use the `${VAR}` brace form throughout — bash-guard blocks bare `$VAR` because Claude Code's scanner prompts on it.)

If that fails because the branch already exists, check it out instead:

```bash
git -C "$WORKSPACE_ROOT" checkout "${BRANCH_NAME}" 2>&1
```

Report: "Created branch `feature/$WORKSPACE_ID` from `$BASE_BRANCH`."

Record in `context.md` under **Key Decisions**: "Branch: `feature/$WORKSPACE_ID` (base: `$BASE_BRANCH`)"

---

## Phase 1.5: Information Sufficiency Gate

Before classifying or searching code, verify the input is actionable.

**Scan `$ARGUMENTS` for image-only or incomplete descriptions:**

Check for these signals:

**Signal A — Image/attachment references:**
- Image placeholders: `[image]`, `[screenshot]`, `[img]`, `[attachment]`, `image-*.png`, `*.png`, `*.jpg`
- Jira/Confluence attachment references: `image-20\d{6}-\d{6}.png`, `Attachments:`, `[Image #`
- Sparse text: after stripping image placeholder tokens, fewer than 15 whitespace-delimited tokens of actual bug/task description remain

**Signal B — Spec quality (applies to full tickets only — multi-paragraph input):**
Check whether the input contains at least one of:
- Acceptance criteria: "acceptance criteria", "AC:", "given/when/then", "✅", "[ ]"
- Observable outcome: "should", "must", "expected", "definition of done", "done when"
- User-facing behavior: what the user will see/experience after the change

If NONE of these are present in a multi-paragraph ticket, that is a spec quality signal.

**Four outcomes — pick exactly one:**

**STOP** — Signal A detected AND text is sparse (< 15 content tokens after stripping):

> "The description references an image or attachment I can't read — the visible text alone doesn't tell me what to change.
> Can you paste the image content, describe the specific bug in one sentence, or copy the text from the screenshot?"

Do not search code. Do not create context.md yet. Only proceed once the blank can be filled:
> "The specific change required is: ___"

**PROCEED + SAVE** — Signal A detected AND sufficient text is present (≥ 15 content tokens):

Save any directly-provided screenshots or images to `$WORKSPACE_ABS/screenshots/`. Name them descriptively (e.g., `before-[feature].png`). Add an `**Attachments**:` entry in `goal.md` listing the saved file(s). Then proceed to Phase 2.

**PROCEED + WARN** — Signal B detected (multi-paragraph ticket with no acceptance criteria or observable outcome):

Proceed to Phase 2, but prepend this note to `plan.md` and report it to the user:

> "⚠ Spec quality note: This ticket has no acceptance criteria or observable outcome defined.
> The plan may need adjustment once you define success criteria.
> Consider adding: what the user will see after this change, and when this ticket is 'done'."

Do NOT block. Do NOT ask a question. Warn once and proceed.

**PROCEED** — no signals: proceed immediately — no question or warning needed.

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
POST http://127.0.0.1:8612/search with scope="agents", query="[primary work type] [key goal words]", limit=5
POST http://127.0.0.1:8612/search with scope="knowledge", query="[primary work type] workflow best practices", limit=5
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
| `/boost` | Start of session — loads RAG; use if session isn't already boosted |
| `/explore <ticket-or-description>` | Full ticket deep-dive: ticket analysis → project indexing → code exploration → plan |
| `/audit <input>` | Parallel audit of code, config, URL, claim, or document with Opus verdict |
| `/review` | Code review — quick A-F grade by default; add `--deep` for full 15-pass parallel review |
| `/security-review` | Security-focused review of pending branch changes |
| `/end-to-end-test` | Browser-based E2E test execution with screenshot evidence |
| `/index-project <path>` | Index project codebase for semantic search via `POST http://127.0.0.1:8612/search with scope="codebase"` |
| `/graph <task-id>` | Build a Files in Scope map using both vector and graph RAG seeded from ticket entities — run at task start or any time you need to refresh the scope map |
| `/visualize` | Interactive architecture board — self-map for ClaudeBoost, project-map for others |
| `/self-improve` | ClaudeBoost self-improvement audit cycle (meta-work only) |
| `/done` | Submit completed work to merge queue |
| `/handoff` | Hand off to a fresh session when context is getting full |
| `/clear-safe` | Pre-flight save before /clear — preserves active workspace state |
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
- **Knowledge bases** (which to load via `POST http://127.0.0.1:8612/context`)

Prune ruthlessly — only include what the work genuinely needs.

**Bug Fix scope rule:** If WORK_TYPES includes Bug Fix, every planned change must trace back to
an explicit statement in the ticket. Any additional issue found during code exploration that is
NOT in the ticket must be flagged as a separate candidate — not silently included:
> "While investigating I also found [X] at file:line. Is this in scope for this ticket, or should I open a separate ticket?"
Never bundle unrequested fixes into the same commit.

**Bug Fix investigation rule:** Before finalizing the fix approach in `plan.md`:
1. Read the **full file** for every location being changed — not just the bug line
2. Find **all callers** of modified methods: use `POST http://127.0.0.1:8612/search with scope="codebase", mode="graph", query="[method name]", project_path=PROJECT_PATH)` if indexed, or `Grep("[method name]"` across the codebase if not
3. Confirm the caller sweep is complete — "no 4th location" must be verified, not assumed
4. Document what was checked in the plan under a **"Pre-fix Investigation"** section, citing file:line for every location reviewed

Skipping any of these steps is a plan quality failure — the code review step should not be the first time surrounding context is read.

---

## Phase 4: Ask About Project (if needed)

If WORK_TYPES includes Feature / Bug Fix / Refactor / Testing / UI / Database / Performance / DevOps / Security and no project path was mentioned in `$ARGUMENTS`:

Ask exactly this:
```
AskUserQuestion: "Does this involve a specific project codebase? Provide the full absolute path (e.g., `/home/user/myapp` on Linux/Mac or `C:/Development/MyApp` on Windows) or say 'none' if this is ClaudeBoost meta-work or codebase-independent."
```

Set `PROJECT_PATH` from the answer. If 'none' or ClaudeBoost meta-work: `PROJECT_PATH = none`.

If the input already implies a path or clearly describes ClaudeBoost-internal work: skip this question and set accordingly.

---

## Phase 4.5: Project RAG Check

Applies when `PROJECT_PATH` is set (not `none`) and WORK_TYPES includes Bug Fix, Feature, Database, Refactor, or Performance.

Check if the project is indexed:
```
POST http://127.0.0.1:8612/search with scope="codebase", project_path="$PROJECT_PATH", query="test", limit=1
```

**If results returned**: "Project RAG active — vector + graph search available. Graph RAG will auto-trace callers/dependents."

**If fails or returns nothing**: emit this warning **once** and proceed — do NOT block:
> "⚠ Project not indexed — codebase vector search and graph RAG unavailable.
> Run `/index-project $PROJECT_PATH` to enable:
> - Vector RAG: semantic code search across the whole codebase
> - Graph RAG: automatic call-graph traversal (finds all callers, dependents, import chains)
> Falling back to direct Grep/Glob for code exploration."

Record the index status in `context.md` under **Key Decisions**: "Project RAG: [active / not indexed — using Grep/Glob]"

---

## Phase 4.6: Scope Graph

Runs only when Phase 4.5 confirmed the project is indexed.

1. Read `$WORKSPACE_ABS/ticket.md` (or `goal.md`) for entity names: file paths, PascalCase class/service names, API endpoint paths, and data model names.

2. For each entity found, run:
   ```
   POST http://127.0.0.1:8612/search with scope="codebase", project_path="$PROJECT_PATH", query="[entity]", mode="graph", limit=3
   ```

3. Collect unique file paths from all graph results.

4. Append to `$WORKSPACE_ABS/context.md`:

   ```markdown
   ## Files in Scope (Graph Map)
   Seeded from ticket entities. Graph structural neighbours via imports/inheritance.
   | File | Relation | Seed Entity |
   |------|----------|------------|
   | [file] | [imports/inherits] | [entity] |

   Update this table as you discover more files during the task.
   ```

If no entities are found in the ticket, or the project is not indexed: skip silently.

---

## Phase 4.5: Research Primer

Research happens automatically. The research gate fires on code edits and pulls in what an agent needs before it writes, so there's no separate priming step to run here. Proceed to Phase 5.

---

## Phase 5: Write the Plan

### COMPLEX+ Tasks (>15 source files or new subsystem)

Before writing `plan.md`, check if this task qualifies as COMPLEX+:
- More than 15 source files will be created or modified, OR
- A new subsystem is being introduced (new module, new service, new data layer, new auth strategy)

If COMPLEX+, run `/create-prd` before spawning agents:

1. `/create-prd` — generates `workspace/$WORKSPACE_ID/prd.md` + `workspace/$WORKSPACE_ID/tasks.md`
2. Review and approve the PRD with the user
3. Then spawn agents per the task list in `tasks.md`

This replaces the standard `plan.md` for COMPLEX+ scope — the PRD provides the goals, acceptance criteria, and out-of-scope boundaries that agents need for large initiatives. Note this in `context.md` under **Key Decisions**: "COMPLEX+ scope — using PRD workflow instead of plan.md."

If the task does NOT qualify as COMPLEX+, proceed with the standard plan below.

---

Write `$WORKSPACE_ABS/plan.md` using this template:

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
**Command**: `[exact skill or agent action — e.g., /explore my-workspace-id or "spawn security-agent"]`
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

Write `$WORKSPACE_ABS/context.md`:
```markdown
# Workspace: $WORKSPACE_ID

## Status
PLAN_READY

## Goal
[one-line summary — ticket title if full ticket was pasted, otherwise the short description; full content is in goal.md / ticket.md]

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
Workspace ready: $WORKSPACE_ABS/

  goal.md     — your goal (verbatim)
  [ticket.md  — full ticket text (verbatim) — only if full ticket was pasted]
  [screenshots/ — attached images (N files) — only if screenshots were saved]
  plan.md     — step-by-step ClaudeBoost implementation plan
  context.md  — session state (restored after /clear via handoff)

Branch         : feature/$WORKSPACE_ID  (base: $BASE_BRANCH)
                 [omit this line if no git repo was detected]

To start executing:
  [Step 1 exact command]

Agents queued  : [comma-separated agent list]
Skills involved: [comma-separated skill list]
Context budget : [sequential/parallel note based on current context level]
```

If any critical ambiguity remains (you genuinely cannot determine work type or scope): ask ONE focused question before presenting the plan. Do not ask about details that the plan itself can accommodate.

If `AUTO_MODE` is true, print the plan but do NOT wait for user approval. Instead, immediately proceed to Phase 7 (Auto Execution Pipeline).

---

## Phase 7: Auto Execution Pipeline (only when `--auto` flag was set)

If `AUTO_MODE` is false, skip this phase entirely. The user will execute manually.

If `AUTO_MODE` is true, proceed through every step below without stopping for user confirmation. Update `context.md` after each stage. If any stage fails, attempt to fix it once before moving on. If the fix fails, log the failure to `context.md` and continue with the next stage.

### 7a — Ticket documentation and understanding

Read the ticket/goal. Write a detailed analysis to `$WORKSPACE_ABS/ticket-analysis.md`:
- What the ticket asks for (in plain language)
- Acceptance criteria (explicit and implied)
- Edge cases and open questions
- Dependencies on other systems

### 7b — Full codebase context (no gaps)

Use RAG and file reads to build complete understanding:
1. `POST /search scope=codebase mode=both` seeded from ticket entities
2. Read every file in the scope graph until there are no unknowns
3. Trace imports, callers, and dependents for every file that will change
4. Write findings to `context.md` as "Codebase Understanding" section
5. If any area is unclear, read more files until it is clear. No gaps.

### 7c — Generate spec, audit, fix gaps

1. Write `$WORKSPACE_ABS/spec.md` with:
   - Every file that will change and exactly what changes
   - New files to create and what they contain
   - Files that must NOT change (out of scope)
2. Self audit the spec against the ticket: does every acceptance criterion have a matching spec entry?
3. Self audit for codebase gaps: does the spec account for all callers and dependents?
4. Fix any gaps found. Repeat until the spec is clean.

### 7c.5 — Socratic brainstorming (challenge your assumptions)

Before implementing, answer these 5 questions in `$WORKSPACE_ABS/brainstorm.md`. Each answer must cite evidence (file:line, RAG score, or specific observation). "I don't know" is a valid answer that triggers more research.

1. **What am I assuming that might not be true?**
   List every assumption in the spec. For each, state what evidence supports it and what would invalidate it.

2. **What's the simplest approach that could work?**
   Describe the minimum viable implementation. If the spec is more complex, justify why.

3. **What existing code am I duplicating or conflicting with?**
   Search the codebase for similar functionality. Cite file:line for anything that overlaps.

4. **What will break if I'm wrong?**
   List every file, endpoint, or user flow that depends on the code being changed. This is the blast radius.

5. **Who or what depends on the code I'm changing?**
   Run `POST /search scope=codebase mode=both` seeded from every file in the spec. List callers, importers, and inheritors.

If any answer reveals a flaw in the spec (wrong assumption, missed dependency, simpler approach available), update spec.md before proceeding to 7d.

### 7d — Code changes

Switch to AUTO mode (`/auto workspace-auto-pipeline`). Execute every change in the spec:
1. For each file, search RAG and write proof before editing (clean-rag enforces this)
2. Follow the plan step by step
3. After each significant change, update `context.md`

### 7e — Code quality review

Run `/xray --deep` on the changed files. Fix every issue flagged as C or below. Rerun until all grades are B or above.

### 7f — Full audit

Run `/audit` on the workspace. Fix anything the audit flags. This covers:
- Correctness against the ticket
- Security (OWASP top 10)
- Performance
- Code quality
- Test coverage gaps

### 7g — QA and audit loop

Run `/qa --code` to execute tests. If tests fail, fix them and rerun. Then:
1. Run `/qa <url>` if there is a UI (localhost only)
2. Focus on local testing: verify every feature locally
3. If the audit finds something QA missed, fix it and rerun QA
4. Loop until the audit passes with no findings and all tests pass
5. Any bugs found during QA must be fixed during QA, not deferred

### 7h — Visualization

Run `/visualize` to generate a visual explanation of:
- What the ticket asked for
- What was implemented
- How the changes connect to the existing codebase

### 7i — IDE change justifications

Generate a change summary for each modified file:
- What changed and why
- Which ticket requirement it satisfies
- Any tradeoffs made

Write this to `$WORKSPACE_ABS/change-justifications.md`.

### 7j — Report completion

Update `context.md` status to COMPLETE. Print a summary:
```
Auto pipeline complete for: $WORKSPACE_ID

  Stages completed: [list]
  Stages with issues: [list, if any]
  Files changed: [count]
  Tests passing: [yes/no]
  XRay grade: [grade]
  Audit status: [passed/issues]

  Artifacts:
    ticket-analysis.md
    spec.md
    change-justifications.md
    context.md (full session log)
```

---

## What's Next After /workspace

Once the plan is in place, these are the most common next moves:

| If you... | Run |
|-----------|-----|
| Are working in an unfamiliar codebase | `/index-project <path>` to enable semantic search |
| Have a new subsystem or >15 files | Consider `/create-prd` to lock down scope before implementation |
| Want a dependency map seeded from ticket entities | `/graph [workspace-id]` |
| Just want to start | Copy the "To start executing" command from the plan and run it |
