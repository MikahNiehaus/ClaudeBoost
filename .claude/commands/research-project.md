---
argument-hint: [project-path] [topic] [url1 url2 ...]
description: Expand the project knowledge base — detects gaps, researches missing pieces, and indexes results permanently into .claudeboost/knowledge/
allowed-tools: Read, Write, Edit, Bash, Glob, Grep, WebSearch, WebFetch
---

# /research-project — Project Knowledge Base Builder

Arguments: `[project-path] [topic] [url1 url2 ...]`

Builds and expands the persistent knowledge base at `<project>/.claudeboost/knowledge/`.
Unlike `/research-task` (per-workspace, ephemeral), this KB accumulates across every
session and workspace. Every agent working on the project benefits from it permanently.

Run this when:
- Starting work on a project for the first time
- Adding a new dependency, API, or technology to the project
- An agent produced a finding that revealed a gap in project knowledge
- You want to capture an architectural decision for future agents

To add specific external docs directly to the KB, pass the URLs inline:
`/research-project /path/to/project https://docs.example.com`

---

## Phase 0 — Resolve Project Path and Seed URLs

Parse `$ARGUMENTS`:
- First token: if it looks like an absolute path or `./relative/path`, treat it as
  `PROJECT_PATH`. Otherwise use the current working directory.
- Remaining non-URL tokens: treat as `TOPIC` (joined as a phrase; may be empty).
- Any `http://` or `https://` tokens: collect as `SEED_URLS`.

Set:
- `PROJECT_PATH` = resolved absolute path
- `KB_DIR` = `$PROJECT_PATH/.claudeboost/knowledge/`
- `KB_INDEX` = `$PROJECT_PATH/.claudeboost/.rag-index/`
- `TOPIC` = optional topic phrase (may be empty)
- `SEED_URLS` = any http/https tokens found in arguments (may be empty)

Check if `$KB_DIR` exists:
- **Yes** → announce "Expanding existing project KB at `$KB_DIR`"
- **No** → announce "Initializing new project KB at `$KB_DIR`" then `mkdir -p "$KB_DIR"`

### Seed source gate (Phase 0b) — only if SEED_URLS is non-empty

Before proceeding, show the seed source table and ask for confirmation:

```
# Seed Sources

| # | URL | Tier | To KB File |
|---|-----|------|------------|
| 1 | ... | A    | stack.md   |
...
```

Guess the target KB file from the URL content — e.g. a framework docs URL → `stack.md`,
a security advisory URL → `gotchas.md`, a migration guide → `decisions.md`, an
architecture or design doc → `architecture.md`. When in doubt, default to `stack.md`.

Assign tier using the same scoring as Phase 3:
- **A** — official docs, GitHub, MDN, OWASP, arxiv, ietf.org
- **B** — Stack Overflow, vendor engineering blogs, dev.to
- **C** — Medium, personal blogs, aggregators (flag in table)

Ask: "Type **all** to add all seed sources, **skip N,M** to exclude some, or type a
KB filename to reassign a source (e.g. `3 → decisions.md`). Reply to continue."

Wait for response. On `all`, proceed with the full list. On `skip N,M`, remove those
rows. On a reassign instruction, update that row's "To KB File" column. On `cancel`,
abort and report nothing was changed.

SEED_URLS (approved ones) join the research pool for their assigned KB file in Phase 3.

---

## Phase 1 — Read Existing KB

Read all `.md` files in `$KB_DIR`. For each, note:
- File name and line count
- Topics already covered (first 200 chars of each H2 heading)

If KB is empty or missing files: all standard topics are gaps.
If KB has content: extract what's already covered so we don't duplicate it.

Standard KB files (create missing ones as empty stubs):
- `architecture.md` — project structure, main modules, entry points
- `patterns.md` — coding patterns this codebase actually uses
- `decisions.md` — key architectural decisions and the reasons behind them
- `stack.md` — language/framework specifics for this project (not generic guides)
- `gotchas.md` — edge cases, bugs, and quirks found in past sessions

---

## Phase 2 — Detect Gaps

### 2a — KB-based gap detection

Given:
- What's already in the KB
- The optional `topic` argument
- The project's actual stack (check for `package.json`, `tsconfig.json`, `*.csproj`,
  `go.mod`, `pyproject.toml`, `requirements.txt`, `pom.xml`)

Identify what's missing or thin. Examples:
- `stack.md` exists but is empty → need stack-specific research
- New topic was provided → find and index docs for it
- `architecture.md` is thin → summarize project structure from the codebase
- No `gotchas.md` content → skip (this one fills in from experience, not research)

List gaps explicitly before proceeding to Phase 2b.

### 2b — Codebase graph gap detection

Call `POST http://127.0.0.1:8612/search` with:
```json
{
  "query": "imports dependencies modules",
  "scope": "codebase",
  "mode": "graph",
  "project_path": "<PROJECT_PATH>",
  "limit": 8
}
```

Extract library and module names from the results — things appearing in import
statements, require() calls, use statements, or go.mod/pyproject.toml entries.

Cross-reference with what's already documented in `stack.md`. Any library that:
- Appears in the codebase graph AND
- Is not already documented in `stack.md`

...is a new gap. Add it to the gap list with source "codebase import".

Log: "Codebase graph found N libraries not yet in KB: [list]"

If RAG is not available or the project is not indexed: skip Phase 2b, note it in the
final report, continue with KB-based gap detection only.

---

## Phase 3 — Research Missing Pieces

For each gap that benefits from external docs (stack specifics, APIs, frameworks):

Cap at **4 gaps** per run to avoid runaway searches. If more gaps exist, note them and
suggest re-running `/research-project` after this batch is indexed.

Run up to 6 search angles per gap:

1. **Official docs** — `[gap topic] official documentation`
2. **Security** — `[gap topic] security vulnerabilities common mistakes`
3. **Performance** — `[gap topic] performance optimization best practices`
4. **Migration** — `[gap topic] migration upgrade breaking changes`
5. **Integration patterns** — `[gap topic] integration patterns examples`
6. **Pitfalls** — `[gap topic] gotchas pitfalls common errors`

Source tier scoring:
- **Tier A** (official docs, GitHub, arxiv, MDN, OWASP, NIST, ietf.org): auto-include
- **Tier B** (Stack Overflow, vendor engineering blogs, dev.to, freecodecamp): include if highly relevant
- **Tier C** (Medium, personal blogs, hashnode): include only if no Tier A/B source exists for this angle
- **Skip** (paywalled, social media, SEO aggregators): exclude silently

Collect 1-2 URLs per angle. Deduplicate across angles. Cap total URL list at 20.

Add approved SEED_URLS (from Phase 0b) to the pool for their assigned KB file.

For gaps that come from the codebase itself (architecture, patterns):
- Read the relevant source files directly — don't search the web
- Summarize what you find into the appropriate KB file

### Phase 3b — Gap detection retry

If an angle returns 0 Tier A or B sources:
1. Refine the query (add version number, add language context, try alternate phrasing)
2. Retry once — hard cap, one retry per angle
3. Log: "Retried angle [name] for [gap topic] — [found N sources | still no sources]"

If retry still returns nothing: note "No authoritative source found for [angle] — [gap topic]"
in the discovery log. Proceed.

---

## Phase 4 — Update KB Files

For each gap found:
1. Fetch the relevant URLs (use `WebFetch` to pull page content)
2. Summarize the key findings relevant to this project's use of the library
3. Append findings to the correct KB file (never overwrite existing content)
4. Add a source comment above each new content block:
   `<!-- Source: [URL] | Tier: A | Date: YYYY-MM-DD -->`
5. Use clear H2 headings so future additions don't duplicate topics

Before appending: check if a heading with the same name already exists in the file.
If it does: skip that entry and log "Skipped: [heading] already exists in [file]".

Keep entries concrete — actual patterns from this project, not generic advice.

Example format for `stack.md`:

```markdown
<!-- Source: https://react.dev/reference/react | Tier: A | Date: 2026-06-14 -->
## React (v18) — hooks pattern
This project uses custom hooks in `src/hooks/`. State lives in hooks, not components.
Never use class components — the codebase has none and tests assume functional components.

<!-- Source: https://example.com/api-docs | Tier: A | Date: 2026-06-14 -->
## API calls
All API calls go through `src/services/api.ts`. Direct `fetch()` in components is banned.
```

### Discovery log

Append a new entry to `$KB_DIR/discovery-log.md` for each gap researched on this run.
Never overwrite existing entries — this file is a permanent audit trail.

```markdown
## [YYYY-MM-DD] — [gap topic]
- Researched: [gap topic]
- Angles run: official docs, security, performance, migration, integration, pitfalls
- Sources found: N (Tier A: N, Tier B: N)
- Retried angles: [any retried angles, or "none"]
- No source found for: [any angles that returned nothing, or "none"]
- KB file updated: [file name]
```

Create `discovery-log.md` if it doesn't exist. Note: this file is **not indexed** —
it's an audit trail, not knowledge for agents.

---

## Phase 5 — Index the KB

Call `POST http://127.0.0.1:8612/index` with:
```json
{
  "project_path": "<PROJECT_PATH>",
  "force": true
}
```

This indexes the full project including `.claudeboost/knowledge/`. Check the response:
- `files_indexed` > 0: success
- `files_failed` > 0: check `errors[]`, retry once; if still failing report the specific files
- HTTP error or connection refused: run `/rag` to verify the server is up, then retry

Note: `research-brief.md` is indexed alongside the project and surfaces as structured
coverage context via `POST /context` Tier 4 results. `discovery-log.md` is not indexed —
to exclude it, add it to the project's `.ragignore` or note that the indexer skips
files named `discovery-log.md` by convention (the brief is the useful artifact; the
log is an audit trail).

Report: `N files indexed, M chunks total`.

---

## Phase 5b — Synthesis layer

After updating KB files, write or update `$KB_DIR/research-brief.md`:

```markdown
# Project Research Brief

Last updated: [YYYY-MM-DD]

## Coverage by Gap

### [Gap topic]
| # | Source | Tier | Angle | Key Takeaway |
|---|--------|------|-------|--------------|
| 1 | [title](url) | A | Official docs | [one sentence] |
| 2 | [title](url) | B | Security | [one sentence] |
...
Confidence: High / Medium / Low

### [Next gap]
...

## Uncovered Areas
- [any gap/angle with no authoritative source found]
```

Confidence rating:
- **High** — 3+ Tier A/B sources agree, no significant gaps in coverage
- **Medium** — 1-2 reputable sources, or a gap angle returned nothing
- **Low** — only Tier C sources, or multiple angles returned nothing

This file IS indexed — it helps agents understand what the KB contains and how well
a topic is covered when they call `POST /context`.

---

## Phase 6 — Report

```
Project KB updated at <PROJECT_PATH>/.claudeboost/knowledge/

Files:
  architecture.md   — N lines  [updated|unchanged|new]
  patterns.md       — N lines  [updated|unchanged|new]
  decisions.md      — N lines  [updated|unchanged|new]
  stack.md          — N lines  [updated|unchanged|new]
  gotchas.md        — N lines  [updated|unchanged|new]
  discovery-log.md  — N entries [updated|new]
  research-brief.md — [updated|new]

Coverage:
  ✓ [gap 1]   — N sources (Tier A: N, Tier B: N)
  ⚠ [gap 2]   — no authoritative source found for: [angle name]

Indexed: M chunks total

KB files are indexed alongside the project codebase. research-brief.md is indexed
as structured coverage context for agents. discovery-log.md is not indexed.
Run /research-project again any time you add a new dependency or technology.
```

---

## Notes

- This KB is per-project and persistent — it survives across workspaces and sessions.
- `/research-task` is still useful for ticket-specific research. Think of it as:
  `/research-project` for what the project always needs to know;
  `/research-task` for what this ticket specifically needs.
- Passing URLs to `/research-project` adds them directly to the project KB. For
  per-ticket research, use `/research-task` instead.
- `research-brief.md` is indexed and surfaces as structured context for agents via
  `POST /context` Tier 4. Agents see what's covered and how confident the coverage is.
- `discovery-log.md` is an audit trail only — not indexed, not surfaced to agents.
- The `.claudeboost/` folder can be committed to git — agents on other machines or in
  CI get the same accumulated knowledge.
- Never store secrets or credentials in KB files — they are indexed and surfaced to agents.
