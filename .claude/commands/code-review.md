---
argument-hint: [scope — "staged", "last 2 commits", branch name, file path, PR #]
description: 14-pass parallel code review — simplicity, patterns, ticket alignment, evaluator
allowed-tools: Read, Write, Bash, Glob, Grep, Agent
---

# /code-review — 14-Pass Parallel Code Review

Run 13 independent review passes as batched parallel agents, then a final Evaluator (pass 14) that classifies every finding. Orchestrator understands the diff with RAG before spawning anything — no blind agent launches.

Scope: **$ARGUMENTS**

---

## Phase 0: Load Knowledge + Index Project

**0a — ClaudeBoost RAG context** (do this FIRST, before any git commands):

Call `rag_context(agent="reviewer-agent", task_description="code review $ARGUMENTS", max_tokens=4000)`.

This loads coding-standards, security, scope-governance guardrails. Read the result — it primes your knowledge for pass selection.

**0b — Project RAG index** (ensure codebase search works):

```bash
pwd
```

Call `rag_index_project(project_path=<cwd output>)`. Report: "X files updated."

---

## Phase 1: Understand the Diff

**1a — Resolve scope and get stat:**

| Argument | Stat command | Diff command |
|----------|-------------|--------------|
| `staged` | `git diff --staged --stat` | `git diff --staged` |
| `last N commits` / `N commits` | `git diff HEAD~N --stat` | `git diff HEAD~N` |
| A commit range `A..B` | `git diff A..B --stat` | `git diff A..B` |
| A branch name | `git diff <branch> --stat` | `git diff <branch>` |
| A file/dir path | auto-detect + append `-- <path>` | same |
| Empty | staged → unstaged → HEAD~1 | same |

Run the stat command. If nothing returns, tell the user "No changes to show" and STOP.

**1b — Get full diff:**

```bash
git diff <resolved-scope>
```

Store this as **REVIEW_DIFF**. Do NOT truncate it.

**1c — RAG-powered pattern search** (understand what changed before spawning):

Summarize what changed in one sentence. Then:

```
rag_search(scope="codebase", project_path=<cwd>, query="<your one-sentence summary>", limit=5)
```

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

**Skip ONLY when clearly inapplicable (state why):**
- **Pass 10** — Manual Smoke Test: skip if pure backend/data/config change with zero UI components touched
- **Pass 11** — Migration/Schema: skip ONLY if zero model class files or migration files appear in the diff
- **Pass 12** — Platform Footguns: skip if purely algorithmic/data logic with no framework APIs or platform-specific patterns

**Never skip passes 1-7, 9** — simplicity, dead code, debug cleanup, patterns, conventions, and spec precision always apply to any diff.

List your selections before spawning:
```
Running: 1, 2, 3, 4, 5, 6, 7, 8, 9, [10 if UI], [11 if schema], [12 if platform], 13, 14
Skipping: [X — reason]
```

---

## Phase 3: Spawn Pass Agents (Batched, 3 at a time)

**Context limit rule:** context < 50% → 3 in parallel; 50-75% → 2; > 75% → 1 at a time.

Spawn agents in batches. Wait for each batch to complete before starting the next.

> **HOOK OVERRIDE**: The PostToolUse verify-gate hook will fire after each batch because pass agents return findings in their JSON. **Do NOT spawn an evaluator between batches.** The hook is a nudge, not a gate (CLAUDE.md: "it is an LLM nudge, not a mechanical gate"). Pass 14 (Evaluator, Opus) is the single verification step — it runs after ALL batches complete. Collect each batch's JSON output and immediately start the next batch.

**EACH AGENT PROMPT must include:**

```
Your FIRST two actions (in order, no exceptions):
1. Call rag_context(agent="reviewer-agent", task_description="<pass name> review pass", project_path="<cwd>")
2. Call rag_search(scope="codebase", project_path="<cwd>", query="<a targeted query relevant to this pass>", limit=5)

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
Question: Did I leave any temporary logs, toasts, flags, debug UI, commented blocks, or test-only handlers?

**Pass 5 — Project Patterns**
Question: How does this repo usually solve this problem?
- Match naming, file placement, error handling, data flow, testing style used nearby
- Check abstraction style: declarative vs imperative — match the codebase
- If codebase has established state management (React state, Vuex, signals, observables), use that — not a parallel mechanism (raw refs, global flags, DOM attributes)

**Pass 6 — Common-Pattern Breaker**
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
Question: Did I match the ticket's wording and requirements exactly?
- "multi select" means multiple values can actually be selected — verify it.
- "alphabetical" means read the list top to bottom — verify the sort.
- No silent reinterpretation — clarify instead of guessing.

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

---

## Phase 4: Evaluator — Pass 14 (Always Runs, Always Last)

After ALL batches complete, spawn a single evaluator agent. Use **Opus model**.

Prompt:
```
Your FIRST action: call rag_context(agent="reviewer-agent", task_description="evaluator pass — classify review findings", project_path="<cwd>")

You are the Evaluator for a code review. You do NOT re-review the code — you review the FINDINGS from passes 1-13.

== ALL FINDINGS ==
<insert the JSON output from every completed pass agent, clearly separated by pass number>
== END FINDINGS ==

For each finding:
1. Classify as:
   - BLOCKER: must fix before merge
   - WARNING: should fix, not blocking
   - NIT: style preference, optional
   - FALSE POSITIVE: not actually an issue — explain precisely why
2. If two findings contradict each other, resolve the conflict with reasoning.
3. Reject vague findings — "this could be simpler" without saying HOW → FALSE POSITIVE.
4. Every BLOCKER and WARNING must have a specific file:line and a concrete fix suggestion. If it doesn't, downgrade it to NIT or FALSE POSITIVE.

Output:
**Grade: A/B/C/D/F**
- A: no blockers, no warnings
- B: no blockers, warnings or nits only
- C: no blockers, meaningful warnings
- D: 1-2 blockers
- F: 3+ blockers

**BLOCKERS** (numbered, file:line, description, fix)
**WARNINGS** (numbered)
**NITS** (numbered)
**FALSE POSITIVES** (with explanation)
```

---

## Phase 5: Report

Output the full evaluator report. Lead with the grade. Then blockers → warnings → nits.

Final message to user:
> "Review complete. Grade: **[X]**. [N blocker(s), M warning(s), K nit(s)]. [If grade C or better: Ready to merge after warnings addressed. If D/F: Address blockers before merging.]"
