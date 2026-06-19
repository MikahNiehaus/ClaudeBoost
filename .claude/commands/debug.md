---
argument-hint: ["error message" | file.py:42 | --live | --static | --no-log]
description: Debug a bug — static analysis for obvious errors, live mcp-debugger step-through for runtime issues. Works with Python, .NET/ASP.NET, Go, Node.js, TypeScript, Java, and Rust. Outputs a Bug Analysis Report.
allowed-tools: Read, Write, Edit, Bash, Glob, Grep, Agent, mcp__mcp-debugger__create_debug_session, mcp__mcp-debugger__list_debug_sessions, mcp__mcp-debugger__list_supported_languages, mcp__mcp-debugger__close_debug_session, mcp__mcp-debugger__set_breakpoint, mcp__mcp-debugger__start_debugging, mcp__mcp-debugger__attach_to_process, mcp__mcp-debugger__detach_from_process, mcp__mcp-debugger__step_over, mcp__mcp-debugger__step_into, mcp__mcp-debugger__step_out, mcp__mcp-debugger__continue_execution, mcp__mcp-debugger__pause_execution, mcp__mcp-debugger__get_stack_trace, mcp__mcp-debugger__list_threads, mcp__mcp-debugger__get_scopes, mcp__mcp-debugger__get_variables, mcp__mcp-debugger__get_local_variables, mcp__mcp-debugger__evaluate_expression, mcp__mcp-debugger__get_source_context, mcp__mcp-debugger__redefine_classes
---

# /debug — Debugging Session

Arguments: **$ARGUMENTS**

One command for the full debugging loop. Give it an error message, a file:line, or just describe what's broken — it figures out whether to do static analysis or fire up mcp-debugger and step through the code live.

---

## Phase 0: Load RAG Context (MANDATORY FIRST ACTION)

**0a — Health check:**

Call `GET http://127.0.0.1:8612/status`. If it fails: stop and tell the user "RAG is not connected. Run `/rag` first."

**0b — Detect project path:**

Run `"${CLAUDEBOOST_PYTHON}" "${CLAUDEBOOST_HOME}/scripts/get-active-workspace.py"` to get the active workspace ID for this Claude instance (same source as the blue WS indicator — per-instance). The output is JSON with `workspace_id`, `workspace_path`, and `project_path`. Fall back to CWD if no workspace is active.

**0c — Load context:**

Call `POST http://127.0.0.1:8612/context` with:
```json
{
  "agent": "debug-agent",
  "task_description": "debug session: $ARGUMENTS",
  "project_path": "<PROJECT_PATH>",
  "workspace_path": "<active workspace path if one exists>"
}
```

If the context call returns an `"error"` key: stop and tell the user to run `/rag`.

---

## Phase 1: Parse Arguments and Classify Mode

Strip flags from `$ARGUMENTS`:
- `--live` present → `FORCE_LIVE = true`
- `--static` present → `FORCE_STATIC = true`
- `--no-log` present → `NO_LOG = true` (skip log file setup in Phase 2)

Remaining text after stripping flags = `TARGET`.

**Parse TARGET format:**

| Format | Example | Action |
|--------|---------|--------|
| `file.ext:NNN` | `app.py:42` | Set `TARGET_FILE = file.ext`, `TARGET_LINE = NNN` |
| `file.ext` | `OrdersController.cs` | Set `TARGET_FILE`, `TARGET_LINE = null` |
| Quoted or plain text | `"NullReferenceException in..."` | Set `ERROR_DESC = TARGET` |
| Empty | — | Ask: "What are you debugging? Paste an error message, a file:line, or describe what's broken." Wait for reply, then re-parse. |

**Classify mode:**

Set `MODE = LIVE` if any of:
- `FORCE_LIVE = true`
- TARGET or user description contains: "breakpoint", "step through", "step into", "step over", "step out", "what is the value of", "watch variable", "live debug", "attach"
- Error is intermittent: "race condition", "intermittent", "sometimes", "flaky"
- Static analysis already failed (previous session or user says "I already checked the code")

Set `MODE = STATIC` if any of:
- `FORCE_STATIC = true`
- Obvious syntax error or compile error in TARGET
- User says "why does", "explain", "review", "what's wrong with this code"
- No running process exists and the user doesn't want to start one

Default: `MODE = HYBRID` — run static analysis first, offer live step-through if static is inconclusive.

Print the classification:
```
Mode    : [STATIC / LIVE / HYBRID]
Target  : [TARGET_FILE:TARGET_LINE or ERROR_DESC]
Project : [PROJECT_PATH]
```

---

## Phase 2: Pre-flight

### 2a — RAG code search (all modes)

Run both searches in parallel — they surface different files:

```
POST http://127.0.0.1:8612/search
  scope=codebase, project_path=<PROJECT_PATH>, mode=vector, limit=8
  query="<TARGET or ERROR_DESC>"

POST http://127.0.0.1:8612/search
  scope=codebase, project_path=<PROJECT_PATH>, mode=graph, limit=8
  query="<TARGET or ERROR_DESC>"
```

If `TARGET_FILE` is set: also read it directly. Note the line range around `TARGET_LINE` (±20 lines).

Collect the top relevant files. These are the starting point for both paths.

### 2b — Language detection (LIVE and HYBRID modes)

Determine `LANGUAGE` from:
1. `TARGET_FILE` extension — `.py` → python, `.cs` / `.csproj` → dotnet, `.go` → go, `.js` / `.ts` → javascript, `.java` → java, `.rs` → rust, `.rb` → ruby
2. If no file: ask the user "What language/runtime is this?" or infer from the error message.
3. Check project root for `*.csproj`, `go.mod`, `requirements.txt`, `package.json`, `pom.xml`, `Cargo.toml` as fallback signals.

### 2c — Prerequisite check (LIVE and HYBRID modes)

Run the check for the detected language:

**Python** — no check needed. debugpy auto-installs.

**Node.js / TypeScript** — no check needed. js-debug uses the built-in V8 inspector.

**Go:**
```bash
command -v dlv
```
If not found:
```
Delve (Go debugger) is not installed. Run:
  go install github.com/go-delve/delve/cmd/dlv@latest

Then add $GOPATH/bin to PATH if not already present.
```
Set `DEBUG_ENABLED = false`, fall back to static analysis. Do not block.

**Rust:**
```bash
rustup show active-toolchain 2>/dev/null
```
- If output contains `msvc` AND user is on Windows → warn: "Your Rust toolchain is MSVC. Variable inspection for enums and complex types may be incomplete or show `<unavailable>`. For reliable debugging, switch to the GNU toolchain: `rustup default stable-x86_64-pc-windows-gnu`. This session will continue but results may be limited."
- Also run: `mcp-debugger check-rust-binary <binary-path>` if a binary path is identifiable, to verify it's debuggable.

**Java:**
Verify JDK 21+:
```bash
java -version 2>&1
```
Parse the version. If below 21: "mcp-debugger requires JDK 21+. Install from https://adoptium.net and set JAVA_HOME."

**C# / .NET:**
```bash
command -v netcoredbg
```
If not found:
```bash
ls "${NETCOREDBG_PATH}/netcoredbg.exe" 2>/dev/null
```
If neither finds it:
```
netcoredbg is not installed. Install via one of:

  Option A (dotnet global tool):
    dotnet tool install -g Samsung.Netcoredbg
    Then ensure %USERPROFILE%\.dotnet\tools is on PATH.

  Option B (manual):
    Download from https://github.com/Samsung/netcoredbg/releases
    Extract and add the folder to PATH, or set NETCOREDBG_PATH.
```
Set `DEBUG_ENABLED = false`, fall back to static. Do not block.

**.NET 10 specific check:** If netcoredbg is found, check the target runtime:
```bash
# Find the csproj and read TargetFramework
grep -r "TargetFramework" "$PROJECT_PATH" --include="*.csproj" -l 2>/dev/null | head -1
```
Read the file and check if it contains `net10.0`. If yes:
```
Warning: netcoredbg 3.1.3 has a known issue with .NET 10. Variable inspection
may return empty call stacks (error 0x80004002).

Fix: copy dbgshim.dll from your .NET 10 runtime directory into netcoredbg's folder:

  C:\Program Files\dotnet\shared\Microsoft.NETCore.App\10.x.x\dbgshim.dll
  → (paste into the netcoredbg install directory)

Continuing without the fix may produce incomplete debug sessions.
```
Do not block — let the user decide.

### 2d — Log visibility setup (LIVE and HYBRID modes, unless --no-log)

mcp-debugger does not expose app stdout/stderr as a tool call. To see log output during the session:

**Step 1 — Check for an existing log file:**

Look for common log file locations in `PROJECT_PATH`:
- `logs/`, `*.log`, `log/`, `app.log`, `debug.log`, `output.log`
- For .NET: check `appsettings.json` or `appsettings.Development.json` for `"File": { "Path": "..." }` in Serilog/NLog config

```bash
find "$PROJECT_PATH" -maxdepth 3 -name "*.log" 2>/dev/null | head -5
```

If a log file is found: set `LOG_FILE = <path>`. Print: "Log file detected: `$LOG_FILE` — will read this during the session."

**Step 2 — If no log file found:**

Offer logpoints as an alternative. Logpoints are non-breaking — they print a message at a line without pausing execution.

Print:
```
No log file found. Two options for log visibility during this session:

  A) Logpoints — set a logpoint at a specific line to print a value without stopping:
     Tell me which line and what expression to log (e.g. "log 'order.Total = {order.Total}' at line 58")
     I'll set it up as a non-breaking breakpoint that emits the message.

  B) Add a file logger — add Serilog/NLog/structlog configured to write to app.log,
     then re-run this session with --no-log skipped.

  Continuing without log visibility. Use evaluate_expression during a pause to inspect values.
```

Do NOT block on this — it's informational.

---

## Phase 3: Static Analysis

Applies when `MODE = STATIC` or as the first pass in `MODE = HYBRID`.

### 3a — Read the relevant files

For each file returned by the Phase 2a RAG search (top 5): read the file. Focus on the function or method that contains the error.

If `TARGET_FILE` is set: read it first, centered on `TARGET_LINE`.

### 3b — Systematic analysis

Apply the Five Whys to the evidence:

```
Problem:   [what the error/symptom is]
Why 1:     [immediate cause — what line or condition triggers it]
Why 2:     [what state/value causes that line to fail]
Why 3:     [what produces that state — upstream caller or data]
Why 4:     [what controls that upstream source]
Why 5:     [root cause — the design decision, missing guard, or wrong assumption]
```

Cite file:line for each step. Skip levels that don't apply — don't force five whys when three are sufficient.

### 3c — Check callers

If a function is the root cause, find all callers. This matters because the same bug often appears at every call site.

```
POST http://127.0.0.1:8612/search
  scope=codebase, project_path=<PROJECT_PATH>, mode=graph, limit=5
  query="<function name>"
```

Read each caller file. Note whether the same incorrect assumption is repeated.

### 3d — Produce static findings

Record:
- Root cause (file:line, one sentence)
- Why it wasn't caught (missing guard, missing test, wrong assumption)
- Whether the same issue appears at other call sites
- Proposed fix (before/after code)

If static analysis is conclusive → jump to Phase 5 (Report).

If static analysis is inconclusive (e.g. "the value should never be null here but somehow it is") → escalate to LIVE mode. Print: "Static analysis inconclusive — escalating to live step-through." Set `MODE = LIVE`.

---

## Phase 4: Live Debugging (mcp-debugger)

Applies when `MODE = LIVE` or when static analysis escalated.

### 4a — Detect running process

**Windows:**
```bash
tasklist /FI "IMAGENAME eq dotnet.exe" /FO CSV 2>nul
tasklist /FI "IMAGENAME eq node.exe" /FO CSV 2>nul
tasklist /FI "IMAGENAME eq python.exe" /FO CSV 2>nul
```

**macOS / Linux:**
```bash
pgrep -la dotnet 2>/dev/null
pgrep -la node 2>/dev/null
pgrep -la python3 2>/dev/null
```

Parse results into a table:
```
Running processes:
  [PID]  dotnet / dotnet.exe
  [PID]  node / node.exe
  [PID]  python / python.exe
```

- If exactly one matching process found → use it. Set `ATTACH_PID = <PID>`, `ATTACH_MODE = true`.
- If multiple matching processes → print the table and ask: "Which process should I attach to? (Enter PID)"
- If no matching process found → `ATTACH_MODE = false`. Will use `start_debugging` to launch.

### 4b — Create debug session

Call `mcp__mcp-debugger__create_debug_session`:
- `language`: detected in Phase 2b (python / javascript / typescript / go / java / dotnet / rust)
- `name`: "debug-[TARGET_FILE or slugified description]-[YYYY-MM-DD]"

Store the returned value as `SESSION_ID`.

### 4c — Attach or launch

**Attach mode** (`ATTACH_MODE = true`):

Call `mcp__mcp-debugger__attach_to_process`:
- `sessionId`: `SESSION_ID`
- `processId`: `ATTACH_PID`

- Success → print "Attached to PID `$ATTACH_PID`."
- Failure → print the error, set `DEBUG_ENABLED = false`, fall back to static analysis. Call `mcp__mcp-debugger__close_debug_session` to clean up.

**Launch mode** (`ATTACH_MODE = false`):

Ask: "No running process found. What command starts the app? (e.g. `python app.py` or `dotnet run`)"

Wait for reply. Then call `mcp__mcp-debugger__start_debugging`:
- `sessionId`: `SESSION_ID`
- `scriptPath`: the main entry point
- `args`: any arguments the user provided
- `dapLaunchArgs`: `{"stopOnEntry": false}`

- Success → print "Process launched and attached."
- Failure → print error, set `DEBUG_ENABLED = false`, close session, fall back to static.

### 4d — Set breakpoint

If `TARGET_LINE` is set: set the breakpoint immediately.

If `TARGET_LINE` is null: search for the best entry point:

```
POST http://127.0.0.1:8612/search
  scope=codebase, project_path=<PROJECT_PATH>, mode=graph, limit=3
  query="<TARGET_FILE or ERROR_DESC> entry point handler"
```

Use the top result's `line_start` as the breakpoint target.

Call `mcp__mcp-debugger__set_breakpoint`:
- `sessionId`: `SESSION_ID`
- `file`: absolute path to `TARGET_FILE` (resolve from project root)
- `line`: `TARGET_LINE` or searched line
- `condition`: omit (condition param is not reliably supported across adapters)

Print: "Breakpoint set at `$TARGET_FILE:$LINE`."

**Logpoint setup** (if user requested in Phase 2d option A):

For each logpoint the user specified, call `mcp__mcp-debugger__set_breakpoint` with the `logMessage` param instead of halting. The message is emitted to the DAP output stream without stopping execution.

### 4e — Trigger the breakpoint

Call `mcp__mcp-debugger__continue_execution` with `sessionId: SESSION_ID`.

Wait for the breakpoint to hit (up to 10 seconds for user-initiated trigger, or ask the user to perform the action that triggers the bug in the app).

Print: "Waiting for breakpoint to hit — perform the action in the app that triggers the bug."

### 4f — Inspect state (runs after breakpoint hits)

**Step 1 — Get frame ID (ALWAYS do this — never hardcode frameId:0):**

Call `mcp__mcp-debugger__get_stack_trace` with `sessionId: SESSION_ID`.

The response contains frame objects with IDs. The top frame is usually frame index 0, but its ID is assigned by the adapter. Extract the top frame's ID as `TOP_FRAME_ID`.

Print the call stack — this shows how execution got here.

**Step 2 — Get code context:**

Call `mcp__mcp-debugger__get_source_context`:
- `sessionId`: `SESSION_ID`
- `file`: `TARGET_FILE`
- `line`: breakpoint line
- `linesContext`: 10

This shows the lines around the breakpoint — useful for reading the logic without switching to Read tool.

**Step 3 — Inspect variables:**

Call `mcp__mcp-debugger__get_local_variables` with `sessionId: SESSION_ID`.

Record the key variable values. Note:
- Python: variables appear in hierarchical containers — if a variable shows `variablesReference > 0`, issue a follow-up `get_variables` call with that reference to expand it.
- JavaScript: may have paused at an internal frame — if locals look wrong, step forward once and re-inspect.
- Java: `redefine_classes` is available for hot-swap without restarting (call with classesDir after editing a file).

**Step 4 — Step through the logic:**

Call `mcp__mcp-debugger__step_over` to advance one line at a time. After each step:
1. Note which branch was taken (if/else, try/catch)
2. Call `mcp__mcp-debugger__get_local_variables` to track how values change
3. Compare against what the code *should* be doing

Use `mcp__mcp-debugger__step_into` when you need to enter a called function.
Use `mcp__mcp-debugger__step_out` to return to the caller.

**Step 5 — Evaluate expressions:**

Use `mcp__mcp-debugger__evaluate_expression` to test hypotheses:
- `sessionId`: `SESSION_ID`
- `expression`: any valid expression in the language (e.g. `order.Items.Count`, `user?.Email ?? "null"`)
- `frameId`: `TOP_FRAME_ID` (always pass this — avoids adapter auto-detect ambiguity)

This is the main tool for answering "what is the value of X at this point."

**Step 6 — Read the log file (if LOG_FILE is set):**

After each significant step, call the `Read` tool on `LOG_FILE` to check what was written since the last pause. This gives you the log context around the breakpoint.

### 4g — Multi-breakpoint iteration

If the first breakpoint reveals the problem is upstream, set a new breakpoint at the caller:

1. Use the call stack from get_stack_trace to find the caller line
2. Call `mcp__mcp-debugger__continue_execution` to resume past the current breakpoint
3. Set the new breakpoint at the caller location
4. Trigger the code path again

Repeat until the root cause is isolated.

### 4h — Close session

Always call `mcp__mcp-debugger__close_debug_session` with `sessionId: SESSION_ID` when the investigation is complete.

Print: "Debug session closed."

---

## Phase 5: Bug Analysis Report

Write `$WORKSPACE_ABS/debug-report-[YYYY-MM-DD].md` (if a workspace exists) or print inline if no workspace.

```markdown
## Bug Analysis Report

### Status: [COMPLETE / BLOCKED / NEEDS_INPUT]

### Problem Statement
- **Symptom**: [What the user observed]
- **Reproducibility**: [Always / Sometimes / Race condition]
- **Target**: [file:line or description]
- **Mode used**: [Static / Live / Hybrid]

### Investigation

#### Evidence Gathered
1. [file:line — what this tells us]
2. [variable value at breakpoint — what this confirms]
(cite every claim)

#### Hypotheses Tested
| Hypothesis | How tested | Result |
|------------|-----------|--------|
| [H1] | [Static read / breakpoint inspection] | [Confirmed / Ruled out] |

### Root Cause

**The actual cause**: [one clear sentence]
**Why it happened**: [what condition, assumption, or missing guard allowed it]
**Why it wasn't caught**: [missing test, wrong assumption, edge case not considered]

### Recommended Fix

```[language]
// Before (buggy)
[relevant code]

// After (fixed)
[corrected code]
```

**Why this fixes it**: [connection to root cause]

### Other Locations

[If the same issue appears at other call sites — list file:line for each. These must also be fixed.]

### Prevention

- [ ] Regression test: [describe a test that would have caught this bug]
- [ ] Review focus: [what to watch for in similar code going forward]

### Debug Evidence

[If live mode was used]
- Breakpoint: `[file:line]`
- Key variable values: `[name = value]` at line [N]
- Branch taken: [which if/else path executed]
- Log output during session: [summary if LOG_FILE was read]
```

---

## Phase 5b: Next Step Suggestion

After printing the report, suggest one of:

- Root cause found, fix is clear: "Consider running `/qa --code` to verify the fix doesn't introduce regressions, then spawn `test-agent` to write a regression test for this bug."
- Root cause is an architectural issue: "Consider spawning `architect-agent` — this reveals a design issue that goes beyond a one-line fix."
- Fix was complex with several changed files: "Consider running `/review` to check the fix before merging."
- Session was BLOCKED (can't reproduce, missing data): "To unblock: [specific thing needed — production logs, a specific test account, etc.]"

---

## What's Next After /debug

| If the session... | Run |
|-------------------|-----|
| Found root cause — fix is clear | `/qa --code` to verify the fix, then `spawn test-agent` for regression coverage |
| Bug reveals a design problem | `spawn architect-agent` — deeper structural fix may be needed |
| Fix looks risky or touches many files | `/review` before merging |
| Couldn't reproduce — needs more data | Check logs or add a logpoint: `/debug --live file.ext:LINE` |
| Fixed and verified | `/done` — pre-push checklist and push |
