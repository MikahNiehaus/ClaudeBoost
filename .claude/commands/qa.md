---
argument-hint: [url | --code | file-path | workspace-id | "description of what to QA"] [scope — auth | crud | nav | errors | responsive | all] [--no-debug] [--fresh]
description: Full QA session — works on anything. Browser apps (pass a URL), code changes (--code or file paths), scripts, artifacts, workspace output. Builds inventory from RAG, writes a risk-prioritized test plan, executes with evidence, and reports what was tested AND what was not
allowed-tools: Read, Write, Edit, Bash, Glob, Grep, Agent, mcp__playwright__browser_navigate, mcp__playwright__browser_snapshot, mcp__playwright__browser_click, mcp__playwright__browser_type, mcp__playwright__browser_take_screenshot, mcp__playwright__browser_evaluate, mcp__playwright__browser_fill_form, mcp__playwright__browser_select_option, mcp__playwright__browser_wait_for, mcp__playwright__browser_press_key, mcp__playwright__browser_console_messages, mcp__playwright__browser_resize, mcp__playwright__browser_close, mcp__mcp-debugger__create_debug_session, mcp__mcp-debugger__list_debug_sessions, mcp__mcp-debugger__list_supported_languages, mcp__mcp-debugger__set_breakpoint, mcp__mcp-debugger__start_debugging, mcp__mcp-debugger__attach_to_process, mcp__mcp-debugger__detach_from_process, mcp__mcp-debugger__get_stack_trace, mcp__mcp-debugger__list_threads, mcp__mcp-debugger__get_scopes, mcp__mcp-debugger__get_variables, mcp__mcp-debugger__get_local_variables, mcp__mcp-debugger__step_over, mcp__mcp-debugger__step_into, mcp__mcp-debugger__step_out, mcp__mcp-debugger__continue_execution, mcp__mcp-debugger__pause_execution, mcp__mcp-debugger__evaluate_expression, mcp__mcp-debugger__get_source_context, mcp__mcp-debugger__close_debug_session, mcp__mcp-debugger__redefine_classes, mcp__test-coverage__coverage_summary, mcp__test-coverage__coverage_file_summary, mcp__test-coverage__start_recording, mcp__test-coverage__get_diff_since_start, mcp__chrome-devtools__navigate_page, mcp__chrome-devtools__new_page, mcp__chrome-devtools__list_pages, mcp__chrome-devtools__select_page, mcp__chrome-devtools__close_page, mcp__chrome-devtools__wait_for, mcp__chrome-devtools__evaluate_script, mcp__chrome-devtools__list_console_messages, mcp__chrome-devtools__get_console_message, mcp__chrome-devtools__list_network_requests, mcp__chrome-devtools__get_network_request, mcp__chrome-devtools__performance_start_trace, mcp__chrome-devtools__performance_stop_trace, mcp__chrome-devtools__performance_analyze_insight, mcp__chrome-devtools__take_screenshot, mcp__chrome-devtools__take_snapshot, mcp__chrome-devtools__lighthouse_audit, mcp__mdb__debugger_status, mcp__mdb__debugger_start, mcp__mdb__debugger_terminate, mcp__mdb__debugger_list_sessions, mcp__mdb__debugger_command, mcp__mdb__lldb_start, mcp__mdb__lldb_terminate, mcp__mdb__lldb_list_sessions, mcp__mdb__lldb_command, mcp__mdb__gdb_start, mcp__mdb__gdb_terminate, mcp__mdb__gdb_list_sessions, mcp__mdb__gdb_command
---

# /qa — QA Session

Arguments: **$ARGUMENTS**

Works on anything — browser apps, API endpoints, Python scripts, JS modules, bash hooks, workspace artifacts, recent git changes, or any description of what to test. No URL required.

---

## Phase 0: Load RAG Context (MANDATORY FIRST ACTION)

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
`[qa] Conflict: status bar shows <X>, context/memory says <Y>. Which workspace should I use?`
Wait for the user's answer — the user is always the source of truth.

If `WORKSPACE_PATH` is empty: note it and continue.

Include `workspace_path="<WORKSPACE_PATH>"` in ALL agent spawn prompts and `/context` calls.



Call `POST http://127.0.0.1:8612/context with agent="workflow-agent", task_description="QA session planning and execution: app inventory, risk-based test plan, browser testing", max_tokens=3000`.

This loads relevant knowledge before any work begins. If `POST http://127.0.0.1:8612/context` fails: stop and tell the user "RAG is not connected. Run /boost before using this skill."

**0b — Verify project is indexed** (required for codebase search to work):

Detect the project path:
1. Read `$CLAUDEBOOST_HOME/state/project-workspaces.json` — use the entry keyed by the current working directory to get the active workspace ID, then look up `project_path` in `workspaces.json`. Fall back to current working directory if the file doesn't exist or has no entry for this directory.

Call `GET http://127.0.0.1:8613/status` and check `indexed_projects` for the detected path.

- **Indexed**: note file/chunk counts and continue.
- **Not indexed**: run `Skill(skill="index-project", args="<project_path>")` immediately. Do not continue until indexing completes.
- **RAG offline**: stop and tell the user to run `/rag` first.

---

## Initialize

**0a — Parse arguments.**

Strip flags from `$ARGUMENTS` before parsing positional tokens:
- `--no-debug` present → set `NO_DEBUG = true` (skip debugger pre-flight entirely in Phase 3 and G4d)
- `--fresh` present → force a new workspace (already handled in 0c)
- `--code` present → set `CODE_FLAG = true` (used in 0a-i to set MODE = general)
- Remaining tokens after stripping all flags: first = `TARGET_URL`, second = `SCOPE` (valid: `auth`, `crud`, `nav`, `errors`, `responsive`, `all`; default `all` if omitted)

**0a-i — Set MODE based on parsed arguments.**

| Condition | MODE | GENERAL_TARGET |
|-----------|------|----------------|
| `TARGET_URL` starts with `http://` or `https://` | `browser` | — |
| `CODE_FLAG = true` (from `--code`) | `general` | Recent git changes (`git diff HEAD~1`) |
| `TARGET_URL` matches `[a-z0-9]+-\d{4}-\d{2}-\d{2}` (workspace ID pattern) | `general` | Files in that workspace |
| `TARGET_URL` contains `/` or `\` or starts with `.` (file path) | `general` | That file or directory |
| `TARGET_URL` ends with `.py`, `.js`, `.ts`, `.sh`, `.rb`, `.go`, `.cs`, `.rs`, or other recognized code extension | `general` | That file (even without a path prefix) |
| `TARGET_URL` is non-empty but none of the above | `general` | Treat as natural language description — resolve to files, scripts, or artifacts |
| `TARGET_URL` is empty | `detect` | Run Steps A–D to find a server |

**Natural language target resolution** (applies when MODE = `general` and target is a description):
- "these three Python scripts" / "the auth module" / "my hook scripts" → use RAG to find matching files, ask user to confirm before proceeding
- "recent changes" / "what I just wrote" → `git diff HEAD~1 --name-only`
- "the workspace output" / "the plan" → files in `$WORKSPACE_ABS/`
- Anything else → print the resolved target and ask "Is this what you want to QA?" before starting

**If MODE = `general`:** skip Steps A–D, skip Phase 0a-iii (ticket tracing), skip Phase 0b (env check), skip Phase 0g (app inventory). Proceed through Phase 0c–0f (workspace, RAG load, index), then jump to **General Mode** section at the bottom of this file.

**If MODE = `detect` and Steps A–C find a running server:** set `MODE = browser` and `TARGET_URL` to the detected address.

**If MODE = `detect` and no server found (Step D):** ask: "No running server found. Paste a URL for browser testing, or describe what to QA (file, workspace ID, or `--code` for recent git changes)." Set MODE based on the reply.

**0a-ii — Auto-detect TARGET_URL if not provided.**

If `TARGET_URL` is empty after parsing, do NOT ask the user yet. Work through these steps in order and stop at the first hit:

**Step A — Check active workspace context.md for a `Dev URL:` field:**
Read `$WORKSPACE_ABS/context.md` (if it exists) and look for a line matching `Dev URL: <url>`. If found, set `TARGET_URL` to that value. Skip steps B–D.

**Step B — Check if a dev server is already running on a common port:**
```bash
for PORT in 3000 5000 5173 7000 8080 4200 8000; do
  curl -s --max-time 1 -o /dev/null -w "%{http_code}" "http://localhost:${PORT}/" 2>/dev/null | grep -qE "^[23]" && echo "http://localhost:${PORT}" && break
done
```
If a port responds with a 2xx or 3xx: set `TARGET_URL = http://localhost:<PORT>`. Print: "Auto-detected running server at `$TARGET_URL`." Skip steps C–D.

**Step C — Read project config for a start command:**

Check in this order (stop at first file found):
1. `$WORKSPACE_ROOT/package.json` → read `scripts.dev`, `scripts.start`, `scripts.serve` — pick first defined
2. `$WORKSPACE_ROOT/Properties/launchSettings.json` → read `profiles[*].applicationUrl` (ASP.NET)
3. `$WORKSPACE_ROOT/.env` or `.env.local` → look for `PORT=` or `VITE_PORT=`

If a start command is found, run it in the background:
```bash
cd "$WORKSPACE_ROOT" && <start-command> &
SERVER_PID=$!
```
Then poll for up to 15 seconds (check every 2s) for any of the standard ports to respond. When one responds, set `TARGET_URL` to that URL. Print: "Started dev server (`<start-command>`) → `$TARGET_URL`."

If the command is found but no port responds within 15 seconds: print "Dev server started but did not respond on any standard port. Check the terminal for errors." Set `TARGET_URL = ""` and fall through to Step D.

**Step D — Ask the user (only if all auto-detect paths failed):**
```
No running dev server found. What do you want to QA?

  Browser testing  — paste a URL (e.g. http://localhost:3000)
  Code / scripts   — say what to test (e.g. "my_service.py", "the hook scripts", "--code" for recent git changes)
  Workspace output — paste a workspace ID or say "the plan" / "the report"
```
Wait for the user's response. Set MODE and TARGET based on what they provide:
- URL → `browser`
- File name, path, description of scripts/code, or `--code` → `general`

**0a-ii-b — Visual feedback loop (browser mode only).**

When `MODE = browser`, apply this loop for every UI-related test case:
1. `browser_navigate` to the route under test
2. `browser_snapshot` — read the accessibility and text state first, before any screenshot
3. `browser_take_screenshot` — capture the visual state
4. Note findings with pixel precise specifics before proposing any fix (e.g. "gap between cards is 8px, design requires 24px")
5. `browser_resize` at 375px, 768px, 1280px for any responsive test case
6. `browser_console_messages` after each test case — show the output, never assume silent

Confirm with the user before implementing any visual change found in QA.
Verify with a before/after screenshot pair after any fix is applied.

**0a-iii — Ticket tracing (ask if not provided).**

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
→ STOP immediately. Print: "Cannot run QA sessions against staging/production URL." No exceptions, no override.

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

If `TICKET_ID` was captured in Phase 0a-iii (not 'none'):

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

Parse `HOSTNAME_SLUG` and `PORT_SLUG` from `TARGET_URL` (e.g. `http://localhost:3000` → `localhost`, `3000`). Also derive `PROJECT_SLUG`: take the last two path components of `WORKSPACE_ROOT`, lowercase, replace non-alphanumeric with `-` (e.g. `C:/Development/MyApp` → `development-myapp`).

Use a Bash glob loop — do NOT use `ls | grep` (banned):
```bash
MATCH=""
for d in "$WORKSPACE_ROOT/workspace/e2e-${HOSTNAME_SLUG}-${PORT_SLUG}-"*/; do
  [ -d "$d" ] && MATCH="$d" && break
done
```

If `MATCH` is non-empty (and `--fresh` was NOT passed):
- Set `TASK_ID` to the matched folder name (strip trailing slash), `WORKSPACE_ABS = $WORKSPACE_ROOT/workspace/$TASK_ID`.

If no match exists OR `$ARGUMENTS` contains `--fresh`:
- Derive: `TASK_ID = e2e-[hostname]-[port]-[project-slug]-[YYYY-MM-DD]`
- Example: `e2e-localhost-3000-myapp-2026-05-10` (project slug prevents same-day collisions across projects on the same port)
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
| Neither `context.md` nor `plan.md` | Workspace exists but no QA session state yet → proceed to Phase 0d |

Print:
```
Resuming workspace: workspace/[existing-task-id]/
Detected state: Phase [N] in progress — skipping completed phases.
(Use /qa <url> --fresh to force a new session.)
```

**0d — Create workspace, set SNAPSHOTS_DIR, PROOF_DIR, and DEBUG_PROOF_DIR.**

Set `SNAPSHOTS_DIR = $WORKSPACE_ABS/screenshots`.

Derive `PROOF_DIR` — where TC pass-evidence screenshots land (separate from discovery and temp shots):
- If `TICKET_ID` is set (not 'none'): `PROOF_DIR = $SNAPSHOTS_DIR/proof-[TICKET_ID]`
  Example: `$WORKSPACE_ABS/screenshots/proof-ASC-1175`
- Otherwise: `PROOF_DIR = $SNAPSHOTS_DIR/proof-[hostname]-[YYYY-MM-DD]`
  Example: `$WORKSPACE_ABS/screenshots/proof-localhost-2026-06-05`

Set `DEBUG_PROOF_DIR = $WORKSPACE_ABS/debug-proof` — where code step-through evidence lands. This is a first-class proof artifact, not an afterthought. Every TC that hits a server breakpoint produces a file here.

```bash
mkdir -p "$SNAPSHOTS_DIR"
mkdir -p "$PROOF_DIR"
mkdir -p "$DEBUG_PROOF_DIR"
```

Announce:
```
Screenshots  → $WORKSPACE_ABS/screenshots/
Proof imgs   → $PROOF_DIR/
Debug proof  → $DEBUG_PROOF_DIR/
```

Workspace folder layout:
```
$WORKSPACE_ABS/
├── context.md              (app map and findings)
├── app-inventory.md        (RAG-built route + entity table)
├── flow-map.md             (user journeys)
├── plan.md                 (test cases with results)
├── coverage-gaps.md        (what was NOT tested)
├── report.md               (final summary)
├── screenshots/            (all browser images)
│   ├── discovery-home.png  (initial load — only one taken during discovery)
│   └── proof-[id]/         (TC pass evidence screenshots)
│       ├── TC-001-after.png
│       └── TC-001-before.png
└── debug-proof/            (code step-through logs — one JSON per TC with server hit)
    ├── TC-001-debug.json
    ├── TC-002-debug.json
    └── session-summary.json  (written at close — totals, miss count, hit count)
```

What goes where:
- `$SNAPSHOTS_DIR/` — discovery shots and anything taken outside a TC
- `$PROOF_DIR/` — TC-NNN-after.png (PASS evidence), TC-NNN-before.png (state-change pairs)
- `$DEBUG_PROOF_DIR/` — TC-NNN-debug.json (stack, variables, branch taken), session-summary.json

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

Call `POST http://127.0.0.1:8612/context with agent="e2e-agent", task_description="QA session for $TARGET_URL scope=$SCOPE — app inventory, browser testing, coverage gap analysis", max_tokens=5000`.

This loads the e2e-testing knowledge base (anti-cheat rules, intelligent test generation, annotation technique), playwright knowledge, and testing patterns.

**0e-ii — Load cross-session memory (browser mode only).**

Before any browser navigation, check for prior-session knowledge files:

1. Check for `$WORKSPACE_ABS/ui-quirks.md` — if it exists, read it fully. These are known tricky elements from prior sessions: wrong-click corrections, elements that need parent-div clicks, custom components with unreliable selectors. Apply this context when deciding how to interact with any element during the session.
2. Check for `$WORKSPACE_ABS/known-failures.md` — if it exists, read it fully. These are flows that were BLOCKED in prior sessions with the exact step that blocked them. Do not re-attempt a known-blocked step the same way — try a different approach or mark BLOCKED immediately with reference to the prior failure.
3. If neither file exists: proceed normally. They will be created during this session if navigation corrections or blocked flows occur.

**Write rule:** Append to `$WORKSPACE_ABS/ui-quirks.md` after any successful navigation correction (wrong click fixed, parent-div workaround discovered). Create the file if it doesn't exist. Never delete existing entries. Append to `$WORKSPACE_ABS/known-failures.md` when any flow is marked BLOCKED, with the exact blocking step.

**0f — Index project codebase.**

Call `POST http://127.0.0.1:8613/index-project {"project_path":"<WORKSPACE_ROOT>"}`. Report: "X files indexed."

Use the WORKSPACE_ROOT detected in step 0c — not raw CWD. CWD may be the ClaudeBoost directory even when the project under test is elsewhere.

This enables RAG search over the app's routes, components, and entities during discovery.

**0g — Comprehensive App Inventory (always runs after project is indexed).**

This is how a QA person learns the project BEFORE opening the browser. Run all six searches in parallel. Use both vector and graph — they surface different things. Never skip this step regardless of whether a ticket was provided.

**Search 1 — Routes and pages:**
```
POST http://127.0.0.1:8613/search {"query":"page route URL path controller action handler navigation","sources":["project:<WORKSPACE_ROOT>"],"mode":"vector","limit":20}
POST http://127.0.0.1:8613/search {"query":"page route URL path controller action handler navigation","sources":["project:<WORKSPACE_ROOT>"],"mode":"graph","limit":20}
```

**Search 2 — Forms and mutations:**
```
POST http://127.0.0.1:8613/search {"query":"form submit create update edit delete save mutation POST PUT PATCH DELETE","sources":["project:<WORKSPACE_ROOT>"],"mode":"vector","limit":15}
POST http://127.0.0.1:8613/search {"query":"form submit create update edit delete save mutation POST PUT PATCH DELETE","sources":["project:<WORKSPACE_ROOT>"],"mode":"graph","limit":15}
```

**Search 3 — Authentication and authorization:**
```
POST http://127.0.0.1:8613/search {"query":"authentication authorization login logout session role permission access control","sources":["project:<WORKSPACE_ROOT>"],"mode":"vector","limit":12}
POST http://127.0.0.1:8613/search {"query":"authentication authorization login logout session role permission access control","sources":["project:<WORKSPACE_ROOT>"],"mode":"graph","limit":12}
```

**Search 4 — Data models and entities:**
```
POST http://127.0.0.1:8613/search {"query":"model entity schema database table class record","sources":["project:<WORKSPACE_ROOT>"],"mode":"vector","limit":15}
POST http://127.0.0.1:8613/search {"query":"model entity schema database table class record","sources":["project:<WORKSPACE_ROOT>"],"mode":"graph","limit":15}
```

**Search 5 — Background jobs and async processing:**
```
POST http://127.0.0.1:8613/search {"query":"background job worker queue scheduled task cron async","sources":["project:<WORKSPACE_ROOT>"],"mode":"vector","limit":8}
POST http://127.0.0.1:8613/search {"query":"background job worker queue scheduled task cron async","sources":["project:<WORKSPACE_ROOT>"],"mode":"graph","limit":8}
```

**Search 6 — External integrations:**
```
POST http://127.0.0.1:8613/search {"query":"external API integration webhook email notification payment third-party","sources":["project:<WORKSPACE_ROOT>"],"mode":"vector","limit":8}
POST http://127.0.0.1:8613/search {"query":"external API integration webhook email notification payment third-party","sources":["project:<WORKSPACE_ROOT>"],"mode":"graph","limit":8}
```

**If ticket was provided — also search ticket entities:**
If `TICKET_ID` was captured (not 'none'):
1. Read `$WORKSPACE_ABS/analysis.md` → `### Code Entities` section (if exists)
2. Fallback: read `$WORKSPACE_ABS/ticket.md` → extract PascalCase names, `/api/` paths, component names
3. For each entity: run vector + graph search (limit=3 each)

**Synthesize results into `$WORKSPACE_ABS/app-inventory.md`:**

From all search results combined, extract and deduplicate:

```markdown
# App Inventory — [WORKSPACE_ROOT]
Built from RAG vector + graph traversal — covers full codebase, not just nav-visible pages.

## Routes / Pages
| Route | Source File | Type (page/api/action) | Auth Required? |
|-------|-------------|------------------------|----------------|
| /login | Controllers/AuthController.cs | page | no |
| /orders | Controllers/OrdersController.cs | page | yes |
| /api/orders | Controllers/OrdersController.cs | api | yes |

(List all routes found — aim for completeness. If source file + path conventions suggest a route exists, include it even if not 100% confirmed.)

## Entities with CRUD
| Entity | Create | Read | Update | Delete | Source File |
|--------|--------|------|--------|--------|-------------|
| Order  | yes    | yes  | yes    | yes    | OrdersController.cs |

## Auth System
- Type: [cookie/JWT/session/OAuth/basic/unknown]
- Login route: [path]
- Protected routes: [list or "most routes"]
- Role system: [yes/no — role names if found]

## Background Jobs
| Job / Worker | Trigger | What it writes | Source File |
|--------------|---------|---------------|-------------|
| (none found / list if found) | | | |

## External Integrations
| Service | What it does | Source File |
|---------|-------------|-------------|
| (none found / list if found) | | |

## UI Pages in Scope (Ticket-Specific)
(Only present if TICKET_ID was provided)
| URL / Route | File | Seed Entity | How Connected |
|-------------|------|-------------|---------------|
```

**This inventory is the QA person's knowledge of the app. Every route in this table gets either tested or explicitly justified as out-of-scope in the final report. There are no silent gaps.**

If RAG returns no results at all (project not indexed or search errors): note this in app-inventory.md and print a warning. Phase 1 browser crawl becomes the primary discovery method, but this is a degraded mode.

---

> **General mode only:** If MODE = `general`, skip Phase 1–4 below. Jump directly to the **General Mode** section at the bottom of this file.

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

**Auth state detection (runs after first navigation, before discovery):**

Call `browser_snapshot`. Scan the accessibility tree for auth indicators:
- Logged-in signals: user avatar, display name, profile link, "Sign out", "Log out", "My account", or any element with `role=navigation` containing the user's name
- Logged-out signals: login form fields, "Sign in" / "Log in" button, username/email + password fields

Set `AUTH_STATE`:
- `AUTHENTICATED` — at least one logged-in signal is present
- `UNAUTHENTICATED` — login form or sign-in button is the primary UI
- `UNKNOWN` — neither signal is clear (proceed as unknown, don't block)

Record `AUTH_STATE` in `context.md` under `## App State`. This is used in Phase 2 (test plan) to:
- Skip `TC-AUTH-LOGIN-*` cases when `AUTH_STATE = AUTHENTICATED` (already logged in — test plan notes this and includes a logout-then-relogin flow instead)
- Prioritize auth TCs when `AUTH_STATE = UNAUTHENTICATED`

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
1. `POST http://127.0.0.1:8612/context` as first action with `agent="workflow-agent"`, `task_description="codebase route and entity analysis for QA session discovery"`, `project_path=<WORKSPACE_ROOT>`
2. Run all three RAG searches in parallel:
   - `POST /search scope=codebase project_path=<WORKSPACE_ROOT> query="routes pages navigation URL paths" mode=graph limit=6`
   - `POST /search scope=codebase project_path=<WORKSPACE_ROOT> query="authentication login session user roles" mode=graph limit=5`
   - `POST /search scope=codebase project_path=<WORKSPACE_ROOT> query="form submit create update delete entity model" mode=graph limit=5`
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

**Inventory cross-reference (runs after nav crawl — finds hidden pages):**

Read `$WORKSPACE_ABS/app-inventory.md` → Routes/Pages table. Compare against the set of pages already visited during the nav crawl (keep a running `VISITED_ROUTES` set).

For each route in the inventory that was NOT visited:
1. `browser_navigate` to `$TARGET_URL + [route]`
2. `browser_snapshot` — record the page title and HTTP result
3. Classify:
   - **2xx/accessible**: page loaded — record in VISITED_ROUTES, note content
   - **Redirect to login**: auth-required route — note as "auth-blocked" (not a bug — expected)
   - **404 / error page**: route exists in code but not accessible — note as "code-discovered but broken"
   - **Redirect to unknown**: inspect where it redirected; re-run Phase 0b blocklist check
4. Do NOT navigate deeper on inventory routes — record the top-level response only

This step finds admin pages, API pages, and routes that aren't linked in the nav but exist in the codebase. A real QA person checks these. Routes that are auth-blocked are still added to the test plan as auth-check TCs.

Append a `## Inventory Cross-Reference` section to `context.md`:
```markdown
## Inventory Cross-Reference
Routes found in code but not in nav — verified during crawl.
| Route | Status | Notes |
|-------|--------|-------|
| /admin | auth-blocked | redirects to /login |
| /api/debug | 404 | code reference found but route not registered |
```

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
1. **App Inventory** (from `$WORKSPACE_ABS/app-inventory.md` Phase 0g — HIGHEST PRIORITY): every entity in the Entities with CRUD table is a journey candidate. For each entity with create/update/delete operations: generate the corresponding journey (create → verify → delete). For each route in the Routes/Pages table: verify it is represented in at least one journey. This is the completeness guarantee — the inventory was built from the actual code, not from what was clickable.
2. **Ticket content** (if TICKET_ID is set): derive journeys directly from the acceptance criteria or bug description. These are always high-risk.
3. **App Map + component registry** (from context.md Phase 1): look at the full set of pages and forms. For each form or interactive action, ask "what user goal does this serve?" That goal is a journey candidate.
4. **RAG codebase search** (for anything not yet covered): query `POST http://127.0.0.1:8613/search` with `{"query":"route controller action","sources":["project:<WORKSPACE_ROOT>"],"mode":"graph","limit":5}`. Use the returned routes to identify multi-step flows (login → redirect, create → confirm, etc.).

**Completeness gate — after deriving journeys:** Count the routes in app-inventory.md. Count the journeys derived. Every route that has no covering journey must either (a) be covered by an existing journey, or (b) have an explicit reason in a `## Uncovered Routes` section of `flow-map.md` explaining why it's not covered (e.g., "admin-only, no test account", "API route only — not browser-testable"). Routes cannot be silently omitted.

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

## Uncovered Routes
Routes from app-inventory.md that have no covering journey — must list a reason for each.
| Route | Reason not covered |
|-------|--------------------|
| (none — all routes have a covering journey) | |
```

**Step 4 — Hard gate:** If `flow-map.md` does not exist when Phase 2b starts, STOP. Print: "Phase 2b blocked: flow-map.md not found. Complete Phase 2a first." Do not generate test cases until the flow map is written.

---

**2b — Generate test cases from flow-map.md journeys + intelligent rules.**

TCs come from journeys, not from components.

**Derive journey invariants first.** Before generating TCs, state what each
journey must hold regardless of input:
- "After completing J1, the user MUST see [expected state] on [page]"
- "J1 MUST NOT leave orphaned records if the user abandons mid-flow"
- "J1 MUST reject [invalid input class] at step N before reaching step N+1"

Use these invariants to drive TC generation: a good TC disproves an
invariant on a wrong implementation, not just confirms a known-good path.

For each journey in flow-map.md:
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

**Mandatory SDK failure TC (add automatically when detected):**

After generating journeys, scan the diff and the pages in scope for external SDK imports:
- `<script type="module" src="https://...">` in any template or HTML file
- `import ... from 'https://...'` in any JS/TS file
- Any third-party CDN script (`cdn.`, `unpkg.com`, `esm.sh`, `jsdelivr.net`)

For EACH external SDK found, generate one additional TC:

```markdown
- [ ] TC-SDK-NNN: [SDK name] fails to load — page does NOT stay stuck in loading state
  - Journey: [the journey that loads this SDK]
  - Steps:
    1. Simulate SDK failure (block the CDN URL via devtools / browser_evaluate network intercept, OR verify behavior when the SDK times out naturally in this environment)
    2. Wait for the SDK's expected load event timeout period + 10 seconds
    3. Call browser_snapshot — verify the page has exited the loading state
  - Expected: Error message or fallback UI visible. Page is NOT showing a permanent loading indicator.
  - Code path: [the JS function that handles the SDK load event or timeout]
  - Evidence: TC-SDK-NNN-after.png
  - Note: If the SDK CDN is permanently blocked in this environment (e.g. Tableau Cloud rejects localhost), this TC is auto-classified as UNVERIFIABLE — mark [U] and add a post-deploy validation note.
```

**External embed URL validation (runs when any external embed SDK is detected — before generating TCs):**

An external embed SDK only accepts content URLs in a format its backend will serve. Using a wrong-format URL causes the SDK to reject the embed immediately — before any server communication, JWT validation, or data loading occurs. Testing with a rejected URL proves nothing about your code.

Before writing TCs for any external embed:

1. **Detect whether the SDK immediately errors after page load.** Navigate to the page and observe: does an error event fire within 1-2 seconds of page load, before any user interaction? If yes, the embed URL is almost certainly wrong-format or unreachable — proceed to step 2.

2. **Determine the required URL format.** Search for it in this order:
   - RAG workspace knowledge (if SDK docs were already indexed for this workspace)
   - SDK documentation for "embed URL format" or "supported URL patterns"
   - Codebase config files (appsettings.json, launchSettings.json, Azure App Config, any Settings page in the app) — look for the canonical URL format already in use
   - Key question: does the embed URL point at the same service that issued the credentials for this SDK? If the credentials come from ServiceX, the embed URL must also point at ServiceX — not at a share link, proxy, or unrelated domain.

3. **If the test URL does NOT match the required format:**
   - Search for a matching URL in: codebase config, ticket.md, context.md, ReportsSettings or equivalent admin pages in the app
   - If a matching URL is found: use it for all TCs that require real SDK rendering
   - If no matching URL is found after searching: mark ALL TCs that depend on real SDK rendering as `[U] UNVERIFIABLE`. This includes the happy path TC and any scenario that requires the embed to actually load — not just the error-handler TC. Document what was searched and why no valid URL was found.

4. **The error-handler TC (`TC-SDK-NNN`) is a separate concern.** Even when the real integration cannot be tested, the error-handler frontend branch can still be verified via synthetic event dispatch. Label any such TC as `[HANDLER-ONLY]` — it proves the handler fires correctly, not that the real service sends the expected error.

Do NOT use a wrong-format URL and mark TCs as PASS. If the SDK errors immediately, the TC did not test your feature.

If no CDN intercept is possible and the CDN is confirmed permanently blocked in the test environment: mark TC as `[U] UNVERIFIABLE` immediately with: "CDN blocked in this environment — validate after deployment to a registered domain."

**Intelligent test generation rules (apply per journey step):**

| Control type | Rule |
|---|---|
| Toggle/select/enum with N≤7 states | Generate ONE TC per state |
| Boolean | Always 2 TCs |
| **Conditional AC** | **Always 2 TCs — one for the true branch (condition met) and one for the false branch (condition NOT met). Applies whenever an AC uses "if", "when", "only when", "unless", or "only if". A TC that tests only one side is INCOMPLETE.** |
| List/collection UI | Always 4 TCs: empty state, one item, 3-5 items, max/full |
| Form validation | One TC per validation rule (not per field) — E2E only if the validation requires a server round-trip or cross-field dependency; client-only validation belongs in unit tests |
| Same component with multiple instances | One UI consistency TC for the type |
| Large enum (N>7) | Boundary values: first option, last option, one invalid |

**Scope-to-category mapping:**

| Scope | Categories to generate |
|---|---|
| `quick` | TC-SMOKE-01, TC-SMOKE-02, plus the top 3 highest-risk journeys from flow-map.md only |
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
- Every **conditional AC** (containing "if", "when", "only when", "unless", "only if") → two TCs: one where the condition is MET (true branch) and one where it is NOT MET (false branch). Scan every AC for conditional language before finalizing plan.md. A plan that covers only the false branch of a conditional AC is incomplete and will be flagged by the evaluator.
- If a discovered component has NO journey that exercises it: write it in a `## Gaps` section of plan-draft.md with a one-line justification. "It seemed unimportant" is not a valid justification.
- BLOCKED `[B]` status is only valid for genuine external preconditions that CAN be removed with setup changes (e.g., "requires admin account not provisioned", "flag must be toggled"). Complexity or difficulty is never a valid reason.
- UNVERIFIABLE `[U]` is distinct from BLOCKED. Use `[U]` for conditions that are permanently untestable in any available environment (e.g., CDN blocks localhost by design, Tableau Cloud rejects non-registered domains, live payment gateway required). Every UNVERIFIABLE TC MUST include: "Post-deploy: [who validates, when, and how]". **Before marking a TC UNVERIFIABLE, you MUST run the TC Blocker Recovery Protocol (defined in Phase 3). A TC marked UNVERIFIABLE without a documented resolution attempt is treated as BLOCKED by difficulty.**

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

Print: "Evaluator removed N test cases as unverified or unit-level (not in QA session scope)."

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

If `plan.md` already contains result entries from a previous run (lines starting with `- [x]`, `- [F]`, `- [B]`, or `- [U]`):

1. Count prior-session results: how many TCs are already marked in each category.
2. Print:
   ```
   ⚠️  RESUMING WORKSPACE — Prior Session Results Detected
   ─────────────────────────────────────────────────────
   Found N tests with prior-session results:
     [x] PASS:          M  →  must re-run or explicitly accepted
     [F] FAIL:          N  →  must re-run or explicitly accepted
     [B] BLOCKED:       N  →  carried over if blocking reason unchanged
     [U] UNVERIFIABLE:  N  →  carried over unless environment has changed

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

**Debug step-through is a mandatory proof deliverable, not an optional enhancement.**

Screenshots prove what the UI shows. The debug step-through proves the server code actually ran. A QA session with screenshots but no debug evidence only proves the frontend rendered correctly — it does not prove the backend logic executed. Both forms of proof are required for a complete session.

Every TC that submits data, calls an API, or triggers a server-side operation MUST produce a `TC-NNN-debug.json` in `$DEBUG_PROOF_DIR/`. If a breakpoint is set and does not hit, that is recorded as a finding ("no server path hit") — it is not a reason to skip the step.

`--no-debug` is an escape hatch for client-side-only projects and CI environments where no server process runs. Using it for convenience when a server is running produces an incomplete session.

**`--no-debug` skip gate:** If `NO_DEBUG = true` (flag was passed in arguments), skip this entire pre-flight block. Set `DEBUG_ENABLED = false` and print: "Debugger skipped (`--no-debug`). Tests will run UI-only with no code proof. Use this flag only when no server process is running." Jump directly to the TC loop.

Otherwise, code-level step-through runs as part of every QA session. This block runs after the prior-session check and before the first TC.

**Step A — Production guard (re-checked here — never skip).**

Before attaching to ANY process: confirm `TARGET_URL` passed Phase 0b. If the URL contains `staging`, `stg`, `stage`, `prod`, `prd`, `production`, or ends with `.azurewebsites.net`, `.herokuapp.com`, `.vercel.app`, `.netlify.app` → **STOP immediately**. Do not attach the debugger. Do not run tests. This is the same hard stop as Phase 0b — it is checked again here to prevent race conditions if Phase 0b was somehow bypassed.

Only attach to processes running on the LOCAL machine. Never use `mcp__mcp-debugger__attach_to_process` with a remote host, IP outside 127.0.0.1/localhost, or credentials from a config file.

**Step B — Detect the running server process.**

Detect OS first:
```bash
uname -s 2>/dev/null
```
- Output starts with `MINGW`, `MSYS`, `CYGWIN`, or the command errors → Windows
- Output is `Darwin` → macOS
- Output is `Linux` → Linux

Run the OS-appropriate detection:

**Windows:**
```bash
tasklist /FI "IMAGENAME eq dotnet.exe" /FO CSV 2>nul
tasklist /FI "IMAGENAME eq node.exe" /FO CSV 2>nul
```

**macOS / Linux:**
```bash
pgrep -la dotnet 2>/dev/null
pgrep -la node 2>/dev/null
```
If `pgrep` is unavailable: `ps aux 2>/dev/null | grep -E " dotnet| node" | grep -v grep`

Parse the output into a table:
```
Detected server processes:
  [PID]  dotnet / dotnet.exe
  [PID]  node / node.exe
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

After installing, re-run this QA session to enable code step-through.
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

---

**TC Blocker Recovery Protocol — mandatory before marking any TC BLOCKED or UNVERIFIABLE.**

When a TC step fails or cannot be executed as written, run this protocol IN ORDER before reaching for BLOCKED or UNVERIFIABLE.

**Step 1 — Diagnose the blocker type.**

| Type | Signal |
|---|---|
| `ENV_URL` | The URL or endpoint used is rejected because it does not match the external service's required format or domain (e.g., vivery.gogrow.com used where `*.online.tableau.com` is required) |
| `ENV_AUTH` | Credentials or accounts required by this TC are not provisioned in this environment |
| `ENV_NETWORK` | External service is unreachable from this host (CDN blocked, firewall, service rejects localhost) |
| `ENV_SETUP` | Required infrastructure is not running (background job not started, email server offline) |
| `ENV_DATA` | Specific data state required (specific user role, specific record) |

**Step 2 — Resolution attempts (by type, in order — stop at first success).**

`ENV_URL`:
1. Search the codebase and config files (appsettings.json, launchSettings.json, Azure App Config, ReportsSettings, ticket.md) for a URL matching the required format
2. If found: swap the URL into the TC and re-execute — do not mark UNVERIFIABLE
3. If not found: document what was searched and fall through to Step 3

`ENV_AUTH`:
1. Check memory, context.md, and ticket.md for provisioned test credentials
2. Check if a lower-privilege account can substitute for the TC's goal
3. If substitute found: adapt TC steps and continue
4. If not found: fall through to Step 3

`ENV_NETWORK`:
1. Try a synthetic alternative: dispatch a corresponding event (e.g., `CustomEvent`) to test the handler in isolation — clearly label any synthetic TC as `[HANDLER-ONLY]`, meaning it proves the frontend handler fires correctly but NOT the real service integration
2. A `[HANDLER-ONLY]` TC DOES NOT replace the full integration TC — it runs alongside it; the original TC is still marked `[U] UNVERIFIABLE` with the synthetic TC noted as partial evidence
3. If no synthetic alternative is possible: fall through to Step 3

`ENV_SETUP`:
1. Search for a dev or admin trigger endpoint (e.g., `/admin/jobs/trigger`, a dev-only controller action)
2. Check if setup can be completed in under 5 minutes
3. If triggerable or setup is quick: complete setup and re-execute
4. If not: fall through to Step 3

`ENV_DATA`:
1. Check if test data can be created via the UI now (use `[E2E-TEST]` prefix)
2. Check if existing data in the environment can substitute
3. If creatable: create and continue
4. If not: fall through to Step 3

**Step 3 — Document if no resolution found.**

Only reach here after exhausting ALL applicable attempts in Step 2.

BLOCKED entry MUST include:
- What was tried (list each resolution attempt from Step 2)
- Why each attempt failed
- The specific setup change that would unblock it

UNVERIFIABLE entry MUST include:
- What was tried (list each resolution attempt from Step 2)
- Why each attempt failed
- Which environment would unblock it (e.g., "staging with Tableau Connected App registered for manager-test.vivery.org")
- Post-deploy plan: who validates, on which environment, when, and what they will confirm

**A TC marked UNVERIFIABLE without documented resolution attempts is treated as BLOCKED by difficulty — the most common form of QA cheating. The auditor will flag it.**

---

**For each `- [ ] TC-NNN` in `plan.md`, execute this loop:**

**Step 1 — BEFORE (state-change tests only).**
For tests that change state (create, delete, update, toggle): call `browser_snapshot` to confirm starting state in text. Take BEFORE screenshot only if the before state matters as evidence.
Skip BEFORE screenshot for smoke/nav tests.

**Step 2 — Execute steps.**
Perform every numbered Step from the test case using ONLY `mcp__playwright__*` tools.
No Bash, no direct API calls, no database reads.

**Credential pre-check (applies when a step fills a password or username field):**

Before calling `browser_fill` or `browser_type` on any auth field, first call `browser_evaluate` to read the field's current value:
```javascript
document.querySelector('[type="password"]')?.value || ''
```
- If the value is non-empty: the browser's password manager has already filled it. Do NOT overwrite. Move directly to the submit step.
- If the value is empty: fill it normally.

Apply the same check to any field labeled "email", "username", or "login" adjacent to a password field.

**Already-authenticated check (applies when a TC requires login as a precondition):**

If `AUTH_STATE = AUTHENTICATED` (set in Phase 1a) and the TC's first step navigates to a login page:
1. Call `browser_snapshot` to confirm whether the login form is actually visible or if the app redirected away.
2. If no login form is visible: the app already has a valid session. Skip the fill/submit steps. Record in plan.md: `PASS | already authenticated — skipped credential fill`.
3. If the login form IS visible despite `AUTH_STATE = AUTHENTICATED` (session expired mid-test): fill normally and continue.

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

**Step 4b — Debug step-through (mandatory code proof — runs after Step 4 for every passing TC with a server code path).**

This step produces the code-level proof that the server actually executed. Without it, you have only UI evidence. Skip ONLY if `DEBUG_ENABLED = false` — not for convenience.

1. **Figure out what code to step through (three-tier lookup — stop at first hit):**

   **Tier 1 — Ticket code entities (highest confidence):**
   If `TICKET_ID` is set and `$WORKSPACE_ABS/analysis.md` exists, read the `### Code Entities` section. For this TC, find the entity whose name or route matches the TC's primary action (e.g., TC "create order" → `OrdersController`, `/api/orders`). Use that file + line as the breakpoint target. Skip tiers 2–3 if found.

   **Tier 2 — Files in Scope graph map (good confidence):**
   Read the `## Files in Scope (Graph Map)` table from `$WORKSPACE_ABS/context.md`. Find the file whose seed entity or route is most relevant to this TC's primary action verb and noun. For example, TC "submit login form" → look for files seeded by `AuthController`, `Login`, or `/api/auth`. Use that file's line_start as the breakpoint target.

   **Tier 3 — RAG graph search (fallback):**
   ```
   POST http://127.0.0.1:8613/search {"query":"[TC primary action — e.g. 'create order controller handler']","sources":["project:<WORKSPACE_ROOT>"],"mode":"graph","limit":3}
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
   - Write debug evidence to `$DEBUG_PROOF_DIR/TC-NNN-debug.json`:
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
   - Write to `$DEBUG_PROOF_DIR/TC-NNN-debug.json`: `{ "tc": "TC-NNN", "verdict": "breakpoint not hit — may be client-side only or async handler", "breakpoint_attempted": "file:line" }`
   - This is still a debug artifact — "not hit" is a valid recorded finding, not a skip.
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
- BLOCKED: `- [B] TC-NNN: ... BLOCKED | reason: [specific verifiable external precondition — removable with setup changes]`
- UNVERIFIABLE: `- [U] TC-NNN: ... UNVERIFIABLE | reason: [why no available environment can test this] | post-deploy: [who validates, when, and how after deployment to a registered environment]`
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
1. Run both searches to find the server-side function handling the operation:
   - `POST http://127.0.0.1:8613/search` with `{"query":"[operation] handler controller service","sources":["project:<WORKSPACE_ROOT>"],"mode":"vector","limit":5}` — semantic match
   - `POST http://127.0.0.1:8613/search` with `{"query":"[operation] handler controller service","sources":["project:<WORKSPACE_ROOT>"],"mode":"graph","limit":5}` — caller chain and module wiring
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
1. `POST http://127.0.0.1:8613/search` with `{"query":"[job class name] job worker execute schedule","sources":["project:<WORKSPACE_ROOT>"],"mode":"graph","limit":5}` — find the job class, its scheduler/dispatcher, and the table/column it writes. mode=graph surfaces the wiring (what registers or enqueues this job alongside the class itself.
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
4. Call `browser_take_screenshot` → overwrite `$PROOF_DIR/TC-NNN-after.png`.
5. Remove the overlay.
6. Note in plan.md alongside the TC: `screenshot retaken after evaluator audit`.

If a retake is not possible (page state cannot be reproduced without side-effects): note in plan.md: `screenshot retake skipped — [reason]`.

Print after the pass: "Screenshot audit complete. Evaluator flagged N / M screenshots for retake. [N] retaken, [K] skipped."

**Coverage Gap Analysis (runs after screenshot audit, before closing debug session).**

This step answers: "what did I NOT test, and why?" A QA report that only lists what was tested is incomplete. Run this before the report phase.

1. Read `$WORKSPACE_ABS/app-inventory.md` — Routes/Pages table and Entities with CRUD table.
2. Read `$WORKSPACE_ABS/plan.md` — collect the route/page reference from every TC (from the `Code path:` field or TC description).
3. Read `$WORKSPACE_ABS/flow-map.md` — `## Uncovered Routes` section (if it exists).

For each route in the inventory:
- Find at least one TC in plan.md that visits or exercises that route
- If found: mark as `covered`
- If not found: check if it's in flow-map.md `## Uncovered Routes` with a reason
- If neither: mark as `gap — no TC and no justification`

For each entity in Entities with CRUD:
- Find TCs for each operation (create/read/update/delete) — mark each operation as `covered` or `gap`

Write `$WORKSPACE_ABS/coverage-gaps.md`:

```markdown
# Coverage Gap Analysis

**Session**: [TASK_ID]
**Date**: [date]
**Inventory source**: app-inventory.md (built from RAG codebase traversal)

## Route Coverage

| Route | Covered by | Status |
|-------|-----------|--------|
| /login | TC-AUTH-01, TC-AUTH-02 | covered |
| /admin/users | — | **GAP** — no TC found, no justification in flow-map.md |
| /api/export | — | out-of-scope — API-only route, not browser-testable |

## Entity Coverage

| Entity | Create | Read | Update | Delete |
|--------|--------|------|--------|--------|
| Order  | TC-003 | TC-004 | TC-005 | **GAP** |
| User   | TC-AUTH-01 | — | **GAP** | — |

## What Was Not Tested (Honest Summary)

List every gap with a classification:
- **Explicit gap**: route or entity operation with no TC and no justification — needs attention
- **Justified gap**: route excluded with a stated reason (admin-only, no test account, API-only, out of scope for this session)
- **Structural gap**: feature exists in code but was unreachable during testing (404, auth-blocked without test credentials)

This section is the QA equivalent of a risk residual — what remains after this session ends.
```

If ALL routes and entity operations are covered: write coverage-gaps.md with "Full coverage achieved — all N routes and M entity operations have corresponding test cases."

**Close debug session (runs after coverage gap analysis and all TCs and evaluator pass complete).**

If `DEBUG_ENABLED = true`:

Count the debug results from `$DEBUG_PROOF_DIR/`:
- `HITS` = number of TC-NNN-debug.json files where `verdict` contains "breakpoint hit"
- `MISSES` = files where `verdict` contains "not hit"
- `TOTAL` = HITS + MISSES

Write `$DEBUG_PROOF_DIR/session-summary.json`:
```json
{
  "session": "[TASK_ID]",
  "date": "[date]",
  "debug_session_id": "[DEBUG_SESSION_ID]",
  "breakpoints_hit": [HITS],
  "breakpoints_missed": [MISSES],
  "total_tcs_with_debug_attempt": [TOTAL],
  "tc_files": ["TC-001-debug.json", "TC-002-debug.json", ...]
}
```

Call `mcp__mcp-debugger__close_debug_session` with `sessionId=DEBUG_SESSION_ID`.
Print: "Debug session closed. [HITS]/[TOTAL] TCs had breakpoint hits. Debug proof → `$DEBUG_PROOF_DIR/`"
Set `DEBUG_ENABLED = false`.

---

## Phase 4: Report

**PHASE 4 ENTRY GATE — runs before any report is written:**

Verify the Phase 3 Close screenshot validation evaluator ran this session. If it did NOT run:

1. Run Phase 3 Close now — spawn `evaluator-agent` for screenshot validation before continuing.
2. Do NOT write the report until the evaluator has returned its verdict.

The orchestrator must NOT self-verify screenshots. "I checked them and they look fine" is not a substitute for the evaluator pass. Apply all RETAKE instructions before proceeding.

**4a — Tally results.**

Read `plan.md`. Count: PASS `[x]`, FAIL `[F]`, BLOCKED `[B]`, UNVERIFIABLE `[U]`, NEEDS-RERUN `[S]`.

**4b — Write report.**

Write `$WORKSPACE_ABS/report.md`:

```markdown
# QA Session Report

**URL**: [TARGET_URL]
**Date**: [date]
**Scope**: [SCOPE]
**App Inventory**: $WORKSPACE_ABS/app-inventory.md
**Coverage Gaps**: $WORKSPACE_ABS/coverage-gaps.md
**Plan**: $WORKSPACE_ABS/plan.md
**Screenshots**: $SNAPSHOTS_DIR/
**Proof**: $PROOF_DIR/

## Summary

| Result         | Count |
|----------------|-------|
| PASS           | N     |
| FAIL           | N     |
| BLOCKED        | N     |
| UNVERIFIABLE   | N     |
| NEEDS-RERUN    | N     |
| Total          | N     |

**Overall**: PASS / FAIL / PARTIAL

## Failures

[For each FAIL: TC-ID, description, expected, observed (snapshot text)]

## Blocked Tests

[For each BLOCKED: TC-ID, description, blocking reason]

## Unverifiable Tests

[For each UNVERIFIABLE: TC-ID, description, reason this environment cannot test it, and post-deploy validation plan]

| TC-ID | Description | Why Unverifiable | Post-Deploy Validation |
|-------|-------------|-----------------|----------------------|
| TC-SDK-001 | Tableau SDK loads successfully | CDN rejects localhost | After deploy to manager-test.vivery.org: QA engineer opens page, confirms dashboard renders within 30s |

## Needs-Rerun

[For each NEEDS-RERUN: TC-ID, description, reason — e.g., "prior session result, not re-executed this session"]

## Evidence Index

| TC-ID | Description | Result | Screenshot | Debug Proof |
|-------|-------------|--------|------------|-------------|
| TC-001 | ... | PASS | TC-001-after.png | TC-001-debug.json (breakpoint hit) |
| TC-002 | ... | PASS | TC-002-after.png | TC-002-debug.json (no server path) |
| TC-003 | ... | FAIL | — | TC-003-debug.json (breakpoint hit) |

Screenshot column: populated for browser mode only. For non-browser (general mode) write "N/A — not a UI test".
Debug proof column: populated whenever `DEBUG_ENABLED = true` — always attempted for TCs with server calls.

## Debug Proof Summary

**Debug session:** [DEBUG_SESSION_ID or "disabled"]
**Breakpoints hit:** [N] / [TOTAL TCs attempted]
**Full debug log:** `$DEBUG_PROOF_DIR/`

For each TC with a breakpoint hit, note the key finding:
| TC-ID | Breakpoint | Key Variables Observed | Branch Taken |
|-------|-----------|----------------------|--------------|
| TC-001 | OrdersController.cs:42 | orderId=123, userId=5 | create path |

## What Was NOT Tested

Copy from `coverage-gaps.md` — the honest summary of gaps.

This section is mandatory. If it is absent from a report, the report is incomplete. A report
that claims "all features were tested" without this section is not credible.

| Route / Feature | Status | Reason |
|-----------------|--------|--------|
| [route] | **GAP** | [no TC, no justification found] |
| [route] | justified | [admin-only — no test credentials provisioned] |

If no gaps: write "No gaps. All N routes and M entity operations in app-inventory.md have covering TCs."

## QA Observations (Non-TC Findings)

These are findings noticed during testing that aren't formal PASS/FAIL test cases — the kind
of thing a real QA person writes in their session notes.

- **UX issues**: confusing flows, misleading labels, unclear feedback
- **Inconsistencies**: same feature behaves differently in different contexts
- **Performance observations**: pages that were noticeably slow to load
- **Accessibility concerns**: missing labels, non-keyboard-navigable controls
- **Data edge cases noticed**: unusual behavior with specific data values
- **Code smells visible in UI**: error messages leaking stack traces, debug UI visible in prod build

If no observations: write "No notable observations this session."

## UI Inconsistencies Found

[List any structural inconsistencies detected by UI consistency TCs]

## Console Errors

[Any browser console errors observed across all tests]

## Temp-Logging Used

[Any TCs that used temp-logging, with rationale and confirmation of removal]

## Post-Deploy Validation Required

[Only present when UNVERIFIABLE count > 0. This section tells the team what still needs to be manually validated after deployment to a registered/production-like environment.]

| TC-ID | What to Validate | Environment Needed | Assigned To | When |
|-------|-----------------|-------------------|-------------|------|
| [TC-SDK-001] | [Tableau dashboard loads, JWT auth chain end-to-end] | [domain registered with Tableau Connected App] | [QA engineer] | [on first deploy to manager-test.vivery.org] |

These items are not bugs — they are genuine environment constraints that prevented local validation. Each must be checked before the feature is considered fully validated.
```

**4c — Print summary to user.**

Print the Summary table. List all failures with their observed state. List blocked tests with reasons.

Do NOT print the final "session complete" message yet — Phase 5 runs next.

---

## Phase 5: Session Integrity Audit + Skipped Test Remediation

**This phase runs automatically after every QA session. It is NOT optional.**

Phase 5 has two jobs:
1. Audit the completed session for real proof (both code and UI where applicable)
2. Attempt to run anything that was skipped, blocked, or unverifiable — if it can now be resolved, resolve it

---

### 5a — Proof inventory check (before running audit)

Before calling `/audit`, inventory what proof exists:

**Code proof (always required when `DEBUG_ENABLED = true`):**

**If MODE = browser:** Count files in `$DEBUG_PROOF_DIR/`. For each TC in plan.md marked `[x] PASS`:
- Does a `TC-NNN-debug.json` exist in `$DEBUG_PROOF_DIR/`? If no → flag as "PASS without code proof"
- A "not hit" json counts as attempted — it is NOT a gap. A missing json IS a gap.

**If MODE = general:** Read `$DEBUG_PROOF_DIR/session-summary.json` (written by G4d). Check `paths_debugged` — if the file does not exist or `paths_debugged = 0`, flag as "no code proof collected." Do NOT check for `TC-NNN-debug.json` files — general mode writes `path-NNN-[function-name].json` artifacts, not TC-named files.

**Screenshot proof (required for browser mode, not required for general mode):**
Only check this if `MODE = browser`. For each TC in plan.md marked `[x] PASS`:
- Does a `TC-NNN-after.png` exist in `$PROOF_DIR/`? If no → flag as "PASS without screenshot"
- For general mode (code testing, scripts, hooks): screenshots are not expected — do not flag their absence.

Print the proof inventory:
```
Proof inventory:
  TCs/paths with PASS                : [N]
  Code proof collected               : [N]  ← gaps: [list TC-IDs or "paths_debugged=0"]  (browser: TC-NNN-debug.json / general: session-summary.json)
  Screenshots (UI proof)             : [N]  ← N/A for general mode
  Items flagged as PASS without proof: [list]
```

---

### 5b — Skipped and blocked test remediation

Before the audit, attempt to clear any BLOCKED `[B]` or NEEDS-RERUN `[S]` items.

For each `[B] BLOCKED` TC:
1. Re-read the blocking reason. Has anything changed that would unblock it?
2. Check if setup can now be completed (the TC Blocker Recovery Protocol already ran before — this is a second pass at a fresh look after the rest of the session is done).
3. If newly unblockable: run it now. Mark result in plan.md.
4. If still genuinely blocked: leave as `[B]`. The audit will see the reason.

For each `[S] NEEDS-RERUN` TC:
1. Re-run it now. Mark result in plan.md.
2. There is no valid reason to leave a NEEDS-RERUN item unrun at the end of a session.

For each `[U] UNVERIFIABLE` TC:
1. These are environment constraints — do not attempt to change the verdict.
2. Confirm the post-deploy validation note is filled in (who validates, when, how). If not filled: fill it before the audit.

---

### 5c — Run the session audit

Invoke `/audit` on the completed session output. Pass it:
- The full content of `$WORKSPACE_ABS/report.md`
- The full content of `$WORKSPACE_ABS/plan.md`
- The proof inventory from 5a
- The debug proof count from `$DEBUG_PROOF_DIR/session-summary.json` (if exists)

The audit checks:
- **Completion coverage** — does the report address all planned TCs? Any TC with no result?
- **Evidence quality** — every PASS must have either a debug json OR a screenshot OR both. A PASS with neither is not evidence.
- **Screenshot requirement** — for browser mode: every PASS for a visible UI state must have a screenshot. For general mode: screenshots are not expected.
- **Code proof requirement** — for any TC that exercises server-side code: a debug json must exist (even a "not hit" json). If the debugger was disabled, this check is waived — but is noted.
- **Skipped item resolution** — any BLOCKED item that could have been resolved (based on the retry attempt in 5b) but wasn't.
- **Post-deploy plans** — every UNVERIFIABLE TC has a filled post-deploy validation entry.
- **Gap honesty** — the "What Was NOT Tested" section is present and non-empty when gaps exist.

---

### 5d — Post-audit remediation

After the audit returns its verdict:

**If audit flags PASS-without-evidence TCs:**
1. For each flagged TC: attempt to gather the missing proof now.
   - Missing debug json: re-run Step 4b for that TC (re-trigger the action, set the breakpoint, capture variables).
   - Missing screenshot (browser mode only): re-run Step 4 for that TC (navigate back, re-execute the final action, take the annotated screenshot).
2. Update plan.md and the evidence index in report.md with any newly gathered proof.
3. If proof still cannot be gathered (page state not reproducible, no server process): downgrade the TC from `[x] PASS` to `[F] FAIL | evidence not collectible post-session — re-run needed`.

**If audit flags unfilled post-deploy entries:**
Fill them now before printing the final output.

**If audit flags a PASS verdict on the overall session (`VERIFIED` or `LEGIT`):**
No remediation needed. Proceed to 5e.

---

### 5e — Final report to user

Print the complete final output to the user:

```
╔══════════════════════════════════════════════════════════════╗
║  QA SESSION COMPLETE                                         ║
╚══════════════════════════════════════════════════════════════╝

Target    : [TARGET_URL or GENERAL_TARGET]
Workspace : [WORKSPACE_ABS]
Date      : [date]

── Test Results ─────────────────────────────────────────────
  PASS         : [N]
  FAIL         : [N]
  BLOCKED      : [N]
  UNVERIFIABLE : [N]
  NEEDS-RERUN  : [N]  (should be 0 after Phase 5b)
  Total        : [N]

── Proof ────────────────────────────────────────────────────
  Debug json files   : [N] / [PASS count] TCs  ([hits]/[total] breakpoints hit)
  Screenshots        : [N] / [PASS count] TCs  [or "N/A — general mode"]
  TCs with no proof  : [N]  (should be 0 after Phase 5d)

── Session Integrity Audit ──────────────────────────────────
  Verdict    : [VERIFIED / PARTIALLY VERIFIED / UNVERIFIED]
  Confidence : [HIGH / MEDIUM / LOW]
  Gaps found : [N]  (resolved: [N], unresolvable: [N])

── Failures ─────────────────────────────────────────────────
[List each FAIL with: TC-ID — what was expected — what was observed]

── Blocked (needs setup to resolve) ─────────────────────────
[List each BLOCKED with: TC-ID — blocking reason — setup needed]

── Not Tested ───────────────────────────────────────────────
[Copy from coverage-gaps.md — every gap named explicitly]

── Post-Deploy Validation Required ──────────────────────────
[List each UNVERIFIABLE with: TC-ID — what to validate — environment needed]

── Files ────────────────────────────────────────────────────
  Full report   → [WORKSPACE_ABS]/report.md
  Test plan     → [WORKSPACE_ABS]/plan.md
  Coverage gaps → [WORKSPACE_ABS]/coverage-gaps.md
  Debug proof   → [WORKSPACE_ABS]/debug-proof/
  Screenshots   → [WORKSPACE_ABS]/screenshots/proof-*/  [or "N/A — general mode"]
```

If there are failures: say what to do next (fix them and re-run `/qa quick` to verify).
If everything passed: say that and suggest `/done` to ship.

Call `browser_close` if `MODE = browser`.

---

## Post-Execution Interaction Rules

**If the user asks whether screenshots were independently verified:**

- If Phase 3 Close evaluator ran → confirm and cite the evaluator's RETAKE count.
- If Phase 3 Close did NOT run → run it now before answering. Do not self-assess screenshot quality.

---

---

## General Mode

**Entry:** MODE = `general`. Used when there is no browser target — QAing code changes, scripts, hooks, artifacts, or workspace output.

---

### G1: Charter

Define the session mission before any work starts.

Template: **"Explore [GENERAL_TARGET] With [test suite + RAG search + edge case tests] To discover [regressions / logic errors / edge case failures / false positives]"**

Derive `GENERAL_TARGET` from MODE detection:
- `--code`: run `git diff HEAD~1 --name-only` and `git diff HEAD~1 --stat` to get the list of changed files
- File path: the file or directory named
- Workspace ID: files in `$WORKSPACE_ABS/` (plan.md, report.md, context.md, research-brief.md)
- Description: the text the user provided

Print the charter:
```
Session charter
  Target  : [GENERAL_TARGET description]
  Mission : Explore [target] with test suite + edge case tests to discover [problem classes]
  Scope   : [list the specific files or artifacts in scope]
```

Write the charter to `$WORKSPACE_ABS/session-charter.md`.

**G1b — Create logs directory.**

```bash
mkdir -p "$WORKSPACE_ABS/logs"
```

This is where temporary logging output will be captured during testing. All log files in this directory are removed at the end of the QA session (see Phase 6).

---

### G2: Inventory

Understand the target before testing it.

**G2a — Read target files.** For each file in scope: read it, note its purpose, test surface, and any obvious inputs/outputs.

**G2b — RAG search for related code.** Run both modes:
```
POST http://127.0.0.1:8613/search {"query":"<target description>","sources":["project:<WORKSPACE_ROOT>"],"mode":"vector","limit":10}
POST http://127.0.0.1:8613/search {"query":"<target description>","sources":["project:<WORKSPACE_ROOT>"],"mode":"graph","limit":10}
```
Use results to find: callers, tests that already exist, related modules the change might affect.

**G2b-ii — Caller-graph regression surface.**

For each changed function or entry point found in G2b, enumerate its callers via graph search:
```
POST http://127.0.0.1:8613/search {"query":"<changed function name>","sources":["project:<WORKSPACE_ROOT>"],"mode":"graph","limit":10}
```

Add a `## Caller Regression Surface` section to `session-inventory.md` (written in G2c):
```markdown
## Caller Regression Surface
| Changed Symbol | Callers Found | Risk |
|---------------|---------------|------|
| [function] | [callers from graph result] | [high if many/external callers, low if private/internal] |
```
These callers define the regression surface. Include at least one TC in G4b that exercises each distinct caller path — a passing test suite that never exercises the changed function through its real callers proves nothing about backward compatibility.

**G2c — Write inventory to `$WORKSPACE_ABS/session-inventory.md`:**
```markdown
# Session Inventory

## Files in Scope
| File | Purpose | Test Surface | Existing Tests |
|------|---------|-------------|----------------|
| path/to/file.py | ... | ... | test_file.py or "none" |

## Related Files (from RAG)
| File | Relationship |
|------|-------------|
| ... | calls this, imports from this, tested alongside |

## Caller Regression Surface
| Changed Symbol | Callers Found | Risk |
|---------------|---------------|------|
| [from G2b-ii] | | |

## Risk Areas
- [things that could break, edge cases, surprising inputs]
```

---

### G3: Static Pass

Run what already exists before writing anything new.

**G3a — Existing test suite.** Detect and run:
- Python: `pytest` in the project root or nearest `tests/` directory
- Node: `npm test` or `npx vitest run`
- Other: check `package.json scripts.test` or `Makefile`

Record output: pass count, fail count, any errors. Write to `$WORKSPACE_ABS/static-results.md`.

**G3b — Type checking (if applicable).**
- Python: `mypy <files-in-scope>` if mypy is installed
- TypeScript: `tsc --noEmit` if tsconfig.json exists

**G3c — Lint (if applicable).**
- Python: `ruff check <files-in-scope>` or `flake8`
- JS/TS: `eslint <files-in-scope>` if config exists

Record any failures by file and line. A lint failure is not a FAIL unless it indicates a real bug — note it as an observation.

---

### G3.5: Code Coverage Audit (MANDATORY — NEVER SKIP)

> **You do not know whether untested code works. You must KNOW, not assume. A passing test suite with no coverage of the new code proves nothing about the new code.**

**G3.5a — Map every public symbol to tests.**

For every file in scope, list all public functions, methods, handlers, and entry points (name + line). Then search for each symbol in the test project:
```bash
grep -rl "<SymbolName>" "$PROJECT_PATH" --include="*Test*" --include="*Spec*" 2>/dev/null
```

Build a coverage table in `$WORKSPACE_ABS/coverage-map.md`:
```markdown
# Coverage Map

| Symbol | File:Line | Covered? | Test File |
|--------|-----------|----------|-----------|
| OnPostCreateTableauDashboard | ReportsSettings.cshtml.cs:396 | UNCOVERED | none |
```

**G3.5b — Write tests for every UNCOVERED symbol in changed or newly-added code.**

Scope: only symbols that appear in the git diff (changed or new). Pre-existing uncovered symbols are noted in `coverage-map.md` as `pre-existing gap — out of session scope` and left for a dedicated coverage pass.

For every in-scope UNCOVERED symbol: write at least one test using the project's established pattern (extract logic into a local helper, test in isolation — no live DI or DB needed). Each auth/validation branch is a separate test case — one test covering the happy path is insufficient.

If a symbol genuinely cannot be unit tested in isolation (requires live DB, live session, etc.): document it as INTEGRATION_REQUIRED, explain why, and describe what would be needed to test it with a running server.

Run the new tests immediately. Record results in `coverage-map.md`.

---

### G3.6: Logging Verification (MANDATORY — NEVER SKIP)

> **Structured logs are the evidence that a handler actually ran the branch you think it ran. Without them you are guessing. Every handler under test must have logging — verify it is there and correct before moving on.**

**What counts as a GOOD permanent log:**
- `LogInformation` on successful mutations only — include resource ID and key discriminating fields (type, regionId, flag state). Nothing else.
  - GOOD: `_logger.LogInformation("Tableau dashboard created — id={Id}, regionId={RegionId}", id, regionId)`
  - BAD: `_logger.LogInformation("Created: {DisplayText}", body.DisplayText)` — logs user-controlled input
- `LogWarning` on auth rejections and validation failures — include which check failed, no raw input values, no user-supplied strings, no URLs
  - GOOD: `_logger.LogWarning("CreateTableauDashboard: validation failed — bodyNull={BodyNull}, validUri={ValidUri}", ...)`
  - BAD: `_logger.LogWarning("Invalid URL: {Url}", body.ResourceUrl)` — logs user input
- `LogError` in every catch block — include the exception and method context
- NO logging on pure read handlers (GET handlers that do not mutate state)
- NEVER log: session keys, JWT values, tokens, emails, API keys, base64 content, raw user-supplied strings

**What counts as a TEMPORARY log:**
- A `LogDebug` / `LogTrace` call added specifically to trace an unclear path during this QA session
- Must have a `// TODO: remove after QA` comment on the same line — visible in code review
- Must appear in a removal checklist in `$WORKSPACE_ABS/temp-log-removal.md` — QA session is not complete until this file is written and each temp log confirmed removed or tracked
- Only valid for async flows where a debugger cannot easily attach — NOT a substitute for setting a breakpoint

**G3.6a — Audit every in-scope handler.** Use Grep to find existing log calls. Document in `$WORKSPACE_ABS/logging-audit.md`:
```markdown
# Logging Audit

| Handler | LogInfo on success? | LogWarning on failures? | LogError in catch? | Sensitive data in params? |
|---------|--------------------|-----------------------|--------------------|--------------------------|
| OnPostCreateTableauDashboard | yes | yes | no catch block | no |
```

**G3.6b — Add missing log calls.** For any handler missing required calls: add them now following the GOOD log patterns above. Then run a build to confirm no compile errors.

**G3.6c — Add temporary coverage logging.** For every function, handler, and code path touched by this ticket, add temporary log statements that will capture execution evidence during testing. These go to `$WORKSPACE_ABS/logs/`:

1. Add `LogDebug` or `print` calls at the entry and exit of every function under test, and at every branch point (if/else, switch cases, error paths)
2. Log inputs (sanitized, no secrets) and outputs so the logs prove which paths were exercised
3. Configure log output to write to `$WORKSPACE_ABS/logs/coverage-trace.log` (or the project's existing log sink if applicable)
4. Every temporary log line MUST have a `// QA-TEMP` marker comment so it can be found and removed later
5. Run a build to confirm no compile errors after instrumentation

The goal is complete code coverage evidence: after running all tests, the log file should show that every branch of every changed function was executed.

---

### G3.7: Bug Fix During QA (MANDATORY)

> **Bugs found during QA are fixed during QA. They are not deferred, not logged for later, not left as known issues.**

When a test reveals a bug:
1. Fix the bug immediately
2. Rerun the test that found the bug to confirm the fix
3. Rerun any tests that could be affected by the fix (regression check)
4. Update `$WORKSPACE_ABS/bugs-fixed.md` with: what was found, what was fixed, which test confirmed it
5. If the fix touches files outside the original scope, note them in context.md

Do not move to Phase 5 (audit) until all discovered bugs are fixed and verified.

---

### G4: Exploratory Pass

Write targeted tests for things the existing suite does not cover.

**G4a — Identify gaps.** Three passes, each surfacing different gaps:

**Pass 1 — Equivalence partitioning.** For each public entry point in the
changed code, name five input classes: valid-typical, valid-boundary,
invalid-format, null/empty, and type-wrong. Any class with no covering test
is a gap.

**Pass 2 — Caller regression.** From the Caller Regression Surface in
`session-inventory.md`, check which callers have a test that exercises the
changed path. A caller with no test is a gap.

**Pass 3 — Behavioral gaps.** From the inventory risk areas and static pass
results, list what is not tested:
- Error paths (what happens when X fails?)
- False positive / false negative risks (for checks and validators)
- Interaction effects (does this change break something it calls or that calls it?)
- Prior-behavior differential: does the change alter return value, type, or
  side effect for any existing caller? If so, a test that asserts the old
  behavior is a gap.

**G4a-ii — Derive correctness invariants (runs before G4b).**

Before writing edge case tests, derive the invariants the changed logic must hold. For each function or handler in scope, complete:
- "For any input X, this function must [return/produce/not produce] Y"
- "This function must NEVER [raise uncaught / return null when non-null expected / corrupt state / produce a value outside bounds]"

Write these as comments at the top of the edge case test file. Use them to drive G4b: a good edge case test disproves an invariant on wrong inputs, not just confirms a known-good path.

Common invariants to check against wrong implementations:
- Off-by-one: does the boundary value (0, 1, N, N+1) trigger the correct branch?
- Null/empty: does None, "", or [] reach the correct guard without raising?
- Idempotency: does calling the function twice with the same input produce the same result?
- Contract: does the function uphold its documented preconditions on invalid input?

When the edge cases are combinatorial (multiple parameters, each with
boundary values), prefer the language's property-based testing library
(`Hypothesis` for Python, `fast-check` for JS/TS, `jqwik` for Java) over
hand-listing a few examples. It generates the inputs you wouldn't think of.

**G4b — Write edge case tests.** For each gap, write a minimal test. Place it alongside the existing test file if one exists, or create `$WORKSPACE_ABS/edge-case-tests.py` (or `.ts`, `.js`).

Each test must be:
- Self-contained: no external state dependencies
- Labeled clearly: what scenario it covers and what outcome it expects
- Runnable: actually run it and record pass/fail

**G4c — Run edge case tests.** Record results. A test that was expected to fail and does pass is a regression catch — flag it.

Write all results to `$WORKSPACE_ABS/static-results.md` under "Edge Case Pass".

**G4c-ii — Mutation check (runs after edge case tests pass).**

Passing tests are necessary, not proof the tests catch bugs. Run the mutation check on changed files only:
```
POST http://127.0.0.1:8613/mutation-test {"project_path":"<WORKSPACE_ROOT>","changed_files":["<files from GENERAL_TARGET>"]}
```
This runs the language's real mutation tool (`mutmut` for Python, `StrykerJS` for JS/TS, `cargo-mutants` for Rust) and returns a kill score. A surviving mutant is a test that would pass on broken code — tighten the test to kill it.

Record the kill score in `$WORKSPACE_ABS/static-results.md` under "Mutation Check":
```
Mutation kill score: [N]% ([K] killed / [T] total mutants)
Surviving mutants: [list or "none"]
```
A kill score below 80% on a non-trivial change is a gap worth addressing before shipping. If the mutation server is unavailable, note it and skip.

---

### G4d: Debugger-Assisted Verification (MANDATORY — ALWAYS — NEVER SKIP)

> **THIS IS NOT OPTIONAL. IT IS ALWAYS REQUIRED. USE BREAKPOINTS HEAVILY.**
>
> Tests tell you pass or fail. The debugger tells you **what actually happened** — which branch ran, what the variables held, whether the comment is accurate. Without breakpoints you are **assuming**. With breakpoints you **know**. There is no acceptable substitute for knowing.
>
> "The tests passed" is not enough. "I can read the logic" is not enough. "It looks correct" is not enough. You must step through the actual running code, inspect actual variable values at actual decision points, and confirm the actual branch taken. Every handler. Every meaningful branch. Every null check that matters.
>
> **The only valid skip condition is `--no-debug` explicitly passed by the user.** Skipping for any other reason produces an incomplete session — write `INCOMPLETE: debugger skipped — [reason]` in the report and surface it to the user.

Running tests tells you pass/fail. The debugger tells you *why* — and whether the code does what the comments claim at runtime. The debug log is the equivalent of a screenshot in browser mode: it is the evidence that the path actually executed.

**When a failure will not yield:** invoke the `debugging-methodology` skill and pick a technique from its symptom table by name rather than stepping the same path again. Regressed since a known good commit is `git bisect`. A large failing input is delta debugging. A working case beside the failing one is differential debugging. Intermittent is record replay. At 2-3 iterations with no new information, switch technique. That skill also carries the per stack CLI recipes (React Native, .NET, Python) for the surfaces `mcp-debugger` does not reach, and the rule that databases are read only in QA: understand the schema from the project's migrations and models, never execute against a live one.

Set `DEBUG_PROOF_DIR = $WORKSPACE_ABS/debug-proof` and create it if it does not exist.

**Debugger pre-flight.**

Call `mcp__mcp-debugger__list_supported_languages` to confirm the language is supported. Then create a session:
```
mcp__mcp-debugger__create_debug_session(
  language = detected language (python / javascript / typescript / go / etc.),
  name     = "qa-general-[TASK_ID]"
)
```
Store the `sessionId`.

**Choose what to step through.**

From the inventory and edge case test results, pick 2-4 code paths worth verifying at runtime. Good candidates:
- Any test that failed — step through to find the actual branch taken
- Any condition with multiple branches (if/elif chains, try/except blocks) where the comment doesn't match your expectation
- Any function that transforms input in a non-obvious way
- Any result that looked surprising during the static or exploratory pass

**Step through each path.**

For each chosen path:

1. `mcp__mcp-debugger__set_breakpoint(sessionId, file, line)` — set at the entry point or the branch you want to verify
2. `mcp__mcp-debugger__start_debugging` — run the test or script that exercises this path
3. When the breakpoint hits:
   - `mcp__mcp-debugger__get_variables` — inspect locals, confirm inputs match what you expect
   - `mcp__mcp-debugger__get_stack_trace` — confirm the call came from where you think
   - `mcp__mcp-debugger__step_over` / `step_into` — walk through the logic step by step
   - `mcp__mcp-debugger__evaluate_expression` — test a hypothesis ("is this value actually None here?")
4. At each decision point: record what the variable values actually are, and whether the branch taken matches what the code comment says it does.

**Record findings — two outputs per path:**

**1. Per-path JSON in `$DEBUG_PROOF_DIR/`:**

Name the file after the code path or test: `path-NNN-[function-name].json`
```json
{
  "path": "NNN",
  "function": "[file:line — function name]",
  "triggered_by": "[test name or script invocation]",
  "variables_at_breakpoint": { ... },
  "branch_taken": "[which branch executed]",
  "matches_expectations": true,
  "finding": "[if false — what the code actually does vs. what was expected]"
}
```

**2. Narrative entry in `$WORKSPACE_ABS/debug-log.md`:**
```markdown
## [function or file:line]
- Breakpoint at: [file:line]
- Triggered by: [test name or manual run]
- Variables at breakpoint: [key locals and their actual values]
- Branch taken: [which path executed]
- Matches code comments/expectations: YES / NO
- Finding: [if NO — what the code actually does vs. what was claimed]
- Proof file: debug-proof/path-NNN-[function-name].json
```

After all paths are stepped through, write `$DEBUG_PROOF_DIR/session-summary.json`:
```json
{
  "session": "[TASK_ID]",
  "date": "[date]",
  "paths_debugged": [N],
  "expectation_mismatches": [N],
  "path_files": ["path-001-funcname.json", ...]
}
```

Close the session when done: `mcp__mcp-debugger__close_debug_session(sessionId)`.

---

### G5: Session Report

Write `$WORKSPACE_ABS/report.md`:

```markdown
# QA Session Report — General Mode
Target: [GENERAL_TARGET]
Date: [today]
Charter: Explore [target] With [tools] To discover [problem classes]

## Summary

| Category | Result |
|----------|--------|
| Existing tests | N passed, N failed |
| Edge case tests written | N |
| Edge case tests passed | N |
| Code paths debugged | N |
| Expectation mismatches found | N |
| Bugs found | N |
| Observations | N |

## Static Pass Results

[paste key output from G3 — test counts, type errors, lint issues]

## Edge Case Results

| Test | Scenario | Expected | Actual | PASS/FAIL |
|------|----------|----------|--------|-----------|
| TC-GEN-001 | empty input | return [] | return [] | PASS |
| ... | | | | |

## Debugger Findings

[Each path stepped through: what was expected, what variables actually held, whether the branch taken matched the comment/assumption. Any mismatch is a finding.]

## Bugs Found

[Each bug: description, file:line, reproduction steps, severity]

## Observations

[Things noticed that aren't formal bugs — code smells, unclear behavior, missing docs, surprising edge cases]

## Skipped Areas

[What was NOT tested and why — explicit, not silent]

## Open Questions

[Things that need more investigation or a decision from the team]
```

**G5b — Proceed to Phase 5.**

Do NOT print the final output yet. General mode sessions also run Phase 5 (Session Integrity Audit + Skipped Test Remediation) before printing the final report to the user.

Jump to **Phase 5** now. Use `MODE = general` context:
- Phase 5a: Check debug proof (no screenshots expected — `MODE = general`)
- Phase 5b: Retry any BLOCKED items
- Phase 5c: Run audit on report.md + debug-proof/session-summary.json
- Phase 5d: Remediate gaps
- Phase 5e: Print the final output to the user (same format as browser mode, screenshot line shows "N/A — general mode")

---

## Phase 6: Log Cleanup and Build Verification (MANDATORY)

**This phase runs after Phase 5 completes. QA is NOT done until logs are cleaned up and the build is verified.**

### 6a — Remove all temporary logging instrumentation

1. Search all in scope files for `// QA-TEMP` marker comments:
   ```bash
   grep -rn "QA-TEMP" "$PROJECT_PATH" --include="*.py" --include="*.cs" --include="*.ts" --include="*.js" --include="*.go" --include="*.java"
   ```
2. Remove every line marked with `// QA-TEMP`
3. Cross reference against `$WORKSPACE_ABS/temp-log-removal.md` (written in G3.6) to confirm nothing was missed
4. If any temp log was accidentally left without the marker, search for common QA log patterns (e.g. "coverage-trace", "QA debug") and remove those too

### 6b — Clean up workspace logs directory

1. Archive the coverage trace log for the audit record:
   ```bash
   cp "$WORKSPACE_ABS/logs/coverage-trace.log" "$WORKSPACE_ABS/logs/coverage-trace-archive.log" 2>/dev/null
   ```
2. Remove all log files from the workspace logs directory:
   ```bash
   rm -f "$WORKSPACE_ABS/logs/"*.log
   ```
   Keep the directory itself and the archive copy.

### 6c — Verify build still passes

Run the project's build command after log removal to confirm nothing was broken:
- Python: `python -m py_compile <changed files>` or `pytest --co` (collect only)
- .NET: `dotnet build`
- Node: `npm run build` or `tsc --noEmit`
- Go: `go build ./...`

If the build fails: a temp log removal broke something. Fix it, rerun the build, and continue.

### 6d — Verify tests still pass

Run the test suite one final time after log removal. If any test fails that was passing before: the temp log was load bearing (it changed behavior). Investigate and fix.

Print:
```
Log cleanup complete:
  Temp logs removed     : [N] lines across [N] files
  Build after removal   : [PASS/FAIL]
  Tests after removal   : [PASS/FAIL]
  Coverage trace saved  : $WORKSPACE_ABS/logs/coverage-trace-archive.log
```

---

## What's Next After /qa

The session integrity audit (Phase 5) and log cleanup (Phase 6) already ran before you saw this output. It checked proof coverage, retried blocked items, and confirmed the verdict.

| If Phase 5 verdict was... | Do this |
|---------------------------|---------|
| VERIFIED — all PASS, proof complete | `/done` — run the pre-push checklist and push |
| PARTIALLY VERIFIED — some gaps remain | Fix the flagged gaps, then re-run `/qa quick` to verify |
| UNVERIFIED — missing proof or open items | Read the audit findings and address each one before shipping |
| Failures in the session | Fix them, re-run `/qa quick`, re-run Phase 5 automatically |
| Coverage gaps noted | Review `coverage-gaps.md` — decide which to backlog vs. address now |
| Security concern visible (auth, input, tokens) | `/security-review` — OWASP-focused review of pending changes |

**Never self-verify.** The evaluator-agent checks annotation presence, annotation placement, and post-action state. These are three distinct checks that the orchestrator cannot objectively answer about its own screenshots — it produced them.
