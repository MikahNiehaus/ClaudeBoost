---
description: Index a project's codebase for semantic search
allowed-tools: mcp__rag-server__rag_status, mcp__rag-server__rag_scan, mcp__rag-server__rag_index_project, mcp__rag-server__rag_search, AskUserQuestion
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

1. **Health check** — call `rag_status()` first. If it fails or returns an error, stop immediately and tell the user: "RAG server not connected — run `/mcp` to reconnect or restart Claude Code, then retry."

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

7. Report results concisely:
   - Files indexed / chunks created / files skipped
   - Total time if notable

8. Verify with a quick search: run `rag_search(query="main entry point", scope="codebase", project_path=<path>)` and show the top 3 results to confirm it's working.
