---
description: Diagnose RAG health for a specific collection or scope
allowed-tools: Bash, Read, Write, Glob
---

# /rag-health — RAG Health Diagnostics

Run a health check on the clean-rag server and one indexed project. Every check produces ✅ PASS, ⚠️ WARN, or ❌ FAIL. Any failure = ❌ FAIL overall. Any warning with no failures = ⚠️ WARN overall.

There is one server and one kind of index: a registered project. ClaudeBoost itself is just another project. The old `knowledge`, `agents` and `memories` collections no longer exist, so there is nothing to check for them.

## Arguments

$ARGUMENTS — what to check (flexible natural language accepted):
- `project` / `codebase` / "for this project" / empty → the current working directory's project
- an absolute path → that project
- `boost` / "claudeboost" → the ClaudeBoost project at `${CLAUDEBOOST_HOME}`
- `task` / `workspace` / "for this task" → the active workspace directory
- `all` → every project listed in `/status`, server and registration checks only

---

## Instructions

### Step 1 — Server status (always first)

```bash
curl -s http://127.0.0.1:8613/status
```

The response carries `status`, `uptime_s`, `code_embedding_model`, `code_embedding_loaded`, `loaded_models`, `projects.count`, `projects.entries`, `clean_rag_home` and `ram_mb`.

Evaluate:
- ❌ FAIL if curl returns an error or connection error → output "RAG server not connected — run /clean-rag-server start." Stop immediately.
- ❌ FAIL if `status != "ready"`
- ❌ FAIL if `code_embedding_loaded == false`

Save the full status JSON for all subsequent steps.

---

### Step 2 — Resolve target from $ARGUMENTS

Map the argument (case-insensitive, fuzzy) to a project path, `workspace`, or `all`. Default to the current working directory.

For `workspace`: read the active workspace from:
```bash
cat "${CLAUDEBOOST_HOME}/state/active-workspace.json" 2>/dev/null || echo "{}"
```
Extract `workspace_path`. If empty, report ⚠️ WARN "No active workspace".

For `all`: run 3a and 3b for every entry in `projects.entries`, then skip to Step 4.

---

### Step 3 — Per-project checks

**3a. Registration check**
Find the entry in `projects.entries` whose `project_path` matches the target (compare case-insensitively, normalise slashes). Keep its key for 3d:
- ❌ FAIL if not found → "Project not indexed — run /index-project first."
- Record `files_indexed`, `files_total`, `chunks_created`, `indexed_at`, and `graph.{edges_total, edges_resolved, edges_unresolved, pagerank_nodes}`.

**3b. Files indexed count**
- ✅ PASS if `files_indexed > 0` or `chunks_created > 0`
- ⚠️ WARN if `files_total` is present and `files_indexed` is well below it → report `files_indexed/files_total`
- ❌ FAIL if both are 0 → "Nothing indexed. Run /index-project."

`files_indexed` can be low on an incremental run where most files were already current, so check 3c before calling that a fault.

**3c. Partial or refused index**
The server decides this itself. An indexing run that stopped before it reached every file, or an index built by a different embedding model, is reported back on every search as `stale_projects`. Read that verdict from the 3g response (run 3g first if not yet done).

- ✅ PASS if 3g returned no `stale_projects` key
- ⚠️ WARN if `stale_projects` names this project with `"served": true` — a partial index. Print its `reason` → "Run /index-project with force to complete it."
- ❌ FAIL if `stale_projects` names this project with `"served": false` — the index was refused outright. Print its `reason` → "Run /index-project with force to rebuild."

**3d. Manifest integrity**
The manifest lives inside clean-rag, not the project. Its directory is the project's key in `projects.entries`. Check `<clean_rag_home>/databases/_projects/<key>/manifest.json` exists and is non-empty (use Read tool):
- ✅ PASS if file exists and is non-empty
- ❌ FAIL if missing or empty → "Manifest not found — run /index-project force"

**3e. Graph liveness**
```bash
curl -s -X POST http://127.0.0.1:8613/search \
  -H "Content-Type: application/json" \
  -d '{"query": "service class method", "sources": ["project:<path>"], "mode": "graph", "limit": 3}'
```
Graph hits carry a `relation` (`imports`, `inherits`, `implements`, `calls`) and the `seed_file` they were reached from. Vector hits carry neither.
- ✅ PASS if at least one result carries `relation` — report `graph.edges_resolved/graph.edges_total`
- ⚠️ WARN if results came back but none carry `relation` while `graph.edges_total > 0` — the graph is built but added nothing for this query
- ❌ FAIL if `graph.edges_total == 0` → "No graph edges — run /index-project force"

**3f. Relevance quality**
Pick a query by the project's dominant language (look at the file extensions under the project root):
- csharp → `"public async Task service repository interface"`
- typescript → `"export interface type generic extends"`
- javascript → `"module exports require callback promise"`
- python → `"def self return async await"`
- mostly markdown (ClaudeBoost) → `"code review security error handling"`
- default → `"class method interface implementation"`

```bash
curl -s -X POST http://127.0.0.1:8613/search \
  -H "Content-Type: application/json" \
  -d '{"query": "<query>", "sources": ["project:<path>"], "mode": "vector", "limit": 5}'
```
Evaluate top result score (prose scores lower than code, so use the markdown row's threshold for ClaudeBoost):
- ✅ PASS if top score ≥ 0.68 (≥ 0.55 for markdown)
- ⚠️ WARN if 0.62–0.68 (below 0.55 for markdown)
- ❌ FAIL if < 0.62, or no results — show top 3 results with scores

**3g. Search pipeline end to end**
```bash
curl -s -X POST http://127.0.0.1:8613/search \
  -H "Content-Type: application/json" \
  -d '{"query": "main entry point", "sources": ["project:<path>"], "mode": "both", "limit": 5}'
```
The response carries `results`, `search_id`, `fallback_triggered`, and
`stale_projects` (the last only when a project's index has a known gap).
- ✅ PASS if `results` is non-empty and there is no `stale_projects` key
- ⚠️ WARN if `results` is non-empty but `stale_projects` names this project — print its `reason`; the index is partial or was refused, so a missing hit proves nothing
- ❌ FAIL if an `error` key is present, or `results` is empty — show the error

**3h. Coverage check**
Glob for unsupported file types in project path (excluding node_modules, obj, bin):
- Check for `**/*.vue`, `**/*.svelte` — these are never indexed
- ✅ PASS if no unsupported types found
- ⚠️ WARN for each unsupported extension found — report count and note it requires a code change to LANGUAGE_EXTENSIONS

**3i. .ragignore compliance**
Read `<project>/.ragignore` with the Read tool:
- ✅ PASS if no .ragignore file → "No .ragignore — all files eligible"
- For each excluded directory, search:
  ```bash
  curl -s -X POST http://127.0.0.1:8613/search \
    -H "Content-Type: application/json" \
    -d '{"query": "<dir> file module", "sources": ["project:<path>"], "mode": "vector", "limit": 3}'
  ```
  - ✅ PASS if no results from excluded directory paths
  - ❌ FAIL if results found from excluded dirs → "Exclusion not active — restart the server with /clean-rag-server stop then start"

---

#### WORKSPACE/TASK CHECKS

Run these instead of 3a–3i when the target is `workspace`.

**3j. Active workspace detection**
- ❌ FAIL if no active workspace found → "No active workspace — run /workspace to activate one"
- ✅ PASS — report workspace_path

**3k. Workspace search**
```bash
curl -s -X POST http://127.0.0.1:8613/search \
  -H "Content-Type: application/json" \
  -d '{"query": "research task documentation", "sources": ["project:<workspace_path>"], "mode": "vector", "limit": 3}'
```
- ✅ PASS if results returned with score > 0
- ⚠️ WARN if no results → a workspace directory is only searchable once it has been registered with /index-project. Most never are, so treat this as informational rather than a fault.

---

### Step 4 — Summary table

After all checks, print:

```
────────────────────────────────────────────────────────────
RAG Health Check — [target] — [date]
────────────────────────────────────────────────────────────
SCOPE        CHECK                    RESULT   DETAIL
─────────────────────────────────────────────────────────────
server       Status                   ✅ PASS  ready, CodeRankEmbed loaded
─────────────────────────────────────────────────────────────
project      Registration             ✅ PASS  indexed 2026-09-20
project      Files indexed count      ⚠️ WARN  32/375 files
project      Partial index            ⚠️ WARN  stale_projects: run stopped early
project      Manifest integrity       ✅ PASS
project      Graph liveness           ✅ PASS  222/2542 edges resolved
project      Relevance quality        ✅ PASS  0.74
project      Search pipeline          ✅ PASS  5 results
project      Coverage                 ✅ PASS
project      .ragignore compliance    ✅ PASS
─────────────────────────────────────────────────────────────
Overall: ⚠️ WARN — 0 failures, 2 warnings
─────────────────────────────────────────────────────────────
Actions needed:
  • Run /index-project with force — only 32 of 375 files indexed and the server reports the run stopped early
```

Rules:
- ❌ FAIL overall if ANY check is ❌ FAIL
- ⚠️ WARN overall if ANY check is ⚠️ WARN (and no failures)
- ✅ HEALTHY if ALL checks pass

Every FAIL and WARN must have a one-line action item in the Actions section at the bottom.
