---
description: Index a project's codebase for semantic search
allowed-tools: AskUserQuestion
---

# Index Project for Codebase RAG

Index the target project's source code into a per-project vector database for semantic search.

## Arguments

$ARGUMENTS — flexible, any of:
- Empty → use the current working directory
- A full path → `/index-project C:/Development/MyApp`
- A short project name → `/index-project PantryEasy`
- A fuzzy description → `/index-project the benefits app` or `/index-project nectar`
- Any of the above plus language filter → `PantryEasy python,typescript`
- Any of the above plus `force` → `PantryEasy force`

## Instructions

1. **Health check** — Before calling `GET http://127.0.0.1:8612/status`, output this exact line to the user:
   > Checking RAG server health...

   Then call `GET http://127.0.0.1:8612/status`. If the tool call is rejected, interrupted, times out, or returns any error — immediately output:
   > RAG server not connected — run `/rag` to start the server, then retry.

   Stop. Do not proceed further.

2. **Resolve the project path** from `$ARGUMENTS`:

   a. **Empty** → use the primary working directory as the project path. Done.

   b. **Full path** (starts with a drive letter like `C:/` or `/`) → use as-is.

   c. **Short name or fuzzy description** → search for a matching directory.
      - Derive the projects root dynamically:
        ```bash
        GIT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
        DEV_DIR=$(dirname "$GIT_ROOT")
        ls "$DEV_DIR/"
        [ -d "$HOME/source/repos" ] && ls "$HOME/source/repos/"
        ```
      - This finds the parent of the current git repo (your dev folder), regardless of where that is on any machine.
      - Pick the folder whose name best matches the argument — exact match first, then case-insensitive substring, then fuzzy (e.g. "nectar" matches "NectarBenefits").
      - If exactly one good match: use it, tell the user which path you resolved to.
      - If multiple plausible matches: show them and use `AskUserQuestion` to ask which one.
      - If no match: tell the user and ask them to provide the full path.

   Strip language and `force` tokens from the argument before doing path resolution:
   - Languages look like `python`, `typescript`, `csharp`, `javascript` (comma-separated)
   - `force` is the literal word `force`

3. Parse remaining tokens after path resolution:
   - If languages specified (comma-separated), pass as `languages` array
   - If `force` is specified, set `force=true`

3. **Scan first** — call `POST http://127.0.0.1:8612/scan with project_path, languages` before indexing.

4. Show the scan summary to the user in a concise table:
   - Files by language (e.g. typescript: 312, csharp: 48)
   - Skipped: gitignore count, too-large count, generated count
   - Estimated size in KB
   - Total files that will be indexed

5. **Show summary and proceed**: Display the scan summary to the user, then index automatically. No confirmation needed.

6. call POST http://127.0.0.1:8612/index with the confirmed parameters.

   **Force decision — use `force=true` ONLY when there is a genuine health problem. Never force just because the incremental run returns 0 new files.**

   | Signal | Action |
   |--------|--------|
   | User passed `force` as argument | Force — **already have permission, proceed immediately** |
   | `needs_reindex: true` in response | **STOP — ask permission** before forcing |
   | `GET /status` shows `files_indexed` < 50% of scan's `files_to_index`, AND incremental returned 0 | **STOP — ask permission** before forcing |
   | Graph resolution < 5% (edges > 0 but resolved ≈ 0) | **STOP — ask permission** before forcing |
   | Manifest file missing | **STOP — ask permission** before forcing |
   | Incremental returns 0 (all files skipped) AND coverage looks healthy | **Do NOT force** — files haven't changed, index is current |
   | Branch just switched with N changed files → incremental returned N updates | **Do NOT force** — incremental correctly picked up only the changed files |
   | Branch just switched → incremental returned 0 AND GET /status shows healthy file count | **Do NOT force** — branch contents match what's indexed |

   **Permission gate for auto-force** — when any signal above says "STOP — ask permission":
   - Explain what health issue was detected
   - Use `AskUserQuestion` to ask: "Force re-index will wipe and rebuild the index from scratch. Proceed?"
   - Only call `POST http://127.0.0.1:8612/index with force=true` after the user confirms YES
   - Never auto-force without explicit user confirmation

   **If the result contains `needs_reindex: true`** (broken index detected):
   - Show the user the `health_issues` list explaining what's wrong
   - **Stop and tell the user**: "Run `/index-project force` to rebuild the index."
   - Do NOT auto-run `force=true` — always wait for explicit user confirmation.

7. Report results concisely:
   - Files indexed / chunks created / files skipped
   - Total time if notable

8. **Post-index quality checks** — run all five checks, then auto-fix anything that can be fixed, then re-verify.

   a. **Coverage check** (Glob, no API calls) — detect unsupported file types silently excluded from the index:
      Glob for `**/*.cshtml`, `**/*.razor`, `**/*.vue`, `**/*.svelte` in the project path (excluding `node_modules`, `obj`, `bin`).
      - PASS: none found, or all found extensions were in the scan's `files_by_language` output
      - WARN: Found N .ext files not indexed — this extension is not supported by the indexer.
      - **Auto-fix**: none — this requires a code change to `LANGUAGE_EXTENSIONS` in `ClaudeBoost/mcp-rag-server/src/rag_server/core/project.py`. Report the exact file and what to add.

   b. **Graph liveness + edge resolution check** (1 search call + GET /status) — verify graph edges are activating and fully resolved:
      `POST http://127.0.0.1:8612/search with query="service class method", scope="codebase", project_path=<path>, mode="graph", limit=3`
      - PASS: `graph_augmented: true`
      - WARN: `graph_augmented: false`

      **Always call `GET http://127.0.0.1:8612/status` after the search** and check `indexed_projects[<id>]` for this project.
      Compute `unresolved = graph_edges - graph_resolved`.

      **Edge resolution sub-check (informational only — `graph_augmented` is the health signal):**
      - Report the ratio as info: e.g. "1165/1250 edges resolved (85 unresolved)".
      - Do NOT auto-fix based on unresolved percentage alone. Unresolved edges are expected for any language that imports external packages (npm, NuGet, pip) — those imports will never resolve to project files and are normal.
      - The only actionable signal is `graph_augmented: false` (handled in the auto-fix sequence below).

      Report in the summary table as: `b. Graph liveness ✓ [graph_resolved/graph_edges edges resolved]`

      **Auto-fix sequence when graph_augmented=false:**
      1. Check `GET http://127.0.0.1:8612/status`:
         - If `graph_edges = 0`: No edges were extracted — language has no graph support. Cannot auto-fix. Report: "No graph edges extracted — graph search unavailable for this language."
         - If `graph_edges > 0` AND `graph_resolved = 0`: Edges exist but none resolved (file map lookup failed). Auto-fix: re-run `POST http://127.0.0.1:8612/index with project_path, force=true)`. Re-check with `POST http://127.0.0.1:8612/search with mode="graph"`. Report FIXED or PERSISTENT.
         - If `graph_active: true` (edges AND resolved > 0) but search still returns `graph_augmented: false`: The seed files for this query have no graph neighbors. Try a second query: `POST http://127.0.0.1:8612/search with query="import module dependency", scope="codebase", project_path=<path>, mode="graph", limit=3`. If `graph_augmented: true` on retry: report PASS — graph is working, the original query's seed files happened to have no neighbors. If still false: report WARN — graph edges may be isolated.

   c. **Relevance quality check** (1 search call) — verify top scores are meaningful:
      Pick a primary query based on the dominant language from scan:
      - csharp/java/kotlin → `"class constructor dependency injection"`
      - typescript → `"interface type export function"`
      - javascript (not typescript) → `"export function module component"`
      - python → `"class method return type"`
      - other → `"function parameter return"`
      `POST http://127.0.0.1:8612/search with query=<above>, scope="codebase", project_path=<path>, limit=5`
      Evaluate:
      - PASS: top score ≥ 0.68 AND top 3 results from primary language files
      - WARN: top score 0.62–0.68
      - FAIL: top score < 0.62 OR top 3 results from irrelevant file types

      **Auto-fix sequence when WARN or FAIL:**
      1. Retry with a vocabulary-rich fallback query for the primary language:
         - csharp → `"public async Task service repository interface"`
         - typescript → `"export interface type generic extends"`
         - javascript → `"module exports require callback promise"`
         - python → `"def self return async await"`
         - other → `"class method interface implementation"`
      2. Re-run POST http://127.0.0.1:8612/search with the fallback query.
         - If new top score ≥ 0.68: report PASS — original query vocabulary didn't match codebase idioms. Show both scores.
         - If still < 0.68: report WARN with suggestion: "Re-index with a stronger embedding model (current: check `GET http://127.0.0.1:8612/status.model`). Consider `sentence-transformers/all-mpnet-base-v2` (768d) for better code semantic resolution."
      Show top 3 results with scores so the user can judge quality.

   d. **Manifest integrity** — confirm manifest was written:
      Check that `<project>/workspace/.rag-index/manifest.json` exists and is non-empty.
      - **Auto-fix**: none — if missing, re-run POST http://127.0.0.1:8612/index with `force=true`.

   e. **Context pipeline smoke test** — confirm the full `POST http://127.0.0.1:8612/context` pipeline works end-to-end:
      `POST http://127.0.0.1:8612/context with agent="explore-agent", task_description="main entry point", max_tokens=3000, project_path=<path>`
      - PASS: `tier_summary.codebase > 0`, no `tier_errors`, `total_tokens_approx` > 0
      - WARN: `tier_summary.codebase = 0`
      - FAIL: `tier_errors` key present

      **Auto-fix for tier_errors containing "dimension mismatch":**
      Re-index the ClaudeBoost knowledge base: call `POST http://127.0.0.1:8612/index with force=true, scope="all"`. Then re-run the smoke test. Report FIXED or PERSISTENT.

   f. **.ragignore compliance** — verify that any excluded directories were actually excluded:
      Read `<project>/.ragignore` using the Read tool (not a bash command).
      - If `.ragignore` does not exist: report PASS — "No .ragignore — all files eligible."
      - If `.ragignore` exists: parse the excluded directory names (strip `#` comments, trailing `/`, blank lines).
        For each excluded directory, run:
        `POST http://127.0.0.1:8612/search with query="<dir-name> file module", scope="codebase", project_path=<path>, limit=3`
        Check that no result's `source` path starts with the excluded directory name.
        - PASS: no results from excluded directories
        - WARN: results found under an excluded directory — exclusion did not take effect
        **Auto-fix when WARN:** The server loaded old code. Clear pycache and reconnect:
        ```bash
        find "$CLAUDEBOOST_HOME/mcp-rag-server" -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null
        echo "Restart the RAG HTTP server (run /rag), then re-run /index-project force"
        ```
        Report: "WARN — .ragignore not active. Clear pycache and restart the RAG server (/rag)."

   g. **Community summary health** — verify that all knowledge communities have LLM summaries:
      Run this exact command:
      ```bash
      python3 -c "
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
      "
      ```
      - PASS: summaries == communities AND communities > 0
      - SKIP: kb_graph.db not found (server not yet indexed ClaudeBoost knowledge)
      - FAIL: summaries < communities — some communities are missing summaries

      **Auto-fix when FAIL:** Call `POST http://127.0.0.1:8612/index with scope="all"` (no force — preserves cached summaries, only retries missing ones). The background thread will regenerate missing summaries using Ollama (qwen3:4b). Report: "⚠ N/M summaries — background regeneration triggered. Check server logs in ~5 minutes."

      **Do NOT block** on summary generation — it's a background process. Always proceed after triggering the fix.

   **After all auto-fixes, print a summary table:**
   ```
   ────────────────────────────────────────────────────────
   Post-Index Quality Checks
   ────────────────────────────────────────────────────────
   a. Coverage          ✓ / ⚠ [detail]
   b. Graph liveness    ✓ / ⚠ [graph_resolved/graph_edges edges resolved] [→ FIXED / cannot auto-fix]
   c. Relevance         ✓ / ⚠ [top score, query used] [→ FIXED via fallback query]
   d. Manifest          ✓ / ⚠
   e. Context pipeline  ✓ / ⚠ [→ FIXED via knowledge re-index]
   f. .ragignore        ✓ / ⚠ [excluded dirs verified / not active → restart RAG server (/rag)]
   g. Summaries         ✓ N/N / ⚠ N/N — background regen triggered / SKIP
   ────────────────────────────────────────────────────────
   ```
   End with one line: `✓ All checks passed` or `⚠ N warning(s) — [non-fixable items listed]`.
