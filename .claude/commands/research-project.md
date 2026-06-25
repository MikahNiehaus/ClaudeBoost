---
argument-hint: [project-path] [url1 url2 ...]
description: Four-layer research waterfall (GitHub clone, llms.txt, BFS crawl, WebSearch) that acquires hundreds to thousands of documents per project technology with zero AI tokens, indexes everything into RAG so agents query via embedding instead of reading.
allowed-tools: Read, Write, Edit, Bash, Glob, Grep, WebSearch, WebFetch
---

# /research-project — Project Stack Research Builder

Arguments: `[project-path] [url1 url2 ...]`

Reads the project's dependency files to discover the full tech stack, then runs a
four-layer document acquisition waterfall on each technology. Every source gets
fetched, converted to clean markdown, and indexed into RAG. The expertise comes
from having hundreds of real authoritative documents that agents can search
through, not from summaries. Embedding replaces reading.

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

### Seed URL gate (Phase 0b) — only if SEED_URLS is not empty

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

No cap on technologies. Layers 1-3 of the waterfall handle each technology with zero AI tokens. Layer 4 (WebSearch) is only used as a fallback for technologies not covered by earlier layers.

---

## Phase 2 — Research (Four Layer Waterfall)

This phase runs a four layer document acquisition waterfall for each technology. Earlier layers produce hundreds of documents with zero AI tokens. Later layers fill gaps.

| Layer | Tool | What it does | Typical yield |
|-------|------|-------------|---------------|
| 1 | `clone-docs.py` | Git sparse checkout of docs folder | 50-500 markdown files |
| 2 | `fetch-docs.py --llms-txt` | Check for llms.txt / llms-full.txt | 1 file (full content) or URL index |
| 3 | `fetch-docs.py --crawl` | BFS crawl of documentation site | 50-200 pages |
| 4 | WebSearch | Targeted angle queries (fallback) | 3-9 URLs per technology |

Each layer marks the technology as "covered" if it produces 5+ files. Covered technologies skip later layers.

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

Before acquiring docs for this technology, check if the project KB already covers it from a prior run:

```bash
curl -s -X POST http://127.0.0.1:8612/search \
  -H "Content-Type: application/json" \
  -d '{"scope":"codebase","project_path":"$KB_DIR","query":"[technology]","limit":5}'
```

Count results with score >= 0.55. If 5 or more: set `has_kb_coverage = true`.
Log: `KB pre-check: [technology] — N cached docs (score >= 0.55) — [covered | not covered]`

If the search errors (project not indexed, server error): set `has_kb_coverage = false` and continue normally.

Skip the entire technology if `has_kb_coverage = true`.

**2a. Source map lookup**

Read `$CLAUDEBOOST_HOME/knowledge/research-source-map.xml`.

Match in order: (1) exact `id`, (2) case-insensitive `<name>`, (3) tech in `<tags>`, (4) tech is substring of name or any tag.

If found: note `<github-docs>`, `<doc-root>`, `<context7-id>`, and all `<source>` entries. Log: `Source map hit: [tech] → github-docs=[yes|no], doc-root=[yes|no], context7=[yes|no], N source URLs`

If not found: log `Source map miss: [tech] — falling through to Layer 4 (WebSearch)`.

**2b. Layer 1: GitHub Sparse Checkout**

Skip if: no `<github-docs>` in source map for this technology.

```bash
"${CLAUDEBOOST_PYTHON}" C:/Development/ClaudeBoost/scripts/clone-docs.py \
  --repo "[github-docs repo]" \
  --path "[github-docs path]" \
  --branch "[github-docs branch, default main]" \
  --kb-dir "$KB_DIR" \
  --topic "[tech-slug]" \
  --extensions "[github-docs extensions, default .md,.mdx,.rst]"
```

Read the script output. If `files_copied >= 5`: set `layer1_covered = true`.
Log: `Layer 1 (GitHub): [tech] — [N] files cloned from [repo]`

**2c. Layer 2: llms.txt Check**

Skip if: `layer1_covered = true`.

Determine the documentation domain for this technology:
- If source map has `<source>` entries: extract the domain from the first Tier A URL
- If no source map: skip this layer

```bash
"${CLAUDEBOOST_PYTHON}" C:/Development/ClaudeBoost/scripts/fetch-docs.py \
  --project-path "PROJECT_PATH" \
  --llms-txt "[doc-domain]" \
  --kb-dir "$KB_DIR" \
  --topic "[tech-slug]"
```

If the script finds and downloads llms-full.txt or indexes llms.txt URLs: set `layer2_covered = true`.
Log: `Layer 2 (llms.txt): [tech] — [found llms-full.txt | found llms.txt with N URLs | not found]`

**2d. Layer 3: BFS Crawl**

Skip if: `layer1_covered = true` OR `layer2_covered = true`.

Use `<doc-root>` from source map if present, otherwise derive from the first Tier A documentation URL.

```bash
"${CLAUDEBOOST_PYTHON}" C:/Development/ClaudeBoost/scripts/fetch-docs.py \
  --project-path "PROJECT_PATH" \
  --crawl "[doc-root url or first Tier A URL]" \
  --kb-dir "$KB_DIR" \
  --topic "[tech-slug]" \
  --max-pages "[doc-root max-pages, default 200]" \
  --depth 3 \
  --delay 0.5
```

If pages fetched >= 5: set `layer3_covered = true`.
Log: `Layer 3 (crawl): [tech] — [N] pages crawled from [url]`

**2e. Context7 (library/framework entities with context7-id)**

Skip if: no `<context7-id>`, or `mcp__claude_ai_Context7__resolve-library-id` is not in the tool list.

This runs alongside any layer, not instead of. It adds role-specific snippets.

1. Use `<context7-id>` from source map as `library_id`, or call `mcp__claude_ai_Context7__resolve-library-id(libraryName=tech)` if no source map entry
2. Call `mcp__claude_ai_Context7__query-docs(libraryId=library_id, query="[angle-2 query for this tech role]")`
3. Write result to `$KB_DIR/context7-[tech-slug].md`
4. Log: `Context7: [tech] — N snippets written`

**2f. Layer 4: WebSearch Fallback**

Run ONLY if: none of layers 1-3 produced 5+ files for this technology. This is the fallback for niche libraries and technologies without source map entries.

Select 3 angles by tech role:

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

Add all discovered URLs (from WebSearch and source map `<source>` entries) to the URL queue for Phase 3 fetching.

### Tier Scoring (Layer 4 URLs only)

Layers 1-3 produce files directly. Tier scoring applies only to Layer 4 WebSearch results and source map `<source>` URLs.

- **Tier A** — official sources, gov, academic (arxiv, ietf), github.com, MDN, OWASP, NIST: auto-include
- **Tier B** — reputable secondary (stackoverflow, dev.to, vendor blogs, freecodecamp): include if clearly relevant
- **Tier C** — personal blogs, medium, hashnode: **EXCLUDED** — never index
- **Skip** — paywalled, social media, SEO farms: exclude silently

### Step 3: Collect results and dedup

After all technologies complete, tally:
- Files produced by layers 1-3 (already saved to `$KB_DIR`)
- URLs queued from Layer 4 WebSearch and source map `<source>` entries

Merge the Layer 4 URL list. Deduplicate. Add approved SEED_URLS. Remove Tier C.

No cap on total files. Layers 1-3 can produce hundreds of files per technology and that's the goal.

---

## Phase 3 — Fetch Layer 4 URLs

Layers 1-3 already saved their files directly. This phase fetches the remaining Layer 4 URLs (WebSearch results + source map `<source>` entries that weren't covered by earlier layers).

No AI agents fetch pages. Pages are downloaded by `fetch-docs.py` using `httpx` + `html2text`.

**Step 1 — Write the URL queue.**

Write all Layer 4 URLs to `$KB_DIR/pending-urls.json`:
```json
[
  {"url": "https://...", "topic": "playwright-python", "tier": "A", "title": "Page title"},
  ...
]
```

Prioritize: all Tier A first, then Tier B. Tier C is never included.

**Step 2 — Run the local downloader.**

```bash
"${CLAUDEBOOST_PYTHON}" C:/Development/ClaudeBoost/scripts/fetch-docs.py \
  --project-path "PROJECT_PATH" \
  --queue "$KB_DIR/pending-urls.json" \
  --kb-dir "$KB_DIR"
```

This downloads each URL with `httpx`, converts HTML to markdown with `html2text`, and saves to `$KB_DIR/`. Files that already exist are skipped.

If the script is unavailable: `pip install httpx html2text`

**Step 3 — Write the discovery log.**

Append to `$KB_DIR/discovery-log.md`:
```markdown
## [YYYY-MM-DD] — Research Run

### Per-Technology Results
| Technology | Layer Used | Files Acquired | Source |
|-----------|-----------|----------------|--------|
| [tech] | 1 (GitHub) | N | [repo] |
| [tech] | 3 (crawl) | N | [url] |
| [tech] | 4 (WebSearch) | N | [angles run] |

### Layer 4 Fetch Results
- URLs queued: N
- Files fetched: N saved, N skipped (existing), N failed
- Failed URLs: [list or "none"]
```

`discovery-log.md` is NOT indexed — audit trail only.

If more than 30% of Layer 4 URLs failed: warn the user and list the failed ones.

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

  Total files     : N in knowledge/

  Acquisition:
    Layer 1 (GitHub clone) : N files across M technologies
    Layer 2 (llms.txt)     : N files across M technologies
    Layer 3 (BFS crawl)    : N files across M technologies
    Layer 4 (WebSearch)    : N files across M technologies

  Per-Technology:
    ✓ [tech 1] ([version]) — [role] — Layer 1: N files (repo)
    ✓ [tech 2] ([version]) — [role] — Layer 3: N pages crawled
    ✓ [tech 3] ([version]) — [role] — Layer 4: N URLs fetched
    ⚠ [tech 4] ([version]) — [role] — Layer 4: 2 URLs (low coverage)

  Total: N documents indexed across M technologies.

  Agents search this KB via POST /search scope=codebase project_path=<PROJECT_PATH>.
  Run /research-project again after adding new dependencies.
```

---

## Notes

- **Four layer waterfall**: Layer 1 (GitHub clone) > Layer 2 (llms.txt) > Layer 3 (BFS crawl) > Layer 4 (WebSearch). Each technology stops at the first layer that produces 5+ files.
- **No cap on files or technologies.** Layers 1-3 can produce hundreds of files per technology. That's the goal. Embedding replaces reading.
- This skill reads **dependency manifests first** to determine what to research.
- Re-running `/research-project` is incremental. `clone-docs.py` skips existing files. `fetch-docs.py` skips existing files. The KB pre-check skips fully covered technologies.
- For ticket-specific research (task-scoped): use `/research-task` instead.
- The `.claudeboost/` folder should be committed to git so other machines get the same KB.
- Never store secrets or credentials in KB files.
