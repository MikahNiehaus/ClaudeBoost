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
for d in "${CLAUDEBOOST_HOME}/workspace/"/*/; do
  [ -d "${d}" ] || continue
  name=$(basename "${d}")
  [ -f "${d}ticket.md" ] || [ -f "${d}context.md" ] || continue
  echo "WORKSPACE:${name}"
  [ -f "${d}ticket.md" ] && head -3 "${d}ticket.md"
  echo "---"
done
python3 -c "import os,subprocess,sys; h=os.environ['CLAUDEBOOST_HOME']; subprocess.run([sys.executable,h+'/scripts/register-workspace.py','--list'])" 2>/dev/null
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
> "Project not indexed."

Run `Skill(skill="index-project", args="$PROJECT_PATH")` immediately, then continue — do not stop.

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

## Phase 5: Structural Gap Analysis

Runs on every call — no ticket required. Takes the Files in Scope table from Phase 4 and
asks: given these files, what SHOULD be present that isn't? This catches missing
implementations, orphaned exports, and untested public API that RAG cannot find because
absent code isn't in the index.

### 5a — Detect languages in scope

From the file extensions in the scope table, identify the primary language(s):
- `.py` → Python
- `.ts`, `.tsx`, `.js`, `.jsx` → TypeScript/JavaScript
- `.cs` → C#
- `.go` → Go

If the language is unrecognised or the scope table is empty, skip to Phase 6 and note:
"Structural gap analysis skipped — no recognised file types in scope."

### 5b — Extract public symbols from RAG chunks

Do NOT use Grep or Read to scan files — the rag-read-guard fires after 2 reads and will
block a per-file grep loop. Instead, retrieve symbols from the RAG index, which already
stores function/class names in the `section` field of every chunk.

For each source file in the scope table (skip `.md`, `.json`, `.yaml` — not source code),
run one RAG vector search:

```bash
python3 -c "
import json, urllib.request
body = json.dumps({
    'query': 'class function definition',
    'scope': 'codebase',
    'project_path': '$PROJECT_PATH',
    'mode': 'vector',
    'limit': 10
}).encode()
req = urllib.request.Request('http://127.0.0.1:8612/search', data=body, headers={'Content-Type': 'application/json'})
with urllib.request.urlopen(req, timeout=10) as r:
    data = json.loads(r.read())
    for h in data.get('results', []):
        if '[target_file]' in h['source']:
            print(h.get('section',''), h.get('line_start',''))
"
```

Parse public symbols from the `section` field. Strip any trailing `[header]`, `[footer]`,
or `[imports]` bracketed suffixes first, then apply these rules:

- Section starts with `"class "` → symbol_name = word after `"class "`, kind=`class`
  e.g. `"class SQLiteGraphStore [header]"` → strip suffix → `"class SQLiteGraphStore"` → `SQLiteGraphStore`
- Section starts with `"def "` or `"async def "` → symbol_name = word after `"def "`, kind=`function`
- Section is `"[imports]"` or `"[header]"` alone (no class/def prefix) → skip
- Section contains `.def ` (e.g. `"class Foo.def bar"`) → method — keep if `bar` doesn't start with `_`
- Any extracted name starting with `_` → skip (private/dunder)

For TypeScript/JavaScript, the section field contains exported names directly.
For C#, look for `class` and `interface` sections.
For Go, capitalised section names are exported by convention.

Collect: `{file, line_start, symbol_name, kind}`. Deduplicate. Cap at 30 symbols total,
prioritising: interfaces > abstract classes > public functions > constants.

### 5c — Check each symbol for consumers

For each symbol, RAG graph search is the primary check. Only fall back to grep if graph
returns nothing, and batch all fallback greps into a single Bash call.

**Step 1 — RAG graph search per symbol:**
```bash
python3 -c "
import json, urllib.request
body = json.dumps({'query': '[symbol_name]', 'scope': 'codebase', 'project_path': '$PROJECT_PATH', 'mode': 'graph', 'limit': 3}).encode()
req = urllib.request.Request('http://127.0.0.1:8612/search', data=body, headers={'Content-Type': 'application/json'})
with urllib.request.urlopen(req, timeout=10) as r:
    data = json.loads(r.read()); [print(h['score'], h['source']) for h in data.get('results', [])]
"
```

A symbol has a consumer if the graph search returns any result where `source` is a file
other than the defining file. Record it as confirmed.

**Step 2 — Batched fallback grep (one Bash call for all inconclusive symbols):**

After ALL graph searches complete, collect any symbols where graph returned 0 external hits
into a `needs_grep` list. Then run ONE Bash call:

```bash
python3 -c "
import subprocess
symbols = ['SymbolA', 'SymbolB']  # replace with actual needs_grep list
project = '$PROJECT_PATH'
for sym in symbols:
    r = subprocess.run(['grep', '-r', '-l', '--include=*.py', '--include=*.ts',
                        '--include=*.cs', '--include=*.go', sym, project],
                       capture_output=True, text=True)
    hits = [f for f in r.stdout.strip().split('\n') if f and '[defining_file]' not in f]
    print(sym, '|', hits)
"
```

Record `consumers` as the combined list of external files from both steps, or empty if
both returned nothing.

### 5d — Classify gaps

Flag a symbol as a structural gap if any of the following apply:

| Gap type | Condition | Do NOT flag if |
|----------|-----------|----------------|
| **orphan-export** | Exported function/class/constant with empty `consumers` — defined but never used | Name matches a framework lifecycle method (`setUp`, `tearDown`, `render`, `main`, `init`, etc.) or is a dunder (`__*__`) |
| **unimplemented-interface** | Interface or abstract class with no external file containing `implements [name]`, `extends [name]`, or `: [name]` | The interface is brand-new in an in-progress branch |
| **missing-test** | Public function/method with no file matching `*test*` or `*spec*` in its path containing the symbol name | Symbol already appears in any test file even if not a dedicated test for it |
| **orphan-file** | A file in scope with empty `consumers` AND no entry-point marker in the file (`@app.route`, `@router`, `[HttpGet]`, `[HttpPost]`, `router.`, `app.use`, `if __name__`, `export default`) | File is a type-definition file, constants file, or migration file |

Skip framework-generated symbols: constructors named the same as their class, `index.ts`
re-exports, `__init__.py` imports.

### 5e — Write Structural Gaps section

Append `## Structural Gaps` to `$WORKSPACE_ABS/context.md` immediately after
`## Files in Scope (Graph Map)`. If the section already exists, replace it.

**No gaps found:**
```markdown
## Structural Gaps
Run by /graph on [date]. [N] symbols checked across [N] files. No structural gaps found.
```

**Gaps found:**
```markdown
## Structural Gaps
Run by /graph on [date]. [N] symbols checked across [N] files. [N] gaps found:

| Symbol | File:Line | Gap Type | Detail |
|--------|-----------|----------|--------|
| PaymentService | src/services/payment.py:12 | orphan-export | No consumers found — defined but never called |
| INotifiable | src/interfaces.ts:34 | unimplemented-interface | No class implements INotifiable in codebase |
| calculate_tax | src/utils/tax.py:88 | missing-test | No test file references calculate_tax |
```

If more than 10 gaps found, show the 10 with highest confidence (both RAG and grep returned 0
external hits) and note how many were trimmed.

If ANY gaps were found, append this call-to-action immediately after the gap table:

```markdown
> Structural gaps are candidates — grep and graph search can miss dynamic dispatch and
> reflection. Run `/audit` to validate these findings with parallel dimension agents before
> acting on them.
```

---

## Phase 6: Completeness Check

Read the ticket acceptance criteria and check whether the in-scope files actually implement each AC item. This catches missing conditions, missing handlers, and untested paths that a file-scope map alone cannot surface.

This phase uses three research-backed techniques: **specification-first enumeration** (enumerate expected values from the AC before touching code), **upstream data flow tracing** (trace where filtered values are set to discover the full input domain), and **iterative second-pass** (when any gap is found, sweep all other filters for the same missing value).

### 6a — Extract acceptance criteria

Read `$WORKSPACE_ABS/ticket.md` (or the AC section of `$WORKSPACE_ABS/context.md` if ticket.md is absent).
Extract each distinct acceptance criterion as a numbered list. If no explicit AC exists, derive expected behaviors from the ticket summary.

If no ticket file exists and no AC can be derived: skip Phase 6 entirely and note "No AC found — completeness check skipped."

### 6b — Build scenario output maps (specification-first)

**Do this before reading any implementation file.** For each AC item, write a "scenario output map": the explicit, exhaustive list of states, values, statuses, roles, or types that this AC scenario can produce or involve. This is the specification — the ground truth you will verify code against.

Example: AC says "users receive notifications when their address changes." Scenario output map:
- Enrollment statuses that can exist at time of address change: Active, Hold, Waitlisted, PendingApproval, Cancelled, Completed
- Roles that can trigger the change: AgencyAdmin, AgencyProgramAdmin, GlobalAdmin, the member themselves
- Notification types: email to DP admin, email to sponsor admin

Write the scenario output map for each AC item before proceeding to 6c. Do not skip this step or defer it.

### 6c — Investigate key in-scope files

Do not assume a file is correct just because it is in scope. Treat every primary implementation file as a suspect and actively look for what it does NOT handle.

For each primary implementation file (processors, controllers, page models, enums, service classes, test files):

1. **Find the relevant section via RAG first** — run `POST http://127.0.0.1:8612/search scope=codebase project_path=$PROJECT_PATH query="[AC concept from 6b]" mode=vector limit=3`. Read only the specific chunk RAG identifies (use `line_start` to target the Read). Do not read the whole file.
2. **Map what it handles** — every condition, branch, filter, status, role, type, or case it covers
3. **Map what it does NOT handle** — ask "what inputs or states could reach this code that are not covered here?" For every filter or allowlist, ask what is excluded. For every branch, ask what falls through. For every role check, ask which roles are absent.
4. **Follow references via RAG** — if the file references an enum, constant list, or helper defined elsewhere, search RAG for it (`query="[enum/constant name]" mode=graph`), then Read only the section RAG returns. Do not read files directly without a RAG search to navigate first.
5. **Trace the data path upstream via RAG** — for every gate or filter, search RAG for where the filtered value is set (`query="[field name] set assign" mode=graph`). Read only the upstream section RAG identifies.

The goal is to build a complete picture of what each file handles AND what it silently ignores. RAG navigates — Read confirms.

### 6d — Check each AC item against its scenario output map

For each AC item: take its scenario output map from 6b, then check whether the implementation covers every item in that map.

This is **specification-first**: you are checking "does the code cover everything the scenario can produce?" — not "does the scenario match what the code does?" The scenario output map is the authority; the code is the thing being verified.

Flag a gap if ANY of the following are true:
- An item in the scenario output map has no corresponding handler/branch/test in the implementation
- A filter list is missing a value that the upstream data path can produce (found via upstream tracing in 6c step 5)
- A role check is missing a role that the AC scenario involves
- An AC item has no corresponding test
- A toggle, flag, or config that the AC requires is absent

Do NOT flag a gap if the AC is implemented but the code is stylistically different from what you'd expect — only flag functional absences.

### 6e — Iterative second-pass: propagate any gap found

If any gap was found in 6d — specifically a missing value in a filter, gate, or allowlist — do not stop. Use that missing value as a new seed:

1. Search all other in-scope files for any other filter list, status gate, role check, or allowlist that handles the same domain (same enum type, same field, same concept)
2. For each one found, check whether the same missing value is absent there too
3. Repeat until no new related filters remain

This catches the pattern where a missing status in one filter (e.g., `AddressChangeAlertEnrollmentStatuses`) is also missing from a related filter elsewhere (e.g., a notification-eligibility check, a UI toggle gate, or a test fixture). A gap in one filter is a signal that the same value was likely overlooked everywhere that domain is filtered.

Add any newly discovered gaps to the gap list before writing results.

### 6f — Write completeness results

Append a `## Completeness Check` section to `$WORKSPACE_ABS/context.md` after the Structural Gaps section:

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

## Phase 7: Report

Print:
```
Scope map built for workspace/$TASK_ID

  Entities used   : N (from analysis.md Code Entities / ticket.md / generic fallback)
  Vector hits     : N unique files
  Graph hits      : N unique files
  Combined        : N files (N from both modes, N vector only, N graph only)

  Written to: $WORKSPACE_ABS/context.md → ## Files in Scope (Graph Map)

Structural gaps : N found across N symbols (or "none") — see ## Structural Gaps in context.md
  (gaps found → run /audit to validate before acting on them)
Completeness    : N/N AC items verified (or "N gaps — see ## Completeness Check in context.md")
  Second-pass   : ran / skipped (ran if any gap found in 6d)

Top files by score:
  1. path/to/file.ts  [imports/inherits — TicketService]
  2. path/to/other.ts [semantic match — /api/tickets]
  ...

To refresh this map at any point: /graph $TASK_ID $PROJECT_PATH
```

---

## Notes

- Re-running `/graph` replaces the Files in Scope, Structural Gaps, and Completeness Check sections — it does not append.
- Vector and graph are complementary: vector finds files that do similar things; graph finds files that are structurally connected (imports, inheritance chains). Both are needed for a complete picture.
- If the ticket has no explicit entity names, the map will be less precise but still useful as a starting point.
- The scope map is informational — it does not replace reactive RAG queries during the task. Use it as a starting navigation map, not a complete picture.
- Graph search requires the project to be indexed. Run `/index-project $PROJECT_PATH` if the project has not been indexed yet.
- Structural gap analysis (Phase 5) runs on every call with no ticket needed. It reads in-scope files directly and uses grep + RAG graph search to find orphaned exports, unimplemented interfaces, and missing tests. It will produce false positives on dynamic dispatch and reflection — treat findings as candidates, not confirmed bugs.
- Completeness check (Phase 6) reads files directly — it is not a substitute for `/audit` which runs parallel dimension agents. Use `/graph` to find gaps early; use `/audit` to verify the full analysis before shipping.
- Phase 6 uses three research-backed techniques: (1) specification-first — enumerate what values/states/roles the AC scenario produces BEFORE looking at code; (2) upstream data flow tracing — for every gate or filter, follow the filtered value back to where it is set to find the full input domain; (3) iterative second-pass — any gap found in one filter is used as a seed to sweep all other in-scope filters for the same missing value.
