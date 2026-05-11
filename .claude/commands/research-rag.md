---
argument-hint: <task-id> [topic] [url1 url2 ...]
description: Build a workspace-scoped research RAG from web pages, PDFs, and docs — then search it during implementation
allowed-tools: Read, Write, Edit, Bash, Glob, Grep, Agent, WebSearch, WebFetch, mcp__rag-server__rag_index_research, mcp__rag-server__rag_search, mcp__rag-server__rag_status
---

Build a per-task research RAG from external sources (web pages, PDFs, docs) scoped to the
current task workspace. The research index lives at `workspace/[task-id]/.rag-index/research/`
and does not pollute the global ClaudeBoost RAG or any project codebase index.

## Phase 0 — Init

Parse `$ARGUMENTS`:
- First token: task-id (if it matches an existing `workspace/*` directory or looks like a
  ticket ID like `AUTH-42`, `FEAT-7`). If no task-id given, ask the user.
- Remaining tokens: topic words and/or bare URLs (http/https)

Set:
- `TASK_ID` = first token
- `WORKSPACE` = absolute path to `workspace/$TASK_ID`
- `TOPIC` = remaining non-URL tokens joined as a phrase (may be empty)
- `SEED_URLS` = any http/https tokens found in arguments

If `$WORKSPACE` doesn't exist, create it with `mkdir -p`.

Read `$WORKSPACE/context.md` if it exists — use it to understand what the task is about.
If `$TOPIC` is empty and context.md exists, derive the topic from the ticket/context summary.

## Phase 1 — Source Discovery (skip if SEED_URLS covers enough sources)

If `$SEED_URLS` is empty or fewer than 3 sources:
- Run 2-3 `WebSearch` queries on `$TOPIC`. Make queries specific:
  - Primary: `$TOPIC site:docs.<relevant-domain>.com OR site:arxiv.org OR site:github.com`
  - Secondary: `$TOPIC tutorial implementation example`
  - Optional: `$TOPIC security considerations` (if security-relevant)

Score each result by domain tier (from `knowledge/research-rag.xml`):
- **Tier A** (arxiv.org, github.com, official docs, MDN, OWASP, NIST, ietf.org): auto-include
- **Tier B** (stackoverflow.com, vendor engineering blogs, dev.to, freecodecamp): include
- **Tier C** (medium.com, hashnode, personal blogs): flag — show to user, not auto-selected
- **Skip** (paywalled, social media, SEO aggregators): exclude silently

Combine `$SEED_URLS` with discovered URLs. Deduplicate.

## Phase 2 — User Approval (always pause here)

Present a source table:

```
# Sources to Index

| # | Title | URL | Tier | Format |
|---|-------|-----|------|--------|
| 1 | ...   | ... | A    | Web    |
| 2 | ...   | ... | B    | PDF    |
...
```

Ask:
> Type **all** to index all sources, **skip N,M** to exclude by number, or paste additional
> URLs to add. Reply to start indexing.

Wait for the user's response before proceeding.

Process the response:
- `all` → index everything in the table
- `skip 2,4` → remove rows 2 and 4, index the rest
- Pasted URLs → add to the list, then confirm again if count > 5 new sources added
- `cancel` or empty → abort, report nothing indexed

## Phase 3 — Index

Call `rag_index_research` with the approved source list and `workspace_path=$WORKSPACE`.

Report results per source:
- ✓ `url` — N chunks indexed (format: pdf/html/text)
- ⚠ `url` — only N chunks (may be blocked or sparse)
- ✗ `url` — error: <message>

If more than half of sources failed or returned fewer than 5 chunks each, warn the user that
the research index may be too sparse to be useful, and suggest alternatives (different URLs,
cached versions, local PDF downloads).

## Phase 4 — Verify

Run `rag_search` with:
- `scope`: `research`
- `workspace_path`: `$WORKSPACE`
- `query`: a specific concept from `$TOPIC` (not the topic itself verbatim)
- `limit`: 3

Show the top 3 results as a preview snippet (first 200 chars of content + source URL).

If 0 results returned, something went wrong — check that workspace_path is correct and
at least one source indexed successfully. Report the issue to the user.

## Phase 5 — Update context.md

Append a "Research Sources" section to `$WORKSPACE/context.md`:

```markdown
## Research Sources

Indexed: <date>
Topic: <topic>

| Source | Format | Chunks | Status |
|--------|--------|--------|--------|
| url    | html   | 23     | ok     |
...

Search with: `rag_search scope=research workspace_path=<WORKSPACE> query="<specific concept>"`
```

If `context.md` already has a "Research Sources" section, replace it.

## Done

Print:
```
Research RAG ready at `workspace/$TASK_ID/`.

Indexed: N sources, M total chunks
Query: rag_search scope=research workspace_path=<WORKSPACE> query="<concept>"
```

---

## Notes

- The research index is **per-task** and ephemeral — do not reuse across tasks.
- Re-running `/research-rag $TASK_ID` with the same URLs is safe — unchanged sources are skipped.
- To force re-index all sources: pass `force=true` to `rag_index_research` manually.
- PDF detection is automatic: `.pdf` extension or `Content-Type: application/pdf` routes to the PDF chunker.
- If a PDF is image-only (scanned), text extraction will return 0 chunks — use an OCR'd version or find an HTML alternative.
