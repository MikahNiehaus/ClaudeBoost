---
argument-hint: <paste ticket descriptions or Jira IDs>
description: Estimate story points by analyzing the codebase with parallel agents
allowed-tools: Read, Write, Bash, Glob, Grep, Agent, AskUserQuestion
---

# /estimate — Codebase Driven Story Point Estimation

Analyze the indexed codebase to produce story point estimates for pasted tickets. Spawns parallel agents across 5 estimation dimensions (blast radius, complexity, test surface, data/migration, pattern precedent), then synthesizes into Fibonacci point estimates with full evidence.

Input: **$ARGUMENTS**

---

## Snippet conventions (read first)

Bash snippets in this file mix two kinds of `$NAMES` — treat them differently:

- **Placeholders** (`$ARGUMENTS`, `$WORKSPACE_ID`, `$WORKSPACE_ABS`, `$PROJECT_PATH`): values YOU resolve in earlier phases. Substitute the actual literal value into the command before running it. Never pass them to Bash as shell variables.
- **Runtime shell variables** (`${TEMP}`, `${CLAUDEBOOST_HOME}`, `${CLAUDEBOOST_PYTHON}`): assigned or exported in the shell itself. Always written in `${VAR}` brace form.

---

## Phase 0: Session Readiness

**0a — Detect project path and active workspace:**

```bash
"${CLAUDEBOOST_PYTHON}" "${CLAUDEBOOST_HOME}/scripts/get-active-workspace.py"
```

Store `project_path` as `PROJECT_PATH` and `workspace_path` as `WORKSPACE_PATH`.
If `PROJECT_PATH` is empty: fall back to current working directory.

**0b — RAG health check:**

Call `GET http://127.0.0.1:8612/status`.

- If it returns an error: STOP. Tell the user: "RAG server not responding — run `/rag` to start the server, then retry `/estimate`."
- If successful: note status and check `indexed_projects` for `PROJECT_PATH`.

**0c — Verify project is indexed:**

Find `PROJECT_PATH` in `indexed_projects` from the status response.

- **Indexed**: note file/chunk counts and continue.
- **Not indexed**: run `Skill(skill="index-project", args="<PROJECT_PATH>")` immediately. Do not continue until indexing completes.

**0d — Load context:**

```
POST http://127.0.0.1:8612/context with agent="architect-agent", task_description="story point estimation for sprint planning", project_path="<PROJECT_PATH>", max_tokens=3000
```

If the result contains an `"error"` key: STOP. Tell the user: "RAG context load failed. Run `/rag` to start the server."

---

## Phase 1: Ticket Parsing

**1a — Get ticket input.**

If `$ARGUMENTS` is empty or contains only whitespace:
```
AskUserQuestion: "Paste the ticket descriptions you want estimated. Include ticket IDs, titles, descriptions, and acceptance criteria. You can paste multiple tickets at once."
```

Store the full input as `TICKET_INPUT`.

**1b — Create or reuse workspace.**

If `WORKSPACE_PATH` is set and contains an active workspace: reuse it. Set `WORKSPACE_ABS = WORKSPACE_PATH`.

Otherwise create a new workspace:

Set `WORKSPACE_ID = sprint-estimate-[today's date YYYY-MM-DD]`.

Check for collision — if the workspace already exists, append `-2`, `-3`, etc.

```bash
mkdir -p "$WORKSPACE_ABS"
```

Register and protect:
```bash
"${CLAUDEBOOST_PYTHON}" "${CLAUDEBOOST_HOME}/scripts/register-workspace.py" "$WORKSPACE_ID" "$WORKSPACE_ABS" "$PROJECT_PATH" --activate

if [ "$PROJECT_PATH" != "${CLAUDEBOOST_HOME}" ]; then
  if ! grep -qxF 'workspace/' "$PROJECT_PATH/.gitignore" 2>/dev/null; then
    echo 'workspace/' >> "$PROJECT_PATH/.gitignore"
  fi
fi
```

Update status bar:
```bash
"${CLAUDEBOOST_PYTHON}" "${CLAUDEBOOST_HOME}/scripts/workspace-status.py" "$WORKSPACE_ID"
```

Announce: "Workspace: `$WORKSPACE_ABS`"

**1c — Save raw tickets.**

Write `$WORKSPACE_ABS/tickets.md`:

```markdown
# Estimation Input

**Date**: [today]
**Project**: $PROJECT_PATH

## Raw Ticket Input

[TICKET_INPUT verbatim — do NOT rephrase or summarize]
```

**1d — Parse individual tickets.**

Scan `TICKET_INPUT` for ticket boundaries. Detect by:
- Ticket ID patterns: `ASC-NNNN`, `JIRA-NNN`, or similar `[A-Z]+-\d+` patterns
- Markdown headers (`# `, `## `) followed by ticket IDs or titles
- Numbered list items that each describe a separate piece of work
- Clear topic boundaries (different features/areas)

For each detected ticket, extract:
- `ticket_id`: the ID if present, otherwise generate `EST-1`, `EST-2`, etc.
- `title`: first line or summary
- `description`: full description text
- `acceptance_criteria`: any Given/When/Then or checklist items
- `entities`: nouns that map to code concepts (controllers, services, models, pages)

If only one ticket is detected, that's fine — the skill works for single tickets too.

Store as `TICKETS` list. Announce: "Found N ticket(s) to estimate."

---

## Phase 2: Parallel Analysis Agents

For each ticket in `TICKETS`, spawn 5 analysis agents. Batch 3 at a time (following context limit rule: context < 50% → 3 parallel; 50-75% → 2; > 75% → 1).

When estimating multiple tickets, interleave agents across tickets to maximize parallelism (e.g., E1 for ticket A + E2 for ticket B + E3 for ticket C in one batch).

### Agent Template

**EVERY agent prompt MUST include all of the following.** Copy this template and fill in the placeholders:

```
Your FIRST action: call POST http://127.0.0.1:8612/context with agent="explore-agent", task_description="estimate dimension: <DIMENSION_NAME> for ticket <TICKET_ID>", project_path="<PROJECT_PATH>", max_tokens=2000

This is a read-only analysis. If you ever do need to edit a code file, the clean-rag research gate blocks the edit until a triage-agent or research-agent has run this turn and declared it covers that file. Spawn one first; it must emit a COVERS line naming the file. Markdown and other non-code files are exempt.

You are an estimation analyst for ONE specific dimension: **<DIMENSION_NAME>**

Your focus: <DIMENSION_FOCUS>

Do NOT estimate points. Do NOT comment on anything outside your dimension. Produce raw evidence only.

== PROJECT PATH ==
<PROJECT_PATH>
== END PROJECT PATH ==

== TICKET ==
ID: <TICKET_ID>
Title: <TICKET_TITLE>
Description: <TICKET_DESCRIPTION>
Acceptance Criteria: <TICKET_AC>
Entities: <TICKET_ENTITIES>
== END TICKET ==

== YOUR DIMENSION ==
<DIMENSION_ID>: <DIMENSION_NAME>
Focus: <DIMENSION_FOCUS>
Search strategy: <DIMENSION_SEARCH>
== END DIMENSION ==

Analyze the codebase for your dimension. Be specific — cite exact file paths, line numbers, and code structures. Vague findings ("this is complex") are not acceptable.

Output format (JSON only, no prose):
{
  "dimension": "<DIMENSION_ID>: <DIMENSION_NAME>",
  "ticket_id": "<TICKET_ID>",
  "score": <1-5>,
  "confidence": "HIGH|MEDIUM|LOW",
  "evidence": [
    {
      "file": "<file path>",
      "detail": "<what was found and why it matters for estimation>",
      "line_range": "<start-end if applicable>"
    }
  ],
  "summary": "<2-3 sentence summary of findings for this dimension>"
}

Score guide for your dimension:
<DIMENSION_SCORE_GUIDE>
```

### Dimension Definitions

**E1: Blast Radius**
- Focus: How many files, layers, components, AND integration entry points does this ticket touch?
- Search strategy:
  1. For each entity in the ticket: `POST http://127.0.0.1:8613/search` with `{"query":"[entity name]","sources":["project:<project_path>"],"mode":"vector","limit":5}`
  2. For each entity: same search with `"mode":"graph"`, limit=5 (finds structural neighbors: callers, importers, inheritors)
  3. Glob for files matching entity names across all project layers
  4. Categorize hits by layer: UI (Pages/, wwwroot/), API (Controllers/), Service (Services/), Data (Models/, Migrations/), Test (*Tests/)
  5. **Integration entry point audit**: For each file that needs changes, count how many DISTINCT call sites, UI actions, or user flows trigger the same code path. A single file with 3 different entry points (e.g., single action, bulk action, dropdown) counts as 3 integration points, not 1. Report both file count AND integration point count.
- Score guide:
  - 1: 1-2 files in 1 layer, 1-2 integration points
  - 2: 3-5 files in 1-2 layers, 2-4 integration points
  - 3: 6-10 files across 2-3 layers, OR fewer files but 5+ integration points
  - 4: 11-20 files across 3-4 layers, OR fewer files but 8+ integration points
  - 5: 20+ files or touches all layers, OR massive integration surface

**E2: Code Complexity**
- Focus: How complex is BOTH the existing code AND the new code that must be written?
- Search strategy:
  1. Use RAG vector search for the main entities to find the primary files
  2. Read the top 10 most relevant files (or relevant sections of large files)
  3. Assess each file: method count, nesting depth (nested if/foreach/try), number of injected dependencies, async patterns, LINQ query complexity, nullable handling
  4. Note coupling: how many other services does each file depend on?
  5. **New code path tracing**: For each acceptance criterion, trace the FULL data flow that needs to be built. If a query, join, or service call doesn't exist yet, note it explicitly. A new 4-table join or a new cross-service orchestration is harder than modifying an existing one. Score the HARDER of (existing complexity, new code complexity).
  6. **AC-to-code mapping**: Map every acceptance criterion to the specific code change it requires. If an AC requires a code pattern that doesn't exist in the affected area (even if it exists elsewhere in the codebase), note this as a "new pattern introduction" and score accordingly.
- Score guide:
  - 1: Simple CRUD, < 3 methods, no complex logic, no new patterns
  - 2: Moderate logic, 3-8 methods, some conditionals, all patterns exist in affected area
  - 3: Business rules, 8-15 methods, multiple branches, some async, OR introduces 1 new pattern to the area
  - 4: Complex orchestration, 15+ methods, deep nesting, heavy async, many dependencies, OR introduces 2+ new patterns
  - 5: Extremely complex, multiple interacting services, state machines, concurrency concerns, novel architecture

**E3: Test Surface**
- Focus: What testing effort does this ticket require?
- Search strategy:
  1. Glob for `**/*Tests*` and `**/*Test*` files matching ticket entity names
  2. Read matched test files to assess: what's already tested, mocking patterns, in-memory DB usage
  3. For each file that needs changes (from entity search): check if corresponding test file exists
  4. Assess new test requirements: unit tests, integration tests, mocking complexity
- Score guide:
  - 1: Existing tests cover the area, minimal new tests (0-1 new test methods)
  - 2: Some existing tests, 2-4 new test methods needed, simple mocking
  - 3: Partial coverage, 5-8 new test methods, moderate mocking or in-memory DB setup
  - 4: Low coverage, 8-15 new test methods, complex mocking, multiple test scenarios
  - 5: No existing tests, 15+ new methods needed, complex setup (multi-service, async, external deps)

**E4: Data/Migration**
- Focus: Does this ticket require database schema changes, migrations, or seed data?
- Search strategy:
  1. Search for entity models: `POST http://127.0.0.1:8613/search` with `{"query":"[entity] model class property","sources":["project:<project_path>"],"mode":"vector","limit":5}`
  2. Search for DbContext references: `POST http://127.0.0.1:8613/search` with `{"query":"DbSet [entity]","sources":["project:<project_path>"],"mode":"vector","limit":5}`
  3. Check for existing migrations touching these entities: Glob for `**/Migrations/**` and grep for entity names
  4. Look for FK relationships, navigation properties, indexes on affected models
  5. Check if new tables, columns, or relationships are implied by acceptance criteria
- Score guide:
  - 1: No schema changes needed
  - 2: Add 1-2 columns to existing table, simple migration
  - 3: New table or significant schema change, FK relationships, needs seed data
  - 4: Multiple table changes, complex relationships, data migration (not just schema)
  - 5: Major schema redesign, breaking changes, data backfill across large tables

**E5: Pattern Precedent**
- Focus: Has similar work been done before? Does the ticket follow ONE pattern or require COMBINING multiple?
- Search strategy:
  1. Search codebase for similar patterns: `POST http://127.0.0.1:8613/search` with `{"query":"[feature description] implementation","sources":["project:<project_path>"],"mode":"vector","limit":5}`
  2. Git log search for recent commits touching similar files: `git -C "<PROJECT_PATH>" log --oneline --all --since="6 months ago" -- "*[entity]*" | head -20`
  3. Look for existing implementations of similar features (e.g., if adding a new notification type, find existing notification implementations)
  4. Assess: can this ticket follow an existing pattern, or does it require a new approach?
  5. **Multi-pattern detection (CRITICAL)**: When a ticket says "follow the X pattern," do NOT stop there. Read EVERY acceptance criterion and map each one to the codebase pattern it matches. If different ACs map to DIFFERENT existing patterns (e.g., AC1 matches the Settings page config pattern but AC3 matches the modal prompt pattern), the ticket requires COMBINING multiple patterns. Combining patterns is significantly harder than following one. Score at least 3 when 2+ distinct patterns must be merged.
  6. **Read the named pattern code**: When a ticket references a specific pattern by name (e.g., "follow the Declined pattern"), actually READ the implementation of that pattern. Then compare what it does vs what ALL the ACs require. If the named pattern only covers a subset of the ACs, note the gap.
- Score guide:
  - 1: Exact single pattern exists, copy and adapt (e.g., add another enum value, clone a page)
  - 2: Similar single pattern exists, minor adaptations needed
  - 3: Related patterns exist but meaningful differences, OR ticket requires combining 2 distinct patterns
  - 4: Partially novel, existing patterns cover some but not all requirements, OR combining 3+ patterns
  - 5: Fully novel, no existing pattern to follow, new architectural decisions needed

---

## Phase 3: Synthesis

After ALL analysis agents complete, collect their JSON outputs as `ANALYSIS_RESULTS`.

**3a — Spawn synthesis agent (use Opus model).**

```
Your FIRST action: call POST http://127.0.0.1:8612/context with agent="architect-agent", task_description="synthesize story point estimates from analysis dimensions", project_path="<PROJECT_PATH>", max_tokens=3000

This is a read-only synthesis. If you ever do need to edit a code file, the clean-rag research gate blocks the edit until a triage-agent or research-agent has run this turn and declared it covers that file.

You are the Estimation Synthesis Agent. You do NOT re-analyze the codebase. You synthesize the findings from all 5 dimension analysts into final story point estimates.

== PROJECT PATH ==
<PROJECT_PATH>
== END PROJECT PATH ==

== TICKETS ==
[list each ticket_id and title]
== END TICKETS ==

== ALL ANALYSIS RESULTS ==
[insert JSON output from every completed analysis agent, grouped by ticket_id]
== END ANALYSIS RESULTS ==

For EACH ticket, produce a final estimate using this methodology:

**Step 1: Validate dimension scores.**
- Discard any dimension result with confidence = LOW and score > 3 (insufficient evidence for high scores)
- If a dimension agent returned no evidence, set its score to the median of other dimensions for that ticket

**Step 2: Calculate weighted score.**
Apply these weights (based on empirical correlation with actual effort):
- E1 Blast Radius: 0.30 (files touched is the strongest predictor of effort)
- E2 Code Complexity: 0.25 (complex code takes proportionally longer)
- E3 Test Surface: 0.20 (testing often equals or exceeds implementation time)
- E4 Data/Migration: 0.15 (schema changes add risk and ceremony)
- E5 Pattern Precedent: 0.10 (novel work takes longer than pattern-following)

weighted_score = (E1 * 0.30) + (E2 * 0.25) + (E3 * 0.20) + (E4 * 0.15) + (E5 * 0.10)

**Step 3: Map to Fibonacci story points.**
- 1.0 to 1.5 → 1 point (XS: trivial change, single file, no tests)
- 1.6 to 2.2 → 2 points (S: small change, few files, minor testing)
- 2.3 to 3.0 → 3 points (M: moderate scope, some complexity, testing needed)
- 3.1 to 3.8 → 5 points (L: significant scope, multiple layers, substantial testing)
- 3.9 to 4.5 → 8 points (XL: large scope, high complexity, extensive testing)
- 4.6 to 5.0 → 13 points (XXL: massive scope, consider splitting)

**Step 4: Apply confidence adjustment.**
- If 4-5 dimensions have HIGH confidence: overall confidence = HIGH
- If 2-3 dimensions have HIGH confidence: overall confidence = MEDIUM
- Otherwise: overall confidence = LOW
- If overall confidence = LOW, note "estimate may be unreliable — consider manual review"

**Step 5: Identify the key factor.**
The dimension with the highest weighted contribution (score * weight) is the "key factor" — the primary driver of the estimate. Name it in the summary.

**Step 6: AC coverage gap check.**
For each ticket, review all acceptance criteria against the combined evidence from all 5 dimension agents. If any AC has NO corresponding evidence from ANY agent (meaning no agent found the code area that AC would require), flag it as an "uncovered AC" and bump the overall score up by 0.5 per uncovered AC (these represent work the agents couldn't quantify). Include uncovered ACs in risk_notes.

**Step 7: Flag splitting candidates.**
If the final estimate is 8+ points AND E1 score >= 4, recommend splitting the ticket. Suggest logical split boundaries based on layers or features identified in E1 evidence.

Output format (JSON only, no prose):
{
  "estimates": [
    {
      "ticket_id": "<ID>",
      "title": "<title>",
      "weighted_score": <float>,
      "points": <fibonacci number>,
      "size_label": "XS|S|M|L|XL|XXL",
      "confidence": "HIGH|MEDIUM|LOW",
      "key_factor": "<dimension name and why>",
      "dimension_scores": {
        "E1_blast_radius": {"score": <1-5>, "weighted": <float>},
        "E2_complexity": {"score": <1-5>, "weighted": <float>},
        "E3_test_surface": {"score": <1-5>, "weighted": <float>},
        "E4_data_migration": {"score": <1-5>, "weighted": <float>},
        "E5_precedent": {"score": <1-5>, "weighted": <float>}
      },
      "risk_notes": ["<risk 1>", "<risk 2>"],
      "split_recommendation": null or "<how to split>"
    }
  ],
  "total_points": <sum>,
  "sprint_notes": "<any overall observations about the batch>"
}
```

Collect the synthesis output as `SYNTHESIS`.

---

## Phase 4: Document Output

**4a — Write the estimate report.**

Write `$WORKSPACE_ABS/estimate.md`:

```markdown
# Sprint Estimation Report

**Date**: [today]
**Project**: [project name from PROJECT_PATH]
**Tickets Analyzed**: [count]
**Workspace**: [WORKSPACE_ABS]

---

## Summary

| Ticket | Title | Points | Size | Confidence | Key Factor |
|--------|-------|--------|------|------------|------------|
[one row per ticket from SYNTHESIS]

**Total Points: [sum]**

---

## Per Ticket Breakdown

[For each ticket in SYNTHESIS, write a section:]

### [ticket_id]: [title]

**Estimate: [points] points ([size_label])** — Confidence: [confidence]

#### Dimension Scores

| Dimension | Score | Weighted | Key Evidence |
|-----------|-------|----------|--------------|
| E1: Blast Radius | [score]/5 | [weighted] | [top evidence item from E1 agent] |
| E2: Code Complexity | [score]/5 | [weighted] | [top evidence item from E2 agent] |
| E3: Test Surface | [score]/5 | [weighted] | [top evidence item from E3 agent] |
| E4: Data/Migration | [score]/5 | [weighted] | [top evidence item from E4 agent] |
| E5: Pattern Precedent | [score]/5 | [weighted] | [top evidence item from E5 agent] |

**Weighted Score**: [weighted_score] → [points] points

#### Files Affected

[table of files from E1 agent evidence: file path, layer, what changes]

#### Risk Notes

[bullet list from risk_notes]

[If split_recommendation is not null:]
#### Split Recommendation

[split_recommendation text]

---

[end per-ticket section]

## Methodology

Estimates produced by parallel codebase analysis across 5 dimensions:
- **Blast Radius (30%)**: files and layers touched
- **Code Complexity (25%)**: structural complexity of affected code
- **Test Surface (20%)**: testing effort required
- **Data/Migration (15%)**: schema and data change scope
- **Pattern Precedent (10%)**: novelty vs established patterns

Weighted scores mapped to Fibonacci story points (1, 2, 3, 5, 8, 13).
Confidence reflects evidence quality across dimensions.
```

**4b — Update context.md.**

Append to `$WORKSPACE_ABS/context.md` (create if missing):

```markdown
## Estimation Results — [today]

- Tickets estimated: [count]
- Total points: [sum]
- [For each ticket: "[ticket_id]: [points] pts ([confidence])"]
- Report: estimate.md
```

**4c — Present results to user.**

Print the summary table and total points. Then:

> "Full estimation report saved to `$WORKSPACE_ABS/estimate.md`."
> 
> [If any ticket scored 8+ points:] "Tickets marked XXL/XL may benefit from splitting — see split recommendations in the report."
> 
> [If any dimension had LOW confidence:] "Some estimates have low confidence due to limited codebase evidence — consider manual review for those tickets."

---

## Resume Notes

- Re-running `/estimate` with the same workspace active appends new estimates to the existing report.
- To re-estimate a specific ticket, paste just that ticket's text again.
- The workspace retains all raw tickets in `tickets.md` for reference.
