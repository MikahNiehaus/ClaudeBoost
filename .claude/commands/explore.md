---
argument-hint: <task-id> [project-path]
description: Ticket exploration — workspace setup, ticket analysis, project indexing, code exploration, and implementation planning
allowed-tools: Read, Write, Edit, Bash, Glob, Grep, Agent, AskUserQuestion
---

# /explore — Ticket Exploration Pipeline

Arguments: **$ARGUMENTS**

Orchestrates a full ticket deep-dive: workspace setup → ticket analysis → definition of done → project indexing → code exploration → implementation plan.

---

## Phase 0: Initialize

**0a — Parse arguments and resolve TASK_ID.**

Split `$ARGUMENTS` on whitespace. Treat the full string as a natural-language description unless a real ticket ID or workspace slug is present.

**Step 1 — Classify the first token** (if any) using these rules in order:

| Pattern | Example | Classification |
|---------|---------|----------------|
| `PROJ-NNN` (2-6 uppercase letters, hyphen, digits) | `ASC-1175`, `FEAT-7` | Ticket ID → use as `TASK_ID` |
| Hyphenated slug with 2+ meaningful parts | `fix-login-bug`, `auth-overhaul` | Workspace slug → use as `TASK_ID` |
| Single common verb or word | `fix`, `add`, `update`, `change`, `the`, `it`, `this` | **NOT a task ID** — treat whole `$ARGUMENTS` as description |
| No arguments at all | | No ID provided |

**Step 2 — If no valid TASK_ID was found** (single-word verb, no arguments, or ambiguous):

Scan for active workspaces and read their names + ticket summaries:
```bash
# ClaudeBoost-local workspaces
for d in "${CLAUDEBOOST_HOME}/workspace/"/*/; do
  [ -d "${d}" ] || continue
  name=$(basename "${d}")
  if [ -f "${d}ticket.md" ] || [ -f "${d}context.md" ]; then
    echo "WORKSPACE:${name} (local)"
    [ -f "${d}ticket.md" ] && head -5 "${d}ticket.md"
    echo "---"
  fi
done
# Project-scoped workspaces from registry
"${CLAUDEBOOST_PYTHON}" "${CLAUDEBOOST_HOME}/scripts/register-workspace.py" --list 2>/dev/null
```

**Decision logic — attempt to resolve automatically before asking anything:**

**Case A — Exactly one active workspace:**
Use it. No question. Announce: "Using existing workspace: `workspace/[name]/`."

**Case B — Multiple active workspaces:**
Fuzzy-match `$ARGUMENTS` against each workspace. Score by:
1. Does the workspace name appear in `$ARGUMENTS`? (e.g., "1175" matches `ASC-1175`)
2. Do keywords from `$ARGUMENTS` appear in that workspace's `ticket.md` first 10 lines?
3. Prefer the most recently modified workspace as a tiebreaker.

If one workspace scores clearly higher: use it silently. Announce: "Matched `workspace/[name]/` from your description."

If two or more workspaces tie (no keyword overlap, no name match): only then ask:
```
AskUserQuestion: "Multiple active workspaces — which does '[description]' belong to?
[list each with one-line ticket summary]
Or say 'new' to start a fresh workspace."
```

**Case C — No active workspaces:**
Derive a slug from `$ARGUMENTS` automatically. Do NOT ask.
- Strip filler words: `fix`, `add`, `update`, `change`, `the`, `it`, `this`, `a`, `an`, `for`, `to`, `of`, `in`, `on`
- Take up to 3 remaining content words, lowercase, hyphenate
- Examples: "fix the Orins issue" → `orins-issue`, "add bottom sheet housing" → `bottom-sheet-housing`, "authentication bug on login" → `auth-bug-login`
- Set `TASK_ID` to the derived slug. Announce: "New workspace: `workspace/[slug]/`."

**Step 3 — Determine project path and workspace root (REQUIRED — workspace creation depends on this).**

Remaining tokens (after the token used as TASK_ID, if any) may be `PROJECT_PATH` — an absolute path starting with a drive letter or `/`. Everything else is description context.

**Resolve `PROJECT_PATH` in this order:**

1. If a `PROJECT_PATH` token was found in the remaining arguments: use it.

2. Otherwise check CWD:
   ```bash
   pwd
   ```
   - If CWD is NOT `$CLAUDEBOOST_HOME`: set `PROJECT_PATH = <cwd>`. Announce: "Project detected: [cwd]."
   - If CWD IS `$CLAUDEBOOST_HOME` and no PROJECT_PATH in args: ask now:
     ```
     AskUserQuestion: "What project does this ticket belong to? Provide the full absolute path (e.g., `/home/user/myapp` on Linux/Mac or `C:/Development/MyApp` on Windows) or 'none' if codebase-independent."
     ```
     Set `PROJECT_PATH` from the answer.

**Set workspace root:**
- If `PROJECT_PATH` is set and not 'none': `WORKSPACE_ROOT = $PROJECT_PATH`
- If `PROJECT_PATH = none`: `WORKSPACE_ROOT = $CLAUDEBOOST_HOME`

Set:
- `WORKSPACE_ROOT` (as determined above)
- `WORKSPACE = workspace/$TASK_ID` (for display)
- `WORKSPACE_ABS = $WORKSPACE_ROOT/workspace/$TASK_ID`
- `DESCRIPTION = $ARGUMENTS` stripped of the task ID token (useful context for agents)

> Snippet convention: `$TASK_ID`, `$WORKSPACE_ABS`, `$WORKSPACE_ROOT`, `$ARGUMENTS` are placeholders — substitute the actual literal values before running a snippet; never pass them to Bash as shell variables (bash-guard blocks bare `$VAR`). `${VAR}` brace form marks real runtime shell variables.

**0b — Resume vs fresh.**

Check if `$WORKSPACE_ABS` exists:
```bash
ls "$WORKSPACE_ABS/"
```

If `ls` succeeds → EXISTS; if it errors → NEW. (No `|| echo` fallback — bash-guard blocks it.)

If **EXISTS** and `ticket.md` is present: print "Resuming `$WORKSPACE_ABS` — ticket already saved." Read the existing `ticket.md` and `context.md` for full context. Skip Phase 0c (ticket capture).

If **NEW**: create the workspace:
```bash
mkdir -p "$WORKSPACE_ABS"
```
Announce: "Created `$WORKSPACE_ABS` — starting fresh exploration."

**Register and protect:**

```bash
# Register in workspaces registry so /restore and /clear-safe can find it
"${CLAUDEBOOST_PYTHON}" "${CLAUDEBOOST_HOME}/scripts/register-workspace.py" "$TASK_ID" "$WORKSPACE_ABS" "$PROJECT_PATH"

# Add workspace/ to project .gitignore if writing to a project dir (not ClaudeBoost itself)
if [ "$WORKSPACE_ROOT" != "$CLAUDEBOOST_HOME" ]; then
  if ! grep -qxF 'workspace/' "$WORKSPACE_ROOT/.gitignore" 2>/dev/null; then
    echo 'workspace/' >> "$WORKSPACE_ROOT/.gitignore"
    echo "Added workspace/ to $WORKSPACE_ROOT/.gitignore"
  fi
fi
```

**0c — Capture ticket content.**

If the user's message contains pasted ticket content (multi-line text that looks like a ticket, story, or bug report), save it verbatim.

Otherwise ask:
```
AskUserQuestion: "Paste the full ticket content below (description, acceptance criteria, notes — everything). This is saved verbatim so nothing is lost."
```

Save to `$WORKSPACE_ABS/ticket.md`:
```markdown
# Ticket: $TASK_ID

[verbatim ticket content exactly as provided — do NOT rephrase or summarize]
```

---

## Phase 0.5: RAG Health Check

**Call `GET http://127.0.0.1:8612/status` now — before spawning any agents or calling POST http://127.0.0.1:8612/context.**

This is a fast probe. `GET /status` does not use the embedding model, so it responds in under 1 second if the server is up.

**If `GET http://127.0.0.1:8612/status` returns an error OR the tool is not available:**
> **STOP. Do not proceed.**
> Tell the user: "RAG server is not responding. Run `/rag` to start the server, then retry `/explore $ARGUMENTS`."

**If `GET http://127.0.0.1:8612/status` returns successfully:** note the result internally and proceed to Phase 1. Do not print the status to the user.

**0b — Verify project is indexed** (required for codebase search to work):

Detect the project path:
1. Read `$CLAUDEBOOST_HOME/state/workspaces.json` — use the `project_path` from the entry whose `workspace_path` was most recently modified
2. Fall back to current working directory if no registry entry found

Call `GET http://127.0.0.1:8612/status` and check `indexed_projects` for the detected path.

- **Indexed**: note file/chunk counts and continue.
- **Not indexed**: run `Skill(skill="index-project", args="<project_path>")` immediately. Do not continue until indexing completes.
- **RAG offline**: stop and tell the user to run `/rag` first.

---

## Phase 1: Ticket Analysis

**Gate: ticket.md must exist before spawning. Read it now to confirm.**

Read `$WORKSPACE_ABS/ticket.md`. If empty or missing, abort and re-run Phase 0c.

**1a — Spawn ticket-analyst-agent.**

Spawn `ticket-analyst-agent` (Sonnet) with this prompt:

```
You are analyzing a ticket for task $TASK_ID.

FIRST ACTION: call POST http://127.0.0.1:8612/context with agent="ticket-analyst-agent", task_description="analyze ticket $TASK_ID and produce analysis + definition of done", max_tokens=4000
If POST http://127.0.0.1:8612/context returns an "error" key, STOP immediately and return: "RAG ERROR: [error message]. Run /rag to start the server."

Then:

1. Read $WORKSPACE_ABS/ticket.md (verbatim ticket content)
2. Produce a Ticket Analysis Report (full output-format from your knowledge base)
3. Write your report to $WORKSPACE_ABS/analysis.md
4. Extract the Definition of Done from your analysis and write it to $WORKSPACE_ABS/definition-of-done.md using this format:

   # Definition of Done — $TASK_ID

   ## Acceptance Criteria
   ```gherkin
   [Given/When/Then from analysis]
   ```

   ## Completion Checklist
   - [ ] [Each specific, testable criterion]
   - [ ] All acceptance criteria pass
   - [ ] Tests written and passing
   - [ ] No regressions introduced

   ## Out of Scope
   - [Explicit exclusions]

5. Note any ambiguities or blockers in analysis.md under a "## Open Questions" section.

Return a brief summary: what the ticket wants, the 3-5 acceptance criteria, and any open questions that need user input before implementation begins.
```

Print the agent's summary when it returns.

**1b — Surface open questions to user.**

If the agent's summary contains open questions: present them now and ask the user to answer before proceeding.

```
AskUserQuestion: "The ticket analyst found these open questions:
[list from analysis]

Please answer them so the exploration can continue with accurate context."
```

Update `$WORKSPACE_ABS/analysis.md` with the user's answers under the "## Open Questions" section.

If no open questions: proceed automatically.

---

## Phase 2: Project Indexing

Skip this phase entirely if `PROJECT_PATH = none`.

**2a — RAG health check.**

Call `GET http://127.0.0.1:8612/status`. If it fails: "RAG server not responding — run `/rag` to start the server and retry."

**2b — Scan the project.**

Call `POST http://127.0.0.1:8612/scan with project_path=$PROJECT_PATH`.

Print a concise scan summary:
- Files by language
- Total files to index
- Estimated size

**2c — Index the project.**

Call `POST http://127.0.0.1:8612/index with project_path=$PROJECT_PATH`.

Report: "Project indexed: X files, Y chunks."

Update `$WORKSPACE_ABS/context.md` (create if missing) with:
```markdown
## Project Index
- Path: $PROJECT_PATH
- Indexed: [date]
- Files: X | Chunks: Y
```

---

## Phase 3: Code Exploration

Skip this phase if `PROJECT_PATH = none`.

Read `$WORKSPACE_ABS/analysis.md` to extract the key areas, entities, and scope from the ticket analysis. This is what the explore agent will target.

**3a — Spawn explore-agent.**

Spawn `explore-agent` (Sonnet) with this prompt:

```
You are exploring a codebase to understand what code is relevant to ticket $TASK_ID.

FIRST ACTION: call POST http://127.0.0.1:8612/context with agent="explore-agent", task_description="find code relevant to $TASK_ID in project at $PROJECT_PATH", max_tokens=4000
If POST http://127.0.0.1:8612/context returns an "error" key, STOP immediately and return: "RAG ERROR: [error message]. Run /rag to start the server."

Context:
- Project path: $PROJECT_PATH
- Ticket analysis: [paste summary from analysis.md — key requirements, entities, and scope]
- Definition of done: [paste from definition-of-done.md]

Your task — do ALL of these:

0. Read $WORKSPACE_ABS/analysis.md and extract the `### Code Entities` section.
   If entities are present, use them as specific graph seeds (steps 1-2 below).
   If the section is empty or missing, fall back to generic queries derived from the ticket summary.

1. Semantic search — vector (find semantically similar code):
   - For each entity in Code Entities: POST http://127.0.0.1:8612/search with scope="codebase", project_path="$PROJECT_PATH", query="[entity name]", mode="vector", limit=3
   - If no entities: POST http://127.0.0.1:8612/search with scope="codebase", project_path="$PROJECT_PATH", query="[key feature from ticket] implementation", mode="vector", limit=5

2. Structural search — graph (find structural neighbours of the vector seeds):
   - For each entity: POST http://127.0.0.1:8612/search with scope="codebase", project_path="$PROJECT_PATH", query="[entity name]", mode="graph", limit=3
   - Collect all unique source files from graph results. These are the starting "Files in Scope" map — files that import, inherit from, or are called by the seed results.
   - If no entities: POST http://127.0.0.1:8612/search with scope="codebase", project_path="$PROJECT_PATH", query="[key feature from ticket] implementation", mode="graph", limit=5

3. Targeted Glob + Grep to find:
   - Entry points (routes, controllers, handlers) relevant to the ticket
   - Service/business logic files touched by this ticket
   - Data models or schemas involved
   - Existing tests for affected areas

3. For each relevant file found: read it (or the relevant section) and note:
   - What it does
   - What would need to change for this ticket
   - What tests exist (and what gaps exist)

4. Write your findings to $WORKSPACE_ABS/exploration.md using this structure:

   # Code Exploration — $TASK_ID

   ## Files to Modify
   | File | Purpose | What Changes | Risk |
   |------|---------|--------------|------|
   | path/file.ts | [purpose] | [what changes] | low/med/high |

   ## Files to Create
   | File | Purpose |
   |------|---------|

   ## Existing Tests
   | Test File | Coverage | Gaps |
   |-----------|----------|------|

   ## Key Dependencies
   - [internal deps that affect scope]
   - [external packages involved]

   ## Files in Scope (Graph Map)
   Files identified via graph search on ticket entities — structural neighbours from imports/inheritance:
   | File | Relation | Source Entity |
   |------|----------|--------------|
   | path/to/file.py | imports from | TicketService |

   ## Risk Areas
   [Anything that could break, needs care, or has side effects]

   ## Implementation Notes
   [Patterns to follow, conventions found, gotchas]

5. Return a brief summary: files to modify, biggest risk, and what tests need to be written.
```

Print the agent's summary when it returns.

---

## Phase 4: Implementation Plan

**4a — Load ClaudeBoost RAG context.**

Call `POST http://127.0.0.1:8612/context with agent="architect-agent", task_description="implementation plan for ticket $TASK_ID", max_tokens=5000`.

**If the result contains an "error" key: STOP. Tell the user: "RAG error loading context — run `/rag` to start the server, then retry."**

This loads architecture, workflow, testing, and security knowledge to validate the plan.

**4b — Search for relevant patterns.**

Run these RAG searches to inform the plan:

```
POST http://127.0.0.1:8612/search with scope="knowledge", query="implementation planning workflow decomposition", limit=3
POST http://127.0.0.1:8612/search with scope="knowledge", query="testing strategy coverage acceptance criteria", limit=3
```

If `PROJECT_PATH` is not none:
```
POST http://127.0.0.1:8612/search with scope="codebase", project_path=$PROJECT_PATH, query="[main entity from ticket] patterns conventions", limit=3
POST http://127.0.0.1:8612/search with scope="codebase", project_path=$PROJECT_PATH, query="[main entity from ticket] patterns conventions", limit=3, mode="graph"
```
Run both modes: vector finds semantically similar patterns, graph surfaces files that import or inherit from the seed files — revealing where these patterns propagate across the codebase.

**4c — Synthesize and write the plan.**

Read all workspace documents produced so far:
- `$WORKSPACE_ABS/ticket.md` — original requirements
- `$WORKSPACE_ABS/analysis.md` — ticket analysis + acceptance criteria
- `$WORKSPACE_ABS/definition-of-done.md` — completion criteria
- `$WORKSPACE_ABS/exploration.md` — relevant code locations

Write `$WORKSPACE_ABS/plan.md`:

```markdown
# Implementation Plan — $TASK_ID

**Ticket**: [one-line summary]
**Date**: [today]
**Status**: DRAFT

## Summary
[2-3 sentences: what this does, why, what changes]

## Approach
[Chosen implementation strategy and rationale. If multiple approaches exist, note why this one was selected.]

## Subtasks

| # | Task | Agent | File(s) | Dependencies | Est. Risk |
|---|------|-------|---------|--------------|-----------|
| 1 | [task] | [agent-name] | [files] | none | low |
| 2 | [task] | [agent-name] | [files] | 1 | med |

## Execution Order
[Sequential or parallel? Diagram if needed.]

## Test Plan
| Test | Type | File | Covers |
|------|------|------|--------|
| [test description] | unit/integration/e2e | [path] | [AC-N] |

## Risks & Mitigations
| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| [risk] | low/med/high | [mitigation] |

## Out of Scope
[Confirmed exclusions from analysis.md]

## Definition of Done
[Copy checklist from definition-of-done.md]
```

**4d — Present plan to user.**

Print the full plan. Then ask:

```
AskUserQuestion: "Plan ready for $TASK_ID.

Workspace: $WORKSPACE_ABS/
  - ticket.md         — original ticket (verbatim)
  - analysis.md       — requirements, acceptance criteria, open questions
  - definition-of-done.md — completion checklist
  - exploration.md    — relevant code, files to change, test gaps
  - plan.md           — implementation plan (this)

Reply 'approve' to begin implementation, 'modify' to adjust the plan, or ask any questions."
```

---

## Resume Notes

- Re-running `/explore $TASK_ID` on an existing workspace resumes from the earliest missing artifact.
- If `ticket.md` exists but `analysis.md` is missing → resumes from Phase 1.
- If `analysis.md` exists but `exploration.md` is missing → resumes from Phase 3.
- If `exploration.md` exists but `plan.md` is missing → resumes from Phase 4.
- If `plan.md` exists → prints the plan and asks if modifications are needed.
