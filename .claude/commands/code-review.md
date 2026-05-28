---
argument-hint: [scope — "staged", "last 2 commits", branch name, file path, PR #]
description: 15-pass parallel code review — simplicity, patterns, ticket alignment, test execution, evaluator
allowed-tools: Read, Write, Bash, Glob, Grep, Agent
---

# /code-review — 15-Pass Parallel Code Review

Run 14 independent review passes as batched parallel agents, then a final Evaluator (pass 15) that classifies every finding. Orchestrator understands the diff with RAG before spawning anything — no blind agent launches.

Scope: **$ARGUMENTS**

---

## Phase 0: Load Knowledge + Index Project

**0a — ClaudeBoost RAG context** (do this FIRST, before any git commands):

Call `rag_context(agent="reviewer-agent", task_description="code review $ARGUMENTS", max_tokens=4000)`.

This loads coding-standards, security, scope-governance guardrails. Read the result — it primes your knowledge for pass selection.

**0b — Project RAG index** (ensure codebase search works):

Wait until Phase 1b resolves `REPO_PATH`, then call `rag_index_project(project_path=<REPO_PATH>)`. Report: "X files updated."

---

## Phase 1: Understand the Diff

**1a — Parse arguments into FEATURE_BRANCH, BASE_BRANCH, REPO_PATH.**

Parse `$ARGUMENTS` using these rules in order:

**Sprint normalization** — convert any of these to a branch name:
- `sprint 45`, `Sprint45`, `sprint-45` → `Sprint-45`
- `sprint 45 diff fix/ASC-1175-benassist-bottom-sheet` → BASE=`Sprint-45`, FEATURE=`fix/ASC-1175-benassist-bottom-sheet`

**Two-branch syntax** — any of these mean "diff FEATURE from BASE":
- `<feature-branch> diff <base-branch>`
- `<feature-branch> from <base-branch>`
- `<base-branch> diff <feature-branch>` (sprint first = sprint is base)
- `<branch> sprint <N>` → feature=branch, base=Sprint-N

**Single branch** — one branch name, no base:
- Use it as FEATURE_BRANCH, BASE_BRANCH = current branch (`git rev-parse --abbrev-ref HEAD`)

**Standard scopes** (no branch names detected):
- `staged`, `last N commits`, `HEAD~N`, `A..B`, file paths — handle as before (BASE=current HEAD)

**Vague or no scope** — the user described what they want without specifying a git expression. In this case, do NOT default silently to HEAD~1. Instead: gather state, show it, and ask.

Run this to understand local state:
```bash
git -C "<REPO_PATH>" status --short
git -C "<REPO_PATH>" diff --stat HEAD
git -C "<REPO_PATH>" diff --staged --stat
git -C "<REPO_PATH>" log --oneline -10
```

Present a summary:
```
I see:
  Staged:    N files (+X/-Y lines)
  Unstaged:  N files (+X/-Y lines)
  Unpushed commits (vs origin): N commits
    - abc1234 commit message
    - def5678 commit message

What do you want reviewed?
  1. Staged changes only
  2. All uncommitted changes (staged + unstaged)
  3. Last N commits
  4. A specific commit range or file
  (Or describe what you changed)
```

Wait for the user's answer before proceeding.

After parsing: set `FEATURE_BRANCH`, `BASE_BRANCH`, `DIFF_SPEC` (= `BASE_BRANCH...FEATURE_BRANCH` for two-branch; appropriate git expression for others).

**1b — Find the repo containing the branch.**

Use `pwd` as the starting REPO_PATH. Try:
```bash
git -C "<pwd>" branch -a | grep -F "<FEATURE_BRANCH>"
```

If not found in cwd, derive the projects root dynamically and scan sibling repos:
```bash
# Parent of the current git root = the projects directory
GIT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
DEV_DIR=$(dirname "$GIT_ROOT")

for d in "$DEV_DIR"/*/; do
  git -C "$d" branch -a 2>/dev/null | grep -qF "<FEATURE_BRANCH>" && echo "$d" && break
done
```

If still not found, try one level deeper (grandchildren of `$DEV_DIR`):
```bash
for d in "$DEV_DIR"/*/*/; do
  git -C "$d" branch -a 2>/dev/null | grep -qF "<FEATURE_BRANCH>" && echo "$d" && break
done
```

Once found: set `REPO_PATH` to that directory. Announce: "Found branch in `<REPO_PATH>`."

If not found anywhere: tell the user "Branch `<FEATURE_BRANCH>` not found — check the branch name or repo path" and STOP.

**1c — Get stat and full diff:**

```bash
git -C "<REPO_PATH>" diff <DIFF_SPEC> --stat
git -C "<REPO_PATH>" diff <DIFF_SPEC>
```

Use `...` (three dots) for branch-vs-branch diffs — this shows only commits unique to FEATURE_BRANCH since it diverged from BASE_BRANCH, not every difference between the two tips.

If stat returns nothing: "No changes between `<BASE_BRANCH>` and `<FEATURE_BRANCH>`" and STOP.

Store the full diff as **REVIEW_DIFF**. Do NOT truncate it.

**1c — RAG-powered pattern search** (understand what changed before spawning):

Summarize what changed in one sentence. Then:

```
rag_search(scope="codebase", project_path=<cwd>, query="<your one-sentence summary>", limit=5)
```

If the changes touch multiple interconnected files (e.g., a service + its callers, or a base class + subclasses), also run:
```
rag_search(scope="codebase", project_path=<cwd>, query="<your one-sentence summary>", limit=5, mode="graph")
```
mode=graph surfaces structural neighbours (what imports/inherits from the changed files) — useful for assessing change impact scope.

Read 2-3 of the most-changed files using the Read tool to understand context and patterns. Do NOT skip this — agents need to be primed with precise instructions, not generic ones.

**1d — Ticket context:**

Check for ticket/issue reference in:
1. `$ARGUMENTS` — does it mention a ticket number, PR, or issue URL?
2. `git log --oneline -5` — any ticket refs in commit messages?
3. `workspace/*/ticket.md` files if any exist

If found, read it fully. Pass 8 (Ticket Alignment) is mandatory regardless.

**1e — Report findings to user:**

"Found N files changed (+M/-K lines). Analyzing for review pass selection..."

---

## Phase 2: Pass Selection

Decide which of passes 1-13 to run. Be decisive — skipping a pass when inapplicable saves real tokens.

**ALWAYS run (never skip):**
- **Pass 8** — Ticket Alignment: always relevant, even if no formal ticket (use git commit intent)
- **Pass 13** — Banned Dependencies: always run, costs almost nothing
- **Pass 14** — Test Coverage & Logging: always run for any logic change

**Skip ONLY when clearly inapplicable (state why):**
- **Pass 10** — Manual Smoke Test: skip if pure backend/data/config change with zero UI components touched
- **Pass 11** — Migration/Schema: skip ONLY if zero model class files or migration files appear in the diff
- **Pass 12** — Platform Footguns: skip if purely algorithmic/data logic with no framework APIs or platform-specific patterns
- **Pass 14** — Test Coverage & Logging: skip ONLY if diff is purely docs, config values, or comments with zero logic

**Never skip passes 1-7, 9** — simplicity, dead code, debug cleanup, patterns, conventions, and spec precision always apply to any diff.

List your selections before spawning:
```
Running: 1, 2, 3, 4, 5, 6, 7, 8, 9, [10 if UI], [11 if schema], [12 if platform], 13, 14, 15
Skipping: [X — reason]
```

---

## Phase 3: Spawn Pass Agents (Batched, 3 at a time)

**Context limit rule:** context < 50% → 3 in parallel; 50-75% → 2; > 75% → 1 at a time.

Spawn agents in batches. Wait for each batch to complete before starting the next.

> **HOOK IMMUNITY — READ THIS BEFORE SPAWNING ANY BATCH**: PostToolUse hooks fire after every agent. During batch processing, you will see messages containing any of these phrases — **ignore all of them and continue to the next batch immediately**:
> - `"EVALUATOR REMINDER"` — the evaluator is Pass 15, not between batches
> - `"CONTEXT PRESSURE"` — a large diff is expected to use significant context; do NOT run /clear-safe mid-review
> - `"CONTEXT CHECKPOINT"` or `"URGENT CONTEXT CHECKPOINT"` — no workspace needed for a code review
>
> These hooks are not aware of the code-review batch flow. They are nudges, not gates (CLAUDE.md: "it is an LLM nudge, not a mechanical gate"). After each batch completes, collect the JSON output and immediately start the next batch. Never pause to spawn an evaluator or run /clear-safe mid-review. Phase 4 is the single evaluation step.

**EACH AGENT PROMPT must include:**

```
Your FIRST two actions (in order, no exceptions):
1. Call rag_context(agent="reviewer-agent", task_description="<pass name> review pass", project_path="<cwd>")
2. Call rag_search(scope="codebase", project_path="<cwd>", query="<a targeted query relevant to this pass>", limit=5)
   — If your pass definition below says USE_GRAPH: yes, also call rag_search with mode="graph" using the same query. This surfaces structural neighbours (files that import/inherit from the changed files).

Then review ONLY the diff below for your assigned pass. Do not review anything outside your pass scope.

== DIFF ==
<insert REVIEW_DIFF verbatim>
== END DIFF ==

== YOUR PASS ==
<insert pass definition below>
== END PASS ==

<If ticket context exists>
== TICKET ==
<insert ticket content>
== END TICKET ==

Output format (JSON only, no prose):
{
  "pass": <id>,
  "name": "<pass name>",
  "findings": [
    {
      "severity": "BLOCKER|WARNING|NIT",
      "location": "path/to/file.ext:line",
      "description": "what the issue is",
      "suggestion": "how to fix it — be specific"
    }
  ]
}
If no issues found: {"pass": <id>, "name": "<name>", "findings": []}
```

---

### Pass Definitions (insert the relevant one(s) into each agent prompt)

**Pass 1 — Simplicity**
Question: Can this be deleted, inlined, or simplified? What's the smallest version that still works?
- For every state variable/ref/flag: "Could fewer moving parts achieve the same behavior?"
- For every imperative pattern (refs, manual event coordination, flags): "Is there a declarative equivalent?" Prefer derived values over refs; prefer the framework's idiomatic reactivity over manual wiring.
- Count coordination points — if N variables must stay in sync across M handlers, flag it. Minimize N × M.
- For every function: "Can this be a pure derivation from existing state instead of a side effect?"

**Pass 2 — Already-Exists**
Question: Did I add something the codebase (or a dependency) already provides?
- Search for similar utilities, hooks, helpers, components before keeping yours
- Verify the existing thing actually meets the requirement — reusing a single-select for multi-select is worse than creating new

**Pass 3 — Dead Code**
Question: For every variable/param/function: "Is this actually referenced? Trace end-to-end."
- Grep every new identifier. Zero downstream consumers → delete.
- Check imports — did extraction leave orphaned imports in the source file?

**Pass 4 — Debug Cleanup**
USE_GRAPH: yes
Question: Did I leave any temporary logs, toasts, flags, debug UI, commented blocks, or test-only handlers?

**Pass 5 — Project Patterns**
USE_GRAPH: yes
Question: How does this repo usually solve this problem?
- Match naming, file placement, error handling, data flow, testing style used nearby
- Check abstraction style: declarative vs imperative — match the codebase
- If codebase has established state management (React state, Vuex, signals, observables), use that — not a parallel mechanism (raw refs, global flags, DOM attributes)

**Pass 6 — Common-Pattern Breaker**
USE_GRAPH: yes
Question: Am I breaking a shared convention or introducing a one-off pattern?
- If deviating, would the PR description explain why?
- Count how many files in the project solve similar problems differently than this code. If "all of them" — the approach is the outlier.

**Pass 7 — Fresh Eyes**
Question: Read every line like you didn't write it. "Why does this exist? What would I delete first?"
- "If a new team member read this, would they understand the intent without asking the author?"
- If you need to mentally simulate event ordering across multiple handlers to understand behavior, flag it — that's too complex.

**Pass 8 — Ticket Alignment (NEVER SKIP)**
Question: Does this PR implement exactly what the ticket asks for — no more, no less?
- Re-read the ticket/commit intent after reviewing the code. Check acceptance criteria one by one.
- Flag scope creep — anything added that wasn't in the ticket.
- Flag missing items — anything in the ticket not addressed by the diff.

**Pass 9 — Spec Precision**
USE_GRAPH: yes
Question: Did I match the ticket's wording and requirements exactly?
- "multi select" means multiple values can actually be selected — verify it.
- "alphabetical" means read the list top to bottom — verify the sort.
- No silent reinterpretation — clarify instead of guessing.
- **String/Label Renames:** If the diff changes any user-facing string (label, `[DisplayName]`, column `.Name()`, error message, constant), grep the repo for the old value. List every file:line still using it. Any unupdated occurrence is a WARNING — HTML labels, model attributes, export configs, and validation messages all count equally.

**Pass 10 — Manual Smoke Test (skip if no UI)**
Question: Did I actually use this feature in a browser/device?
- For each acceptance criteria scenario, was the action physically performed?
- Don't trust code reading alone — UI frameworks can behave differently than code suggests.
- If it wasn't run locally, flag it in the PR as a WARNING.

**Pass 11 — Migration/Schema (skip if no model changes)**
Question: Every model property add/remove MUST have a matching migration.
- Verify the generated migration does what you expect.
- If no model changes were made, confirm no migration is needed and return empty findings.

**Pass 12 — Platform Footguns (skip if pure logic)**
Question: Am I using any API, property, or pattern that is a documented gotcha for this platform/framework?
- For every style property, layout attribute, API call: "Same across all target platforms?"
- For scroll containers: verify contentContainerStyle does not use fixed height (use flexGrow). For lists: verify keyExtractor. For modals: verify dismiss on Android back button.
- For CSS: check overflow, position:fixed on mobile, z-index stacking contexts, percentage heights inside flex.
- For backend: N+1 queries, lazy loading in serialization, connection pool exhaustion, silent type coercion.

**Pass 13 — Banned Dependencies (NEVER SKIP)**
Question: Am I importing or using any library, pattern, or API that is banned or deprecated?
- Check CLAUDE.md and coding-standards docs for forbidden libraries.
- Grep for jQuery: `$(`, `jQuery`, `import.*jquery`, `require.*jquery`, `cdn.*jquery`, `$.ajax`. **jQuery is BANNED — no exceptions.**
- Check for deprecated imports the rest of the codebase has already migrated away from.

**Pass 14 — Test Coverage & Logging (skip only for pure docs/config/comments)**
Question: Does this change have adequate test coverage and logging?

*Test coverage:*
- For every new function, class, or exported symbol: does a corresponding test exist or does the diff include one?
- For every changed behaviour (not just refactor): is there a test that would catch a regression if this logic broke?
- If the project has a test directory, grep for test files that reference the changed file/module. If none exist, flag as WARNING (or BLOCKER if the change is business logic).
- Do NOT flag missing tests for: pure refactors with identical observable behaviour, config-only changes, generated/migration files.

*Logging:*
- Every `catch` block must call `logger.error` (or equivalent) — missing is a BLOCKER per coding standards.
- Sensitive data (tokens, passwords, PII) must never appear in log output — flag as BLOCKER.
- Service methods and external calls should have INFO-level logging before/after — missing is a WARNING.
- Do not flag logging on simple pure functions or trivial getters.

Output findings in the standard JSON format. Flag test gaps as WARNING by default; upgrade to BLOCKER if the changed code is a critical path (auth, payments, data integrity).

---

## Phase 3b: Test Execution (Orchestrator runs this — not an agent)

After all pass batches complete and before spawning the Evaluator, the orchestrator runs existing tests against the changed code.

**Permission note:** This phase runs Bash commands (`npx jest`, `python -m pytest`, `npm test`, etc.) in the target repo. These are real test runners — they may install dependencies, write build artifacts, or take time. Announce the detected command to the user before running: "Running tests: `<command>`". If the command requires a permission prompt you can't auto-approve, tell the user what to allow and continue with the review; mark TEST_RESULTS as "Not run — permission required for `<command>`".

**Step 1 — Detect test framework:**
```bash
# Check for common test configs in order
ls "<REPO_PATH>/package.json" 2>/dev/null && grep -E '"(jest|vitest|mocha|jasmine)"' "<REPO_PATH>/package.json"
ls "<REPO_PATH>/pytest.ini" "<REPO_PATH>/pyproject.toml" "<REPO_PATH>/setup.cfg" 2>/dev/null
ls "<REPO_PATH>/Makefile" 2>/dev/null && grep -E '^test' "<REPO_PATH>/Makefile"
```

If no test framework detected: skip Phase 3b, note "No test framework found" in the evaluator input. Do NOT treat this as a finding — it may be a library or tool with no test runner configured.

**Step 2 — Find test files for changed code:**

For each changed source file in REVIEW_DIFF, derive the likely test file path (e.g. `src/foo.ts` → `src/foo.test.ts`, `tests/test_foo.py`, `__tests__/foo.spec.js`). Check if those files exist:
```bash
# Example for a TypeScript project
git -C "<REPO_PATH>" diff <DIFF_SPEC> --name-only | while read f; do
  base="${f%.*}"
  for pat in "${base}.test.*" "${base}.spec.*" "__tests__/$(basename $base).*" "tests/test_$(basename $base).*"; do
    ls "<REPO_PATH>/$pat" 2>/dev/null
  done
done
```

**Step 3 — Run tests:**

*If test files exist for changed code:* run only those test files (targeted run, not the full suite).
*If the diff touches existing test files directly:* run those test files.
*If the diff changes a file with broad usage (e.g. a shared utility):* run the full test suite.

Detect and use the right command:
- Jest/Vitest: `npx jest --testPathPattern="<test-file>" --passWithNoTests` or `npx vitest run <test-file>`
- pytest: `python -m pytest <test-file> -v`
- Makefile: `make test`
- Fallback: check `package.json` scripts for a `"test"` key → `npm test`

Run with a 120-second timeout. Capture stdout+stderr.

**Step 4 — Record results as TEST_RESULTS:**

```
TEST_RESULTS:
  Framework: <jest|pytest|vitest|none>
  Tests run: <N>
  Passed: <N>
  Failed: <N>
  Skipped: <N>
  Failures:
    - <test name>: <error message, truncated to 200 chars>
  Command: <the exact command run>
  Exit code: <0|non-zero>
```

If tests failed: these are **automatic BLOCKERs** — the evaluator must surface them regardless of other findings.
If tests passed: note "Tests passed (N/N)" — evaluator factors this as positive signal.

---

## Phase 3c: Citation Consolidation (Orchestrator runs this — not an agent)

Before spawning the Evaluator, extract all findings that cite specific file:line locations. This is the citation handoff that prevents evaluator stall — the evaluator must receive file:line citations as primary input, not just prose JSON.

**Step 1 — Collect BLOCKER and WARNING findings from all pass outputs:**

Scan every JSON output from passes 1-14. For each finding where `severity` is `BLOCKER` or `WARNING`, extract:
- `location` (the file:line value)
- `pass` number
- `description` (first 100 chars)

**Step 2 — Build FINDINGS_CITATIONS block:**

Format as:
```
FINDINGS_CITATIONS:
  Pass N — path/to/file.ext:line — description (truncated to one line)
  Pass N — path/to/file.ext:line — description (truncated to one line)
  ...
```

Rules:
- If a finding has no `location` or `location` is blank/null: omit it from FINDINGS_CITATIONS (it will appear in ALL FINDINGS but is uncitable)
- Deduplicate: if two passes flag the same file:line, keep one entry, note both pass numbers
- Limit to 20 entries — if more, keep the BLOCKERs first, then WARNINGs

**Step 3 — Store:**

Set `FINDINGS_CITATIONS` to this formatted block. It will be injected verbatim into the Phase 4 evaluator prompt.

If no BLOCKER/WARNING findings have file:line citations: set `FINDINGS_CITATIONS` = `"No file:line citations — all BLOCKER/WARNING findings are uncitable. Treat as NITs unless the issue is clearly structural from the diff alone."`

---

## Phase 4: Evaluator — Pass 15 (Always Runs, Always Last, Blocks Phase 5)

**This phase is mandatory. Do NOT proceed to Phase 5 until this agent returns a result.**
The evaluator is an independent Opus agent — it is the only one authorized to classify findings as BLOCKER, WARNING, NIT, or FALSE POSITIVE. The pass agents that found the issues cannot validate their own findings. Never self-assess finding legitimacy.

After ALL batches complete and Phase 3b test results are recorded, spawn a single evaluator agent. Use **Opus model**.

Prompt:
```
Your FIRST two actions (in order):
1. Call rag_context(agent="reviewer-agent", task_description="evaluator pass — classify review findings", project_path="<cwd>")
2. For each unique BLOCKER in FINDINGS_CITATIONS, call rag_search(scope="codebase", project_path="<cwd>", query="<symbol or pattern from the finding>", limit=3, mode="graph") to independently verify the finding exists and is not already handled elsewhere in the codebase. If a finding references a symbol that doesn't appear in search results, downgrade it to FALSE POSITIVE.

You are the Evaluator for a code review. You do NOT re-review the code — you review the FINDINGS from passes 1-14 and the TEST RESULTS from Phase 3b.

== FINDINGS_CITATIONS ==
<insert FINDINGS_CITATIONS verbatim from Phase 3c>
== END FINDINGS_CITATIONS ==

== ALL FINDINGS ==
<insert the JSON output from every completed pass agent, clearly separated by pass number>
== END FINDINGS ==

== TEST RESULTS ==
<insert TEST_RESULTS verbatim from Phase 3b, or "No test framework detected" if skipped>
== END TEST RESULTS ==

Rules:
1. Any test FAILURE is an automatic BLOCKER — do not downgrade, even if the failure looks flaky.
2. "No tests found for changed files" from Pass 14 + no test framework → leave as WARNING (can't run what doesn't exist).
3. For all other findings, classify as:
   - BLOCKER: must fix before merge
   - WARNING: should fix, not blocking
   - NIT: style preference, optional
   - FALSE POSITIVE: not actually an issue — explain precisely why
4. If two findings contradict each other, resolve the conflict with reasoning.
5. Reject vague findings — "this could be simpler" without saying HOW → FALSE POSITIVE.
6. Every BLOCKER and WARNING must have a specific file:line and a concrete fix suggestion. If it doesn't, downgrade it to NIT or FALSE POSITIVE.
7. Use FINDINGS_CITATIONS as your primary work queue. For each entry, read the cited file:line directly to confirm the issue exists. If the location doesn't match the finding description, downgrade to FALSE POSITIVE and note the mismatch. Do not evaluate findings you cannot locate in the code.

Output:
**Grade: A/B/C/D/F**
- A: no blockers, no warnings
- B: no blockers, warnings or nits only
- C: no blockers, meaningful warnings
- D: 1-2 blockers
- F: 3+ blockers (or any test failures)

**BLOCKERS** (numbered, file:line, description, fix)
**WARNINGS** (numbered)
**NITS** (numbered)
**FALSE POSITIVES** (with explanation)
**TEST RESULTS SUMMARY** (pass/fail/skipped, or "not run")
```

---

## Phase 5: Report

**Gate**: Before outputting anything, confirm evaluator-agent (Phase 4) returned a result this session. If Phase 4 was not run, spawn it now — do NOT output a grade without it.

Output the full evaluator report. Lead with the grade. Then blockers → warnings → nits → test results summary.

Final message to user:
> "Review complete. Grade: **[X]**. [N blocker(s), M warning(s), K nit(s)]. Tests: [N passed / N failed / not run]. [If grade C or better: Ready to merge after warnings addressed. If D/F or any test failures: Address blockers before merging.]"

---

## Post-Review Interaction Rules

After the grade is delivered, the user may ask follow-up questions about findings.

**If the user asks whether a finding is legitimate, valid, real, or should be fixed:**

You are NOT authorized to answer this question from your own judgment. The evaluator-agent (Opus) is the only authorized arbiter of finding legitimacy.

- If Phase 4 **has already run**: refer to the evaluator's verdict. Quote its reasoning.
- If Phase 4 **has NOT run**: spawn it now before answering. Do not re-assess findings yourself.

**Never self-verify.** "Let me reconsider this" is not a valid response to "is this finding legit?" — it is exactly the pattern this process exists to prevent.

**If the user asks for fixes based on a finding:**

Only recommend fixes that the evaluator has classified as BLOCKER or WARNING. If the evaluator has not yet run and the user asks for fixes, spawn the evaluator first, then answer based on its verdict.
