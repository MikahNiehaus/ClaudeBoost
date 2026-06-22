---
argument-hint: [project-path] [url1 url2 ...]
description: Build expert-level knowledge for everything the project uses — reads dependency files, researches each technology deeply from external sources, indexes permanently into .claudeboost/knowledge/
allowed-tools: Read, Write, Edit, Bash, Glob, Grep, WebSearch, WebFetch
---

# /research-project — Project Stack Expert Builder

Arguments: `[project-path] [url1 url2 ...]`

Reads the project's dependency files to discover the full tech stack, then does
deep multi-angle web research on each technology — official docs, security advisories,
performance guides, common pitfalls. The result is a permanent expert knowledge base
that every agent on every future task loads automatically.

Think of it as: "I'm new to this project — what do I need to know to become an expert
in everything it uses?" Not a gap-filler. An expertise builder.

Run this:
- When starting work on a project for the first time
- After adding a major new dependency or technology
- When an agent needs deeper knowledge of a specific library

To add specific external docs manually:
`/research-project /path/to/project https://docs.example.com`

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

Create any missing standard KB files as empty stubs:
- `stack.md` — primary output: expert knowledge per technology
- `patterns.md` — coding patterns the codebase uses
- `decisions.md` — key architectural decisions
- `gotchas.md` — edge cases, bugs, and quirks
- `architecture.md` — project structure, main modules

### Seed URL gate (Phase 0b) — only if SEED_URLS is non-empty

Before proceeding, show the seed source table:

```
# Seed Sources

| # | URL | Tier | To KB File |
|---|-----|------|------------|
| 1 | ... | A    | stack.md   |
...
```

Guess target KB file from URL content — framework/library docs → `stack.md`,
security advisory → `gotchas.md`, migration guide → `decisions.md`,
architecture doc → `architecture.md`. When in doubt: `stack.md`.

Assign tier:
- **A** — official docs, GitHub, MDN, OWASP, arxiv, ietf.org
- **B** — Stack Overflow, vendor engineering blogs, dev.to
- **C** — Medium, personal blogs (flag in table)

Ask: "Type **all** to add all, **skip N,M** to exclude, or `N → filename.md` to reassign."
Wait for response. On `cancel`: abort. Approved SEED_URLS join the research pool in Phase 3.

---

## Phase 1 — Extract Full Tech Stack from Dependency Files

**This is the PRIMARY input. Not gap analysis. Not KB inspection.**

Read dependency manifests in the project root (check each file; collect from all that exist):

**JavaScript/TypeScript** — read `package.json`:
- Extract all keys from `dependencies` and `devDependencies`
- Note version numbers (strip `^~>=` prefix)
- Exclude tooling noise: jest, vitest, eslint, prettier, husky, typescript, @types/*
- Include: the framework (React, Vue, Next.js, Express, etc.), major libraries
  (zustand, axios, prisma, etc.), auth libs (passport, next-auth), API clients (stripe, twilio)

**Python** — read `requirements.txt` or `pyproject.toml`:
- Extract package names and versions
- Exclude: black, flake8, mypy, isort, pytest, ruff
- Include: web framework (FastAPI, Django, Flask), ORM (SQLAlchemy, Tortoise), key libraries

**Go** — read `go.mod`:
- Extract module paths from `require` block
- Exclude: testify
- Include: web framework (gin, echo, fiber), DB drivers, key libraries

**Ruby** — read `Gemfile`:
- Extract gem names
- Exclude: rubocop, rspec
- Include: rails/sinatra, major gems

**.NET** — read `*.csproj`:
- Extract `<PackageReference Include="..." />` names
- Include: Entity Framework, ASP.NET packages, major NuGet packages

**Java/Kotlin** — read `pom.xml` or `build.gradle`:
- Extract dependency declarations
- Include: Spring, Hibernate, major libraries

After reading all manifests: deduplicate, group by role:
- **Framework** (React, Django, Spring, Next.js) — highest priority
- **Database/ORM** (Prisma, SQLAlchemy, GORM) — high priority
- **Auth/Security** (passport, next-auth, JWT libs) — high priority
- **External API clients** (stripe, twilio, aws-sdk, openai) — high priority
- **Utilities** (lodash, axios, zod, pydantic) — medium priority
- **Build tooling** (webpack, vite, babel) — skip

Log: "Extracted N technologies from dependency manifests: [list grouped by role]"

Cap at **6 technologies per run**, prioritising by role order above. If the project has
more, note which will be covered in subsequent runs.

---

## Phase 2 — Duplicate Heading Check

Read all existing `.md` files in `$KB_DIR`. For each technology in the research list:
- Check if a matching H2 heading already exists (case-insensitive, partial match is fine)
- **Heading exists, same version** → skip, log "Skipped [tech]: already in KB at [version]"
- **Heading exists, different version** → keep in list, note "Updating [tech]: KB has [old], now [new]"
- **No heading** → keep in list

This is the ONLY role of the existing KB in this skill — preventing duplicate effort.
We do not scan the KB for gaps. We start from what the project actually uses.

---

## Phase 3 — Multi-Angle External Research (Parallel Agents)

Spawn **one research agent per technology in parallel** — all run concurrently. Each agent is responsible for one technology and all its search angles.

For each technology, the agent runs up to 6 search angles. For each angle, run **multiple search queries** with different phrasings to maximise Tier A coverage — not just one query per angle:

1. **Official docs** — run 3-5 queries: `[tech] [version] official documentation reference`, `[tech] [version] API reference site:docs.[domain].com`, `[tech] [version] guide tutorial site:github.com`, etc.
2. **Security** — run 3-5 queries: `[tech] security vulnerabilities CVE common attacks OWASP`, `[tech] [version] CVE NVD`, `[tech] security best practices NIST`, `[tech] auth bypass injection site:owasp.org`, etc.
3. **Performance** — run 3-5 queries: `[tech] performance optimization best practices scaling`, `[tech] [version] benchmark profiling`, `[tech] performance tuning production`, etc.
4. **Migration/upgrade** — run 3-5 queries: `[tech] [version] migration guide upgrade breaking changes`, `[tech] changelog site:github.com`, `[tech] release notes`, etc.
5. **Integration patterns** — run 3-5 queries: `[tech] integration patterns examples production usage`, `[tech] [version] tutorial example site:github.com`, `[tech] cookbook patterns`, etc.
6. **Pitfalls/gotchas** — run 3-5 queries: `[tech] common mistakes gotchas pitfalls troubleshooting`, `[tech] [version] known issues bugs site:github.com`, `[tech] anti-patterns`, etc.

Source tier scoring:
- **Tier A** (official docs, github.com, arxiv.org, MDN, OWASP, NIST, ietf.org): auto-include
- **Tier B** (stackoverflow.com, vendor engineering blogs, dev.to, freecodecamp): include if clearly relevant
- **Tier C** (medium.com, hashnode, personal blogs): only if no Tier A/B found for this angle
- **Skip** (paywalled, social media, SEO aggregators): exclude silently

Collect as many Tier A URLs as possible per angle — target **20+ Tier A sources per angle**. Deduplicate across all angles for this technology.

Each agent returns its collected URLs with tier, angle, and technology labels. After all parallel agents complete, merge and deduplicate the full URL pool across all technologies. Add approved SEED_URLS to the merged pool for their assigned KB file.

### Phase 3b — Low-source angle retry

If an angle returns fewer than 20 Tier A sources after all queries:
1. Refine and expand: add version number, add primary language, try alternate phrasing, use site-specific operators
2. Run additional searches — no hard cap per angle; keep going until 20 Tier A sources are found or you've exhausted all reasonable query variations
3. Log: "Expanded search for [angle] / [tech] with: '[refined query]' → N sources found (total: M)"
4. If no further Tier A/B sources are findable after exhausting queries: log "Exhausted queries for [angle] — [tech], collected N Tier A sources", continue

### Phase 3c — Minimum Source Gate

After completing all angles for all technologies:

Count total Tier A sources collected across all technologies and all angles. **Minimum required: 1000 Tier A sources.**

If total Tier A count < 1000:
1. Log: "Minimum source gate: collected N Tier A sources — need 1000. Running expansion pass."
2. For each technology and angle with the fewest Tier A sources, run additional searches with new query variants (include related terms, alternative spellings, version aliases, ecosystem packages)
3. Keep expanding until total Tier A sources >= 1000 or all reasonable query space is exhausted
4. If total Tier A < 1000 after exhausting all queries: log "Source gate: collected N Tier A sources (below 1000 target) — query space exhausted. Proceeding with available sources."

Do not proceed to Phase 4 until this gate passes or is explicitly logged as exhausted.

---

## Phase 4 — Fetch, Index, and Write Expert Content

For each technology, in parallel:

**Step 1 — Fetch.** Use `WebFetch` to retrieve the raw content of each collected URL.

**Step 2 — Convert.** Clean and convert the fetched content into indexed-ready markdown:
- Strip HTML tags, navigation, ads, cookie banners, and repeated boilerplate — keep only substantive content
- Convert to clean markdown: preserve headings, lists, tables, and code blocks
- For PDFs: extract text, preserve section structure, discard page numbers and repeated headers
- For API docs: preserve method signatures, parameter tables, and example code
- For GitHub READMEs and changelogs: preserve version sections and breaking-change markers
- Normalize whitespace; remove duplicate blank lines

**Step 3 — Save.** Write each converted document directly to `$KB_DIR/[tech]-[slug].md`.
Do NOT create a `sources/` subdirectory — files live at the top level of `knowledge/`.
Include a source header at the top of each file:
```markdown
<!-- Source: [URL] | Tier: [A/B] | Tech: [technology] | Angle: [angle] | Fetched: [date] -->
```

Do NOT save URL lists as standalone files. URLs are telemetry only — they go in `discovery-log.md`.

**Step 4 — Index the content files.** After each technology batch:
```json
{
  "sources": ["<KB_DIR>/[tech]-[file-1].md", "<KB_DIR>/[tech]-[file-2].md", ...],
  "workspace_path": "<KB_DIR>"
}
```

If indexing fails for a file, log it and continue — don't block the phase on one failure.

**Step 5 — Synthesize.** Extract the information that makes an agent an expert in this technology and write the synthesized summary to the KB files. Both the raw indexed content and the summary are kept — they serve different purposes.

Focus on:
- What this library does and why the project likely uses it
- Security properties and known vulnerabilities
- Performance characteristics and known bottlenecks
- Version-specific behavior, especially breaking changes from prior versions
- Integration patterns relevant to the project's other dependencies
- Common mistakes and how to avoid them

Append to `stack.md` (security/pitfalls content may also go to `gotchas.md`). Format:

```markdown
<!-- Source: [URL] | Tier: A | Date: YYYY-MM-DD -->
## [Technology] ([version]) — [role in project]

### What It Does
[2-3 sentences on what this library provides and why the project uses it]

### Security
[Key security properties, known CVEs, what to watch for in code]

### Performance
[Key characteristics, what's fast, what's slow, configuration that matters]

### Pitfalls
[3-5 common mistakes specific to this version]

### Integration in This Project
[How it connects to the other libraries in this stack]
```

Before appending each block: check if a heading `## [Technology]` already exists.
If it does and the version matches: skip. (Safety net — Phase 2 removes same-version
items from the research list, but this guard catches partial-run cases where stack.md
was manually edited after Phase 2 ran.) If version differs: append a new versioned
block below the old one.

### Discovery log

Append to `$KB_DIR/discovery-log.md` for each technology researched this run. This is the ONLY place URLs are recorded — do not save URL lists anywhere else.

```markdown
## [YYYY-MM-DD] — [technology] [version]
- Role: [framework|database|auth|API client|utility]
- Angles run: official docs, security, performance, migration, integration, pitfalls
- Sources found: N (Tier A: N, Tier B: N)
- URLs (all collected, before fetch):
  - [url-1] (Tier A, official docs)
  - [url-2] (Tier B, security)
  - ...
- Files saved: [tech]-[slug-1].md, [tech]-[slug-2].md, ...
- Retried angles: [list or "none"]
- No source found for: [list or "none"]
- KB file updated: stack.md
```

`discovery-log.md` is NOT indexed — audit trail only. Agents never read it.

---

## Phase 5 — Index the KB

Call `POST http://127.0.0.1:8612/index` with:
```json
{
  "project_path": "<PROJECT_PATH>",
  "force": true
}
```

Check response:
- `files_indexed` > 0: success
- `files_failed` > 0: check `errors[]`, retry once; if still failing report the specific files
- HTTP error: tell the user to run `/rag`, then retry

### Phase 5b — Synthesis layer

Write or update `$KB_DIR/research-brief.md`:

```markdown
# Project Research Brief

Last updated: [YYYY-MM-DD]
Project: [PROJECT_PATH]

## Technologies Researched

| Technology | Version | Role | Sources | Confidence |
|------------|---------|------|---------|------------|
| [name] | [ver] | Framework | N (Tier A: N, B: N) | High/Medium/Low |
...

## Coverage by Technology

### [Technology]
| Angle | Sources | Key Takeaway |
|-------|---------|--------------|
| Official docs | N | [one sentence] |
| Security | N | [one sentence] |
| Performance | N | [one sentence] |
| Migration | N | [one sentence] |
| Integration | N | [one sentence] |
| Pitfalls | N | [one sentence] |

### [Next technology]
...

## Uncovered Areas
- [any technology/angle where no authoritative source was found]

## Deferred (run /research-project again)
- [technologies beyond the cap-6 limit, with their roles]
```

Confidence:
- **High** — 3+ Tier A/B sources, all 6 angles covered
- **Medium** — 2-3 sources, or 1-2 angles uncovered
- **Low** — only Tier C sources, or 3+ angles uncovered

`research-brief.md` IS indexed — agents see coverage confidence when they call `POST /context`.

---

## Phase 6 — Evaluator Pass

Spawn a single `evaluator-agent` with this prompt:

"First action: call POST http://127.0.0.1:8612/context with:
{\"agent\":\"evaluator-agent\",\"task_description\":\"verify research-brief.md coverage for project stack research\",\"project_path\":\"<PROJECT_PATH>\"}

Then read `[KB_DIR]/research-brief.md`. Verify:
1. Every technology in the Technologies Researched table has at least one Tier A or Tier B source
2. The Coverage by Technology section has an entry for each technology in the table
3. No technology that appears in `[KB_DIR]/discovery-log.md` under today's date is missing
   from research-brief.md

Output a simple table:
| Technology | Tier A/B sources? | In brief? | Verdict (CONFIRMED/NEEDS_EVIDENCE) |

Flag NEEDS_EVIDENCE items. End your response with ## Summary (≤300 words) only."

Surface any NEEDS_EVIDENCE items before printing the final report.

---

## Phase 7 — Report

```
Project KB updated at <PROJECT_PATH>/.claudeboost/knowledge/

Technologies researched this run:
  ✓ [tech 1] ([version]) — [role]   — N sources (Tier A: N, Tier B: N)
  ✓ [tech 2] ([version]) — [role]   — N sources (Tier A: N, Tier B: N)
  ⚠ [tech 3] ([version]) — [role]   — security angle: no authoritative source found

Deferred for next run:
  - [tech 4] ([version]) — [role]
  - [tech 5] ([version]) — [role]

KB files:
  stack.md          — N lines  [updated|new]
  gotchas.md        — N lines  [updated|unchanged]
  discovery-log.md  — N entries [updated|new]
  research-brief.md — [updated|new]

Indexed: N files, M chunks

research-brief.md is indexed — agents get stack expertise via POST /context automatically.
Run /research-project again to cover deferred technologies or after adding new dependencies.
```

---

## Notes

- This skill reads **dependency manifests first**, not the existing KB. The KB is only
  checked to avoid writing duplicate headings.
- Cap of 6 technologies per run is intentional — quality beats breadth. Deep coverage
  of 6 is more useful than shallow coverage of 20.
- Run `/research-project` again after the first batch completes to cover deferred technologies.
- For ticket-specific research (ephemeral, task-scoped): use `/research-task` instead.
- `research-brief.md` is indexed and surfaces as structured context for agents via
  `POST /context` Tier 4.
- `discovery-log.md` is audit trail only — not indexed, not surfaced to agents.
- The `.claudeboost/` folder should be committed to git — other machines and CI
  get the same accumulated expertise.
- Never store secrets or credentials in KB files.
