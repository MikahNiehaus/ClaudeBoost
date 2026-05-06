---
description: Index a project's codebase for semantic search
allowed-tools: mcp__rag-server__rag_index_project, mcp__rag-server__rag_search
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

1. Parse the arguments:
   - If no path provided, use the primary working directory
   - If languages specified (comma-separated after path), pass as `languages` array
   - If "force" is specified, set `force=true`

2. Call `rag_index_project` with the resolved parameters.

3. Report results concisely:
   - Project ID and index location
   - Files indexed / chunks created / files skipped
   - If this was a re-index, note how many files actually changed

4. Verify with a quick search: run `rag_search(query="main entry point", scope="codebase", project_path=<path>)` and show the top 3 results to confirm it's working.
