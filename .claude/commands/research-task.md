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

## Phase 3: Multi-Angle Search (Parallel Agents)

Spawn **one search agent per entity in parallel** — all run concurrently.

Each agent handles its own entity across 6 angles with 3 query phrasings per angle.

### Domain-Specific Angles

**code:**
1. Official docs — `[entity] official documentation`, `[entity] API reference site:github.com`, `[entity] guide site:docs.[domain].com`
2. Security — `[entity] security vulnerabilities OWASP`, `[entity] CVE NVD`, `[entity] security best practices NIST`
3. Performance — `[entity] performance optimization`, `[entity] benchmark profiling`, `[entity] scaling production`
4. Migration/upgrade — `[entity] migration guide breaking changes`, `[entity] changelog site:github.com`, `[entity] upgrade guide`
5. Integration patterns — `[entity] integration examples tutorial`, `[entity] cookbook site:github.com`, `[entity] production patterns`
6. Pitfalls — `[entity] common mistakes gotchas`, `[entity] anti-patterns known issues site:github.com`, `[entity] troubleshooting`

**legal:**
1. Primary legislation — `[entity] legislation statute text`, `[entity] act law site:gov`, `[entity] regulation official text`
2. Case law — `[entity] case law court decision`, `[entity] legal precedent ruling`, `[entity] court judgment`
3. Regulatory guidance — `[entity] regulatory guidance official`, `[entity] compliance guidance site:gov`, `[entity] regulatory FAQ`
4. Compliance requirements — `[entity] compliance requirements checklist`, `[entity] legal obligations`, `[entity] penalties enforcement`
5. Jurisdiction specifics — `[entity] specific rules`, `[entity] state federal differences`, `[entity] international variation`
6. Recent changes — `[entity] recent amendments 2024 2025`, `[entity] law update changes`, `[entity] proposed regulations`

**design:**
1. Design standards — `[entity] design system guidelines`, `[entity] UI component patterns`, `[entity] design specification`
2. Accessibility — `[entity] accessibility WCAG`, `[entity] a11y requirements`, `[entity] screen reader support`
3. User research — `[entity] user research findings`, `[entity] usability study`, `[entity] UX research data`
4. Pattern libraries — `[entity] UI pattern library`, `[entity] component library examples`, `[entity] design pattern`
5. Best practices — `[entity] UX best practices`, `[entity] design principles`, `[entity] interface design guidelines`
6. Case studies — `[entity] design case study`, `[entity] before after redesign`, `[entity] UX improvement results`

**market:**
1. Industry reports — `[entity] industry report 2024 2025`, `[entity] market size statistics`, `[entity] market analysis`
2. Competitor analysis — `[entity] competitor comparison`, `[entity] competitive landscape`, `[entity] vs alternatives`
3. Market trends — `[entity] market trends 2024 2025`, `[entity] growth forecast`, `[entity] emerging trends`
4. Consumer behavior — `[entity] consumer behavior research`, `[entity] user survey data`, `[entity] customer insights`
5. Business strategy — `[entity] strategy framework`, `[entity] business model`, `[entity] go to market`
6. Data and statistics — `[entity] statistics data`, `[entity] survey results`, `[entity] site:statista.com OR site:pewresearch.org`

**science:**
1. Primary research — `[entity] research paper arxiv`, `[entity] study findings site:pubmed.ncbi.nlm.nih.gov`, `[entity] academic paper`
2. Reviews — `[entity] systematic review`, `[entity] meta-analysis`, `[entity] literature review`
3. Specifications/standards — `[entity] technical specification`, `[entity] standard IEEE ISO`, `[entity] RFC ietf.org`
4. Data sets — `[entity] dataset open data`, `[entity] benchmark data`, `[entity] experimental results`
5. Expert consensus — `[entity] expert consensus`, `[entity] scientific consensus`, `[entity] position statement`
6. Recent developments — `[entity] recent research 2024 2025`, `[entity] new findings`, `[entity] latest study`

**general:**
1. Overview — `[entity] overview guide`, `[entity] introduction explained`, `[entity] what is [entity]`
2. Best practices — `[entity] best practices`, `[entity] recommended approach`, `[entity] how to`
3. Case studies — `[entity] case study example`, `[entity] real world example`, `[entity] success story`
4. Expert opinion — `[entity] expert opinion analysis`, `[entity] in depth guide`
5. Data/evidence — `[entity] data statistics evidence`, `[entity] research findings`, `[entity] survey results`
6. Pitfalls — `[entity] common mistakes pitfalls`, `[entity] what to avoid`, `[entity] lessons learned`

### Tier Scoring

- **Tier A** — official sources, gov sites, academic (arxiv, pubmed, ietf), github.com, MDN, OWASP, NIST, WHO, ISO, IEEE: auto-include
- **Tier B** — reputable secondary (stackoverflow, dev.to, vendor blogs, freecodecamp, established news, industry publications): include if clearly relevant
- **Tier C** — personal blogs, medium, hashnode: only if no Tier A/B found for this angle
- **Skip** — paywalled, social media, SEO farms: exclude silently

Each agent returns collected URLs with tier, angle, and entity labels. Merge and deduplicate across all agents. Add any `SEED_URLS` from arguments.

**Minimum required: 100 sources (Tier A + Tier B combined).**

### Phase 3b: Gap Detection Retry

If any angle returned 0 Tier A/B sources for any entity: spawn a retry agent. Refine the query — alternate phrasing, more specifics, different site operators.

Log each retry: `Retried [entity] [angle] with: "[refined query]" → N sources found`

### Phase 3c: Minimum Source Gate

If total Tier A + Tier B < 100:
1. Log: "Minimum source gate: collected N sources — need 100. Running expansion."
2. Spawn additional search agents targeting entities and angles with the fewest hits
3. Keep expanding until total >= 100 or query space is exhausted
4. If still < 100: log "Source gate: collected N sources (below 100 target) — query space exhausted. Proceeding."

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

## Phase 4: Fetch, Convert, Save, and Index

For each URL in the approved list, in parallel batches of 10:

**Step 1 — Fetch.** Use `WebFetch` to retrieve the raw content.

**Step 2 — Convert.** Clean and convert to indexed-ready markdown:
- Strip HTML tags, navigation, ads, cookie banners, boilerplate — keep only substantive content
- Convert to clean markdown: preserve headings, lists, tables, code blocks
- For PDFs: extract text, preserve section structure, discard page numbers and repeated headers
- For legislation/legal docs: preserve section numbering, definitions, and clause structure
- For academic papers: preserve abstract, key findings, methodology notes, conclusions
- Normalize whitespace; remove duplicate blank lines

**Step 3 — Save.** Write the converted content to `$WORKSPACE_ABS/knowledge/[sanitized-title].md`.
Files go directly in `knowledge/` — do NOT create subdirectories.
Include a header at the top of each file:
```markdown
<!-- Source: [URL] | Tier: [A/B/C] | Domain: [domain] | Angle: [angle] | Fetched: [date] -->
```

Do NOT save URL lists as standalone files. URLs go in `discovery-log.md` only.

**Step 4 — Index each batch.** After each batch of 10:
```json
{
  "sources": ["<WORKSPACE_ABS>/knowledge/[file-1].md", "<WORKSPACE_ABS>/knowledge/[file-2].md"],
  "workspace_path": "<WORKSPACE_ABS>"
}
```

If a URL fails to fetch: log it, skip, continue. If more than 30% fail: warn the user and list the failed URLs.

### Discovery log

Append to `$WORKSPACE_ABS/discovery-log.md`:

```markdown
## [YYYY-MM-DD] — [entity]
- Domain: [domain]
- Angles run: [list]
- Sources found: N (Tier A: N, Tier B: N)
- Files saved: [file-1].md, [file-2].md, ...
- Retried angles: [list or "none"]
- No source found for: [list or "none"]
```

`discovery-log.md` is NOT indexed — audit trail only.

---

## Phase 5: Final Index

Call `POST http://127.0.0.1:8612/index`:
```json
{
  "project_path": "<PROJECT_PATH>",
  "workspace_path": "<WORKSPACE_ABS>",
  "force": true
}
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
