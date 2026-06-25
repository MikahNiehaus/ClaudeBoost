---
argument-hint: [workspace-id] [--approve] [url1 url2 ...]
description: Four-layer research waterfall (GitHub clone, llms.txt, BFS crawl, WebSearch) that acquires hundreds to thousands of documents per task with zero AI tokens, indexes everything into RAG so agents query via embedding instead of reading.
allowed-tools: Read, Write, Edit, Bash, Glob, Grep, Agent, WebSearch, WebFetch
---

# /research-task — Task Research Builder

Arguments: `[workspace-id] [--approve] [url1 url2 ...]`

Works for any domain — software, legal, design, market research, compliance, science, or anything else. Reads the ticket, extracts the key topics, runs multi-angle web searches, fetches every source, converts to clean markdown, and indexes everything into the workspace KB. Expertise comes from having hundreds of real authoritative documents in RAG — not from summaries.

- Default (no URLs, no `--approve`) — fully automatic. No approval gate.
- With URLs or `--approve` — shows a source table before fetching so you can review first.

Run this after creating a workspace but before delegating to implementation agents.

---

## Phase 0: Resolve Workspace

**Workspace detection (run before any other action):**

Run `get-active-workspace.py` to get the active workspace for this Claude
instance — matches the blue "WS XXXX" status bar (per-instance, not the
stale shared global file):
```bash
"${CLAUDEBOOST_PYTHON}" "${CLAUDEBOOST_HOME}/scripts/get-active-workspace.py"
```

Store `project_path` as `PROJECT_PATH` and `workspace_path` as `WORKSPACE_PATH`.
If `PROJECT_PATH` is empty: fall back to current working directory (`pwd`).

**Collision check:** if your context or memory references a different workspace
than what the script returned, print:
`[research-task] Conflict: status bar shows <X>, context/memory says <Y>. Which workspace should I use?`
Wait for the user's answer — the user is always the source of truth.

If `WORKSPACE_PATH` is empty: note it and continue.

Include `workspace_path="<WORKSPACE_PATH>"` in ALL agent spawn prompts and `/context` calls.



Parse `$ARGUMENTS`. Collect any `http://` or `https://` tokens as `SEED_URLS`. Note if `--approve` flag is present.

If workspace-id not provided: resolve from the per-instance file.
Run `workspace-status.py` (no args) or read `$CLAUDEBOOST_HOME/state/ws-instance/{instance_id}.json` keyed by current working directory. If still not found, ask the user.

Resolve:
- `WORKSPACE_ID` = the workspace slug (e.g. `ASC-1199`, `gdpr-compliance-2026-06-22`)
- `WORKSPACE_ABS` = absolute path. Check in order:
  1. `$CLAUDEBOOST_HOME/workspace/$WORKSPACE_ID/` (ClaudeBoost meta-work)
  2. `state/workspaces.json` registry lookup (project workspaces)

If neither exists: error — "workspace $WORKSPACE_ID not found".

Create `$WORKSPACE_ABS/knowledge/` directory if it doesn't exist.

---

## Phase 0b: Domain Detection and Entity Extraction

Read `$WORKSPACE_ABS/ticket.md` (fall back to `context.md` if ticket.md absent).

**Step 1 — Detect domain.** Classify the primary domain:

- **code** — software implementation, bug fix, library integration, API design, architecture
- **legal** — laws, regulations, compliance, contracts, jurisdiction rules, case law
- **design** — UI/UX, visual design, accessibility, user research, design systems
- **market** — market research, competitor analysis, industry trends, business strategy
- **science** — academic research, studies, data analysis, technical specifications
- **general** — anything that doesn't fit the above cleanly

Log: `Domain detected: [domain]`

If the ticket spans two domains, note both — primary drives angle selection, secondary adds supplementary angles.

**Step 2 — Extract entities.** Pull out the key topics to research:

1. The primary subject or goal
2. Named concepts, laws, frameworks, tools, methodologies, or standards mentioned
3. Key constraints or requirements stated
4. Any specific versions, jurisdictions, platforms, or contexts mentioned

For code tasks: also check dependency manifests in the project root (`package.json`, `requirements.txt`, `go.mod`, `Gemfile`, `*.csproj`) and merge any relevant library names into the entity list.

Deduplicate. Cap at 8 entities. Log each entity and where it came from.

---

## Phase 0c: Project Index Check (Code Tasks Only)

Skip if domain is not `code`.

Detect project path from `$CLAUDEBOOST_HOME/state/project-workspaces.json`.
Call `GET http://127.0.0.1:8612/status` and check `indexed_projects`.

- **Indexed**: note file/chunk counts and continue.
- **Not indexed**: run `Skill(skill="index-project", args="<project_path>")` immediately.
- **RAG offline**: stop and tell the user to run `/rag` first.

---

## Phase 1: RAG Health Check

Call `GET http://127.0.0.1:8612/status`. If it fails: stop and tell the user to run `/rag`.

---

## Phase 2: Simplicity Guard

If the task is genuinely self-contained — a one-line change, a pure rename, nothing with an external knowledge dependency — print:

```
No external research needed for this task — ticket is self-contained.
```

And stop.

---

## Phase 3: Research (Four Layer Waterfall)

This phase runs a four layer document acquisition waterfall for each entity. Earlier layers produce hundreds of documents with zero AI tokens. Later layers fill gaps.

| Layer | Tool | What it does | Typical yield |
|-------|------|-------------|---------------|
| 1 | `clone-docs.py` | Git sparse checkout of docs folder | 50-500 markdown files |
| 2 | `fetch-docs.py --llms-txt` | Check for llms.txt / llms-full.txt | 1 file (full content) or URL index |
| 3 | `fetch-docs.py --crawl` | BFS crawl of documentation site | 50-200 pages |
| 4 | WebSearch | Targeted angle queries (fallback) | 3-9 URLs per entity |

Each layer marks the entity as "covered" if it produces 5+ files. Covered entities skip later layers.

### Step 1: Detect task type (code domain only)

Classify the ticket using the first matching signal:

| Signal in ticket | Task type |
|------------------|-----------|
| "bug", "error", "broken", "fix", "crash", "exception", "fails" | `bugfix` |
| "integrate", "connect", "wire up", "add support for", "plugin", "setup", "configure" | `integration` |
| "security", "vulnerability", "OWASP", "CVE", "auth", "permissions" | `security` |
| "slow", "performance", "latency", "optimize", "memory", "scale", "throughput" | `performance` |
| "migrate", "upgrade", "breaking change", "version", "deprecat" | `migration` |
| anything else | `general` |

Log: `Task type: [type]`

### Step 2: For each entity (run sequentially)

**Workspace KB pre-check**

Before acquiring docs for this entity, check if the workspace KB already covers it from a prior run:

```bash
curl -s -X POST http://127.0.0.1:8612/search \
  -H "Content-Type: application/json" \
  -d '{"scope":"codebase","project_path":"$WORKSPACE_ABS/knowledge","query":"[entity]","limit":5}'
```

Count results with score >= 0.55. If 5 or more: set `has_kb_coverage = true`.
Log: `KB pre-check: [entity] — N cached docs (score >= 0.55) — [covered | not covered]`

If the search errors (project not indexed, server error): set `has_kb_coverage = false` and continue normally.

Skip the entire entity if `has_kb_coverage = true`.

**2a. Source map lookup**

Read `$CLAUDEBOOST_HOME/knowledge/research-source-map.xml`.

Match in order: (1) exact `id`, (2) case-insensitive `<name>`, (3) entity in `<tags>`, (4) entity is substring of name or any tag.

If found: note `<github-docs>`, `<doc-root>`, `<context7-id>`, and all `<source>` entries. Log: `Source map hit: [entity] → github-docs=[yes|no], doc-root=[yes|no], context7=[yes|no], N source URLs`

If not found: log `Source map miss: [entity] — falling through to Layer 4 (WebSearch)`.

**2b. Layer 1: GitHub Sparse Checkout** (code domain only)

Skip if: domain is not `code`, or no `<github-docs>` in source map for this entity.

If applicable:

```bash
"${CLAUDEBOOST_PYTHON}" C:/Development/ClaudeBoost/scripts/clone-docs.py \
  --repo "[github-docs repo]" \
  --path "[github-docs path]" \
  --branch "[github-docs branch, default main]" \
  --kb-dir "$WORKSPACE_ABS/knowledge" \
  --topic "[entity-slug]" \
  --extensions "[github-docs extensions, default .md,.mdx,.rst]"
```

Read the script output. If `files_copied >= 5`: set `layer1_covered = true`.
Log: `Layer 1 (GitHub): [entity] — [N] files cloned from [repo]`

**2c. Layer 2: llms.txt Check**

Skip if: `layer1_covered = true` (already have enough docs).

Determine the documentation domain for this entity:
- If source map has `<source>` entries: extract the domain from the first Tier A URL (e.g. `https://fastapi.tiangolo.com/` becomes `https://fastapi.tiangolo.com`)
- If no source map: skip this layer

```bash
"${CLAUDEBOOST_PYTHON}" C:/Development/ClaudeBoost/scripts/fetch-docs.py \
  --project-path "PROJECT_PATH" \
  --llms-txt "[doc-domain]" \
  --kb-dir "$WORKSPACE_ABS/knowledge" \
  --topic "[entity-slug]"
```

If the script finds and downloads llms-full.txt or indexes llms.txt URLs: set `layer2_covered = true`.
Log: `Layer 2 (llms.txt): [entity] — [found llms-full.txt | found llms.txt with N URLs | not found]`

**2d. Layer 3: BFS Crawl**

Skip if: `layer1_covered = true` OR `layer2_covered = true`.

Use `<doc-root>` from source map if present, otherwise derive from the first Tier A documentation URL.

```bash
"${CLAUDEBOOST_PYTHON}" C:/Development/ClaudeBoost/scripts/fetch-docs.py \
  --project-path "PROJECT_PATH" \
  --crawl "[doc-root url or first Tier A URL]" \
  --kb-dir "$WORKSPACE_ABS/knowledge" \
  --topic "[entity-slug]" \
  --max-pages "[doc-root max-pages, default 200]" \
  --depth 3 \
  --delay 0.5
```

If pages fetched >= 5: set `layer3_covered = true`.
Log: `Layer 3 (crawl): [entity] — [N] pages crawled from [url]`

**2e. Context7 (code domain + library entities with context7-id)**

Skip if: domain is not `code`, or no `<context7-id>`, or `mcp__claude_ai_Context7__resolve-library-id` is not in the tool list.

This runs alongside any layer, not instead of. It adds task-specific snippets.

1. Use `<context7-id>` from source map as `library_id`, or call `mcp__claude_ai_Context7__resolve-library-id(libraryName=entity)` if no source map entry
2. Call `mcp__claude_ai_Context7__query-docs(libraryId=library_id, query="[angle-2 query for this task type]")`
3. Write result to `$WORKSPACE_ABS/knowledge/context7-[entity-slug].md`
4. Log: `Context7: [entity] — N snippets written`

**2f. Layer 4: WebSearch Fallback**

Run ONLY if: none of layers 1-3 produced 5+ files for this entity. This is the fallback for niche topics, non-code domains, and entities without source map entries.

Select 3 angles by task type:

| Task type | Angle 1 | Angle 2 | Angle 3 |
|-----------|---------|---------|---------|
| bugfix | debugging | pitfalls | official-docs |
| integration | official-docs | integration-patterns | best-practices |
| security | security | best-practices | official-docs |
| performance | performance | configuration | real-world-usage |
| migration | migration-upgrade | official-docs | pitfalls |
| general | official-docs | best-practices | integration-patterns |

Use 1 query phrasing per angle:

| Angle | Query |
|-------|-------|
| official-docs | `[entity] official documentation` |
| security | `[entity] security vulnerabilities best practices` |
| performance | `[entity] performance optimization production` |
| migration-upgrade | `[entity] migration guide breaking changes` |
| integration-patterns | `[entity] integration patterns tutorial` |
| pitfalls | `[entity] common mistakes gotchas` |
| best-practices | `[entity] best practices recommended patterns` |
| debugging | `[entity] debugging common errors troubleshooting` |
| configuration | `[entity] configuration deployment settings` |
| real-world-usage | `[entity] production example site:github.com` |

**Non-code domains** always use Layer 4 (no github-docs or doc-root for legal, design, etc.):
- legal: `[entity] legislation statute text` / `[entity] compliance requirements checklist` / `[entity] recent amendments 2025`
- design: `[entity] design system guidelines` / `[entity] accessibility WCAG` / `[entity] UX best practices`
- market: `[entity] industry report 2025` / `[entity] market trends 2025` / `[entity] competitor comparison`
- science: `[entity] research paper arxiv` / `[entity] technical specification standard` / `[entity] recent research 2025`
- general: `[entity] overview guide` / `[entity] best practices` / `[entity] common mistakes pitfalls`

Add all discovered URLs (from WebSearch and source map `<source>` entries) to the URL queue for Phase 4 fetching.

### Tier Scoring (Layer 4 URLs only)

Layers 1-3 produce files directly. Tier scoring applies only to Layer 4 WebSearch results and source map `<source>` URLs.

- **Tier A** — official sources, gov, academic (arxiv, pubmed, ietf), github.com, MDN, OWASP, NIST: auto-include
- **Tier B** — reputable secondary (stackoverflow, dev.to, vendor blogs, freecodecamp, industry publications): include if clearly relevant
- **Tier C** — personal blogs, medium, hashnode: **EXCLUDED** — never index
- **Skip** — paywalled, social media, SEO farms: exclude silently

### Step 3: Collect results and dedup

After all entities complete, tally:
- Files produced by layers 1-3 (already saved to `$WORKSPACE_ABS/knowledge/`)
- URLs queued from Layer 4 WebSearch and source map `<source>` entries

Merge the Layer 4 URL list. Deduplicate. Add any `SEED_URLS` from arguments. Remove Tier C.

No cap on total files. Layers 1-3 can produce hundreds of files per entity and that's the goal.

---

## Phase 3d: Manual URL Mode (Approval Gate)

**Trigger**: `SEED_URLS` is non-empty OR `--approve` flag was passed.

Show the acquisition summary BEFORE fetching Layer 4 URLs:

```
# Research Acquisition Summary

## Layers 1-3 (already complete)
| Entity | Layer | Files | Source |
|--------|-------|-------|--------|
| react  | 1 (GitHub) | 312 | reactjs/react.dev |
| fastapi | 1 (GitHub) | 89 | fastapi/fastapi |
| ...    | ...   | ...   | ...    |

## Layer 4 URLs (pending fetch)
| # | Title | URL | Tier | Angle |
|---|-------|-----|------|-------|
| 1 | ...   | ... | A    | official-docs |
| 2 | ...   | ... | B    | best-practices |
```

Ask:
> Layers 1-3 produced **N** files. **M** Layer 4 URLs pending. Type **all** to fetch remaining, **skip N,M** to exclude by number, or paste more URLs.

Wait for response before proceeding.

**Auto mode** (no `SEED_URLS`, no `--approve`): skip the table and go straight to Phase 4.

---

## Phase 4: Fetch Layer 4 URLs

Layers 1-3 already saved their files directly. This phase fetches the remaining Layer 4 URLs (WebSearch results + source map `<source>` entries that weren't covered by earlier layers).

No AI agents fetch pages. Pages are downloaded by `fetch-docs.py` using `httpx` + `html2text`.

**Step 1 — Write the URL queue.**

Write all Layer 4 URLs to `$WORKSPACE_ABS/knowledge/pending-urls.json`:
```json
[
  {"url": "https://...", "topic": "entity-name", "tier": "A", "title": "Page title"},
  ...
]
```

Prioritize: all Tier A first, then Tier B. Tier C is never included.

**Step 2 — Run the local downloader.**

```bash
"${CLAUDEBOOST_PYTHON}" C:/Development/ClaudeBoost/scripts/fetch-docs.py \
  --project-path "PROJECT_PATH" \
  --queue "$WORKSPACE_ABS/knowledge/pending-urls.json" \
  --kb-dir "$WORKSPACE_ABS/knowledge"
```

This downloads each URL with `httpx`, converts HTML to markdown with `html2text`, and saves to `$WORKSPACE_ABS/knowledge/`. Files that already exist are skipped.

If the script is unavailable: `pip install httpx html2text`

**Step 3 — Write the discovery log.**

Append to `$WORKSPACE_ABS/discovery-log.md`:
```markdown
## [YYYY-MM-DD] — Research Run

### Per-Entity Results
| Entity | Layer Used | Files Acquired | Source |
|--------|-----------|----------------|--------|
| [entity] | 1 (GitHub) | N | [repo] |
| [entity] | 3 (crawl) | N | [url] |
| [entity] | 4 (WebSearch) | N | [angles run] |

### Layer 4 Fetch Results
- URLs queued: N
- Files fetched: N saved, N skipped (existing), N failed
- Failed URLs: [list or "none"]
```

`discovery-log.md` is NOT indexed — audit trail only.

If more than 30% of Layer 4 URLs failed: warn the user and list the failed ones.

---

## Phase 5: Final Index

```bash
curl -s --max-time 120 -X POST http://127.0.0.1:8612/index \
  -H "Content-Type: application/json" \
  -d '{"project_path": "PROJECT_PATH", "workspace_path": "WORKSPACE_ABS", "force": true}'
```

---

## Phase 6: Report

```
Research complete for workspace/[WORKSPACE_ID]

  Domain          : [detected domain]
  Topics          : [entity list]
  Total files     : N in knowledge/

  Acquisition:
    Layer 1 (GitHub clone) : N files across M entities
    Layer 2 (llms.txt)     : N files across M entities
    Layer 3 (BFS crawl)    : N files across M entities
    Layer 4 (WebSearch)    : N files across M entities

  Per-Entity:
    ✓ [entity 1]  — Layer 1: 312 files (reactjs/react.dev)
    ✓ [entity 2]  — Layer 3: 89 pages crawled
    ✓ [entity 3]  — Layer 4: 6 URLs fetched
    ⚠ [entity 4]  — Layer 4: 2 URLs (low coverage)

  Agents get this research automatically when spawned with
  workspace_path="[WORKSPACE_ABS]"
```

Update `$WORKSPACE_ABS/context.md` under "Research Sources":

```markdown
## Research Sources

Domain: [domain] | Indexed: [date]
Files: [WORKSPACE_ABS]/knowledge/ ([N] files)
Discovery log: [WORKSPACE_ABS]/discovery-log.md
```

---

## Notes

- **Four layer waterfall**: Layer 1 (GitHub clone) > Layer 2 (llms.txt) > Layer 3 (BFS crawl) > Layer 4 (WebSearch). Each entity stops at the first layer that produces 5+ files.
- **No cap on files.** Layers 1-3 can produce hundreds of files per entity. That's the goal. Embedding replaces reading.
- Re-running `/research-task` on the same workspace is incremental. `clone-docs.py` skips existing files. `fetch-docs.py` skips existing files. The KB pre-check skips fully covered entities.
- Non-code domains (legal, design, market, science) go straight to Layer 4 since there are no GitHub repos or doc sites to clone/crawl.
- Domain detection is automatic but you can override it by stating the domain in the ticket.
- For cross-domain tasks, note both domains in the ticket. Primary drives angle selection, secondary adds supplementary angles.
- `mode=graph` only works on `scope=codebase`. Research scope always uses vector internally.
- Passing URLs directly: `/research-task my-workspace https://example.com/doc.pdf` triggers manual approval mode.
- All results are logged to `$WORKSPACE_ABS/discovery-log.md` for audit purposes only.
