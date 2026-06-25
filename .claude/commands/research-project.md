---
argument-hint: [project-path] [url1 url2 ...]
description: Build a deep indexed knowledge base for every technology the project uses — reads dependency files, runs multi-angle web research, fetches every source, indexes everything so agents can search it.
allowed-tools: Read, Write, Edit, Bash, Glob, Grep, WebSearch, WebFetch
---

# /research-project — Project Stack Research Builder

Arguments: `[project-path] [url1 url2 ...]`

Reads the project's dependency files to discover the full tech stack, then runs deep
multi-angle web research on each technology. Every source gets fetched, converted to
clean markdown, and indexed into RAG. The expertise comes from having hundreds of real
authoritative documents that agents can search through — not from summaries.

Run this:
- When starting work on a project for the first time
- After adding a major new dependency or technology
- To add specific external docs: `/research-project /path/to/project https://docs.example.com`

---

## Phase 0 — Resolve Project Path and Seed URLs

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
`[research-project] Conflict: status bar shows <X>, context/memory says <Y>. Which workspace should I use?`
Wait for the user's answer — the user is always the source of truth.

If `WORKSPACE_PATH` is empty: note it and continue.

Include `workspace_path="<WORKSPACE_PATH>"` in ALL agent spawn prompts and `/context` calls.



Parse `$ARGUMENTS`:
- First token: if it looks like an absolute path or `./relative/path`, treat it as
  `PROJECT_PATH`. Otherwise use current working directory.
- Any `http://` or `https://` tokens: collect as `SEED_URLS`.

Set:
- `PROJECT_PATH` = resolved absolute path
- `KB_DIR` = `$PROJECT_PATH/.claudeboost/knowledge/`

Check if `$KB_DIR` exists:
- **Yes** → announce "Expanding project KB at `$KB_DIR`"
- **No** → announce "Initializing project KB at `$KB_DIR`", then `mkdir -p "$KB_DIR"`

### Seed URL gate (Phase 0b) — only if SEED_URLS is non-empty

Show the seed source table:

```
# Seed Sources

| # | URL | Tier | Notes |
|---|-----|------|-------|
| 1 | ... | A    |       |
```

Assign tier:
- **A** — official docs, GitHub, MDN, OWASP, arxiv, ietf.org
- **B** — Stack Overflow, vendor engineering blogs, dev.to
- **C** — Medium, personal blogs (flag in table)

Ask: "Type **all** to add all, **skip N,M** to exclude."
Wait for response. On `cancel`: abort. Approved SEED_URLS join the research pool in Phase 2.

---

## Phase 1 — Extract Full Tech Stack from Dependency Files

**This is the PRIMARY input.**

Read dependency manifests in the project root (check each file; collect from all that exist):

**JavaScript/TypeScript** — read `package.json`:
- Extract all keys from `dependencies` and `devDependencies`
- Note version numbers (strip `^~>=` prefix)
- Exclude tooling noise: jest, vitest, eslint, prettier, husky, typescript, @types/*
- Include: frameworks, major libraries, auth libs, API clients

**Python** — read `requirements.txt` or `pyproject.toml`:
- Extract package names and versions
- Exclude: black, flake8, mypy, isort, pytest, ruff
- Include: web framework, ORM, key libraries

**Go** — read `go.mod`:
- Extract module paths from `require` block
- Exclude: testify
- Include: web framework, DB drivers, key libraries

**Ruby** — read `Gemfile`:
- Exclude: rubocop, rspec
- Include: rails/sinatra, major gems

**.NET** — read `*.csproj`:
- Extract `<PackageReference Include="..." />` names

**Java/Kotlin** — read `pom.xml` or `build.gradle`:
- Extract dependency declarations

After reading all manifests: deduplicate, group by role:
- **Framework** — highest priority
- **Database/ORM** — high priority
- **Auth/Security** — high priority
- **External API clients** — high priority
- **Utilities** — medium priority
- **Build tooling** — skip

Log: "Extracted N technologies from dependency manifests: [list grouped by role]"

Cap at **6 technologies per run**. If the project has more, note which will be covered in subsequent runs.

---

## Phase 2 — Research (Source Map + Context7 + Smart Angles)

Run sequentially per technology — no parallel agents for search.

### Step 1: Classify tech role

Map each technology to a role using its dependency group and name:

| Role | Examples |
|------|---------|
| framework | React, Django, Rails, Express, ASP.NET, FastAPI, Next.js |
| database | PostgreSQL, SQLite, MongoDB, Redis, SQLAlchemy, Prisma |
| auth | Auth0, NextAuth, Passport, OAuth, JWT, Devise |
| utility/library | lodash, axios, httpx, numpy, boto3, date-fns |
| testing | Jest, pytest, RSpec, Cypress, Playwright |
| devops/infra | Docker, Kubernetes, Terraform, Nginx, GitHub Actions |
| unknown | anything else |

Log: `Tech role: [tech] → [role]`

### Step 2: For each technology (run sequentially)

**Project KB pre-check**

Before running WebSearch for this technology, check if the project KB already covers it from a prior run:

```bash
curl -s -X POST http://127.0.0.1:8612/search \
  -H "Content-Type: application/json" \
  -d '{"scope":"codebase","project_path":"$KB_DIR","query":"[technology]","limit":5}'
```

Count results with score ≥ 0.55. If 2 or more: set `has_kb_coverage = true`.
Log: `KB pre-check: [technology] — N cached docs (score ≥ 0.55) — [covered | not covered]`

If the search errors (project not indexed, server error): set `has_kb_coverage = false` and continue normally.

**2a. Source map lookup**

Read `$CLAUDEBOOST_HOME/knowledge/research-source-map.xml`.

Match in order: (1) exact `id`, (2) case-insensitive `<name>`, (3) tech in `<tags>`, (4) tech is substring of name or any tag.

If found: add all `<source>` entries to URL queue at their declared tier. Note `<context7-id>` if present. Log: `Source map hit: [tech] → N URLs`

If not found: log `Source map miss: [tech] — using WebSearch`. Set `has_context7 = false`.

**2b. Context7 (library/framework entities with a context7-id only)**

Skip if: `has_context7` is false, or `mcp__claude_ai_Context7__resolve-library-id` is not in the tool list.

If applicable:
1. Use `<context7-id>` from source map as `library_id`, or call `mcp__claude_ai_Context7__resolve-library-id(libraryName=tech)` if no source map entry
2. Call `mcp__claude_ai_Context7__query-docs(libraryId=library_id, query="[angle-2 query for this tech role]")`
3. Write result to `$KB_DIR/context7-[tech-slug].md`
4. Log: `Context7: [tech] → N snippets written`

Tech is now covered — run only angle 2 (role-specific) via WebSearch. Skip angles 1 and 3.

Fallback: if Context7 returns 0 results or is unavailable — fall through to 2c normally (run all 3 angles).

**2c. Smart angles via WebSearch**

Skip entirely if `has_kb_coverage = true` (technology already covered in project KB from a prior run).

Select 3 angles by tech role. If Context7 covered this tech: run only angle 2.

| Tech role | Angle 1 | Angle 2 | Angle 3 |
|-----------|---------|---------|---------|
| framework | official-docs | best-practices | integration-patterns |
| database | official-docs | performance | configuration |
| auth | security | official-docs | best-practices |
| utility/library | official-docs | integration-patterns | pitfalls |
| testing | official-docs | best-practices | integration-patterns |
| devops/infra | official-docs | configuration | real-world-usage |
| unknown | official-docs | best-practices | integration-patterns |

Use 1 query phrasing per angle:

| Angle | Query |
|-------|-------|
| official-docs | `[tech] [version] official documentation` |
| security | `[tech] security vulnerabilities best practices` |
| performance | `[tech] performance optimization production` |
| integration-patterns | `[tech] integration patterns tutorial` |
| pitfalls | `[tech] common mistakes gotchas` |
| best-practices | `[tech] best practices recommended patterns` |
| configuration | `[tech] configuration deployment settings` |
| real-world-usage | `[tech] production example site:github.com` |

### Tier Scoring

- **Tier A** — official sources, gov, academic (arxiv, ietf), github.com, MDN, OWASP, NIST: auto-include
- **Tier B** — reputable secondary (stackoverflow, dev.to, vendor blogs, freecodecamp): include if clearly relevant
- **Tier C** — personal blogs, medium, hashnode: **EXCLUDED** — never index
- **Skip** — paywalled, social media, SEO farms: exclude silently

### Step 3: Dedup and tier filter

Merge URLs from source map (2a), Context7 .md files (2b), and WebSearch (2c). Deduplicate. Add approved SEED_URLS. Remove Tier C.

**Target: 15–20 sources per technology (Tier A + Tier B). Minimum to proceed: 15 total.**

If below 15: log a coverage warning and continue — do not run additional searches.

---

## Phase 3 — Build URL Queue and Fetch Locally

No AI agents fetch pages. Pages are downloaded by a local Python script using `httpx` + `html2text`. This avoids burning tokens on content conversion.

**Step 1 — Write the URL queue.**

Write all collected URLs to `$KB_DIR/pending-urls.json`:
```json
[
  {"url": "https://...", "topic": "playwright-python", "tier": "A", "title": "Page title"},
  {"url": "https://...", "topic": "praw-reddit",       "tier": "A", "title": "..."},
  ...
]
```

Prioritize: all Tier A first, then Tier B (cap at 20). Tier C is never included.

**Step 2 — Run the local downloader.**

```bash
"${CLAUDEBOOST_PYTHON}" "${CLAUDEBOOST_HOME}/scripts/fetch-docs.py" --project-path "PROJECT_PATH"
```

This reads `pending-urls.json` from the KB dir, downloads each URL with `httpx`, converts HTML to markdown with `html2text`, and saves the result as `$KB_DIR/[topic]-[slug].md`. Files that already exist are skipped.

Check the output for any 403/404 failures and note them. No AI used — just HTTP.

If the script is unavailable (missing deps), install them:
```bash
pip install httpx html2text
```

**Step 3 — Write the discovery log.**

Append to `$KB_DIR/discovery-log.md`:
```markdown
## [YYYY-MM-DD] — [technology] [version]
- Role: [framework|database|auth|API client|utility]
- Angles searched: official docs, security, performance, migration, integration, pitfalls
- Sources found: N (Tier A: N, Tier B: N)
- Files fetched: N saved, N failed
- Retried angles: [list or "none"]
- No source found for: [list or "none"]
```

`discovery-log.md` is NOT indexed — audit trail only.

---

## Phase 4 — Final Index

```bash
curl -s --max-time 120 -X POST http://127.0.0.1:8612/index \
  -H "Content-Type: application/json" \
  -d '{"project_path": "PROJECT_PATH", "force": true}'
```

Check response:
- `files_indexed + files_unchanged` > 0: success
- `files_failed` > 0: check `errors[]`, retry once; report any persistent failures
- HTTP error or timeout: tell the user to run `/rag`, then retry

After the index completes, confirm success by checking the `indexed_projects` entry in `GET /status`.

---

## Phase 5 — Report

```
Project KB updated at <PROJECT_PATH>/.claudeboost/knowledge/

Technologies researched this run:
  ✓ [tech 1] ([version]) — [role]   — N docs indexed (Tier A: N, Tier B: N)
  ✓ [tech 2] ([version]) — [role]   — N docs indexed (Tier A: N, Tier B: N)
  ⚠ [tech 3] ([version]) — [role]   — security angle: no authoritative source found

Deferred for next run:
  - [tech 4] ([version]) — [role]
  - [tech 5] ([version]) — [role]

Total: N documents indexed across M technologies.

Agents search this KB via POST /search scope=codebase project_path=<PROJECT_PATH>.
Run /research-project again to cover deferred technologies or after adding new dependencies.
```

---

## Notes

- This skill reads **dependency manifests first** to determine what to research.
- Cap of 6 technologies per run is intentional — deep coverage of 6 beats shallow coverage of 20.
- Run `/research-project` again after the first batch to cover deferred technologies.
- For ticket-specific research (task-scoped): use `/research-task` instead.
- The `.claudeboost/` folder should be committed to git so other machines get the same KB.
- Never store secrets or credentials in KB files.
