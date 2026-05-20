---
description: Index a project's codebase for semantic search
allowed-tools: mcp__rag-server__rag_status, mcp__rag-server__rag_scan, mcp__rag-server__rag_index_project, mcp__rag-server__rag_search, mcp__rag-server__rag_context, AskUserQuestion
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

1. **Health check** — call `rag_status()` first. If it fails or returns an error, stop immediately and tell the user: "RAG server not connected — run `/mcp` to reconnect, then retry."

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

3. **Scan first** — call `rag_scan(project_path, languages)` before indexing.

4. Show the scan summary to the user in a concise table:
   - Files by language (e.g. typescript: 312, csharp: 48)
   - Skipped: gitignore count, too-large count, generated count
   - Estimated size in KB
   - Total files that will be indexed

5. **Show summary and proceed**: Display the scan summary to the user, then index automatically. No confirmation needed.

6. Call `rag_index_project` with the confirmed parameters.

   **If the result contains `needs_reindex: true`** (broken index detected):
   - Show the user the `health_issues` list explaining what's wrong
   - Ask: "The index has pre-existing issues. Run with force=True to rebuild cleanly, or continue with the broken state?"
   - If user chooses force: re-call `rag_index_project` with `force=true`
   - If user chooses continue: proceed as-is and note the issues in the report

7. Report results concisely:
   - Files indexed / chunks created / files skipped
   - Total time if notable

8. **Post-index quality checks** — run all five. Two extra searches + one Glob. Fast but catches real gaps.

   a. **Coverage check** (Glob, no API calls) — detect unsupported file types silently excluded from the index:
      Glob for `**/*.cshtml`, `**/*.razor`, `**/*.vue`, `**/*.svelte` in the project path (excluding `node_modules`, `obj`, `bin`).
      - If any of these extensions exist AND were not in the scan's `files_by_language` output: WARN — "Found N .ext files not indexed — this extension is not supported by the indexer."
      - This catches the class of bug where an entire UI layer (Razor views, Vue components, etc.) is silently absent from the index.

   b. **Graph liveness check** (1 search call) — verify graph edges were actually built:
      `rag_search(query="service class method", scope="codebase", project_path=<path>, mode="graph", limit=3)`
      - PASS: response contains `graph_augmented: true` — structural neighbors are being added
      - WARN: `graph_augmented: false` — graph.db exists but has no edges; graph-mode searches are identical to vector-only. Note: "graph edges not built — graph search provides no benefit over vector."

   c. **Relevance quality check** (1 search call) — verify top scores are meaningful, not noise:
      Pick a query based on the primary language from scan:
      - csharp/java/kotlin → `"class constructor dependency injection"`
      - typescript/javascript → `"interface type export function"`
      - python → `"class method return type"`
      - other → `"function parameter return"`
      `rag_search(query=<above>, scope="codebase", project_path=<path>, limit=5)`
      Evaluate results:
      - PASS: top score ≥ 0.68 AND top 3 results are from primary language files
      - WARN: top score 0.62–0.68 — index is returning best-of-bad-matches; queries need to be more specific
      - FAIL: top score < 0.62 OR top 3 results are from irrelevant file types (e.g. enum files, config files for a code query)
      Show top 3 results with scores so the user can judge quality.

   d. **Manifest integrity** — confirm manifest was written:
      Check that `<project>/workspace/.rag-index/manifest.json` exists and is non-empty.

   e. **Context pipeline smoke test** — confirm the full `rag_context` pipeline works end-to-end:
      `rag_context(agent="explore-agent", task_description="main entry point", max_tokens=3000, project_path=<path>)`
      - `tier_summary.codebase > 0` — WARN if 0
      - No `tier_errors` key — FAIL if present (shows which tier broke and why)
      - `total_tokens_approx` is reasonable (not 0, not wildly over max_tokens)

   Report `✓ quality checks passed` or list each failure with its specific value and a one-line fix.
   Common fixes to show inline:
   - Coverage gap: "Add the extension to LANGUAGE_EXTENSIONS in ClaudeBoost/mcp-rag-server/src/rag_server/core/project.py, then re-index."
   - Graph not built: "GraphRAG edges may require a specific indexer flag — check rag_index_project parameters."
   - Low scores: "Use more specific, vocabulary-rich queries; or re-index with a stronger embedding model."
