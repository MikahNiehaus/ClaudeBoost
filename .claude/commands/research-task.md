---
argument-hint: [workspace-id] [--approve] [url1 url2 ...]
description: Auto-discover and index sources for a task based on ticket entities — fully automated, no approval pause. Use for routine pre-task research.
allowed-tools: Read, Write, Edit, Bash, Glob, Grep, Agent, WebSearch, WebFetch
---

# /research-task — Task Research Builder

Arguments: `[workspace-id] [--approve] [url1 url2 ...]`

**When to use this vs manual URL mode:**
- Default (no URLs, no `--approve`) — automatic. Reads the ticket, extracts entities from
  multiple sources, runs multi-angle web searches, indexes results without pausing. Good for
  routine pre-task research before delegating to agents.
- With URLs or `--approve` flag — manual approval gate. Discovered and provided sources are
  shown in a table; you review and confirm before anything is indexed. This replaces
  `/research-rag` for manual curation.

Both paths write to the same Tier 3c workspace path. Once indexed, every agent spawned with
`workspace_path` automatically gets the research as context.

Run this after creating a workspace but before delegating to implementation agents.

---

## Phase 0: Resolve Workspace

Parse `[workspace-id]` from arguments. Collect any `http://` or `https://` tokens as
`SEED_URLS`. Note if `--approve` flag is present.

If workspace-id not provided: check `$CLAUDEBOOST_HOME/state/active-workspace.json` for the
current workspace. If still not found, ask the user.

Resolve:
- `WORKSPACE_ID` = the workspace slug (e.g. `ASC-1199`, `knowledge-tiers-2026-06-03`)
- `WORKSPACE_ABS` = absolute path. Check in order:
  1. `$CLAUDEBOOST_HOME/workspace/$WORKSPACE_ID/` (ClaudeBoost meta-work)
  2. `state/workspaces.json` registry lookup (project workspaces)

If neither exists: error — "workspace $WORKSPACE_ID not found".

**0b — Entity Extraction from Three Sources**

Read `$WORKSPACE_ABS/ticket.md` (fall back to `context.md` if ticket.md absent). Extract:
1. Primary pattern/approach being implemented (e.g. "JWT token issuance")
2. Frameworks and libraries with versions if mentioned
3. Domain concepts and business patterns
4. External APIs or services

Then check for dependency manifests in the project root (read in order, stop when found):
- `package.json` → extract top-level keys from `dependencies` and `devDependencies`
- `requirements.txt` / `pyproject.toml` → extract package names
- `go.mod` → extract module paths from `require` block
- `Gemfile` → extract gem names
- `*.csproj` → extract `<PackageReference Include="...">` names

Then call `POST http://127.0.0.1:8612/search` with:
```json
{
  "query": "<primary ticket entity>",
  "scope": "codebase",
  "mode": "graph",
  "project_path": "<PROJECT_PATH>",
  "limit": 5
}
```
Extract library/module names from graph results not already in the entity list.

Merge all three sources into a deduplicated entity list. Cap at 8 entities. Log which came
from ticket, manifest, and codebase graph (e.g. "ticket: React, manifest: zustand, graph: react-router").

**0c — Verify project is indexed** (required for codebase search to work):

Detect project path:
1. Read `$CLAUDEBOOST_HOME/state/workspaces.json` — use `project_path` from the entry whose
   `workspace_path` was most recently modified.
2. Fall back to current working directory if no registry entry found.

Call `GET http://127.0.0.1:8612/status` and check `indexed_projects` for the detected path.

- **Indexed**: note file/chunk counts and continue.
- **Not indexed**: run `Skill(skill="index-project", args="<project_path>")` immediately. Do
  not continue until indexing completes.
- **RAG offline**: stop and tell the user to run `/rag` first.

---

## Phase 1: RAG Health Check

Call `GET http://127.0.0.1:8612/status`. If it fails: stop and tell the user to run `/rag`.

---

## Phase 2: Simplicity Guard

Check the ticket content. If the task is very simple — single-file change, pure UI tweak,
no external libraries or APIs involved — print:

```
No external research needed for this task — ticket is self-contained.
```

And stop. Do not run searches for tasks that have no external knowledge dependency.

---

## Phase 3: Multi-Angle Search

Take up to 4 entities from the extracted list (prioritise those from ticket + manifest over
codebase graph). For each entity, generate up to 6 search angles:

1. **Official docs** — `[entity] official documentation site:docs.[domain].com OR site:github.com`
2. **Security** — `[entity] security vulnerabilities common mistakes OWASP`
3. **Performance** — `[entity] performance optimization scaling best practices`
4. **Migration/upgrade** — `[entity] migration guide upgrade breaking changes`
5. **Integration patterns** — `[entity] integration patterns examples tutorial`
6. **Pitfalls/gotchas** — `[entity] gotchas pitfalls common errors troubleshooting`

Run all angles. For each, collect 1-2 URLs and score by tier:

- **Tier A** (official docs, github.com, arxiv.org, MDN, OWASP, NIST, ietf.org): auto-include
- **Tier B** (stackoverflow.com, vendor engineering blogs, dev.to, freecodecamp): include if
  clearly relevant to this entity and angle
- **Tier C** (medium.com, hashnode, personal blogs): skip unless no Tier A/B found for this angle
- **Skip**: paywalled, social media, SEO aggregators — exclude silently

Deduplicate URLs across all angles. Add any `SEED_URLS` from arguments (assign tier by
domain). Cap total URL list at 20.

---

## Phase 3b: Gap Detection Retry

After collecting URLs per angle:

- If an angle returned 0 Tier A/B sources: refine the query. Add a version number, make it
  more specific, or drop generic modifiers. Run one more search.
- Hard cap: 1 retry per angle. If still no Tier A/B after the retry, note it:
  "no authoritative source found for [entity] [angle]" — continue without blocking.
- Log each retry: `Retried [entity] [angle] with: "[refined query]" → N sources found`

---

## Phase 3c: Manual URL Mode (Approval Gate)

**Trigger**: `SEED_URLS` is non-empty OR `--approve` flag was passed.

Show the full source table BEFORE indexing:

```
# Sources to Index

| # | Title | URL | Tier | From |
|---|-------|-----|------|------|
| 1 | ...   | ... | A    | search: official docs |
| 2 | ...   | ... | A    | manual |
| 3 | ...   | ... | B    | search: security |
...
```

Ask:
> Type **all** to index everything, **skip N,M** to exclude by number, or paste more URLs.
> Reply to start indexing.

Wait for the user's response before proceeding.

Process:
- `all` → index everything in the table
- `skip 2,4` → remove those rows, index the rest
- Pasted URLs → add them to the list, re-show if more than 5 new URLs added
- `cancel` or empty → abort, report nothing indexed

**Auto mode** (no `SEED_URLS`, no `--approve`): skip the table entirely and proceed directly
to Phase 4.

---

## Phase 4: Index Research

Call `POST http://127.0.0.1:8612/index_research` with:
```json
{
  "sources": ["<url-1>", "<url-2>", ...],
  "workspace_path": "<WORKSPACE_ABS>"
}
```

Wait for the result. Collect per-source chunk counts and any errors.

If more than half of sources failed or returned fewer than 5 chunks each, warn the user that
the research index may be too sparse to be useful and suggest alternatives.

---

## Phase 5: Synthesis Layer

Write `$WORKSPACE_ABS/research-brief.md`:

```markdown
# Research Brief — [WORKSPACE_ID]

Generated: [date]
Topics researched: [entity list]
Total sources indexed: N

## Sources

| # | Source | Tier | Chunks | Angle | Key Takeaway |
|---|--------|------|--------|-------|-------------|
| 1 | [title](url) | A | 23 | Official docs | [one sentence: what this source contributes] |
| 2 | [title](url) | A | 15 | Security | [one sentence] |
...

## Coverage Summary

| Angle | Sources Found | Confidence |
|-------|--------------|------------|
| Official docs | 2 | High |
| Security | 1 | Medium |
| Performance | 0 | ⚠ No authoritative source found |
| Migration/upgrade | 1 | Medium |
| Integration patterns | 2 | High |
| Pitfalls/gotchas | 1 | Medium |

## Gaps

- [any topic/angle where no good source was found]
```

This file is NOT indexed into RAG. It lives in the workspace for humans and agents to
reference. Append a pointer to it in `$WORKSPACE_ABS/context.md` under "Research Sources":

```markdown
## Research Sources

Indexed: [date]
Research brief: [WORKSPACE_ABS]/research-brief.md

| Source | Tier | Chunks | Angle |
|--------|------|--------|-------|
| url    | A    | 23     | Official docs |
...
```

If `context.md` already has a "Research Sources" section, replace it entirely.

---

## Phase 6: Evaluator Pass

Spawn a single `evaluator-agent` with this prompt:

"Read `[WORKSPACE_ABS]/research-brief.md`. Verify:
1. Every source in the Sources table has Chunks > 0
2. The Coverage Summary has at least one angle with High or Medium confidence
3. No source that was approved/discovered is silently missing from the Sources table

Output a simple table:
| Source/Claim | Chunks > 0? | Verdict (CONFIRMED/NEEDS_EVIDENCE) |

Flag any NEEDS_EVIDENCE items. Under 400 tokens."

Surface any NEEDS_EVIDENCE items before printing the final report.

---

## Phase 7: Final Report

```
Research complete for workspace/[WORKSPACE_ID]

  Topics        : [entity list]
  Sources indexed: N (N failed)
  Research brief : workspace/[WORKSPACE_ID]/research-brief.md

  Coverage:
    ✓ Official docs      — N sources
    ✓ Security           — N sources
    ✓ Performance        — N sources
    ⚠ Migration          — no authoritative source found
    ✓ Integration        — N sources
    ✓ Pitfalls           — N sources

  Agents get research as Tier 3c context automatically when spawned
  with workspace_path="$WORKSPACE_ABS"
```

---

## Notes

- Re-running `/research-task` on the same workspace is incremental — unchanged sources are
  skipped automatically.
- Quality over quantity: 6 authoritative docs > 20 blog posts.
- If the task involves a specific library version, prefer versioned docs URLs (e.g. `/en/v8.0/`
  not `/en/latest/`).
- **When to use `--approve`**: when you have specific docs in mind and want to review the
  source table before indexing. This is the same approval-gate behavior as the retired
  `/research-rag` command.
- **Passing URLs directly**: `/research-task my-workspace https://docs.example.com` — URLs are
  auto-detected from arguments and trigger manual approval mode.
- `research-brief.md` is NOT indexed into RAG. It exists for human and agent reading only.
- `mode=graph` only works on `scope=codebase` — research scope always uses vector internally.
