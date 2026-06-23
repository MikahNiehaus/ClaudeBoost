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

## Phase 2 — Multi-Angle Web Research (Parallel Agents)

Spawn **one research agent per technology in parallel** — all run concurrently. Each agent is responsible for one technology and all its search angles.

For each technology, run up to 6 search angles with multiple query phrasings per angle:

1. **Official docs** — `[tech] [version] official documentation reference`, `[tech] [version] API reference site:docs.[domain].com`, `[tech] [version] guide tutorial site:github.com`
2. **Security** — `[tech] security vulnerabilities CVE OWASP`, `[tech] [version] CVE NVD`, `[tech] security best practices NIST`
3. **Performance** — `[tech] performance optimization best practices scaling`, `[tech] [version] benchmark profiling`, `[tech] performance tuning production`
4. **Migration/upgrade** — `[tech] [version] migration guide upgrade breaking changes`, `[tech] changelog site:github.com`, `[tech] release notes`
5. **Integration patterns** — `[tech] integration patterns examples production usage`, `[tech] [version] tutorial example site:github.com`, `[tech] cookbook patterns`
6. **Pitfalls** — `[tech] common mistakes pitfalls troubleshooting`, `[tech] [version] known issues bugs site:github.com`, `[tech] anti-patterns`
7. **Best practices** — `[tech] best practices recommended patterns`, `[tech] idiomatic usage examples site:github.com`, `[tech] production usage guide`
8. **Testing** — `[tech] testing patterns unit test`, `[tech] mocking test utilities site:github.com`, `[tech] how to test [tech] integration`
9. **Debugging** — `[tech] debugging common errors troubleshooting`, `[tech] error messages diagnosis`, `[tech] logging diagnostics production`
10. **Configuration/deployment** — `[tech] configuration deployment production`, `[tech] pool sizing timeout settings`, `[tech] environment variables dangerous defaults`
11. **Real-world usage** — `[tech] site:github.com production example`, `[tech] open source project example`, `[tech] real world implementation patterns`

Source tier scoring:
- **Tier A** (official docs, github.com, arxiv.org, MDN, OWASP, NIST, ietf.org): auto-include
- **Tier B** (stackoverflow.com, vendor engineering blogs, dev.to, freecodecamp): include if clearly relevant
- **Tier C** (medium.com, hashnode, personal blogs): only if no Tier A/B found for this angle
- **Skip** (paywalled, social media, SEO aggregators): exclude silently

Each agent returns collected URLs with tier, angle, and technology labels. After all parallel agents complete, merge and deduplicate the full URL pool. Add approved SEED_URLS to the pool.

### Phase 2b — Low-source angle retry

If an angle returns fewer than 20 Tier A sources:
1. Refine and expand: add version number, try alternate phrasing, use site-specific operators
2. Run additional searches — no hard cap; keep going until 20 Tier A sources are found or queries are exhausted
3. Log: "Expanded search for [angle] / [tech] with: '[refined query]' → N sources found (total: M)"

### Phase 2c — Minimum Source Gate

Count total Tier A + Tier B sources across all technologies and angles. **Target: 50-100 sources. Minimum to proceed: 30.**

If total < 30:
1. Log: "Minimum source gate: collected N sources — target 50-100. Running expansion pass."
2. For each technology and angle with the fewest hits, run one more search with a different query
3. If still < 30 after one expansion: log "Source gate: N sources (below 30) — proceeding anyway."

Do not spawn additional agents in a loop trying to hit 300+. One expansion pass is enough.

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

Prioritize: all Tier A first, then Tier B (cap at 40), then Tier C (cap at 5).

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
