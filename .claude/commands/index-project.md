---
description: Index a project's codebase for semantic search
allowed-tools: Bash, Read, Write, Glob, Grep, AskUserQuestion
---

# Index Project for Codebase RAG

Index the target project's source code into a per-project vector database for semantic search.

## Arguments

$ARGUMENTS — flexible, any of:
- Empty → use the current working directory
- A full path → `/index-project /home/user/myapp` (Linux/Mac) or `/index-project C:/Development/MyApp` (Windows)
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

   **Large project handling** — when `force=true` AND scan shows > 500 files:
   1. Warn the user before starting: "Large project (N files) — indexing may take several minutes."
   2. Run the index in the background and poll `/index/progress` every 30 seconds for live updates:
      ```bash
      curl -s -X POST http://127.0.0.1:8612/index \
        -H "Content-Type: application/json" \
        -d '{"project_path": "<path>", "force": true}' \
        -o "${TEMP}/rag_index_result.json" &
      INDEX_PID=$!
      echo "Indexing started (background PID $INDEX_PID)..."
      while kill -0 "$INDEX_PID" 2>/dev/null; do
        curl -s http://127.0.0.1:8612/index/progress
        sleep 30
      done
      wait "$INDEX_PID"
      cat "${TEMP}/rag_index_result.json"
      ```
   3. Report progress to the user every poll: show `files_done/files_total`, `pct%`, `eta_s`, and `current_file`.
   4. When complete, read the result from `${TEMP}/rag_index_result.json`.

   **Note on progress endpoint:** `GET http://127.0.0.1:8612/index/progress` returns live indexing state including `active`, `pct`, `files_done`, `files_total`, `eta_s`, and `current_file`. Use it to confirm the index is actually progressing, not stalled.

7. Report results concisely:
   - Files indexed / chunks created / files skipped
   - Total time if notable

8. **Post-index quality check** — run `/rag-health project` to validate the index end to end.

   `/rag-health project` covers all checks in one pass: coverage, graph liveness, relevance quality, manifest integrity, context pipeline, .ragignore compliance, partial index ratio, and community summaries. Any failure or warning includes the specific action needed. Follow those actions rather than running ad-hoc fixes.

   > Legacy inline checks (coverage, graph, relevance, manifest, context, .ragignore, summaries, partial ratio) have been replaced by `/rag-health project`. Do not run them separately.


