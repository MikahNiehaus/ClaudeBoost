---
argument-hint: <target-url> [scope — auth | crud | nav | errors | responsive | all]
description: End-to-end UI testing — discovers app via RAG + browser, writes test plan, executes browser-only with screenshot evidence
allowed-tools: Read, Write, Edit, Bash, Glob, Grep, Agent, mcp__playwright__browser_navigate, mcp__playwright__browser_snapshot, mcp__playwright__browser_click, mcp__playwright__browser_type, mcp__playwright__browser_take_screenshot, mcp__playwright__browser_evaluate, mcp__playwright__browser_fill_form, mcp__playwright__browser_select_option, mcp__playwright__browser_wait_for, mcp__playwright__browser_press_key, mcp__playwright__browser_console_messages, mcp__playwright__browser_resize, mcp__playwright__browser_close, mcp__mcp-debugger__create_debug_session, mcp__mcp-debugger__attach_to_process, mcp__mcp-debugger__set_breakpoint, mcp__mcp-debugger__continue_execution, mcp__mcp-debugger__get_variables, mcp__mcp-debugger__get_scopes, mcp__mcp-debugger__step_over, mcp__mcp-debugger__step_into, mcp__mcp-debugger__step_out, mcp__mcp-debugger__evaluate_expression, mcp__mcp-debugger__list_debug_sessions, mcp__mcp-debugger__close_debug_session, mcp__mcp-debugger__get_stack_trace
---

# /end-to-end-test — Browser-Only E2E Test Suite

Arguments: **$ARGUMENTS**
(Format: `<url>` or `<url> <scope>` — e.g., `http://localhost:3000 auth`)

---

## Phase 0: Load RAG Context (MANDATORY FIRST ACTION)

Call `POST http://127.0.0.1:8612/context with agent="workflow-agent", task_description="end-to-end UI test planning and execution", max_tokens=3000`.

This loads relevant knowledge before any work begins. If `POST http://127.0.0.1:8612/context` fails: stop and tell the user "RAG is not connected. Run /boost before using this skill."

**0b — Verify project is indexed** (required for codebase search to work):

Detect the project path:
1. Read `$CLAUDEBOOST_HOME/state/workspaces.json` — use the `project_path` from the entry whose `workspace_path` was most recently modified
2. Fall back to current working directory if no registry entry found

Call `GET http://127.0.0.1:8612/status` and check `indexed_projects` for the detected path.

- **Indexed**: note file/chunk counts and continue.
- **Not indexed**: run `Skill(skill="index-project", args="<project_path>")` immediately. Do not continue until indexing completes.
- **RAG offline**: stop and tell the user to run `/rag` first.

---

## Phase 1: Initialize

**0a — Parse arguments.**

Split `$ARGUMENTS` on whitespace. First token = `TARGET_URL`. Second token = `SCOPE` (valid: `auth`, `crud`, `nav`, `errors`, `responsive`, `all`; default to `all` if omitted).

**0a-ii — Ticket tracing (ask if not provided).**

If the user is working from a ticket (e.g., `ASC-1175`, `FEAT-42`), ask:
```
Which ticket is this testing? (Enter ID or 'none')
What was the original bug / broken behavior?
```

Record the answers as `TICKET_ID` and `ORIGINAL_BUG_DESC`. These are used in Phase 2 to ensure at least one TC directly targets the broken scenario — not just the display side of the fix.

If the user says 'none', skip ticket tracing. Do not block on this.

**0b — Environment hard-stop (check BEFORE any browser action).**

**URL pattern check (static):**
If `TARGET_URL` contains any of: `staging`, `stg`, `stage`, `prod`, `prd`, `production`
OR ends with: `.azurewebsites.net`, `.herokuapp.com`, `.vercel.app`, `.netlify.app`, `.azure.com`, `.cloudapp.net`, `.onmicrosoft.com`
→ STOP immediately. Print: "Cannot run E2E tests against staging/production URL." No exceptions, no override.

> Note: This is a static check on the URL you were given. A live environment probe happens in Phase 1a AFTER navigation, which catches OAuth redirects and hidden prod environments.

**0c — Derive TASK_ID and workspace root (resume-first).**

Before creating anything, check for an existing workspace. **Ticket workspace takes priority over URL-based workspace.**

**Determine workspace root:**

Check CWD:
```bash
pwd
```
- If CWD is NOT `$CLAUDEBOOST_HOME`: set `WORKSPACE_ROOT = <cwd>`. Announce: "Project detected: [cwd]."
- If CWD IS `$CLAUDEBOOST_HOME`: set `WORKSPACE_ROOT = $CLAUDEBOOST_HOME`.

**Step 1 — Ticket workspace check (runs first if TICKET_ID is set):**

If `TICKET_ID` was captured in Phase 0a-ii (not 'none'):

First check the registry for a project-scoped workspace:
```bash
"${CLAUDEBOOST_PYTHON}" "${CLAUDEBOOST_HOME}/scripts/register-workspace.py" --get "$TICKET_ID" 2>/dev/null
```
If it returns a path, use that as `WORKSPACE_ABS`. Set `TASK_ID = $TICKET_ID`. Skip Step 2. Proceed to resume-phase detection below.

Otherwise check `$WORKSPACE_ROOT/workspace/$TICKET_ID/`:
```bash
ls "$WORKSPACE_ROOT/workspace/$TICKET_ID/" 2>/dev/null
```
If the folder exists → set `TASK_ID = $TICKET_ID`, `WORKSPACE_ABS = $WORKSPACE_ROOT/workspace/$TASK_ID`. Skip Step 2. Proceed to resume-phase detection below.

**Step 2 — URL-based workspace check (runs only if no ticket workspace found):**

```bash
ls "$WORKSPACE_ROOT/workspace/" 2>/dev/null | grep "^e2e-[HOSTNAME]-[PORT]-"
```

(Replace `[HOSTNAME]` and `[PORT]` with the values parsed from `TARGET_URL`.)

If one or more matching workspaces exist:
- Find the most recent (sort by date suffix descending).
- Set `TASK_ID` to that folder name, `WORKSPACE_ABS = $WORKSPACE_ROOT/workspace/$TASK_ID`.

If no matching workspace exists OR `$ARGUMENTS` contains `--fresh`:
- Derive: `TASK_ID = e2e-[hostname]-[port]-[YYYY-MM-DD]`
- Example: `e2e-localhost-3000-2026-05-10`
- Set `WORKSPACE_ABS = $WORKSPACE_ROOT/workspace/$TASK_ID`
- Proceed to Phase 0d (no resume check needed for a new workspace).

**Resume-phase detection (runs after TASK_ID is set to an existing folder):**

Check which files exist in `$WORKSPACE_ABS/`:

| Files present | Resume at |
|---|---|
| `report.md` | All phases complete — print "Workspace has a completed report. Use `--fresh` to start over." then STOP. |
| `plan.md` with at least one `- [ ] TC-` line | Phase 2 done → skip Phases 0e–2, jump to Phase 3 |
| `plan.md` but no unchecked `[ ]` lines | All TCs already marked → print "All tests have results. Use `--fresh` to re-run." then STOP. |
| `context.md` and `flow-map.md` but no `plan.md` | Phase 1 + 2a done → skip Phases 0e–2a, jump to Phase 2b |
| `context.md` but no `flow-map.md` and no `plan.md` | Phase 1 done → skip Phases 0e–1, jump to Phase 2 |
| Neither `context.md` nor `plan.md` | Workspace exists but no E2E state yet → proceed to Phase 0d |

Print:
```
Resuming workspace: workspace/[existing-task-id]/
Detected state: Phase [N] in progress — skipping completed phases.
(Use /end-to-end-test <url> --fresh to force a new session.)
```

**0d — Create workspace, set SNAPSHOTS_DIR and PROOF_DIR.**

Set `SNAPSHOTS_DIR = $WORKSPACE_ABS/screenshots`.

Derive `PROOF_DIR` — this is where TC pass-evidence screenshots land (separate from discovery and temp shots):
- If `TICKET_ID` is set (not 'none'): `PROOF_DIR = $SNAPSHOTS_DIR/proof-[TICKET_ID]`
  Example: `$WORKSPACE_ABS/screenshots/proof-ASC-1175`
- Otherwise: `PROOF_DIR = $SNAPSHOTS_DIR/proof-[hostname]-[YYYY-MM-DD]`
  Example: `$WORKSPACE_ABS/screenshots/proof-localhost-2026-06-05`

```bash
mkdir -p "$SNAPSHOTS_DIR"
mkdir -p "$PROOF_DIR"
```

Announce: "Screenshots → `$SNAPSHOTS_DIR/` | Proof → `$PROOF_DIR/`"

What goes where:
- `$SNAPSHOTS_DIR/` — discovery shots (`discovery-home.png`) and anything taken outside a TC
- `$PROOF_DIR/` — TC-NNN-after.png (PASS evidence), TC-NNN-before.png (state-change pairs), TC-NNN-debug.json

**Register and protect (new workspaces only):**

```bash
# Register so /restore and /clear-safe can find this workspace
"${CLAUDEBOOST_PYTHON}" "${CLAUDEBOOST_HOME}/scripts/register-workspace.py" "$TASK_ID" "$WORKSPACE_ABS" "$WORKSPACE_ROOT"

# Add workspace/ to project .gitignore if writing to a project dir
if [ "$WORKSPACE_ROOT" != "$CLAUDEBOOST_HOME" ]; then
  if ! grep -qxF 'workspace/' "$WORKSPACE_ROOT/.gitignore" 2>/dev/null; then
    echo 'workspace/' >> "$WORKSPACE_ROOT/.gitignore"
    echo "Added workspace/ to $WORKSPACE_ROOT/.gitignore"
  fi
fi
```

**0e — Load knowledge via RAG (do this FIRST before any browser action).**

Call `POST http://127.0.0.1:8612/context with agent="e2e-agent", task_description="end-to-end UI test of $TARGET_URL scope=$SCOPE", max_tokens=5000`.

This loads the e2e-testing knowledge base (anti-cheat rules, intelligent test generation, annotation technique), playwright knowledge, and testing patterns.

**0f — Index project codebase.**

```bash
pwd
```

Call `POST http://127.0.0.1:8612/index with project_path=<cwd output>`. Report: "X files indexed."

This enables RAG search over the app's routes, components, and entities during discovery.

**0g — UI Scope Graph (runs when TICKET_ID is set and project is indexed).**

Skip if `TICKET_ID` was not provided or project indexing failed.

Extract UI-relevant entities from the ticket workspace in this order:

1. Read `$WORKSPACE_ABS/analysis.md` — look for the `### Code Entities` section (written by ticket-analyst-agent). Extract names from Files/paths, Services/classes, and Endpoints.
2. If analysis.md is absent or Code Entities is empty: read `$WORKSPACE_ABS/ticket.md` and extract PascalCase names, `/api/` paths, component names, and page/route references from the ticket text.

For each entity found, run **both** calls — never just one:

```
POST http://127.0.0.1:8612/search with scope="codebase", project_path=<cwd>, query="[entity]", mode="vector", limit=3
POST http://127.0.0.1:8612/search with scope="codebase", project_path=<cwd>, query="[entity]", mode="graph", limit=3
```

Vector finds files that do the same thing as the entity. Graph finds files that import, render, or call the entity — route files, page components, API handlers, and form validators that are structurally connected to it.

From the combined results, identify:
- **Route / page files** that render or navigate to the entity (e.g., `OrdersPage.tsx`, `OrdersController.cs`)
- **Form / action files** that submit or mutate the entity
- **API handler files** the ticket changes

Map each file to its most likely URL route using filename and path conventions (e.g., `src/pages/orders/index.tsx` → `/orders`, `controllers/OrdersController.cs` → `/orders`).

Append a **UI Pages in Scope** section to `$WORKSPACE_ABS/context.md` (create context.md if it doesn't exist yet):

```markdown
## UI Pages in Scope (Graph Map)
Seeded from ticket entities — vector + graph RAG. Prioritize these in browser crawl and test plan.
| URL / Route | File | Seed Entity | How Connected |
|-------------|------|-------------|---------------|
| /orders | src/pages/orders/index.tsx | OrderService | imports |
| /orders/:id | src/pages/orders/detail.tsx | OrderService | imports |
```

If no entities are found or graph returns no results: skip silently — Phase 1b's general searches cover the case.

---

## Phase 1: App Discovery

**Token efficiency: use `browser_snapshot` (text) for all discovery. Only ONE `browser_take_screenshot` at the very start.**

**1a — Navigate and take initial screenshot.**

Display environment confirmation:
```
┌────────────────────────────────────┐
│ ENVIRONMENT CONFIRMED              │
│ Type: LOCALHOST                    │
│ URL: $TARGET_URL                   │
│ Status: Auto-approved              │
└────────────────────────────────────┘
```

Call `browser_navigate(url=$TARGET_URL)`.
Call `browser_take_screenshot` → save to `$SNAPSHOTS_DIR/discovery-home.png`. (Discovery shot — stays in base screenshots/ folder, not in proof subfolder.)
Call `browser_console_messages` — note any startup errors.

**Live environment probe (runs immediately after first navigation — catches OAuth redirects):**

1. Call `browser_snapshot`. Read the current URL from the accessibility tree.
   - If the URL has changed from `TARGET_URL` (e.g., redirected by SSO/OAuth), re-run the Phase 0b blocklist check against the NEW URL.
   - If the new URL matches any blocked pattern → **STOP**. Print: "Redirect detected to non-local URL: [new url]. Halting to protect production data."

2. Call `browser_evaluate` with:
   ```javascript
   JSON.stringify({
     hostname: window.location.hostname,
     env: window.__ENV__ || window.ENV || window.environment || null,
     title: document.title
   })
   ```
   - If `hostname` is not `localhost`, `127.0.0.1`, `0.0.0.0`, or a `.local`/`.test` domain → **STOP**.
   - If `env` value contains `prod`, `production`, `live`, or `staging` → **STOP**.
   - If `title` contains `Production`, `PROD`, or `Live` → **STOP**.
   - On any STOP: Print: "Environment probe blocked execution: [detail]. This appears to be a non-local or production environment."

3. Scan `browser_snapshot` accessibility tree for visible text: "Production Environment", "PROD", "Live Site", "Do not test here". If found → **STOP** with the same message.

Only continue past this probe if ALL checks pass.

**Switch to snapshots-only from here forward during discovery.**

**1b — Parallel discovery: spawn codebase analysis agent while browser crawl runs.**

Do not wait for codebase analysis before starting the browser crawl. Dispatch both at the same time.

**Spawn `workflow-agent` (background) for codebase analysis.** The spawn prompt must include:
1. `POST http://127.0.0.1:8612/context` as first action with `agent="workflow-agent"`, `task_description="codebase route and entity analysis for E2E discovery"`, `project_path=<cwd>`
2. Run all three RAG searches in parallel:
   - `POST /search scope=codebase project_path=<cwd> query="routes pages navigation URL paths" mode=graph limit=6`
   - `POST /search scope=codebase project_path=<cwd> query="authentication login session user roles" mode=graph limit=5`
   - `POST /search scope=codebase project_path=<cwd> query="form submit create update delete entity model" mode=graph limit=5`
3. Also search for server-side handlers: `POST /search scope=codebase query="controller handler action endpoint API" mode=graph limit=6`
4. Return: a deduplicated list of (route path → source file → method/function name) mappings, plus auth mechanism and form structures found.
5. End with `## Summary` (≤200 words): route list, auth type, entity names, top controller files.

**Main agent — immediately start the browser crawl (Phase 1c) in parallel.**

Read `UI Pages in Scope` from context.md (built in Phase 0g) while the agent runs — these are the highest-confidence targets for the browser.

Merge results when the agent returns: combine the agent's route/entity findings with the browser crawl's direct observations. Deduplicate by route. The combined list becomes the app map and test plan seed.

**1c — Browser crawl (snapshots only, max 2 levels deep).**

Call `browser_snapshot`. From the accessibility tree, extract ALL nav links, buttons, and top-level interactive elements. Record each.

**Crawl order — pages from UI Pages in Scope go first:**
If Phase 0g built a UI Pages in Scope map, navigate to those routes before the general nav crawl. They're the highest-priority pages for this ticket. For each in-scope route:
- `browser_navigate` to the route (confirm it exists — note if 404)
- `browser_snapshot` — record: page title, forms, tables, interactive elements, component types
- Return to `$TARGET_URL`

Then crawl remaining top-level nav links found in the snapshot:
- `browser_navigate` to the link
- `browser_snapshot` — record: page title, forms present, lists/tables present, buttons, component types
- Do NOT go deeper than one level from here

Return to `$TARGET_URL` after crawling each branch.

**1d — Build component registry.**

While crawling, catalog every UI component instance with its type, page, and structure:

| Component type | Page | Selector hint | N states / items |
|---|---|---|---|
| `<select>` dropdown | /products | #sort-select | 4 options |
| Toggle (radio group) | /settings | [role=radiogroup] | 3 states |
| List/collection | /orders | [role=list] | variable |
| Form | /create | form#create | 5 fields |

Flag any component that uses a **different HTML structure** than other instances of the same logical type (e.g., `<select>` on one page, `<div role="combobox">` on another — this is a UI inconsistency candidate).

**1e — Write App Map.**

Write `$WORKSPACE_ABS/context.md`:

```markdown
# App Map — $TARGET_URL

**Date**: [date]
**Scope**: $SCOPE

## Pages Discovered
- / — [description]
- /[page] — [description]
(list all pages found)

## Authentication
- Required: yes/no
- Login route: [path if found]
- Protected routes: [list]

## Entities
[list entity names found via RAG and browser]

## Key Flows
[list CRUD flows, auth flows, etc. found]

## Component Registry
[table from step 1d]

## UI Pages in Scope (Graph Map)
[copy from Phase 0g if built — otherwise 'N/A — no ticket provided']

## Startup Console Errors
[any errors from browser_console_messages on load]
```

---

## Phase 2: Test Plan Generation

**PHASE 2 ENTRY GATE — verify before starting:**

Read `$WORKSPACE_ABS/context.md`. Confirm it exists and has a non-empty "Pages Discovered" section.

If context.md does NOT exist or has no pages listed → **STOP**. Do not proceed. Print: "Phase 2 blocked: App Map not found. Complete Phase 1 first." Return to Phase 1.

---

**The test plan is written to disk BEFORE any test executes. This is structural anti-cheat — a plan that predates execution cannot be fabricated.**

---

**2a — Map user journeys. Write `flow-map.md` BEFORE any test cases.**

The most common source of bad E2E tests is generating them from what the browser saw (components, pages, fields) instead of from what users actually do (journeys). This step inverts that: identify the 5–10 highest-risk user journeys first, then derive TCs from those journeys.

**What is a user journey?** A journey is a goal a real user wants to accomplish — "register an account", "submit an order", "edit a saved address". It spans multiple pages and involves a sequence of actions. A page is not a journey. A form field is not a journey.

**Step 1 — Derive journeys from available sources (in priority order):**
1. **Ticket content** (if TICKET_ID is set): derive journeys directly from the acceptance criteria or bug description. These are always high-risk.
2. **App Map + component registry** (from context.md Phase 1): look at the full set of pages and forms. For each form or interactive action, ask "what user goal does this serve?" That goal is a journey candidate.
3. **RAG codebase search**: query `POST http://127.0.0.1:8612/search scope=codebase query="route controller action" mode=graph limit=5`. Use the returned routes to identify multi-step flows (login → redirect, create → confirm, etc.).

**Step 2 — Score each journey by risk:**

| Risk signal | Score |
|---|---|
| Involves authentication or authorization | +3 |
| Involves writing data (create, update, delete) | +2 |
| Is the primary revenue or conversion path | +3 |
| Involves multiple pages or redirects | +1 |
| Involves external integration (email, payment, webhook) | +2 |
| Has a known prior bug (from TICKET_ID) | +3 |
| Is purely navigational (no state change) | +0 |

Keep all journeys scoring 3+. Keep the top 10 maximum. Smoke tests (home loads, nav links) are always included but don't need journey scoring.

**Step 3 — Write `$WORKSPACE_ABS/flow-map.md`:**

```markdown
# Flow Map — [APP_NAME] — [DATE]

## Journeys

| # | Journey Name | User Goal | Entry URL | Steps | Pages Touched | Risk Score |
|---|---|---|---|---|---|---|
| J1 | User Registration | New user creates account | /register | 1. Navigate to /register → 2. Fill form → 3. Submit → 4. Verify welcome state | /register, /dashboard | 6 |
| J2 | ... | ... | ... | ... | ... | ... |

## Smoke Tests (always include)
- S1: Home page loads without console errors
- S2: All primary nav links resolve without 404
```

**Step 4 — Hard gate:** If `flow-map.md` does not exist when Phase 2b starts, STOP. Print: "Phase 2b blocked: flow-map.md not found. Complete Phase 2a first." Do not generate test cases until the flow map is written.

---

**2b — Generate test cases from flow-map.md journeys + intelligent rules.**

TCs come from journeys, not from components. For each journey in flow-map.md:
- Generate TCs that walk the journey end-to-end: entry → actions → final observable state
- Take the **most direct path to the feature** — no roundabout navigation through unrelated pages
- Each TC must reference its parent journey: `[Journey: J1 — User Registration, Step 3]`
- One TC covers one step or one decision point in the journey; don't bundle multiple independent decisions into one TC

**E2E scope boundary — what belongs here vs in unit tests:**

| Belongs in E2E | Belongs in unit/integration tests (skip here) |
|---|---|
| Full journey: enter data → submit → verify server persisted it | Whether a single field validator rejects an empty string |
| Auth redirect: unauthenticated user → sent to login → returns after auth | Whether a pure function returns the correct computed value |
| State visible after server round-trip: create → reload page → item still shown | Whether an API endpoint returns the right JSON shape |
| Cross-page flow: form on /checkout → confirmation on /orders | Whether a CSS class is applied by a component |

**Rule:** If a TC could be fully verified by calling a function directly (no browser, no server round-trip, no multi-page flow), it belongs in unit tests. Drop it or demote it to a `## Unit Coverage Notes` section in plan-draft.md.

**Always include regardless of scope:**
- `TC-SMOKE-01`: Home page loads without console errors
- `TC-SMOKE-02`: All primary nav links resolve without 404

**Intelligent test generation rules (apply per journey step):**

| Control type | Rule |
|---|---|
| Toggle/select/enum with N≤7 states | Generate ONE TC per state |
| Boolean | Always 2 TCs |
| List/collection UI | Always 4 TCs: empty state, one item, 3-5 items, max/full |
| Form validation | One TC per validation rule (not per field) — E2E only if the validation requires a server round-trip or cross-field dependency; client-only validation belongs in unit tests |
| Same component with multiple instances | One UI consistency TC for the type |
| Large enum (N>7) | Boundary values: first option, last option, one invalid |

**Scope-to-category mapping:**

| Scope | Categories to generate |
|---|---|
| `auth` | Login happy path, login bad credentials, logout, protected route without auth |
| `crud` | Create / read list / read detail / update / delete / empty state — per entity |
| `nav` | Each nav link resolves, back-button, breadcrumb accuracy |
| `errors` | Required field blank (if server-validated), invalid format (if server-validated), 404 page |
| `responsive` | Key pages at 375px, 768px, 1280px |
| `all` | Union of all above + UI consistency pass |

**Each test case format:**
```markdown
- [ ] TC-001: [Category] — [Description]
  - Journey: [J# — Journey Name, Step N] (or "smoke" for smoke tests)
  - Steps: [numbered, browser-action-only steps — most direct path to the feature]
  - Expected: [exact observable UI outcome after the final step]
  - Evidence: TC-001-after.png
  - Code path: [file:line — server-side entry point this TC hits, from UI scope graph or RAG; leave as 'client-side' if no server call involved]
  - Source: [RAG hit / browser discovery / component registry]
```

**Coverage completeness mandate (anti-laziness — enforce before writing draft):**

- Every **journey in flow-map.md** → at least one TC per decision point or observable outcome in that journey. These cannot be omitted or marked BLOCKED for difficulty.
- Every **page in UI Pages in Scope** (from Phase 0g) that is part of a journey → covered by the journey's TCs; no extra per-page TCs needed unless the page has a form or action not covered by any journey.
- Every **entity** discovered via RAG with CRUD routes → create + read-list + delete TCs (update if an edit route exists) — these map to the CRUD journeys.
- If a discovered component has NO journey that exercises it: write it in a `## Gaps` section of plan-draft.md with a one-line justification. "It seemed unimportant" is not a valid justification.
- BLOCKED status is only valid for genuine external preconditions (e.g., "requires admin account not provisioned"). Complexity or difficulty is never a valid reason.

**Ticket tracing (if TICKET_ID was provided in Phase 0):**

Add a `TC-TICKET-01` test case that directly exercises `ORIGINAL_BUG_DESC`. This TC:
- Must test the **write side or trigger side** of the fix, not just the display side.
- Example: if the bug was "background job not writing DB records", the TC must verify records were written — not just that the UI renders them.
- If the write side requires a background job, use the **Background Job Verification protocol** in Phase 3.
- Mark this TC as `[REQUIRED — ticket regression]` in the plan. It cannot be BLOCKED or marked "prior session".

**Write draft plan to disk:** `$WORKSPACE_ABS/plan-draft.md`

**2c — Anti-hallucination evaluator.**

Spawn `evaluator-agent` to audit the draft plan. Pass in:
- The full contents of `plan-draft.md`
- The flow-map.md journeys
- The App Map from `context.md`
- The RAG search result summaries from Phase 1b

Evaluator checks each TC:
- Does the TC reference a journey from flow-map.md?
- Does the route/page referenced appear in the App Map?
- Does the TC test an observable user-facing outcome (not an implementation detail)?
- Does the TC take the most direct path to the feature (no unnecessary navigation steps)?

Evaluator returns a list of TCs to remove or demote. Apply those changes.

Print: "Evaluator removed N test cases as unverified or unit-level (not E2E scope)."

**2d — Write final plan and present to user.**

Write cleaned plan to `$WORKSPACE_ABS/plan.md`.

Show the full plan to the user. Print test count.

**PAUSE HERE — do not start Phase 3 until user responds.**

Ask: "Test plan written to `$WORKSPACE_ABS/plan.md`. Found **N test cases** (M removed by evaluator as unverified). Respond **'go'** to start execution, or describe changes."

---

## Phase 3: Test Execution — Browser Only

**⛔ PHASE 3 ENTRY GATE — MANDATORY CHECK BEFORE ANY BROWSER ACTION:**

1. Read `$WORKSPACE_ABS/plan.md`.
2. Verify it exists AND contains at least one `- [ ] TC-` line.

If plan.md does NOT exist or has no test cases → **STOP**. Do not proceed to any browser action.
Print: "Phase 3 blocked: plan.md not found or empty. Complete Phase 2 first."
Return to Phase 2 and generate the test plan.

This gate exists because Phase 3 executes a pre-written plan. There is no such thing as "running tests while writing the plan" — that produces fabricated results. The plan must exist on disk, written before execution began.

---

**Prior-session result check (mandatory when resuming an existing workspace):**

If `plan.md` already contains result entries from a previous run (lines starting with `- [x]`, `- [F]`, or `- [B]`):

1. Count prior-session results: how many TCs are already marked in each category.
2. Print:
   ```
   ⚠️  RESUMING WORKSPACE — Prior Session Results Detected
   ─────────────────────────────────────────────────────
   Found N tests with prior-session results:
     [x] PASS:    M  →  must re-run or explicitly accepted
     [F] FAIL:    N  →  must re-run or explicitly accepted
     [B] BLOCKED: N  →  carried over if blocking reason unchanged

   Type 'rerun all'          — re-run everything from scratch
   Type 'accept TC-001,002'  — carry over specific results as-is
   Type 'rerun TC-003,004'   — re-run specific tests, carry over the rest
   ─────────────────────────────────────────────────────
   ```
3. **PAUSE — wait for user response before running any test.**
4. Apply the user's selection:
   - Accepted TCs: keep existing result entry unchanged.
   - Re-run TCs: reset their line to `- [ ] TC-NNN: ...` (unchecked) in plan.md.
   - Any TC not explicitly accepted → reset to `[ ]` and re-run.
5. **TC-TICKET-01 marked `[REQUIRED — ticket regression]` is NEVER accepted as a prior-session result.** Reset it to `[ ]` regardless of what the user says and re-run it.
6. If no prior-session results exist (this is a fresh plan): skip this block and proceed immediately.

---

**Phase 3 Pre-flight: Attach Debugger (runs once, before any TC executes).**

Code-level step-through is always part of every E2E session. This block runs after the prior-session check and before the first TC.

**Step A — Production guard (re-checked here — never skip).**

Before attaching to ANY process: confirm `TARGET_URL` passed Phase 0b. If the URL contains `staging`, `stg`, `stage`, `prod`, `prd`, `production`, or ends with `.azurewebsites.net`, `.herokuapp.com`, `.vercel.app`, `.netlify.app` → **STOP immediately**. Do not attach the debugger. Do not run tests. This is the same hard stop as Phase 0b — it is checked again here to prevent race conditions if Phase 0b was somehow bypassed.

Only attach to processes running on the LOCAL machine. Never use `mcp__mcp-debugger__attach_to_process` with a remote host, IP outside 127.0.0.1/localhost, or credentials from a config file.

**Step B — Detect the running server process.**

Run on Windows:
```bash
tasklist /FI "IMAGENAME eq dotnet.exe" /FO CSV 2>nul && tasklist /FI "IMAGENAME eq node.exe" /FO CSV 2>nul
```

Parse the output into a table:
```
Detected server processes:
  [PID]  dotnet.exe
  [PID]  node.exe
```

**Step C — Determine language and attach.**

- If only dotnet processes found → language = `csharp`, pick the first PID.
- If only node processes found → language = `javascript`, pick the first PID.
- If both found → print the table and ask: "Which process should the debugger attach to? (Enter PID)"
- If neither found → set `DEBUG_ENABLED = false`. Print: "No server process found — tests will run UI-only. Start the app in debug mode and re-run to enable code verification." Skip to the TC loop.

**Step D — Verify debugger prerequisites before attaching.**

If `language = csharp`: check that `netcoredbg` is available (mcp-debugger requires it for .NET).

Run (two separate calls — compound `|| echo` fallbacks and bare `$VAR` are blocked by bash-guard):
```bash
command -v netcoredbg
```

If that errors, check the configured path:
```bash
ls "${NETCOREDBG_PATH}/netcoredbg.exe"
```

- If either command returns a path → continue to attach (use that path).
- If both error → NOT_FOUND: set `DEBUG_ENABLED = false`. Print the following, then skip to the TC loop:

```
netcoredbg not found. mcp-debugger requires netcoredbg for .NET debugging.

To install — pick one:

  Option A (dotnet global tool):
    dotnet tool install -g Samsung.Netcoredbg
    Then add the tool path to PATH (usually %USERPROFILE%\.dotnet\tools)

  Option B (manual install, Windows):
    1. Download the latest release from:
       https://github.com/Samsung/netcoredbg/releases
    2. Extract netcoredbg.exe to a folder (e.g. C:\Tools\netcoredbg\)
    3. Either add that folder to your PATH, or set the env var:
       $env:NETCOREDBG_PATH = "C:\Tools\netcoredbg"

After installing, re-run this E2E test to enable code step-through.
Tests will run UI-only for this session.
```

If `language = javascript`: no extra prerequisites — Node.js uses the built-in V8 inspector. Continue to attach.

Call `mcp__mcp-debugger__create_debug_session` with `language=<detected>` and `name="e2e-session"` → store result as `DEBUG_SESSION_ID`.

Call `mcp__mcp-debugger__attach_to_process` with `sessionId=DEBUG_SESSION_ID` and `processId=<PID>`.

- Success → set `DEBUG_ENABLED = true`. Print: "Debugger attached (PID <PID>, session <DEBUG_SESSION_ID>)."
- Failure → set `DEBUG_ENABLED = false`. Print: "Debugger attach failed: <error>. Tests will run UI-only." Call `mcp__mcp-debugger__close_debug_session` to clean up.

Keep `DEBUG_SESSION_ID` open for the entire Phase 3 session.

---

**Print this block BEFORE running any test:**

```
========================================
EXECUTION MODE: UI-ONLY
========================================
BANNED ACTIONS IN THIS PHASE:
  - Bash: no psql, mysql, sqlite3, mongosh, redis-cli, or any DB query
  - No reads of .db, .sqlite, seed, or migration files as verification
  - No internal API calls via browser_evaluate to bypass the UI
  - No marking [x] PASS before the AFTER screenshot is saved
  - No silent omissions — every TC gets PASS / FAIL / BLOCKED
  - No BLOCKED for difficulty — only for genuine missing preconditions
  - No skipping steps because they "seem unnecessary"
  - No inferring success without snapshot confirmation
========================================
TOKEN EFFICIENCY: snapshot first (text), screenshot only after
text confirms expected state. Failed tests: no screenshot needed.
========================================
```

**Destructive action pre-flight (MANDATORY — runs once before ANY test executes):**

1. Scan `plan.md` for all TCs whose Steps contain: create, submit, save, add, update, edit, delete, remove, toggle, change, clear, reset.
2. Build a table of destructive TCs:

   | TC-ID | Action type | Entity / target |
   |-------|-------------|-----------------|
   | TC-03 | create      | Order           |
   | TC-07 | delete      | Product         |

3. If the table is non-empty → **PAUSE**. Print:

   ```
   ⚠️  DESTRUCTIVE ACTION REVIEW
   ───────────────────────────────────────
   The following TCs will write or delete real data:
   [table from step 2]

   This is a local dev environment (confirmed by probe).
   Test data will be prefixed with "[E2E-TEST]" where the
   UI has a name/title/label field, to aid cleanup.

   Confirm: type 'go' to proceed, or list TC-IDs to skip.
   ───────────────────────────────────────
   ```

4. Do NOT execute any destructive TC until user responds with `go` or a skip list.
5. For all destructive TCs that create named records: prefix the value in any name/title/label field with `[E2E-TEST]` during execution. This makes synthetic records identifiable.
6. Note each destructive TC in the report under a "Data Side-Effects" section.

**For each `- [ ] TC-NNN` in `plan.md`, execute this loop:**

**Step 1 — BEFORE (state-change tests only).**
For tests that change state (create, delete, update, toggle): call `browser_snapshot` to confirm starting state in text. Take BEFORE screenshot only if the before state matters as evidence.
Skip BEFORE screenshot for smoke/nav tests.

**Step 2 — Execute steps.**
Perform every numbered Step from the test case using ONLY `mcp__playwright__*` tools.
No Bash, no direct API calls, no database reads.

**Step 3 — Verify state in text FIRST.**
Call `browser_snapshot`. Scan the accessibility tree text for the Expected state.
- Does the expected text, element, or state appear in the snapshot?
- If YES → proceed to screenshot
- If NO → mark FAIL immediately with the observed snapshot text. No screenshot needed (saves tokens).

**Step 4 — Annotate and screenshot (only if Step 3 confirmed PASS).**

Identify the element or region to annotate (from browser_snapshot coordinates).

**CRITICAL — floating widgets (dropdowns, popups, tooltips, Kendo/Select2/custom comboboxes):**

- **NEVER call `scrollIntoView` on an option inside a floating widget.** This triggers an outside-click and closes the popup before the screenshot fires — leaving the annotation on empty space with stale coordinates.
- To scroll a dropdown list: use `scrollTop` on the popup's `<ul>` or scroll container, NOT on the individual option element.
- **Inject overlay and take screenshot as the very last two actions** — no intervening `browser_snapshot`, `browser_evaluate`, `browser_wait_for`, or any other call between inject and screenshot. Any intermediate action can close the widget.
- After injecting the overlay, immediately call `browser_take_screenshot`. Do not read or verify anything first.
- If the element's bounding rect returns `{0,0,0,0}` — the element is not rendered (popup closed). Do NOT use stale coordinates. Re-open the popup and retry from Step 2.

Inject annotation overlay via `browser_evaluate`:
```javascript
(function() {
  const e = document.getElementById('__e2e_ann__');
  if (e) e.remove();
  const d = document.createElement('div');
  d.id = '__e2e_ann__';
  // browser_snapshot returns page-absolute coordinates; subtract scroll offset so
  // position:fixed (which is viewport-relative) lands on the correct element.
  const top  = TOP_PX  - window.scrollY;
  const left = LEFT_PX - window.scrollX;
  d.style.cssText = `position:fixed;top:${top}px;left:${left}px;width:W_PXpx;height:H_PXpx;border:3px solid #FF0000;background:rgba(255,0,0,0.08);z-index:999999;pointer-events:none;border-radius:2px;`;
  document.body.appendChild(d);
  return true;
})();
```

**ANNOTATION GATE — must pass before screenshot fires. No exceptions.**

Call `browser_evaluate` with this check:
```javascript
(function(){ const e = document.getElementById('__e2e_ann__'); if (!e) return false; const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; })()
```

- Returns `true` → overlay is present and visible. Proceed to screenshot.
- Returns `false` → overlay was not injected, or the coordinates placed it off-screen (zero bounding box). **FAIL this TC immediately.** Record: `FAIL | annotation gate failed — overlay not visible (element off-screen or inject returned without appending)`. Call the remove-snippet, then skip directly to Step 5. Do NOT take the screenshot — an unannotated image is not valid evidence.

Call `browser_take_screenshot` → save as `$PROOF_DIR/TC-NNN-after.png`.

Remove overlay:
```javascript
(function(){ const e=document.getElementById('__e2e_ann__'); if(e)e.remove(); })();
```

If coordinates unknown from snapshot: annotate the relevant viewport region (e.g., `top:0,left:0,width:full-width,height:80` for nav bar tests).

**Step 4b — Debug step-through (always runs after Step 4 if DEBUG_ENABLED = true and TC is not FAIL/BLOCKED).**

Skip if `DEBUG_ENABLED = false`.

1. **Figure out what code to step through (three-tier lookup — stop at first hit):**

   **Tier 1 — Ticket code entities (highest confidence):**
   If `TICKET_ID` is set and `$WORKSPACE_ABS/analysis.md` exists, read the `### Code Entities` section. For this TC, find the entity whose name or route matches the TC's primary action (e.g., TC "create order" → `OrdersController`, `/api/orders`). Use that file + line as the breakpoint target. Skip tiers 2–3 if found.

   **Tier 2 — Files in Scope graph map (good confidence):**
   Read the `## Files in Scope (Graph Map)` table from `$WORKSPACE_ABS/context.md`. Find the file whose seed entity or route is most relevant to this TC's primary action verb and noun. For example, TC "submit login form" → look for files seeded by `AuthController`, `Login`, or `/api/auth`. Use that file's line_start as the breakpoint target.

   **Tier 3 — RAG graph search (fallback):**
   ```
   POST http://127.0.0.1:8612/search scope=codebase project_path=<cwd> query="[TC primary action — e.g. 'create order controller handler']" mode=graph limit=3
   ```
   Use the top result's `source` and `line_start`.

   If all three tiers return nothing: write `{ "verdict": "no code path found — TC may be client-side only" }` and skip to Step 5.

2. **Set breakpoint** at the entry of the relevant code:
   Call `mcp__mcp-debugger__set_breakpoint` with `sessionId=DEBUG_SESSION_ID`, `file=<source path>`, `line=<line_start>`.

3. **Trigger the code path** by re-running the TC's primary server-calling step in the browser (the step that submits a form, navigates, or calls an API — not navigation-only steps).

4. **Call `mcp__mcp-debugger__continue_execution`** with `sessionId=DEBUG_SESSION_ID` and wait for the breakpoint to hit (up to 5 seconds).

5. **If breakpoint hits:**
   - Call `mcp__mcp-debugger__get_stack_trace` — record the call stack
   - Call `mcp__mcp-debugger__get_variables` — capture local variables and parameters
   - Call `mcp__mcp-debugger__step_over` 2–3 times through the key logic
   - Call `mcp__mcp-debugger__get_variables` again — capture post-step state
   - Call `mcp__mcp-debugger__continue_execution` to let the request complete
   - Write debug evidence to `$PROOF_DIR/TC-NNN-debug.json`:
     ```json
     {
       "tc": "TC-NNN",
       "breakpoint": "file:line",
       "stack": [ ... ],
       "variables_at_entry": { ... },
       "variables_after_steps": { ... },
       "verdict": "breakpoint hit — code path executed"
     }
     ```

6. **If breakpoint does NOT hit within 5 seconds:**
   - Write: `{ "tc": "TC-NNN", "verdict": "breakpoint not hit — may be client-side only or async handler", "breakpoint_attempted": "file:line" }`
   - Call `mcp__mcp-debugger__continue_execution` to unblock.

7. **Remove the breakpoint** before the next TC to avoid it accumulating:
   Call `mcp__mcp-debugger__set_breakpoint` with `enabled=false` (or call the appropriate disable/remove API).

**Step 5 — Console check.**
Call `browser_console_messages`. Record any errors.

**Step 6 — Self-audit (answer YES to ALL before marking PASS).**
1. Did I perform EVERY numbered step in the test case — none skipped?
2. Did the snapshot in Step 3 confirm the Expected state in actual text?
3. Did I take the AFTER screenshot AFTER performing the steps (not before)?
4. Does the screenshot show the annotated point of interest?
5. Did I use ONLY `mcp__playwright__*` for verification — no Bash, no direct API calls?
6. If marking BLOCKED: is the blocking reason a specific external precondition, NOT complexity or difficulty?
7. If this is a resumed workspace: was this TC re-run in the current session, or explicitly accepted by the user? A prior-session result that was NOT explicitly accepted is NOT valid evidence — it must be NEEDS-RERUN.

**If ANY answer is NO → mark FAIL, BLOCKED, or NEEDS-RERUN, never PASS. "It probably worked" is FAIL, not PASS.**

**Step 7 — Update plan.md.**

Edit `plan.md`, replacing the checkbox:
- PASS (with debug): `- [x] TC-NNN: ... PASS | evidence: TC-NNN-after.png | code path: file:line | debug: TC-NNN-debug.json (breakpoint hit)`
- PASS (no debug hit): `- [x] TC-NNN: ... PASS | evidence: TC-NNN-after.png | code path: file:line | debug: no server breakpoint hit`
- PASS (debug disabled): `- [x] TC-NNN: ... PASS | evidence: TC-NNN-after.png | code path: client-side | debug: UI-only (no server process found)`
- FAIL (annotation gate): `- [F] TC-NNN: ... FAIL | annotation gate failed — overlay not visible (element '[label]' not found in DOM or zero bounding box)`
- FAIL: `- [F] TC-NNN: ... FAIL | observed: [snapshot text describing what was seen]`
- BLOCKED: `- [B] TC-NNN: ... BLOCKED | reason: [specific verifiable reason]`
- NEEDS-RERUN: `- [S] TC-NNN: ... NEEDS-RERUN | reason: [prior session result not re-executed / precondition changed]`

**Step 8 — Rollback attempt (destructive TCs only).**

Only applies if this TC was destructive (Steps contained: create, submit, save, add, update, edit, delete, remove, toggle, change, clear, reset).

1. **Attempt cleanup via UI** (for create/add TCs): navigate to the entity's list page and delete the `[E2E-TEST]`-prefixed record using the app's Delete button.
   - Deletion succeeds → mark this TC as **CLEANED UP**. No further action.
   - No delete UI, delete is disabled, or deletion fails → mark this TC as **UNCLEAN STATE**. Add to session `UNCLEAN_DESTRUCTIVE_TCS`:
     ```
     [TC-ID] | [action type] | [entity/target] | cleanup not possible: [reason]
     ```

2. For **delete/update TCs**: mark as **UNCLEAN STATE** only if the deletion removed non-test data with no restore path, or the update overwrote real data with no undo.

**Gate — before each subsequent destructive TC:**

Before executing any TC whose Steps contain: create, submit, save, add, update, edit, delete, remove, toggle, change, clear, reset — check `UNCLEAN_DESTRUCTIVE_TCS`.

If the list is non-empty → **PAUSE**. Print:

```
⚠️  UNROLLED DESTRUCTIVE STATE DETECTED
──────────────────────────────────────────────
Prior test(s) wrote data that has NOT been cleaned up:

[table: TC-ID | action | entity | reason cleanup was skipped]

About to execute: [next TC-ID] — [description]

Type 'go'         to proceed anyway
Type 'skip TC-NNN' to skip the next destructive TC
Type 'stop'       to end execution and go to the report phase
──────────────────────────────────────────────
```

Do NOT execute the next destructive TC until user responds.
If user types `stop` → jump directly to Phase 4.

**Batch optimization for nav tests:**
For all `TC-NAV-*` tests: navigate to each page in sequence, call `browser_snapshot` after each (text check for 404/title), then take ONE screenshot per page. Annotate the page title/header region. This avoids per-test overhead for simple navigation checks.

**UI consistency TCs:**
- Navigate to each page containing instances of the component type
- Call `browser_snapshot`, extract HTML structure of each instance
- Compare element type, aria roles, and structure against the first (canonical) instance
- If INCONSISTENT: inject annotation overlays on BOTH the canonical AND the deviant instance, take ONE screenshot showing both
- Mark FAIL: "Component inconsistency: [canonical element] on [page A], [different element] on [page B]"
- If CONSISTENT: mark PASS, no screenshot needed (snapshot text is sufficient evidence)

**Optional temp-logging (only when UI provides zero observable confirmation):**

Legitimate uses: async background jobs, webhooks to external services, audit log entries with no UI.
NOT legitimate: UI shows a success toast or list update — use the UI instead.

Protocol:
1. `POST http://127.0.0.1:8612/search with scope="codebase", query="[operation] handler controller service")` to find the server-side function handling the operation. Add `mode="graph"` if you need to trace which module calls this function (i.e., finding the caller chain, not just the function itself.
2. `Read` the target file
3. Insert: `console.log('[E2E-TEMP] TC-NNN: [description]');` after the operation
4. Perform the browser action
5. Call `browser_console_messages` — confirm the log line appears
6. **Immediately** `Edit` the file to remove the log line
7. `Read` the file again to confirm the log line is gone
8. Note in plan.md: `PASS | verified via temp-log (removed)`

Print warning if used >2 times: "WARNING: Temp-logging invoked N times. Each use requires a legitimate reason — no visible UI confirmation must be available."

**Background Job Verification (only for async scheduled/queued jobs with no UI trigger):**

Legitimate uses: cron jobs, Hangfire/Sidekiq/Quartz workers, service-bus consumers — jobs that run in the background, write to the DB, and have no synchronous UI response to verify.
NOT legitimate: UI shows a success toast, list update, or status badge — use the UI instead. Also NOT a replacement for temp-logging when a synchronous server-side function needs verification.

Protocol:
1. `POST http://127.0.0.1:8612/search with scope="codebase", query="[job class name] job worker execute schedule", mode="graph")` — find the job class, its scheduler/dispatcher, and the table/column it writes. mode=graph surfaces the wiring (what registers or enqueues this job alongside the class itself.
2. `Read` the job class file. Identify:
   - What DB table/column the job writes (the "write side" — this is what must be verified)
   - Any dev/admin endpoint that can trigger the job manually (e.g., `/admin/jobs/trigger`, `/api/internal/run-job`, a dev-only controller action)
   - Any existing test helper or rake task that fires the job
3. **Trigger strategy (pick first available):**
   a. **Admin/dev endpoint**: use `browser_navigate` to the trigger URL, or `browser_evaluate` to call it via `fetch`. Confirm the response indicates the job ran.
   b. **Browser UI trigger**: if there is an admin panel button that enqueues the job, click it.
   c. **Wait for schedule**: only if the job fires within 60 seconds. Note the start time. Poll every 10s using `browser_snapshot` or a curl to a read-only status endpoint.
   d. **No trigger available**: mark TC as `[B] BLOCKED | reason: No local trigger found for [JobClassName]. Manual DB seeding or job invocation needed.` Do NOT invent a result, do NOT substitute temp-logging.
4. **Verify the write side after the job runs:**
   - Navigate to the UI page that displays the job's output (the record, status, or count). Call `browser_snapshot`. Confirm the expected text/state appears.
   - OR: `curl` a **local, read-only** API endpoint that returns the written data. Confirm the expected record exists in the response.
   - The query itself returning rows is not sufficient — the app must surface the result through the UI or a local API read, so you know the app is reading what the job wrote.
5. Take a screenshot showing the verified output. Annotate the relevant element or data row.
6. Note in plan.md: `PASS | verified via background-job-verification (trigger: [method used], verified via: [UI page / curl endpoint])`

---

## Phase 3 Close — Screenshot Validation Pass

**Run this pass after ALL TCs complete, before Phase 4.**

Spawn `evaluator-agent` to independently audit every screenshot taken this session. The main orchestrator must NOT self-verify — this is the hallucination guard.

**Pass `evaluator-agent` the following:**

1. The list of all `TC-NNN-after.png` files saved to `$PROOF_DIR/` this session.
2. The corresponding TC entry from `plan.md` for each screenshot (TC-ID, description, expected outcome).
3. The instruction below.

**Evaluator instruction:**

> For each screenshot, determine:
> 1. **Annotation present?** — Is there a visible red border overlay on a specific element or region? (Not a full-screen border or a border on a blank area.) Mark: YES / NO.
> 2. **Annotation on point of interest?** — Does the annotated region correspond to the element described in the TC's Expected outcome? Mark: YES / MISPLACED / UNCLEAR.
> 3. **Screenshot taken after action?** — Does the visible page state reflect the post-action state described in the expected outcome (e.g., record created, toast shown, nav link highlighted)? Mark: YES / NO.
>
> For each screenshot, return one of:
> - `OK` — all three checks pass
> - `RETAKE: [reason]` — annotation missing, misplaced, or screenshot shows wrong state

**Orchestrator — apply evaluator results:**

For each screenshot the evaluator marks `RETAKE`:

1. Re-navigate to the page the TC exercised (`browser_navigate`).
2. Reproduce the exact post-action state by re-running the TC steps (use judgment — for a create TC, if the record was cleaned up, re-create it with `[E2E-TEST-RETAKE]` prefix so it's identifiable).
3. Re-inject the annotation overlay targeting the correct element.
4. Call `browser_take_screenshot` → overwrite `$SNAPSHOTS_DIR/TC-NNN-after.png`.
5. Remove the overlay.
6. Note in plan.md alongside the TC: `screenshot retaken after evaluator audit`.

If a retake is not possible (page state cannot be reproduced without side-effects): note in plan.md: `screenshot retake skipped — [reason]`.

Print after the pass: "Screenshot audit complete. Evaluator flagged N / M screenshots for retake. [N] retaken, [K] skipped."

**Close debug session (runs after all TCs and evaluator pass complete).**

If `DEBUG_ENABLED = true`:
Call `mcp__mcp-debugger__close_debug_session` with `sessionId=DEBUG_SESSION_ID`.
Print: "Debug session closed. N TCs had breakpoint hits, M had no server code path found."
Set `DEBUG_ENABLED = false`.

---

## Phase 4: Report

**PHASE 4 ENTRY GATE — runs before any report is written:**

Verify the Phase 3 Close screenshot validation evaluator ran this session. If it did NOT run:

1. Run Phase 3 Close now — spawn `evaluator-agent` for screenshot validation before continuing.
2. Do NOT write the report until the evaluator has returned its verdict.

The orchestrator must NOT self-verify screenshots. "I checked them and they look fine" is not a substitute for the evaluator pass. Apply all RETAKE instructions before proceeding.

**4a — Tally results.**

Read `plan.md`. Count: PASS `[x]`, FAIL `[F]`, BLOCKED `[B]`, NEEDS-RERUN `[S]`.

**4b — Write report.**

Write `$WORKSPACE_ABS/report.md`:

```markdown
# E2E Test Report

**URL**: [TARGET_URL]
**Date**: [date]
**Scope**: [SCOPE]
**Plan**: $WORKSPACE_ABS/plan.md
**Screenshots**: $SNAPSHOTS_DIR/
**Proof**: $PROOF_DIR/

## Summary

| Result       | Count |
|--------------|-------|
| PASS         | N     |
| FAIL         | N     |
| BLOCKED      | N     |
| NEEDS-RERUN  | N     |
| Total        | N     |

**Overall**: PASS / FAIL / PARTIAL

## Failures

[For each FAIL: TC-ID, description, expected, observed (snapshot text)]

## Blocked Tests

[For each BLOCKED: TC-ID, description, blocking reason]

## Needs-Rerun

[For each NEEDS-RERUN: TC-ID, description, reason — e.g., "prior session result, not re-executed this session"]

## Evidence Index

| TC-ID | Description | Result | Before | After |
|-------|-------------|--------|--------|-------|
| TC-001 | ... | PASS | — | TC-001-after.png |

## UI Inconsistencies Found

[List any structural inconsistencies detected by UI consistency TCs]

## Console Errors

[Any browser console errors observed across all tests]

## Temp-Logging Used

[Any TCs that used temp-logging, with rationale and confirmation of removal]
```

**4c — Print summary to user.**

Print the Summary table. List all failures with their observed state. List blocked tests with reasons.

End with: "Full report → `$WORKSPACE_ABS/report.md`. Proof screenshots → `$PROOF_DIR/`. All screenshots → `$SNAPSHOTS_DIR/`."

Call `browser_close`.

---

## Post-Execution Interaction Rules

**If the user asks whether screenshots were independently verified:**

- If Phase 3 Close evaluator ran → confirm and cite the evaluator's RETAKE count.
- If Phase 3 Close did NOT run → run it now before answering. Do not self-assess screenshot quality.

**Never self-verify.** The evaluator-agent checks annotation presence, annotation placement, and post-action state. These are three distinct checks that the orchestrator cannot objectively answer about its own screenshots — it produced them.
