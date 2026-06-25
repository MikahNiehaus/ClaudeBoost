---
argument-hint: [workspace-id] [--approve] [url1 url2 ...]
description: Run deep multi-angle web research for a specific task — finds hundreds of sources, fetches every one, indexes them all so agents have expert context automatically.
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

## Phase 3: Research (Source Map + Context7 + Smart Angles)

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

### Step 2: For each entity (run sequentially — no parallel agents for search)

**Workspace KB pre-check**

Before running WebSearch for this entity, check if the workspace KB already covers it from a prior run:

```bash
curl -s -X POST http://127.0.0.1:8612/search \
  -H "Content-Type: application/json" \
  -d '{"scope":"codebase","project_path":"$WORKSPACE_ABS/knowledge","query":"[entity]","limit":5}'
```

Count results with score ≥ 0.55. If 2 or more: set `has_kb_coverage = true`.
Log: `KB pre-check: [entity] — N cached docs (score ≥ 0.55) — [covered | not covered]`

If the search errors (project not indexed, server error): set `has_kb_coverage = false` and continue normally.

**2a. Source map lookup**

Read `$CLAUDEBOOST_HOME/knowledge/research-source-map.xml`.

Match in order: (1) exact `id`, (2) case-insensitive `<name>`, (3) entity in `<tags>`, (4) entity is substring of name or any tag.

If found: add all `<source>` entries to URL queue at their declared tier. Note `<context7-id>` if present. Log: `Source map hit: [entity] → N URLs`

If not found: log `Source map miss: [entity] — using WebSearch`. Set `has_context7 = false`.

**2b. Context7 (code domain + library entities with a context7-id only)**

Skip if: domain is not `code`, or `has_context7` is false, or `mcp__claude_ai_Context7__resolve-library-id` is not in the tool list.

If applicable:
1. Use `<context7-id>` from source map as `library_id`, or call `mcp__claude_ai_Context7__resolve-library-id(libraryName=entity)` if no source map entry
2. Call `mcp__claude_ai_Context7__query-docs(libraryId=library_id, query="[angle-2 query for this task type]")`
3. Write result to `$WORKSPACE_ABS/knowledge/context7-[entity-slug].md`
4. Log: `Context7: [entity] → N snippets written`

Entity is now covered — run only angle 2 (task-specific) via WebSearch. Skip angles 1 and 3.

Fallback: if Context7 returns 0 results or is unavailable — fall through to 2c normally (run all 3 angles).

**2c. Smart angles via WebSearch**

Skip entirely if `has_kb_coverage = true` (entity already covered in workspace KB from a prior run).

Select 3 angles by task type. If Context7 covered this entity: run only angle 2.

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

**Non-code domains** — 3 angles per entity, 1 phrasing each:
- legal: `[entity] legislation statute text` · `[entity] compliance requirements checklist` · `[entity] recent amendments 2025`
- design: `[entity] design system guidelines` · `[entity] accessibility WCAG` · `[entity] UX best practices`
- market: `[entity] industry report 2025` · `[entity] market trends 2025` · `[entity] competitor comparison`
- science: `[entity] research paper arxiv` · `[entity] technical specification standard` · `[entity] recent research 2025`
- general: `[entity] overview guide` · `[entity] best practices` · `[entity] common mistakes pitfalls`

### Tier Scoring

- **Tier A** — official sources, gov, academic (arxiv, pubmed, ietf), github.com, MDN, OWASP, NIST: auto-include
- **Tier B** — reputable secondary (stackoverflow, dev.to, vendor blogs, freecodecamp, industry publications): include if clearly relevant
- **Tier C** — personal blogs, medium, hashnode: **EXCLUDED** — never index
- **Skip** — paywalled, social media, SEO farms: exclude silently

### Step 3: Dedup and tier filter

Merge URLs from source map (2a), Context7 .md files (2b), and WebSearch (2c). Deduplicate. Add any `SEED_URLS` from arguments. Remove Tier C.

**Target: 15–20 sources (Tier A + Tier B). Minimum to proceed: 15.**

If below 15: log a coverage warning and continue — do not run additional WebSearch calls.

---

## Phase 3d: Manual URL Mode (Approval Gate)

**Trigger**: `SEED_URLS` is non-empty OR `--approve` flag was passed.

Show the full source table BEFORE fetching or indexing:

```
# Sources to Index

| # | Title | URL | Tier | Domain | Angle |
|---|-------|-----|------|--------|-------|
| 1 | ...   | ... | A    | legal  | Primary legislation |
| 2 | ...   | ... | A    | manual | — |
```

Ask:
> Type **all** to fetch and index everything, **skip N,M** to exclude by number, or paste more URLs.

Wait for response before proceeding.

**Auto mode** (no `SEED_URLS`, no `--approve`): skip the table and go straight to Phase 4.

---

## Phase 4: Build URL Queue and Fetch Locally

No AI agents fetch pages. Pages are downloaded by a local Python script using `httpx` + `html2text`. This avoids burning tokens on content conversion.

**Step 1 — Write the URL queue.**

Write all approved URLs to `$WORKSPACE_ABS/knowledge/pending-urls.json`:
```json
[
  {"url": "https://...", "topic": "entity-name", "tier": "A", "title": "Page title"},
  ...
]
```

Prioritize: all Tier A first, then Tier B (cap at 20). Tier C is never included.

**Step 2 — Run the local downloader.**

Determine project path from the workspace registry (`state/workspaces.json`).

```bash
"${CLAUDEBOOST_PYTHON}" "${CLAUDEBOOST_HOME}/scripts/fetch-docs.py" \
  --project-path "PROJECT_PATH" \
  --queue "WORKSPACE_ABS/knowledge/pending-urls.json" \
  --kb-dir "WORKSPACE_ABS/knowledge"
```

This downloads each URL with `httpx`, converts HTML to markdown with `html2text`, and saves to `$WORKSPACE_ABS/knowledge/`. Files that already exist are skipped.

If the script is unavailable: `pip install httpx html2text`

**Step 3 — Write the discovery log.**

Append to `$WORKSPACE_ABS/discovery-log.md`:
```markdown
## [YYYY-MM-DD] — [entity]
- Domain: [domain]
- Angles run: [list]
- Sources found: N (Tier A: N, Tier B: N)
- Files fetched: N saved, N failed
- Retried angles: [list or "none"]
- No source found for: [list or "none"]
```

`discovery-log.md` is NOT indexed — audit trail only.

If more than 30% of URLs failed: warn the user and list the failed ones.

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
  Sources indexed : N (Tier A: N, Tier B: N, N failed)
  Files saved     : knowledge/ ([N] files)

  Coverage:
    ✓ [entity 1]  — N sources
    ✓ [entity 2]  — N sources
    ⚠ [entity 3]  — no authoritative source found

  Coverage gaps (entities with < 2 Tier A sources — treat agent decisions here as less certain):
    • [entity 3] — 0 Tier A sources
    [none — all entities have 2+ Tier A sources]

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

- All collected URLs are logged to `$WORKSPACE_ABS/discovery-log.md` for audit purposes only.
- Re-running `/research-task` on the same workspace is incremental — unchanged sources are skipped automatically.
- Domain detection is automatic but you can override it by stating the domain in the ticket.
- For cross-domain tasks, note both domains in the ticket — primary drives angle selection, secondary adds supplementary angles.
- `mode=graph` only works on `scope=codebase` — research scope always uses vector internally.
- Passing URLs directly: `/research-task my-workspace https://example.com/doc.pdf` — URLs trigger manual approval mode.
