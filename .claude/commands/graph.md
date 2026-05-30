---
argument-hint: <task-id> [project-path]
description: Build a Files in Scope map using both vector and graph RAG seeded from ticket entities
allowed-tools: Read, Write, Edit, Bash, Glob, Grep, mcp__rag-server__rag_status, mcp__rag-server__rag_search, mcp__rag-server__rag_context
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

Call `rag_status()`.

If it fails or the tool is unavailable:
> "RAG server is not responding. Run `/mcp` to reconnect, then retry `/graph $ARGUMENTS`."

Stop. Do not proceed.

If it returns successfully: check that the project is indexed.
```
rag_search(scope="codebase", project_path="$PROJECT_PATH", query="test", limit=1)
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
```
rag_search(scope="codebase", project_path="$PROJECT_PATH", query="[entity]", mode="vector", limit=3)
```

**Call 2 — Graph** (structural neighbours — finds code that imports, inherits, or calls the seed):
```
rag_search(scope="codebase", project_path="$PROJECT_PATH", query="[entity]", mode="graph", limit=3)
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

## Phase 5: Report

Print:
```
Scope map built for workspace/$TASK_ID

  Entities used : N (from analysis.md Code Entities / ticket.md / generic fallback)
  Vector hits   : N unique files
  Graph hits    : N unique files
  Combined      : N files (N from both modes, N vector only, N graph only)

  Written to: $WORKSPACE_ABS/context.md → ## Files in Scope (Graph Map)

Top files by score:
  1. path/to/file.ts  [imports/inherits — TicketService]
  2. path/to/other.ts [semantic match — /api/tickets]
  ...

To refresh this map at any point: /graph $TASK_ID $PROJECT_PATH
```

---

## Notes

- Re-running `/graph` on the same workspace replaces the Files in Scope section — it does not append.
- Vector and graph are complementary: vector finds files that do similar things; graph finds files that are structurally connected (imports, inheritance chains). Both are needed for a complete picture.
- If the ticket has no explicit entity names, the map will be less precise but still useful as a starting point.
- The scope map is informational — it does not replace reactive RAG queries during the task. Use it as a starting navigation map, not a complete picture.
- Graph search requires the project to be indexed with `rag_index_project`. Run `/index-project $PROJECT_PATH` if the project hasn't been indexed yet.
