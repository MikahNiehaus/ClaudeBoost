---
argument-hint: <task-id> [topic] [url1 url2 ...]
description: Index user-curated sources (specific URLs or PDFs) into a workspace research index — includes an approval gate before indexing. Use when you have specific docs in mind.
allowed-tools: Read, Write, Edit, Bash, Glob, Grep, Agent, WebSearch, WebFetch
---

Build a research index from sources YOU specify. You provide the URLs (or a topic for
discovery), review the source list, then approve before anything is indexed.

**When to use this vs `/research-task`:**
- `/research-rag` — you have specific docs, papers, or URLs in mind. Pauses for your
  approval before indexing. Good for one-off questions or curated deep-dives.
- `/research-task` — you want automatic source discovery from ticket entities, no
  approval pause, runs end-to-end. Good for routine pre-task research.

Both write to the same Tier 3c workspace path and auto-load when agents are spawned
with `workspace_path`. The difference is source discovery, not persistence.

The research index lives at `workspace/[task-id]/.rag-index/research/`
and does not pollute the global ClaudeBoost RAG or any project codebase index.

---

## SEARCH RULES — NEVER SKIP EITHER CALL

Every research query during implementation MUST run **both** of the following. No exceptions.

**Call 1 — Research vector search** (external content: web pages, PDFs, docs):
```
POST http://127.0.0.1:8612/search scope=research workspace_path=$WORKSPACE query="<concept>" mode=vector
```

**Call 2 — Codebase graph search** (structural neighbours from the project source):
```
POST http://127.0.0.1:8612/search scope=codebase project_path=$PROJECT_PATH query="<concept>" mode=graph
```

Rules:
- **NEVER run only one.** Both calls are mandatory on every query.
- **NEVER skip the graph call** because "research already covered it" — graph traversal finds import/inheritance neighbours that vector alone misses.
- **NEVER skip the vector call** because "you already know the codebase" — the research index has external context the codebase does not.
- If the project has not been indexed yet (POST /index not run), note it and run Call 1 only — but flag the gap explicitly.
- `mode=graph` is only meaningful for `scope=codebase`. Research scope always uses vector internally; always pass `mode=vector` explicitly to make intent clear.

---

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

If `$WORKSPACE` already exists, announce: "Resuming workspace/$TASK_ID — research index will be appended, not replaced." Do NOT re-run mkdir.
If `$WORKSPACE` does not exist, create it with `mkdir -p`.

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

Call `POST http://127.0.0.1:8612/index_research` with the approved source list and `workspace_path=$WORKSPACE`.

Report results per source:
- ✓ `url` — N chunks indexed (format: pdf/html/text)
- ⚠ `url` — only N chunks (may be blocked or sparse)
- ✗ `url` — error: <message>

If more than half of sources failed or returned fewer than 5 chunks each, warn the user that
the research index may be too sparse to be useful, and suggest alternatives (different URLs,
cached versions, local PDF downloads).

## Phase 4 — Dual-Mode Verify

Run **both** searches. NEVER skip either.

**Search A — Research vector** (verifies index content):
- `scope`: `research`
- `workspace_path`: `$WORKSPACE`
- `mode`: `vector`
- `query`: a specific concept from `$TOPIC` (not the topic verbatim)
- `limit`: 3

**Search B — Codebase graph** (verifies structural context is reachable):
- `scope`: `codebase`
- `project_path`: current project path (ask user if unknown)
- `mode`: `graph`
- `query`: same concept as Search A
- `limit`: 3

Show results from both as preview snippets (first 200 chars + source). Label which came from research vs codebase.

If Search A returns 0 results: index is broken — check workspace_path and re-run Phase 3.
If Search B returns 0 results: project not indexed — note it, proceed, flag that `POST /index` should be run before implementation begins.
If both return 0: stop and report to user before continuing.

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

Search with: `POST http://127.0.0.1:8612/search scope=research workspace_path=<WORKSPACE> query="<specific concept>"`
```

If `context.md` already has a "Research Sources" section, replace it.

## Final Step: Evidence Verification

Before printing the "Done" output, spawn a single `evaluator-agent` with this prompt:

"Read the Research Sources table that was just written to context.md for task $TASK_ID. Verify:
1. Every source marked 'ok' in the Status column has a chunk count greater than 0.
2. Every source that was in the approved list appears in the table (no silent omissions).
3. The search example query is specific enough to return meaningful results (not just the topic name verbatim).

Output a simple table:
| Source/Claim | Evidence present? | Verdict (CONFIRMED/NEEDS_EVIDENCE) |

Flag any NEEDS_EVIDENCE items (e.g., a source marked 'ok' with 0 chunks, or a missing approved source). Under 500 tokens."

Surface any NEEDS_EVIDENCE items to the user before reporting Done.

## Done

Print:
```
Research RAG ready at `workspace/$TASK_ID/`.

Indexed: N sources, M total chunks

MANDATORY dual-mode search pattern (NEVER run only one):
  POST http://127.0.0.1:8612/search scope=research  workspace_path=<WORKSPACE>    query="<concept>" mode=vector
  POST http://127.0.0.1:8612/search scope=codebase  project_path=<PROJECT_PATH>   query="<concept>" mode=graph
```

---

## Notes

- The research index is **per-task** and ephemeral — do not reuse across tasks.
- Re-running `/research-rag $TASK_ID` with the same URLs is safe — unchanged sources are skipped.
- To force re-index all sources: pass `force=true` to `POST http://127.0.0.1:8612/index_research` manually.
- PDF detection is automatic: `.pdf` extension or `Content-Type: application/pdf` routes to the PDF chunker.
- If a PDF is image-only (scanned), text extraction will return 0 chunks — use an OCR'd version or find an HTML alternative.
- `mode=graph` only works on `scope=codebase` — research scope always uses vector internally. Always pass `mode=vector` explicitly on research calls to make intent visible.
- **NEVER run only vector or only graph.** Both calls are required on every query during implementation. Graph traversal finds import/inheritance neighbours that semantic search alone misses; research vector finds external context the codebase does not contain. They are complementary, not interchangeable.
