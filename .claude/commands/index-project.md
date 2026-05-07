---
description: Index a project's codebase for semantic search
allowed-tools: mcp__rag-server__rag_status, mcp__rag-server__rag_scan, mcp__rag-server__rag_index_project, mcp__rag-server__rag_search, AskUserQuestion
---

# Index Project for Codebase RAG

Index the target project's source code into a per-project vector database for semantic search.

## Arguments

$ARGUMENTS — can be:
- A project path (e.g., `/index-project C:/Development/MyApp`)
- A language filter (e.g., `/index-project C:/Development/MyApp python,typescript`)
- `force` to re-index everything (e.g., `/index-project C:/Development/MyApp force`)
- Empty — uses the current working directory

## Instructions

1. **Health check** — call `rag_status()` first. If it fails or returns an error, stop immediately and tell the user: "RAG server not connected — run `/mcp` to reconnect or restart Claude Code, then retry."

2. Parse the arguments:
   - If no path provided, use the primary working directory
   - If languages specified (comma-separated after path), pass as `languages` array
   - If "force" is specified, set `force=true`

3. **Scan first** — call `rag_scan(project_path, languages)` before indexing.

4. Show the scan summary to the user in a concise table:
   - Files by language (e.g. typescript: 312, csharp: 48)
   - Skipped: gitignore count, too-large count, generated count
   - Estimated size in KB
   - Total files that will be indexed

5. **Confirmation gate**: If `files_to_index > 500`, use `AskUserQuestion` to present the summary and ask:
   - "Proceed with all languages?" — index as-is
   - "Filter to specific languages?" — re-scan with the chosen subset, then ask again if still large
   - "Cancel" — abort

   If `files_to_index <= 500`, proceed automatically without asking.

6. Call `rag_index_project` with the confirmed parameters.

7. Report results concisely:
   - Files indexed / chunks created / files skipped
   - Total time if notable

8. Verify with a quick search: run `rag_search(query="main entry point", scope="codebase", project_path=<path>)` and show the top 3 results to confirm it's working.
