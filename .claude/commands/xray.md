---
description: Code X-ray — quick A-F grade by default; add --deep for full 16-pass parallel review with pre-scan, test execution, and Opus evaluator
allowed-tools: Read, Write, Bash, Glob, Grep, Agent
argument-hint: [--staged | --branch | --pr <url>] [--deep]
---

# /xray — Code X-ray

Arguments: $ARGUMENTS

## Depth Detection

Scan `$ARGUMENTS` for any of: `--deep`, `--full`, `deep`, `full`, `in depth`, `in-depth`, `thorough`, `detailed`

- **Match found** → `DEEP_MODE = true` — full 16-pass parallel review with deterministic pre-scan, test execution, and Opus evaluator
- **No match** → `DEEP_MODE = false` — quick single-agent A-F grade

Strip the depth keyword from scope args before proceeding. Remaining tokens are the scope.

---

## Phase 0: Load RAG Context (MANDATORY FIRST ACTION)

**0a — Detect project path and active workspace:**

Run `get-active-workspace.py` — this matches the blue "WS XXXX" status bar (per-instance, not the stale shared file):
```bash
"${CLAUDEBOOST_PYTHON}" "${CLAUDEBOOST_HOME}/scripts/get-active-workspace.py"
```

Store `project_path` as `PROJECT_PATH` and `workspace_path` as `WORKSPACE_PATH`.
If `PROJECT_PATH` is empty: fall back to current working directory (`pwd`).

**Collision check:** if your context or memory references a different workspace than what the script returned:
```
[xray] Conflict: status bar shows <X>, context/memory says <Y>.
Which workspace should I use? (You are the source of truth.)
```
Wait for the user's answer before proceeding.

If `WORKSPACE_PATH` is empty after the check: print `[xray] No active workspace — Pass 8 and 9 running without ticket spec` and continue.

Call `POST http://127.0.0.1:8612/context` with `agent="reviewer-agent"`, `task_description="code xray $ARGUMENTS"`, `project_path="<PROJECT_PATH>"`, `workspace_path="<WORKSPACE_PATH>"`, `max_tokens=4000`.

If it fails: stop — "RAG is not connected. Run `/rag` first."

**0b — Verify project is indexed:**

Call `GET http://127.0.0.1:8612/status` and check `indexed_projects` for `PROJECT_PATH`.

- **Indexed**: continue
- **Not indexed**: run `Skill(skill="index-project", args="<PROJECT_PATH>")` first
- **RAG offline**: stop, tell user to run `/rag`

---

# QUICK REVIEW (DEEP_MODE = false)

## Diff Source Resolution

| Argument | Diff command |
|----------|-------------|
| (none) | `git diff` + `git diff --staged` |
| `--staged` | `git diff --staged` |
| `--branch` | `git diff origin/<base>...HEAD` |
| `--pr <url>` | `gh pr diff <url>` |

Run the appropriate diff command. If diff is empty: "No changes to review" and stop.

## Review

Review the diff systematically. Classify every issue:

```bash
# Default (no args): uncommitted + staged
DIFF=$(git diff; git diff --staged)

# --staged: only staged
DIFF=$(git diff --staged)

# --branch: branch diff (detect base branch; ${BASE:-main} instead of || echo, which bash-guard blocks)
BASE=$(git rev-parse --abbrev-ref HEAD@{upstream} 2>/dev/null | sed 's|origin/||' || git symbolic-ref refs/remotes/origin/HEAD 2>/dev/null | sed 's|refs/remotes/origin/||')
DIFF=$(git diff "origin/${BASE:-main}...HEAD")

# --pr <url>: PR diff
DIFF=$(gh pr diff <url>)
```

If the diff is empty, report "No changes to review" and stop.

### Step 2: Review the diff

Review the diff systematically. For each issue found, classify by severity:

**CRITICAL** - Must fix before merge:
- Security vulnerabilities (injection, auth bypass, secrets in code)
- Data loss risks (missing transactions, unsafe deletes)
- Correctness bugs (race conditions, nil dereference, logic errors)

**MAJOR** — should fix before merge:
- Logic errors that may not crash but produce wrong results
- Missing error handling on external calls
- API contract violations
- Missing tests for critical paths

**MINOR** — nice to fix:
- Style inconsistencies with surrounding code
- Unclear naming
- Missing comments on non-obvious logic
- Minor code smells

For each issue: file:line, severity, description, suggested fix.

## Grade

| Grade | Criteria | Verdict |
|-------|----------|---------|
| **A** | No issues at all | PASS |
| **B** | MINOR issues only | PASS |
| **C** | MAJOR issues, no CRITICAL | FAIL |
| **D** | CRITICAL issues present | FAIL |
| **F** | Unreviewable | SKIP |

## Output

```
Grade: <A|B|C|D|F>

CRITICAL (<count>)
  <file>:<line> — <description>
    Fix: <actionable fix>

MAJOR (<count>)
  <file>:<line> — <description>
    Fix: <actionable fix>

MINOR (<count>)
  <file>:<line> — <description>
    Fix: <actionable fix>

Summary: N CRITICAL, N MAJOR, N MINOR
Verdict: PASS | FAIL | SKIP
```

Omit empty severity sections. If Grade A:
```
Grade: A
No issues found.
Verdict: PASS
```

## Evidence Verification

Spawn a single `evaluator-agent`:

"Verify the review output: (1) every CRITICAL and MAJOR cites a specific file:line, (2) Grade is consistent with issue counts, (3) Verdict matches Grade. Output a table: Claim | Evidence? | CONFIRMED/NEEDS_EVIDENCE. Under 500 tokens."

Surface any NEEDS_EVIDENCE items alongside the grade.

## Escalation Offer

After delivering the grade, always end with:

> "Quick review done. Reply **deep** to run the full 16-pass X-ray with deterministic pre-scan, test execution, and Opus evaluator."

## Post-Review: Escalation Handling

If the user replies with any of: `deep`, `in depth`, `full`, `go deep`, `more detail`, `thorough`, `--deep` — and a quick review was just completed — immediately run the **DEEP REVIEW** section below using the same scope.

---

# DEEP REVIEW (DEEP_MODE = true)

## Phase 1: Understand the Diff

**1a — Parse arguments into FEATURE_BRANCH, BASE_BRANCH, REPO_PATH.**

**Sprint normalization:** `sprint 45`, `Sprint45`, `sprint-45` → `Sprint-45`

**Two-branch syntax:**
- `<feature> diff <base>` / `<feature> from <base>` / `<base> diff <feature>` → obvious pairing
- `<branch> sprint <N>` → feature=branch, base=Sprint-N

**Single branch:** use as FEATURE_BRANCH, BASE_BRANCH = current HEAD

**Standard scopes:** `staged`, `last N commits`, `HEAD~N`, file paths — handle as-is

**No scope / vague scope:** gather state and ask:

```bash
git -C "<REPO_PATH>" status --short
git -C "<REPO_PATH>" diff --stat HEAD
git -C "<REPO_PATH>" diff --staged --stat
git -C "<REPO_PATH>" log --oneline -10
```

Present summary and ask what to review. Wait for answer before proceeding.

**1b — Find the repo containing the branch.**

Start with `pwd`. If branch not found, scan sibling repos under the parent of the git root. If still not found: tell user and stop.

**1c — Get stat and full diff:**

```bash
git -C "<REPO_PATH>" diff <DIFF_SPEC> --stat
git -C "<REPO_PATH>" diff <DIFF_SPEC>
```

Store as `REVIEW_DIFF`. Do NOT truncate.

**RAG pattern search:**

Summarize what changed in one sentence. Then:
```
POST http://127.0.0.1:8612/search scope="codebase", project_path=<cwd>, query="<summary>", limit=5
POST http://127.0.0.1:8612/search scope="codebase", project_path=<cwd>, query="<summary>", mode="graph", limit=5
```

Both calls are mandatory — vector finds semantic matches, graph finds structural neighbours.

**1d — Ticket context:**

Check for ticket in: `$ARGUMENTS`, recent git log, `workspace/*/ticket.md`.

If found, extract and print before proceeding:
```
TICKET CONTEXT EXTRACTED:
  TICKET_ARTIFACT_TYPE      : <endpoint|page|service|component|...>
  TICKET_ACCEPTANCE_CRITERIA:
    - AC1: ...
  TICKET_ROUTING_OR_PATTERN : <any routing/pattern constraints>
```

If not found, print the "no ticket found" version with inferred intent from commits.

**1e:** "Found N files changed (+M/-K lines). Analyzing for pass selection..."

---

## Phase 2: Pass Selection

**Always run (NEVER SKIP):** Pass 8 (Ticket Alignment), Pass 13 (Banned Dependencies), Pass 14 (Test Coverage & Logging), Pass 15b (Async Pattern Audit)

**Run when applicable:**
- Pass 14b (Template Rendering Security): run if diff contains ANY `.cshtml`, `.razor`, `.html`, `.j2`, `.hbs`, or `.ejs` file

**Skip only when clearly inapplicable:**
- Pass 10 (Smoke Test): skip if pure backend/config with no UI
- Pass 11 (Migration/Schema): skip if zero model/migration files in diff
- Pass 12 (Platform Footguns): skip if purely algorithmic logic

**Never skip passes 1-7, 9.**

List selections before spawning:
```
Running: 1, 2, 3, 4, 5, 6, 7, 8, 9, [10-12 conditional], 13, 14, [14b if templates], 15b
Evaluator: Phase 4 (always last, always Opus — not a numbered pass)
Skipping: [X — reason]
Pre-scan flags: [results from Phase 2b below]
```

---

## Phase 2b: Deterministic Pre-Scan (runs before any agent spawns)

Before spawning pass agents, run these deterministic grep checks against `REVIEW_DIFF` or the actual changed files. They cost nothing and feed hard evidence into the relevant passes.

**Pre-scan 1 — Closure-scoped timers:**
Search the diff for `setTimeout` or `setInterval` inside a function that can be called more than once. Specifically look for:
- `const\s+\w+\s*=\s*set(Timeout|Interval)` inside a function body (not module scope)
- Same variable used without `clearTimeout`/`clearInterval` before the next `set*` call

```bash
# Extract added lines from diff and grep
grep "^+" "$DIFF_FILE" | grep -E "(const|let)\s+\w+\s*=\s*set(Timeout|Interval)"
```

Flag: if found AND no matching `clear(Timeout|Interval)` call on same variable in the function → `PRE_SCAN: CLOSURE_TIMER_BUG` (feeds into Pass 15b as evidence)

**Pre-scan 2 — addEventListener inside re-callable function:**
```bash
grep "^+" "$DIFF_FILE" | grep -E "addEventListener\s*\("
```
Flag: if `addEventListener` appears inside a named function (not a module-level setup block) → `PRE_SCAN: DUPLICATE_LISTENER_RISK` (feeds into Pass 15b as WARNING)

**Pre-scan 3 — Template secret rendering:**
```bash
grep "^+" "$DIFF_FILE" | grep -E "(@Json\.Serialize|@Html\.Raw|@ViewBag\.|@ViewData\[)" 
```
Flag: if found inside a `<script>` block context → `PRE_SCAN: TEMPLATE_RENDER_IN_SCRIPT` (feeds into Pass 14b as evidence)

**Pre-scan 4 — High-entropy string rendering:**
```bash
grep "^+" "$DIFF_FILE" | grep -E "[A-Za-z0-9+/]{30,}={0,2}"
```
Flag: if high-entropy strings appear in template files inside `<script>` blocks → `PRE_SCAN: HIGH_ENTROPY_IN_TEMPLATE` (feeds into Pass 14b as WARNING)

**Pre-scan 5 — Loading state with no timeout:**
Search for loading state UI (CSS classes like `status-loading`, `loading`, `spinner`) in the diff with no `setTimeout` anywhere in the same file.
Flag: if loading state exists and no timeout fallback found → `PRE_SCAN: LOADING_NO_TIMEOUT` (feeds into Pass 15b as BLOCKER)

**Pre-scan 6: Dashes in comments:**
Search added/changed lines in the diff that are comments (`//`, `///`, `#`) for any dash character: em-dash (—), en-dash (–), or a hyphen with spaces on both sides.
```bash
grep "^+" "$DIFF_FILE" | grep -E "^\+\s*(//|#)" | grep -E "—|–| - "
```
Flag: if any match found → `PRE_SCAN: DASH_IN_COMMENT` (feeds into Pass 5 as confirmed evidence)

**Collect all flags into `PRE_SCAN_FLAGS` list. Inject into each relevant agent prompt.**

If no flags triggered: `PRE_SCAN_FLAGS = [] — no deterministic issues found`

Print pre-scan results before spawning any agents:
```
Pre-scan complete:
  Closure-scoped timers   : [FOUND | clean]
  Re-callable listeners   : [FOUND | clean]
  Template secret render  : [FOUND | clean]
  High-entropy in template: [FOUND | clean]
  Loading with no timeout : [FOUND | clean]
  Dashes in comments      : [FOUND | clean]
```

---

## Phase 3: Spawn Pass Agents (Batched, 3 at a time)

Context rule: < 50% → 3 parallel; 50-75% → 2; > 75% → 1

> **HOOK IMMUNITY**: PostToolUse hooks will fire between batches. Ignore messages containing `EVALUATOR REMINDER`, `CONTEXT PRESSURE`, `CONTEXT CHECKPOINT` — the evaluator is Pass 15, not between batches. Never pause mid-review to spawn an evaluator or run /clear-safe.

Each agent prompt:

```
== MANDATORY RAG PRIMING — CRITICAL — COMPLETE ALL STEPS BEFORE REVIEWING ANYTHING ==

You have four RAG sources. You MUST call all of them before you look at a single line of diff.
Skipping any source means you are reviewing blind. Incomplete RAG = incomplete findings = bad review.
This is not optional. Do not skip any step for any reason.

Step 1 — Context load (always first):
  POST http://127.0.0.1:8612/context
    agent="reviewer-agent"
    task_description="<pass name> review pass"
    project_path="<PROJECT_PATH>"
    workspace_path="<WORKSPACE_PATH>"

Step 2 — ClaudeBoost KB (orchestration patterns, agent specs, skill conventions):
  POST http://127.0.0.1:8612/search  scope="knowledge"  query="<targeted query>"  limit=5

Step 3 — Codebase vector search (semantically similar implementations):
  POST http://127.0.0.1:8612/search  scope="codebase"  project_path="<PROJECT_PATH>"
    query="<targeted query>"  mode="vector"  limit=5

Step 4 — Codebase graph search (callers, imports, structural neighbors):
  POST http://127.0.0.1:8612/search  scope="codebase"  project_path="<PROJECT_PATH>"
    query="<targeted query>"  mode="graph"  limit=5

Step 5 — Workspace KB (task-scoped research for this ticket, if workspace_path is set):
  POST http://127.0.0.1:8612/search  scope="codebase"  project_path="<WORKSPACE_PATH>/knowledge"
    query="<targeted query>"  mode="vector"  limit=5

Vector and graph return different files. Running only one will miss findings. All five steps
are required every time. There are no exceptions.

== END RAG PRIMING — NOW YOU MAY REVIEW THE DIFF ==

Review ONLY the diff below for your assigned pass. Exception: if you are about to flag something as MISSING (missing row, missing emit, missing field, missing record) you MUST read the full enclosing method in the actual file — not just the diff — before raising the finding. Pre-existing code above or below the changed lines may already handle what appears absent from the diff.

== DIFF ==
<REVIEW_DIFF verbatim>
== END DIFF ==

== YOUR PASS ==
<pass definition>
== END PASS ==

<if ticket exists>
== TICKET ==
<ticket content>
== END TICKET ==

== PRE-SCAN FLAGS ==
<PRE_SCAN_FLAGS — list any flags relevant to your pass; treat flagged patterns as confirmed starting points, not hypotheses>
== END PRE-SCAN FLAGS ==

Output JSON only:
{
  "pass": <id>,
  "name": "<name>",
  "findings": [{"severity":"BLOCKER|WARNING|NIT","location":"file:line","description":"...","suggestion":"..."}]
}
If no issues: {"pass": <id>, "name": "<name>", "findings": []}
```

### Pass Definitions

**Pass 1 — Simplicity**
Can this be deleted, inlined, or simplified? Prefer derived values over refs. Minimize state variables and coordination points. Flag any N×M sync complexity.

**Pass 2 — Already-Exists**
Did you add something the codebase or a dependency already provides? Verify existing things actually meet the requirement before reusing.

**Pass 3 — Dead Code**
For every variable/param/function: is it actually referenced end-to-end? Check orphaned imports. Use `POST /search mode=graph` to verify external consumers.

**Pass 4 — Debug Cleanup** | USE_GRAPH: yes
Any temporary logs, toasts, flags, debug UI, commented blocks, or test-only handlers left in?

**Pass 5 — Project Patterns** | USE_GRAPH: yes
How does this repo usually solve this problem? Match naming, file placement, error handling, data flow, testing style. Don't introduce a parallel mechanism when the codebase has an established one.

Also check every new or changed comment in the diff (`//`, `///`, block comments). Flag as WARNING if any comment contains a dash of any kind: em-dash (—), en-dash (–), or spaced hyphen ( - ). This rule applies even when a dash would be grammatically correct. Also flag comments that are overly formal, verbose, or unprofessional in tone. Use the exact comment text as evidence. Check PRE_SCAN_FLAGS for `DASH_IN_COMMENT` as a confirmed starting point.

**Pass 6 — Common-Pattern Breaker** | USE_GRAPH: yes
Are you breaking a shared convention? Count how many files solve similar problems differently — if all of them do it differently, this approach is the outlier.

**Pass 7 — Fresh Eyes**
Read every line like you didn't write it. If a new team member needs to mentally simulate event ordering to understand behavior, flag it.

**Pass 8 — Ticket Alignment (NEVER SKIP)**
Does this implement exactly what the ticket asks — no more, no less?
- Artifact type check: if ticket says "endpoint", verify it's a controller action, not a Razor page.
- Prerequisites check: verify infrastructure for the pattern exists.
- AC check: each AC item one-by-one against the diff. Missing = BLOCKER.
- Flag scope creep. Flag missing items.

Pass 8 output MUST include:
```json
{"pass":8,"name":"Ticket Alignment","artifact_type_checked":true,"artifact_type_match":true,"prerequisites_verified":true,"findings":[]}
```
Missing `artifact_type_checked` → Evaluator flags as INCOMPLETE. `artifact_type_match: false` → auto-BLOCKER.

**Pass 9 — Spec Precision** | USE_GRAPH: yes
Did you match ticket wording exactly? "multi select" means multiple values selectable. "alphabetical" means verified sort. No silent reinterpretation. For any user-facing string rename: grep for the old value and list every unupdated occurrence.

**Pass 10 — Manual Smoke Test** (skip if no UI)
Was this actually used in a browser for each AC scenario? If not, flag as WARNING.

**Pass 11 — Migration/Schema** (skip if no model changes)
Every model property add/remove must have a matching migration. Verify the migration does what you expect.

**Pass 12 — Platform Footguns** (skip if pure logic)
Any API, property, or pattern that is a documented platform gotcha? Scroll containers, N+1 queries, lazy loading in serialization, CSS overflow/position:fixed, etc.

**Pass 13 — Banned Dependencies (NEVER SKIP)**
Importing anything banned? Check CLAUDE.md and coding-standards.
Grep for jQuery: `$(`, `jQuery`, `import.*jquery`, `require.*jquery`. **jQuery is BANNED.**

**Pass 14 — Test Coverage & Logging** (skip only for pure docs/config/comments)
*Tests:* new functions/classes need test coverage. Changed behaviour needs regression test. Flag missing tests as WARNING (BLOCKER for auth/payments/data integrity).
*Logging:* every `catch` block must call `logger.error` (BLOCKER if missing). No sensitive data in logs (BLOCKER). Service methods and external calls should have INFO logging (WARNING if missing).

**Pass 14b — Template Rendering Security** (skip if zero template files in diff)
Scan every `.cshtml`, `.razor`, `.html`, `.j2`, `.hbs`, and `.ejs` file in the diff. For any server-rendered expression (`@Json.Serialize()`, `@Html.Raw()`, `@ViewBag.*`, `@ViewData[]`, `{{variable}}`, `<%= ... %>`) that appears inside a `<script>` block or inline event handler:

- **User display data only** (name, email, role label): acceptable — no finding
- **Config values, feature flags, app settings**: WARNING — prefer server-side conditional rendering, not JS config injection
- **JWT or auth tokens rendered for a display SDK** (e.g. Tableau Embedding API, embedded analytics): WARNING — requires a sign-off comment explaining why the token must be in the page
- **Secrets, credentials, connection strings, API keys, private keys**: BLOCKER — never render server-side secrets into page output
- **High-entropy strings (20+ chars, base64-ish, or hex)**: WARNING — verify this is not a credential

Check PRE_SCAN_FLAGS for `TEMPLATE_RENDER_IN_SCRIPT` and `HIGH_ENTROPY_IN_TEMPLATE` — if flagged, treat as confirmed starting points for this pass.

Pass 14b output MUST include:
```json
{"pass":"14b","name":"Template Rendering Security","template_files_scanned":["file1.cshtml"],"findings":[]}
```

**Pass 15b — Async Pattern Audit (NEVER SKIP)**
Find patterns where async state can get stuck or corrupt across multiple calls. Check the diff for all of these:

1. **Closure-scoped timer leak**: `const` or `let` timer variable declared inside a function body that can be called more than once. If a second call fires before the timeout, the first timer runs against stale state and there is no way to cancel it. Severity: BLOCKER.
   - Pattern: `const \w+ = setTimeout(...)` or `let \w+ = setTimeout(...)` inside a function, not at module scope
   - Fix: hoist the timer variable to module/component scope and call `clearTimeout` at the start of each invocation

2. **Missing cancel pair**: `setTimeout` or `setInterval` call with no corresponding `clearTimeout`/`clearInterval` on the same variable within the same function or component lifecycle. Severity: BLOCKER.

3. **Loading state with no exit**: A UI loading state (spinner, "Loading..." text, progress indicator) that has no guaranteed exit path. If the async operation never resolves (CDN blocked, network hang, event never fires), the user sees a permanent loading state with no feedback. Severity: BLOCKER.
   - Check: if loading state set in a function, confirm there is a `setTimeout` fallback AND that it is reachable even when the primary async event never fires
   - Check: verify timeout variable is cleared before being reset (to prevent stale timeout firing after a successful reload)

4. **Re-callable function with addEventListener**: An event listener attached inside a function that can be called multiple times. Each call attaches another listener; listeners accumulate and fire N times per event. Severity: WARNING.
   - Pattern: `element.addEventListener(...)` inside a named function that is called as part of a load/init flow
   - Fix: attach listeners once at setup time, or call `removeEventListener` before re-attaching

Check PRE_SCAN_FLAGS for `CLOSURE_TIMER_BUG`, `DUPLICATE_LISTENER_RISK`, and `LOADING_NO_TIMEOUT` — if flagged, treat as confirmed starting points and cite the exact diff line.

Pass 15b output MUST include:
```json
{"pass":"15b","name":"Async Pattern Audit","async_audit_complete":true,"findings":[]}
```
Missing `async_audit_complete` → Evaluator flags pass as INCOMPLETE.

---

## Phase 3b: Test Execution (Orchestrator — not an agent)

**Step 0 — Build check (.NET only):**
```bash
ls "<REPO_PATH>"/*.sln "<REPO_PATH>"/**/*.csproj 2>/dev/null | head -1
```
If found: `dotnet build "<REPO_PATH>/<solution>.sln" --no-restore -v quiet`. Build errors = automatic BLOCKER.

**Step 1 — Detect test framework:**
Check for `.sln`, `package.json` (jest/vitest/mocha), `pytest.ini`/`pyproject.toml`, `Makefile`.

**Step 2 — Find test files for changed code.** Derive likely test paths from diff filenames.

**Step 3 — Run tests** (targeted run for changed files; full suite for shared utilities). 120s timeout.

**Step 4 — Record TEST_RESULTS:**
```
TEST_RESULTS:
  Framework: <name>
  Tests run / Passed / Failed / Skipped: N/N/N/N
  Failures: <test name: error message>
  Command: <exact command>
  Exit code: <0|non-zero>
```
Test failures = automatic BLOCKERs.

---

## Phase 3c: Citation Consolidation (Orchestrator — not an agent)

Scan all pass outputs. For every BLOCKER or WARNING with a `location` field, build:
```
FINDINGS_CITATIONS:
  Pass N — path/to/file.ext:line — description (one line)
  ...
```
Deduplicate same-location findings. Keep BLOCKERs first, cap at 20 entries. If no citations: note "No file:line citations — treat as NITs unless clearly structural."

---

## Phase 4: Evaluator — Pass 15 (Always Runs, Always Last, Opus)

Spawn one Opus evaluator after ALL batches and Phase 3b complete. Do NOT proceed to Phase 5 without it.

```
Your FIRST two actions:
1. Call POST http://127.0.0.1:8612/context with agent="evaluator-agent", task_description="evaluator pass — classify review findings", project_path="<PROJECT_PATH>", workspace_path="<WORKSPACE_PATH>"
2. For each unique BLOCKER in FINDINGS_CITATIONS: call POST http://127.0.0.1:8612/search scope="codebase", project_path="<PROJECT_PATH>", query="<symbol from finding>", mode="graph", limit=3 to verify it exists and isn't already handled elsewhere.

You are the Evaluator. You do NOT re-review the code — you review the FINDINGS and TEST RESULTS.

== FINDINGS_CITATIONS ==
<FINDINGS_CITATIONS verbatim>
== END FINDINGS_CITATIONS ==

== ALL FINDINGS ==
<JSON from every pass agent>
== END FINDINGS ==

== TEST RESULTS ==
<TEST_RESULTS or "No test framework detected">
== END TEST RESULTS ==

Rules:
1. Test FAILURE = automatic BLOCKER — do not downgrade.
2. Findings without specific evidence (exact quote, file:line) = FALSE POSITIVE.
3. Multiple findings about the same issue count as one.
4. Every BLOCKER/WARNING must have file:line and a concrete fix. If not: downgrade to NIT or FALSE POSITIVE.
5. Use FINDINGS_CITATIONS as your work queue. Read each cited file:line to confirm the issue exists. For any BLOCKER claiming something is MISSING (missing row, missing emit, missing field, missing record) — read the full enclosing method from its opening brace, not just the cited line. A row that looks absent from the emission block may be present via a write path in pre-existing code above it that was not in the diff. Confirm or discard based on the full data flow.
6. Pass 8 without `artifact_type_checked` field = INCOMPLETE — flag it.
7. Pass 14b without `template_files_scanned` field = INCOMPLETE — flag it.
8. Pass 15b without `async_audit_complete` field = INCOMPLETE — flag it.

Output:
**Grade: A/B/C/D/F** (A=no blockers/warnings, B=warnings/nits only, C=meaningful warnings, D=1-2 blockers, F=3+ blockers or test failures)
**BLOCKERS** (file:line, description, fix)
**WARNINGS**
**NITS**
**FALSE POSITIVES** (with explanation)
**TEST RESULTS SUMMARY**
**INCOMPLETE PASSES** (passes missing required output fields)
```

---

## Phase 5: Report

Gate: confirm evaluator returned a result. If not, spawn it now.

Output the full evaluator report. Lead with grade → blockers → warnings → nits → test summary.

Final message:
> "X-ray complete. Grade: **[X]**. [N blocker(s), M warning(s), K nit(s)]. Tests: [N passed / N failed / not run]. [C or better: ready to merge after warnings addressed. D/F or test failures: fix blockers first.]"

---

## Post-Review Interaction

**If the user asks whether a finding is legitimate:**
Only the evaluator (Phase 4) is authorized to answer. If it has run: quote its verdict. If it hasn't: spawn it first. Never self-verify.

**If the user asks for fixes:**
Only recommend fixes the evaluator classified as BLOCKER or WARNING.

**If the user replies with escalation keywords** (deep, in depth, full, more detail, thorough) **after a QUICK review:**
Run DEEP REVIEW immediately using the same scope. Do not ask for confirmation.
