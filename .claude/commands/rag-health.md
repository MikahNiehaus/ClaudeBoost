---
description: Diagnose RAG health for a specific collection or scope
allowed-tools: Bash, Read, Write, Glob
---

# /rag-health — RAG Health Diagnostics

Run a comprehensive health check on a specific RAG collection. Every check produces ✅ PASS, ⚠️ WARN, or ❌ FAIL. Any failure = ❌ FAIL overall. Any warning with no failures = ⚠️ WARN overall.

## Arguments

$ARGUMENTS — which collection to check (flexible natural language accepted):
- `project` / `codebase` / "for this project" → project codebase index (current working dir)
- `knowledge` / "knowledge rag" / "knowledge base" → ClaudeBoost knowledge collection
- `agents` / "agent definitions" → ClaudeBoost agents collection
- `memories` / "memory" → user memories collection
- `task` / `workspace` / "for this task" / "research" → active workspace research index
- `all` / empty / "everything" → run all applicable scopes

---

## Instructions

### Step 1 — Server status (always first)

```bash
curl -s http://127.0.0.1:8612/status
```

Evaluate:
- ❌ FAIL if curl returns an error or SSL/connection error → output "RAG server not connected — run /rag to start it." Stop immediately.
- ❌ FAIL if `status != "ready"`
- ❌ FAIL if `code_model_ready == false`
- ⚠️ WARN if `dimension_mismatch` list is non-empty — note which collections are affected

Save the full status JSON for all subsequent steps.

---

### Step 2 — Resolve target from $ARGUMENTS

Map the argument (case-insensitive, fuzzy) to one of: `project`, `knowledge`, `agents`, `memories`, `workspace`, `all`.
Default to `all` if empty.

For `project`: project_path = current working directory.
For `workspace`: read active workspace from:
```bash
cat "${CLAUDEBOOST_HOME}/state/active-workspace.json" 2>/dev/null || echo "{}"
```
Extract `workspace_path`. If empty, report ⚠️ WARN "No active workspace" for that scope.

---

### Step 3 — Run per-scope checks

Only run checks matching the resolved target. For `all`, run all sections.

---

#### PROJECT CODEBASE CHECKS

**3a. Registration check**
Find the project in `indexed_projects` from the saved status by matching `project_path`:
- ❌ FAIL if not found → "Project not indexed — run /index-project first."
- Record `files_indexed`, `files_unchanged` (may be absent in older registry entries — treat as 0 if missing), `graph_edges`, `graph_resolved`, `graph_active`, `indexed_at`.

**3b. Files indexed count**
From the registry entry. `files_indexed` counts files newly embedded in the last run; `files_unchanged` counts files that were already current (hash-matched) and skipped. Together they represent the total covered by the index.

Let `effective = files_indexed + files_unchanged` (treat missing `files_unchanged` as 0).

When `effective == 0` (either `files_unchanged` is absent from the registry or both counters are 0), **fall back to the manifest count before failing**: the manifest is read in check 3d, so run 3d first if not yet done. If the manifest has entries, the index has content and the zero counters are an artifact of an old registry format — report ⚠️ WARN (old registry format, manifest OK) not ❌ FAIL.

- ✅ PASS if `effective > 0`
- ⚠️ WARN if `effective == 0` but manifest has entries → "Registry missing files_unchanged (old format) — index appears healthy via manifest. Run any incremental index to update the registry."
- ❌ FAIL if `effective == 0` AND manifest is missing or empty → "Nothing indexed. Run /index-project."

Do NOT fail solely because `files_indexed == 0`. That is normal when all files are already current.

**3c. Partial index ratio**
Scan the project to get total file count:
```bash
curl -s -X POST http://127.0.0.1:8612/scan \
  -H "Content-Type: application/json" \
  -d '{"project_path": "<path>"}'
```
Let `effective = files_indexed + files_unchanged`. When `files_unchanged` is absent, use manifest entry count as `effective` (count keys in `manifest.json` excluding `__schema_version__` and `__embedding_model__`).

Compare `effective` to `files_to_index` (from scan):
- ✅ PASS if effective >= 90% of files_to_index
- ⚠️ WARN if 50–89% → "Index may have timed out mid-run — run /index-project force"
- ❌ FAIL if < 50% → "Index is severely incomplete (N/M files). Run /index-project force."

**3d. Manifest integrity**
Check `<project>/workspace/.rag-index/manifest.json` exists and is non-empty (use Read tool):
- ✅ PASS if file exists and is non-empty
- ❌ FAIL if missing or empty → "Manifest not found — run /index-project force"

**3e. Dimension consistency**
Check `dimension_mismatch` from saved status — look for "codebase" entry:
- ✅ PASS if not in mismatch list
- ❌ FAIL if present → "Dimension mismatch in codebase — run /index-project force to rebuild"

**3f. Graph liveness**
```bash
curl -s -X POST http://127.0.0.1:8612/search \
  -H "Content-Type: application/json" \
  -d '{"query": "service class method", "scope": "codebase", "project_path": "<path>", "mode": "graph", "limit": 3}'
```
- ✅ PASS if `graph_augmented: true` — report `graph_resolved/graph_edges` from registry
- ⚠️ WARN if `graph_augmented: false` AND `graph_active: true` in registry
- ❌ FAIL if `graph_active: false` in registry → "No graph edges — run /index-project force"

**3g. Relevance quality**
Pick query by dominant language (highest count in scan.files_by_language):
- csharp → `"public async Task service repository interface"`
- typescript → `"export interface type generic extends"`
- javascript → `"module exports require callback promise"`
- python → `"def self return async await"`
- default → `"class method interface implementation"`

```bash
curl -s -X POST http://127.0.0.1:8612/search \
  -H "Content-Type: application/json" \
  -d '{"query": "<query>", "scope": "codebase", "project_path": "<path>", "limit": 5}'
```
Evaluate top result score:
- ✅ PASS if top score ≥ 0.68
- ⚠️ WARN if 0.62–0.68
- ❌ FAIL if < 0.62 — show top 3 results with scores

**3h. Context pipeline**
```bash
curl -s -X POST http://127.0.0.1:8612/context \
  -H "Content-Type: application/json" \
  -d '{"agent": "explore-agent", "task_description": "main entry point", "max_tokens": 3000, "project_path": "<path>"}'
```
- ✅ PASS if `tier_summary.codebase > 0` and no `tier_errors`
- ⚠️ WARN if `tier_summary.codebase == 0`
- ❌ FAIL if `tier_errors` key present — show the errors

**3i. Coverage check**
Glob for unsupported file types in project path (excluding node_modules, obj, bin):
- Check for `**/*.vue`, `**/*.svelte` — these are never indexed
- Check if `**/*.cshtml` / `**/*.razor` appear in the scan's `files_by_language` (they should — cshtml IS supported)
- ✅ PASS if no unsupported types found
- ⚠️ WARN for each unsupported extension found — report count and note it requires a code change to LANGUAGE_EXTENSIONS

**3j. .ragignore compliance**
Read `<project>/.ragignore` with the Read tool:
- ✅ PASS if no .ragignore file → "No .ragignore — all files eligible"
- For each excluded directory, search:
  ```bash
  curl -s -X POST http://127.0.0.1:8612/search \
    -H "Content-Type: application/json" \
    -d '{"query": "<dir> file module", "scope": "codebase", "project_path": "<path>", "limit": 3}'
  ```
  - ✅ PASS if no results from excluded directory paths
  - ❌ FAIL if results found from excluded dirs → "Exclusion not active — restart RAG server (/rag)"

---

#### KNOWLEDGE CHECKS

**3k. Collection existence**
From saved status, check `collections.knowledge.chunks`:
- ❌ FAIL if 0 → "Knowledge not indexed — run /index-boost"
- ⚠️ WARN if < 100 (expected: 1700+)
- ✅ PASS — report chunk/file counts

**3l. Dimension consistency**
Check `collections.knowledge.dim_ok` from status:
- ✅ PASS if `dim_ok: true`
- ❌ FAIL if `dim_ok: false` → report stored_dim vs active model dim → "Run /index-boost with force to rebuild"

**3m. Relevance quality**
```bash
curl -s -X POST http://127.0.0.1:8612/search \
  -H "Content-Type: application/json" \
  -d '{"query": "code review security error handling", "scope": "knowledge", "limit": 3}'
```
- ✅ PASS if top score ≥ 0.55 (prose embeddings score lower than code)
- ⚠️ WARN if top score < 0.55
- ❌ FAIL if no results returned

**3n. Community summaries health**
Write this script to `${TEMP}/cb_community_health.py` using the Write tool, then run it:
```python
import sqlite3, os
db_path = os.path.join(os.environ.get('LOCALAPPDATA', os.path.expanduser('~')), 'rag-server-index', 'kb_graph.db')
if not os.path.exists(db_path):
    print('SKIP: kb_graph.db not found')
else:
    db = sqlite3.connect(db_path)
    communities = db.execute('SELECT COUNT(DISTINCT community_id) FROM communities').fetchone()[0]
    summaries = db.execute('SELECT COUNT(*) FROM community_summaries').fetchone()[0]
    db.close()
    status = 'PASS' if summaries >= communities and communities > 0 else 'FAIL'
    print(f'{status}: {summaries}/{communities} community summaries exist')
```
Run with: `"${CLAUDEBOOST_PYTHON}" "${TEMP}/cb_community_health.py"`
- ✅ PASS if all communities have summaries
- SKIP → report as ✅ PASS (not yet indexed)
- ❌ FAIL if any missing → "Run POST /index scope=all to regenerate"

---

#### AGENTS CHECKS

**3o. Collection existence**
From saved status, check `collections.agents.chunks`:
- ❌ FAIL if 0 → "Agents not indexed — run /index-boost"
- ⚠️ WARN if < 20
- ✅ PASS — report chunk/file counts

**3p. Dimension consistency**
Check `collections.agents.dim_ok`:
- ✅ PASS if `dim_ok: true`
- ❌ FAIL if `dim_ok: false` → "Run /index-boost with force to rebuild"

**3q. Relevance quality**
```bash
curl -s -X POST http://127.0.0.1:8612/search \
  -H "Content-Type: application/json" \
  -d '{"query": "agent explore codebase task", "scope": "agents", "limit": 3}'
```
- ✅ PASS if top score ≥ 0.50
- ⚠️ WARN if top score < 0.50
- ❌ FAIL if no results

---

#### MEMORIES CHECKS

**3r. Collection existence**
From saved status, check `collections.memories.chunks`:
- ⚠️ WARN if 0 → "No memories indexed yet — this is normal for new sessions"
- ✅ PASS if chunks > 0 — report count

**3s. Dimension consistency**
Check `collections.memories.dim_ok`:
- ✅ PASS if `dim_ok: true`
- ❌ FAIL if `dim_ok: false` → report stored_dim vs active model dim → "Memories were built with a different model. Run /index-boost or re-save memories to rebuild."

---

#### WORKSPACE/TASK CHECKS

**3t. Active workspace detection**
- ❌ FAIL if no active workspace found → "No active workspace — run /workspace to activate one"
- ✅ PASS — report workspace_path

**3u. Research collection**
```bash
curl -s -X POST http://127.0.0.1:8612/search \
  -H "Content-Type: application/json" \
  -d '{"query": "research task documentation", "scope": "research", "workspace_path": "<path>", "limit": 3}'
```
- ✅ PASS if results returned with score > 0
- ⚠️ WARN if no results → "No research indexed for this workspace — run /research-task if needed"

---

### Step 4 — Summary table

After all checks, print:

```
────────────────────────────────────────────────────────────
RAG Health Check — [scope] — [date]
────────────────────────────────────────────────────────────
SCOPE        CHECK                    RESULT   DETAIL
─────────────────────────────────────────────────────────────
server       Status                   ✅ PASS  ready, 768d
server       Dimension mismatch       ✅ PASS  none
─────────────────────────────────────────────────────────────
project      Registration             ✅ PASS  indexed 2026-06-15
project      Files indexed count      ❌ FAIL  32 files (< 100)
project      Partial index ratio      ❌ FAIL  32/1636 (2%)
project      Manifest integrity       ✅ PASS
project      Dimension consistency    ✅ PASS
project      Graph liveness           ✅ PASS  150088/150532 edges
project      Relevance quality        ✅ PASS  0.74
project      Context pipeline         ⚠️ WARN  codebase tier = 0
project      Coverage                 ⚠️ WARN  287 .cshtml not in scan
project      .ragignore compliance    ✅ PASS
─────────────────────────────────────────────────────────────
knowledge    Collection               ✅ PASS  1759c / 108f
knowledge    Dimension consistency    ✅ PASS
knowledge    Relevance quality        ✅ PASS  0.61
knowledge    Community summaries      ✅ PASS  4/4
─────────────────────────────────────────────────────────────
Overall: ❌ FAIL — 2 failures, 2 warnings
─────────────────────────────────────────────────────────────
Actions needed:
  • Run /index-project force — project index is severely incomplete (32/1636 files)
```

Rules:
- ❌ FAIL overall if ANY check is ❌ FAIL
- ⚠️ WARN overall if ANY check is ⚠️ WARN (and no failures)
- ✅ HEALTHY if ALL checks pass

Every FAIL and WARN must have a one-line action item in the Actions section at the bottom.
