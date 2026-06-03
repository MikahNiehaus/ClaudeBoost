---
argument-hint: <task-id> [project-path]
description: Build a Files in Scope map using both vector and graph RAG seeded from ticket entities
allowed-tools: Read, Write, Edit, Bash, Glob, Grep
---

# /graph — Scope Graph Builder

Arguments: **$ARGUMENTS**

Builds a "Files in Scope" map for a task by running both vector and graph RAG on ticket entities.
Vector search finds semantically similar code; graph search finds structural neighbours (imports,
inheritance, callers). Together they give a starting navigation map that either mode alone misses.

Run this at task start, or any time you need to refresh the scope map during a task.

---

## Phase 0: Resolve Arguments

Parse `$ARGUMENTS`:
- First token: `TASK_ID` (workspace slug or ticket ID like `ASC-1199`). If not provided, scan active workspaces.
- Remaining tokens: optional `PROJECT_PATH` (absolute path starting with a drive letter or `/`)

**If no TASK_ID given**, scan active workspaces:
```bash
for d in "$CLAUDEBOOST_HOME/workspace/"/*/; do
  [ -d "$d" ] || continue
  name=$(basename "$d")
  [ -f "${d}ticket.md" ] || [ -f "${d}context.md" ] || continue
  echo "WORKSPACE:$name"
  [ -f "${d}ticket.md" ] && head -3 "${d}ticket.md"
  echo "---"
done
python3 "$CLAUDEBOOST_HOME/scripts/register-workspace.py" --list 2>/dev/null
```

If exactly one active workspace: use it. If multiple: ask which one. If none: ask the user.

**Resolve PROJECT_PATH:**
1. From arguments if provided
2. From `$WORKSPACE_ABS/context.md` — look for `Project:` or `Path:` line
3. From CWD if not `$CLAUDEBOOST_HOME`
4. If still unknown: ask the user

Set:
- `WORKSPACE_ABS` = resolved absolute path to `workspace/$TASK_ID`
- `PROJECT_PATH` = resolved project path

---

## Phase 1: RAG Health Check

Call `GET /status``.

If it fails or the tool is unavailable:
> "RAG server is not responding. Run `/rag` to start it, then retry `/graph $ARGUMENTS`."

Stop. Do not proceed.

If it returns successfully: check that the project is indexed.
```bash
python3 -c "
import json, urllib.request
body = json.dumps({'query': 'test', 'scope': 'codebase', 'project_path': '$PROJECT_PATH', 'limit': 1}).encode()
req = urllib.request.Request('http://127.0.0.1:8612/search', data=body, headers={'Content-Type': 'application/json'})
with urllib.request.urlopen(req, timeout=10) as r:
    print(json.loads(r.read()))
"
```

If this returns nothing:
> "Project not indexed — run `/index-project $PROJECT_PATH` first, then retry `/graph`."

Stop. Do not proceed.

---

## Phase 2: Extract Entities

Read in this order, stopping at the first source that yields entities:

**Source A — `analysis.md` Code Entities section** (most structured):
Read `$WORKSPACE_ABS/analysis.md`. Look for the `### Code Entities` section.
Extract every non-empty item under Files/paths, Services/classes, Endpoints, Models/tables.

**Source B — `ticket.md` or `goal.md`** (fallback):
If analysis.md doesn't exist or Code Entities section is empty, read `$WORKSPACE_ABS/ticket.md`
(or `goal.md` if ticket.md is absent). Extract:
- File paths and filenames (anything with `/`, `\`, or a `.ext` pattern)
- PascalCase names (services, classes, components)
- API endpoint paths (anything starting with `/api/` or similar)
- Table/model names (words followed by "model", "table", "entity", "schema")

**Source C — generic fallback**:
If neither source yields any entities, derive 2-3 key search terms from the ticket summary
(the main noun phrases describing what the ticket changes). These will be less precise but
still better than nothing.

Collect all entities into a flat list. Deduplicate. If the list has more than 10 entries,
keep the 10 most specific (prefer file paths and PascalCase names over generic words).

Report how many entities were found and from which source.

---

## Phase 3: Dual-Mode Search

For each entity, run BOTH calls. Never skip either.

**Call 1 — Vector** (semantic similarity — finds code that does the same thing):
```bash
python3 -c "
import json, urllib.request
body = json.dumps({'query': '[entity]', 'scope': 'codebase', 'project_path': '$PROJECT_PATH', 'mode': 'vector', 'limit': 3}).encode()
req = urllib.request.Request('http://127.0.0.1:8612/search', data=body, headers={'Content-Type': 'application/json'})
with urllib.request.urlopen(req, timeout=10) as r:
    data = json.loads(r.read()); [print(h['score'], h['source']) for h in data.get('results', [])]
"
```

**Call 2 — Graph** (structural neighbours — finds code that imports, inherits, or calls the seed):
```bash
python3 -c "
import json, urllib.request
body = json.dumps({'query': '[entity]', 'scope': 'codebase', 'project_path': '$PROJECT_PATH', 'mode': 'graph', 'limit': 3}).encode()
req = urllib.request.Request('http://127.0.0.1:8612/search', data=body, headers={'Content-Type': 'application/json'})
with urllib.request.urlopen(req, timeout=10) as r:
    data = json.loads(r.read()); [print(h['score'], h['source']) for h in data.get('results', [])]
"
```

Collect results from all searches. For each result record:
- `file` — source file path (normalise to repo-relative)
- `relation` — "semantic match" (from vector) or "imports/inherits" (from graph)
- `seed` — which entity triggered the result
- `score` — relevance score from the search result

Deduplicate by file path. Where the same file appears from both modes, keep the graph
relation label (structural is more informative) and note both in a combined entry.

Sort by score descending. Cap the table at 20 files — if more are found, keep the
highest-scoring 20 and note how many were trimmed.

---

## Phase 4: Write Files in Scope

Write or replace the `## Files in Scope (Graph Map)` section in `$WORKSPACE_ABS/context.md`.

If the section already exists: replace it entirely with the new results.
If context.md doesn't exist: create it with just this section.

Format:
```markdown
## Files in Scope (Graph Map)
Built by /graph on [date] from [N] ticket entities using vector + graph RAG.
Update this table as you discover more files during the task.

| File | Relation | Seed Entity |
|------|----------|------------|
| path/to/file.ts | imports/inherits | TicketService |
| path/to/other.ts | semantic match | /api/tickets |
```

If the entity list was empty and the search returned nothing: write a note instead of an
empty table:
```markdown
## Files in Scope (Graph Map)
No entities found in ticket — run /explore first to produce analysis.md with Code Entities,
then re-run /graph to build the map.
```

---

## Phase 5: Completeness Check

Read the ticket acceptance criteria and check whether the in-scope files actually implement each AC item. This catches missing conditions, missing handlers, and untested paths that a file-scope map alone cannot surface.

This phase uses three research-backed techniques: **specification-first enumeration** (enumerate expected values from the AC before touching code), **upstream data flow tracing** (trace where filtered values are set to discover the full input domain), and **iterative second-pass** (when any gap is found, sweep all other filters for the same missing value).

### 5a — Extract acceptance criteria

Read `$WORKSPACE_ABS/ticket.md` (or the AC section of `$WORKSPACE_ABS/context.md` if ticket.md is absent).
Extract each distinct acceptance criterion as a numbered list. If no explicit AC exists, derive expected behaviors from the ticket summary.

If no ticket file exists and no AC can be derived: skip Phase 5 entirely and note "No AC found — completeness check skipped."

### 5b — Build scenario output maps (specification-first)

**Do this before reading any implementation file.** For each AC item, write a "scenario output map": the explicit, exhaustive list of states, values, statuses, roles, or types that this AC scenario can produce or involve. This is the specification — the ground truth you will verify code against.

Example: AC says "users receive notifications when their address changes." Scenario output map:
- Enrollment statuses that can exist at time of address change: Active, Hold, Waitlisted, PendingApproval, Cancelled, Completed
- Roles that can trigger the change: AgencyAdmin, AgencyProgramAdmin, GlobalAdmin, the member themselves
- Notification types: email to DP admin, email to sponsor admin

Write the scenario output map for each AC item before proceeding to 5c. Do not skip this step or defer it.

### 5c — Investigate key in-scope files

Do not assume a file is correct just because it is in scope. Treat every primary implementation file as a suspect: read it and actively look for what it does NOT handle, not just what it does.

For each primary implementation file (processors, controllers, page models, enums, service classes, test files):

1. **Read it** — the full relevant section, not just a summary
2. **Map what it handles** — every condition, branch, filter, status, role, type, or case it covers
3. **Map what it does NOT handle** — ask "what inputs or states could reach this code that are not covered here?" For every filter or allowlist, ask what is excluded. For every branch, ask what falls through. For every role check, ask which roles are absent.
4. **Follow references** — if the file references an enum, constant list, config value, or helper defined elsewhere, read that definition too. Do not assume a referenced value is complete or correct without reading it.
5. **Trace the data path upstream** — for every gate, filter list, or allowlist, trace the filtered value backward: where is it set? Read the controller, trigger, migration, or upstream caller that writes that value. What are ALL the values it can carry when it arrives at the gate? A filter can only be complete if you know the full input domain from upstream code, not just what the filter currently lists.

The goal is to build a complete picture of what each file handles AND what it silently ignores, with the full upstream input domain known for every gate.

### 5d — Check each AC item against its scenario output map

For each AC item: take its scenario output map from 5b, then check whether the implementation covers every item in that map.

This is **specification-first**: you are checking "does the code cover everything the scenario can produce?" — not "does the scenario match what the code does?" The scenario output map is the authority; the code is the thing being verified.

Flag a gap if ANY of the following are true:
- An item in the scenario output map has no corresponding handler/branch/test in the implementation
- A filter list is missing a value that the upstream data path can produce (found via upstream tracing in 5c step 5)
- A role check is missing a role that the AC scenario involves
- An AC item has no corresponding test
- A toggle, flag, or config that the AC requires is absent

Do NOT flag a gap if the AC is implemented but the code is stylistically different from what you'd expect — only flag functional absences.

### 5e — Iterative second-pass: propagate any gap found

If any gap was found in 5d — specifically a missing value in a filter, gate, or allowlist — do not stop. Use that missing value as a new seed:

1. Search all other in-scope files for any other filter list, status gate, role check, or allowlist that handles the same domain (same enum type, same field, same concept)
2. For each one found, check whether the same missing value is absent there too
3. Repeat until no new related filters remain

This catches the pattern where a missing status in one filter (e.g., `AddressChangeAlertEnrollmentStatuses`) is also missing from a related filter elsewhere (e.g., a notification-eligibility check, a UI toggle gate, or a test fixture). A gap in one filter is a signal that the same value was likely overlooked everywhere that domain is filtered.

Add any newly discovered gaps to the gap list before writing results.

### 5f — Write completeness results

Append a `## Completeness Check` section to `$WORKSPACE_ABS/context.md` after the Files in Scope section:

**If all AC items are covered:**
```markdown
## Completeness Check
Run by /graph on [date]. All [N] AC items verified with specific file:line evidence.
```

**If gaps exist:**
```markdown
## Completeness Check
Run by /graph on [date]. [N] of [total] AC items verified. [N] gaps found:

### Gaps
| AC | Gap | File | Detail |
|----|-----|------|--------|
| AC2 | No unit test for DP email model | AddressChangeAlertProcessorUnitTests.cs | Tests assert result count only; AdminSiteBaseUrl=null skips email send — no assertion on AddressChangeAlertDeliveryProviderModel |
| AC5 | Toggle shown to dual-role food+sponsor admin | Account/Index.cshtml.cs:62–68 | ShowAddressChangeAlertToggle has no !IsFoodProviderAdmin guard — a food+sponsor admin would see the toggle |
```

---

## Phase 6: Report

Print:
```
Scope map built for workspace/$TASK_ID

  Entities used : N (from analysis.md Code Entities / ticket.md / generic fallback)
  Vector hits   : N unique files
  Graph hits    : N unique files
  Combined      : N files (N from both modes, N vector only, N graph only)

  Written to: $WORKSPACE_ABS/context.md → ## Files in Scope (Graph Map)

Completeness: N/N AC items verified (or "N gaps — see ## Completeness Check in context.md")
  Second-pass: ran / skipped (ran if any gap found in 5d)

Top files by score:
  1. path/to/file.ts  [imports/inherits — TicketService]
  2. path/to/other.ts [semantic match — /api/tickets]
  ...

To refresh this map at any point: /graph $TASK_ID $PROJECT_PATH
```

---

## Notes

- Re-running `/graph` on the same workspace replaces both the Files in Scope and Completeness Check sections — it does not append.
- Vector and graph are complementary: vector finds files that do similar things; graph finds files that are structurally connected (imports, inheritance chains). Both are needed for a complete picture.
- If the ticket has no explicit entity names, the map will be less precise but still useful as a starting point.
- The scope map is informational — it does not replace reactive RAG queries during the task. Use it as a starting navigation map, not a complete picture.
- Graph search requires the project to be indexed. Run `/index-project $PROJECT_PATH` if the project has not been indexed yet.
- Completeness check reads files directly — it is not a substitute for `/audit` which runs parallel dimension agents. Use `/graph` to find gaps early; use `/audit` to verify the full analysis before shipping.
- Phase 5 uses three research-backed techniques: (1) specification-first — enumerate what values/states/roles the AC scenario produces BEFORE looking at code; (2) upstream data flow tracing — for every gate or filter, follow the filtered value back to where it is set to find the full input domain; (3) iterative second-pass — any gap found in one filter is used as a seed to sweep all other in-scope filters for the same missing value.
