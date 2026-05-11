---
argument-hint: <target-url> [scope — auth | crud | nav | errors | responsive | all]
description: End-to-end UI testing — discovers app via RAG + browser, writes test plan, executes browser-only with screenshot evidence
allowed-tools: Read, Write, Edit, Bash, Glob, Grep, Agent, mcp__rag-server__rag_context, mcp__rag-server__rag_index_project, mcp__rag-server__rag_search, mcp__playwright__browser_navigate, mcp__playwright__browser_snapshot, mcp__playwright__browser_click, mcp__playwright__browser_type, mcp__playwright__browser_take_screenshot, mcp__playwright__browser_evaluate, mcp__playwright__browser_fill_form, mcp__playwright__browser_select_option, mcp__playwright__browser_wait_for, mcp__playwright__browser_press_key, mcp__playwright__browser_console_messages, mcp__playwright__browser_resize, mcp__playwright__browser_close
---

# /end-to-end-test — Browser-Only E2E Test Suite

Arguments: **$ARGUMENTS**
(Format: `<url>` or `<url> <scope>` — e.g., `http://localhost:3000 auth`)

---

## Phase 0: Initialize

**0a — Parse arguments.**

Split `$ARGUMENTS` on whitespace. First token = `TARGET_URL`. Second token = `SCOPE` (valid: `auth`, `crud`, `nav`, `errors`, `responsive`, `all`; default to `all` if omitted).

**0b — Environment hard-stop (check BEFORE any browser action).**

If `TARGET_URL` contains any of: `staging`, `stg`, `stage`, `prod`, `prd`, `production`
OR ends with: `.azurewebsites.net`, `.herokuapp.com`, `.vercel.app`, `.netlify.app`
→ STOP immediately. Print: "Cannot run E2E tests against staging/production URL." No exceptions, no override.

**0c — Derive TASK_ID.**

Format: `e2e-[hostname]-[port]-[YYYY-MM-DD]`
Example: `e2e-localhost-3000-2026-05-10`

**0d — Create workspace.**

```bash
mkdir -p "$CLAUDEBOOST_HOME/workspace/$TASK_ID/snapshots"
```

**0e — Load knowledge via RAG (do this FIRST before any browser action).**

Call `rag_context(agent="e2e-agent", task_description="end-to-end UI test of $TARGET_URL scope=$SCOPE", max_tokens=5000)`.

This loads the e2e-testing knowledge base (anti-cheat rules, intelligent test generation, annotation technique), playwright knowledge, and testing patterns.

**0f — Index project codebase.**

```bash
pwd
```

Call `rag_index_project(project_path=<cwd output>)`. Report: "X files indexed."

This enables RAG search over the app's routes, components, and entities during discovery.

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
Call `browser_take_screenshot` → save to `workspace/$TASK_ID/snapshots/discovery-home.png`.
Call `browser_console_messages` — note any startup errors.

**Switch to snapshots-only from here forward during discovery.**

**1b — RAG-powered codebase scan.**

Run these 3 searches before crawling the UI (gives you a head start on what to expect):

```
rag_search(scope="codebase", project_path=<cwd>, query="routes pages navigation URL paths", limit=6)
rag_search(scope="codebase", project_path=<cwd>, query="authentication login session user roles", limit=5)
rag_search(scope="codebase", project_path=<cwd>, query="form submit create update delete entity model", limit=5)
```

Extract from results: known route paths, entity names, auth mechanism, form structures.

**1c — Browser crawl (snapshots only, max 2 levels deep).**

Call `browser_snapshot`. From the accessibility tree, extract ALL nav links, buttons, and top-level interactive elements. Record each.

For each top-level nav link found:
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

Write `workspace/$TASK_ID/context.md`:

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

## Startup Console Errors
[any errors from browser_console_messages on load]
```

---

## Phase 2: Test Plan Generation

**PHASE 2 ENTRY GATE — verify before starting:**

Read `workspace/$TASK_ID/context.md`. Confirm it exists and has a non-empty "Pages Discovered" section.

If context.md does NOT exist or has no pages listed → **STOP**. Do not proceed. Print: "Phase 2 blocked: App Map not found. Complete Phase 1 first." Return to Phase 1.

---

**The test plan is written to disk BEFORE any test executes. This is structural anti-cheat — a plan that predates execution cannot be fabricated.**

**2a — Generate test cases from SCOPE + App Map + component registry.**

**Always include regardless of scope:**
- `TC-SMOKE-01`: Home page loads without console errors
- `TC-SMOKE-02`: All primary nav links resolve without 404

**Intelligent test generation rules (apply these during generation):**

| Control type | Rule |
|---|---|
| Toggle/select/enum with N≤7 states | Generate ONE TC per state |
| Boolean | Always 2 TCs |
| List/collection UI | Always 4 TCs: empty state, one item, 3-5 items, max/full |
| Form validation | One TC per validation rule (not per field) |
| Same component with multiple instances | One UI consistency TC for the type |
| Large enum (N>7) | Boundary values: first option, last option, one invalid |

**Scope-to-category mapping:**

| Scope | Categories to generate |
|---|---|
| `auth` | Login happy path, login bad credentials, logout, protected route without auth |
| `crud` | Create / read list / read detail / update / delete / empty state — per entity |
| `nav` | Each nav link resolves, back-button, breadcrumb accuracy |
| `errors` | Required field blank, invalid format, 404 page |
| `responsive` | Key pages at 375px, 768px, 1280px |
| `all` | Union of all above + UI consistency pass |

**Each test case format:**
```markdown
- [ ] TC-001: [Category] — [Description]
  - Steps: [numbered, browser-action-only steps]
  - Expected: [exact observable UI outcome]
  - Evidence: TC-001-after.png
  - Source: [RAG hit / browser discovery / component registry]
```

**Write draft plan to disk:** `workspace/$TASK_ID/plan-draft.md`

**2b — Anti-hallucination evaluator.**

Spawn `evaluator-agent` to audit the draft plan. Pass in:
- The full contents of `plan-draft.md`
- The App Map from `context.md`
- The RAG search result summaries from Phase 1b

Evaluator checks each TC:
- Does the route/page referenced appear in the App Map?
- Does the UI element (toggle, dropdown, form) appear in the component registry?
- Is this testing something actually discovered, not inferred?

Evaluator returns a list of TCs to remove or demote. Apply those changes.

Print: "Evaluator removed N test cases as unverified (not found in app discovery)."

**2c — Write final plan and present to user.**

Write cleaned plan to `workspace/$TASK_ID/plan.md`.

Show the full plan to the user. Print test count.

**PAUSE HERE — do not start Phase 3 until user responds.**

Ask: "Test plan written to `workspace/$TASK_ID/plan.md`. Found **N test cases** (M removed by evaluator as unverified). Respond **'go'** to start execution, or describe changes."

---

## Phase 3: Test Execution — Browser Only

**⛔ PHASE 3 ENTRY GATE — MANDATORY CHECK BEFORE ANY BROWSER ACTION:**

1. Read `workspace/$TASK_ID/plan.md`.
2. Verify it exists AND contains at least one `- [ ] TC-` line.

If plan.md does NOT exist or has no test cases → **STOP**. Do not proceed to any browser action.
Print: "Phase 3 blocked: plan.md not found or empty. Complete Phase 2 first."
Return to Phase 2 and generate the test plan.

This gate exists because Phase 3 executes a pre-written plan. There is no such thing as "running tests while writing the plan" — that produces fabricated results. The plan must exist on disk, written before execution began.

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
========================================
TOKEN EFFICIENCY: snapshot first (text), screenshot only after
text confirms expected state. Failed tests: no screenshot needed.
========================================
```

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

Inject annotation overlay:
```javascript
(function() {
  const e = document.getElementById('__e2e_ann__');
  if (e) e.remove();
  const d = document.createElement('div');
  d.id = '__e2e_ann__';
  d.style.cssText = 'position:fixed;top:TOP_PXpx;left:LEFT_PXpx;width:W_PXpx;height:H_PXpx;border:3px solid #FF0000;background:rgba(255,0,0,0.08);z-index:999999;pointer-events:none;border-radius:2px;';
  document.body.appendChild(d);
})();
```

Call `browser_take_screenshot` → save as `workspace/$TASK_ID/snapshots/TC-NNN-after.png`.

Remove overlay:
```javascript
(function(){ const e=document.getElementById('__e2e_ann__'); if(e)e.remove(); })();
```

If coordinates unknown from snapshot: annotate the relevant viewport region (e.g., `top:0,left:0,width:full-width,height:80` for nav bar tests).

**Step 5 — Console check.**
Call `browser_console_messages`. Record any errors.

**Step 6 — Self-audit (answer YES to ALL before marking PASS).**
1. Did I perform every Step in the browser?
2. Did the snapshot in Step 3 confirm the Expected state?
3. Did I take the AFTER screenshot AFTER performing the steps?
4. Does the screenshot show the annotated point of interest?
5. Did I use ONLY `mcp__playwright__*` for verification?

**If ANY answer is NO → mark FAIL or BLOCKED, never PASS.**

**Step 7 — Update plan.md.**

Edit `plan.md`, replacing the checkbox:
- PASS: `- [x] TC-NNN: ... PASS | evidence: TC-NNN-after.png`
- FAIL: `- [F] TC-NNN: ... FAIL | observed: [snapshot text describing what was seen]`
- BLOCKED: `- [B] TC-NNN: ... BLOCKED | reason: [specific verifiable reason]`

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
1. `rag_search(scope="codebase")` to find the server-side function handling the operation
2. `Read` the target file
3. Insert: `console.log('[E2E-TEMP] TC-NNN: [description]');` after the operation
4. Perform the browser action
5. Call `browser_console_messages` — confirm the log line appears
6. **Immediately** `Edit` the file to remove the log line
7. `Read` the file again to confirm the log line is gone
8. Note in plan.md: `PASS | verified via temp-log (removed)`

Print warning if used >2 times: "WARNING: Temp-logging invoked N times. Each use requires a legitimate reason — no visible UI confirmation must be available."

---

## Phase 4: Report

**4a — Tally results.**

Read `plan.md`. Count: PASS `[x]`, FAIL `[F]`, BLOCKED `[B]`.

**4b — Write report.**

Write `workspace/$TASK_ID/report.md`:

```markdown
# E2E Test Report

**URL**: [TARGET_URL]
**Date**: [date]
**Scope**: [SCOPE]
**Plan**: workspace/$TASK_ID/plan.md
**Snapshots**: workspace/$TASK_ID/snapshots/

## Summary

| Result  | Count |
|---------|-------|
| PASS    | N     |
| FAIL    | N     |
| BLOCKED | N     |
| Total   | N     |

**Overall**: PASS / FAIL / PARTIAL

## Failures

[For each FAIL: TC-ID, description, expected, observed (snapshot text)]

## Blocked Tests

[For each BLOCKED: TC-ID, description, blocking reason]

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

End with: "Full report → `workspace/$TASK_ID/report.md`. Screenshots → `workspace/$TASK_ID/snapshots/`."

Call `browser_close`.
