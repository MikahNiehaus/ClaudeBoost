---
argument-hint: [workspace-id] [--approve] [url1 url2 ...]
description: Auto-discover, fetch, convert, and index sources for any task — code, legal, UI design, market research, or anything else. Fully automated by default.
allowed-tools: Read, Write, Edit, Bash, Glob, Grep, Agent, WebSearch, WebFetch
---

# /research-task — Task Research Builder

Arguments: `[workspace-id] [--approve] [url1 url2 ...]`

Works for any domain — software tasks, legal research, UI/UX design, market research,
compliance, science, business strategy, or anything else. Reads the ticket, figures out
what kind of task it is, runs domain-appropriate searches, fetches every source, converts
the content into clean indexed documents, and loads it all into RAG so agents have it automatically.

**When to use this vs manual URL mode:**
- Default (no URLs, no `--approve`) — automatic. Reads the ticket, extracts topics, runs
  multi-angle web searches, fetches and converts results, indexes without pausing.
- With URLs or `--approve` flag — manual approval gate. Discovered and provided sources shown
  in a table; you review and confirm before anything is indexed.

Both paths write to the same Tier 3c workspace path. Once indexed, every agent spawned with
`workspace_path` automatically gets the research as context.

Run this after creating a workspace but before delegating to implementation agents.

---

## Phase 0: Resolve Workspace

Parse `[workspace-id]` from arguments. Collect any `http://` or `https://` tokens as
`SEED_URLS`. Note if `--approve` flag is present.

If workspace-id not provided: resolve from the per-instance file.
Run `workspace-status.py` (no args) or read `$CLAUDEBOOST_HOME/state/ws-instance/{instance_id}.json`
keyed by current working directory. If still not found, ask the user.

Resolve:
- `WORKSPACE_ID` = the workspace slug (e.g. `ASC-1199`, `gdpr-compliance-2026-06-21`)
- `WORKSPACE_ABS` = absolute path. Check in order:
  1. `$CLAUDEBOOST_HOME/workspace/$WORKSPACE_ID/` (ClaudeBoost meta-work)
  2. `state/workspaces.json` registry lookup (project workspaces)

If neither exists: error — "workspace $WORKSPACE_ID not found".

Create `$WORKSPACE_ABS/knowledge/` directory if it doesn't exist — converted documents go here.
Do NOT create a `research/` subdirectory — all fetched content goes directly in `knowledge/`.

---

## Phase 0b: Domain Detection and Entity Extraction

Read `$WORKSPACE_ABS/ticket.md` (fall back to `context.md` if ticket.md absent).

**Step 1 — Detect domain.** Read the ticket and classify the primary domain. Pick the best fit:

- **code** — software implementation, bug fix, library integration, API design, architecture
- **legal** — laws, regulations, compliance, contracts, jurisdiction rules, case law
- **design** — UI/UX, visual design, accessibility, user research, design systems
- **market** — market research, competitor analysis, industry trends, consumer behavior, business strategy
- **science** — academic research, studies, data analysis, technical specifications
- **general** — anything that doesn't fit the above cleanly

Log: `Domain detected: [domain]`

If the ticket clearly spans two domains (e.g. legal + code for a compliance feature), note both — the primary domain drives angle selection, the secondary adds supplementary angles.

**Step 2 — Extract entities.** From the ticket, pull out the key topics to research:

For any domain:
1. The primary subject or goal (what is this task fundamentally about?)
2. Named concepts, laws, frameworks, tools, methodologies, or standards mentioned
3. Key constraints or requirements stated
4. Any specific versions, jurisdictions, platforms, or contexts mentioned

For code tasks only — also check dependency manifests in the project root:
- `package.json` → `dependencies` and `devDependencies`
- `requirements.txt` / `pyproject.toml` → package names
- `go.mod` → module paths from `require` block
- `Gemfile` → gem names
- `*.csproj` → `<PackageReference Include="...">` names

Merge all into a deduplicated entity list. Cap at 8 entities. Log each entity and where it came from.

---

## Phase 0c: Project Index Check (Code Tasks Only)

Skip this phase entirely if domain is not `code`.

For code tasks: detect project path from `$CLAUDEBOOST_HOME/state/project-workspaces.json`.
Call `GET http://127.0.0.1:8612/status` and check `indexed_projects`.

- **Indexed**: note file/chunk counts and continue.
- **Not indexed**: run `Skill(skill="index-project", args="<project_path>")` immediately.
- **RAG offline**: stop and tell the user to run `/rag` first.

For code tasks only, also call `POST http://127.0.0.1:8612/search` with:
```json
{
  "query": "<primary ticket entity>",
  "scope": "codebase",
  "mode": "graph",
  "project_path": "<PROJECT_PATH>",
  "limit": 5
}
```
Add any new library/module names found to the entity list.

---

## Phase 1: RAG Health Check

Call `GET http://127.0.0.1:8612/status`. If it fails: stop and tell the user to run `/rag`.

---

## Phase 2: Simplicity Guard

Check the ticket content. If the task is genuinely self-contained — a one-line change, a
pure rename, something with no external knowledge dependency at all — print:

```
No external research needed for this task — ticket is self-contained.
```

And stop. Don't run searches for tasks where external knowledge clearly can't help.

---

## Phase 3: Multi-Angle Search (Parallel Agents)

Take up to 8 entities from the extracted list. Spawn **one search agent per entity in parallel** — all run concurrently.

Each agent handles its own entity. The search angles depend on the detected domain.

### Domain-Specific Angles

**code:**
1. Official docs — `[entity] official documentation`, `[entity] API reference site:github.com`, `[entity] guide site:docs.[domain].com`
2. Security — `[entity] security vulnerabilities OWASP`, `[entity] CVE NVD`, `[entity] security best practices NIST`
3. Performance — `[entity] performance optimization`, `[entity] benchmark profiling`, `[entity] scaling production`
4. Migration/upgrade — `[entity] migration guide breaking changes`, `[entity] changelog site:github.com`, `[entity] upgrade guide`
5. Integration patterns — `[entity] integration examples tutorial`, `[entity] cookbook site:github.com`, `[entity] production patterns`
6. Pitfalls/gotchas — `[entity] common mistakes gotchas`, `[entity] anti-patterns known issues site:github.com`, `[entity] troubleshooting`

**legal:**
1. Primary legislation — `[entity] legislation statute text`, `[entity] act law site:gov`, `[entity] regulation official text`
2. Case law — `[entity] case law court decision`, `[entity] legal precedent ruling`, `[entity] court judgment [entity]`
3. Regulatory guidance — `[entity] regulatory guidance official`, `[entity] compliance guidance site:gov`, `[entity] regulatory FAQ`
4. Compliance requirements — `[entity] compliance requirements checklist`, `[entity] legal obligations`, `[entity] penalties enforcement`
5. Jurisdiction specifics — `[entity] [jurisdiction] specific rules`, `[entity] state federal differences`, `[entity] international variation`
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
2. Reviews/meta-analyses — `[entity] systematic review`, `[entity] meta-analysis`, `[entity] literature review`
3. Specifications/standards — `[entity] technical specification`, `[entity] standard IEEE ISO`, `[entity] RFC ietf.org`
4. Data sets — `[entity] dataset open data`, `[entity] benchmark data`, `[entity] experimental results`
5. Expert consensus — `[entity] expert consensus`, `[entity] scientific consensus`, `[entity] position statement`
6. Recent developments — `[entity] recent research 2024 2025`, `[entity] new findings`, `[entity] latest study`

**general:**
1. Overview — `[entity] overview guide`, `[entity] introduction explained`, `[entity] what is [entity]`
2. Best practices — `[entity] best practices`, `[entity] recommended approach`, `[entity] how to`
3. Case studies — `[entity] case study example`, `[entity] real world example`, `[entity] success story`
4. Expert opinion — `[entity] expert opinion analysis`, `[entity] site:medium.com professional`, `[entity] in depth guide`
5. Data/evidence — `[entity] data statistics evidence`, `[entity] research findings`, `[entity] survey results`
6. Pitfalls — `[entity] common mistakes pitfalls`, `[entity] what to avoid`, `[entity] lessons learned`

For each angle, run 3 queries with different phrasings. Collect as many Tier A/B URLs as possible — no per-angle cap.

### Tier Scoring (all domains)

- **Tier A** — official sources, gov sites, academic institutions (arxiv, pubmed, ietf), github.com, MDN, OWASP, NIST, WHO, ISO, IEEE: auto-include
- **Tier B** — reputable secondary sources (stackoverflow, dev.to, vendor blogs, freecodecamp, established news, industry publications): include if clearly relevant
- **Tier C** — personal blogs, medium, hashnode: only if no Tier A/B found for this angle
- **Skip** — paywalled, social media, SEO farms: exclude silently

Each agent returns collected URLs with tier, angle, and entity labels. Merge and deduplicate across all agents. Add any `SEED_URLS` from arguments.

**Minimum required: 100 sources (Tier A + Tier B combined).**

---

## Phase 3b: Gap Detection Retry

After merging results from all parallel agents:

- If any angle returned 0 Tier A/B sources for any entity: spawn a retry agent for that gap. Refine the query — try alternate phrasing, add specifics, try different site operators.
- No hard retry cap per angle — keep searching until at least 1 Tier A/B is found or query space is exhausted.
- Log each retry: `Retried [entity] [angle] with: "[refined query]" → N sources found`

### Phase 3c: Minimum Source Gate

Count total Tier A + Tier B sources across all entities and angles.

**If total < 100:**
1. Log: "Minimum source gate: collected N sources — need 100. Running expansion."
2. Spawn additional search agents in parallel targeting entities and angles with the fewest hits
3. Keep expanding until total sources >= 100 or all reasonable query space is exhausted
4. If still < 100: log "Source gate: collected N sources (below 100 target) — query space exhausted. Proceeding."

Do not proceed to the approval gate or Phase 4 until this gate passes or is logged as exhausted.

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
| 3 | ...   | ... | B    | design | Accessibility |
...
```

Ask:
> Type **all** to fetch and index everything, **skip N,M** to exclude by number, or paste more URLs.
> Reply to start.

Wait for the user's response before proceeding.

- `all` → fetch and index everything in the table
- `skip 2,4` → remove those rows, fetch and index the rest
- Pasted URLs → add to the list, re-show if more than 5 new URLs added
- `cancel` or empty → abort

**Auto mode** (no `SEED_URLS`, no `--approve`): skip the table entirely and go to Phase 4.

---

## Phase 4: Fetch, Convert, and Index

For each URL in the approved list, in parallel batches of 10:

**Step 1 — Fetch.** Use `WebFetch` to retrieve the raw content.

**Step 2 — Convert.** Clean and convert the fetched content into a format suitable for indexing:
- Strip all HTML tags, navigation, headers/footers, ads, cookie banners, and boilerplate — keep only the substantive content
- Convert to clean markdown: preserve headings, lists, tables, code blocks, and meaningful structure
- For PDFs: extract text, preserve section structure, discard page numbers and repeated headers
- For legislation/legal docs: preserve section numbering, definitions, and clause structure — these are semantically meaningful
- For academic papers: preserve abstract, key findings, methodology notes, conclusions
- Normalize whitespace; remove duplicate blank lines

**Step 3 — Save.** Write the converted content to `$WORKSPACE_ABS/knowledge/[sanitized-title].md`.
Files go directly in `knowledge/` — do NOT create a `research/` subdirectory.
Use the page title or URL slug as the filename. Include a header:
```markdown
<!-- Source: [URL] | Tier: [A/B/C] | Domain: [domain] | Angle: [angle] | Fetched: [date] -->
```

Do NOT save URL lists as standalone files. URLs are recorded in `discovery-log.md` only.

**Step 4 — Index the content files.** After each batch:
```json
{
  "sources": ["<WORKSPACE_ABS>/knowledge/[file-1].md", "<WORKSPACE_ABS>/knowledge/[file-2].md", ...],
  "workspace_path": "<WORKSPACE_ABS>"
}
```

If a URL fails to fetch: log it, skip, continue. If more than 30% of sources fail, warn the
user and list the failed URLs.

---

## Phase 5: Synthesis Layer

Write `$WORKSPACE_ABS/research-brief.md`:

```markdown
# Research Brief — [WORKSPACE_ID]

Generated: [date]
Domain: [detected domain]
Topics researched: [entity list]
Total sources indexed: N (Tier A: N, Tier B: N)
Converted documents: knowledge/

## Sources

| # | Source | Tier | Angle | Key Takeaway |
|---|--------|------|-------|-------------|
| 1 | [title](url) | A | Primary legislation | [one sentence] |
| 2 | [title](url) | A | Official docs | [one sentence] |
...

## Coverage Summary

| Angle | Sources Found | Confidence |
|-------|--------------|------------|
| [angle 1] | N | High / Medium / ⚠ No authoritative source |
...

## Gaps

- [any topic/angle where no good source was found]
```

Append a pointer in `$WORKSPACE_ABS/context.md` under "Research Sources":

```markdown
## Research Sources

Domain: [domain] | Indexed: [date]
Research brief: [WORKSPACE_ABS]/research-brief.md
Converted documents: [WORKSPACE_ABS]/knowledge/

| Source | Tier | Angle |
|--------|------|-------|
| url    | A    | [angle] |
...
```

Replace the section entirely if it already exists.

---

## Phase 6: Evaluator Pass

Spawn a single `evaluator-agent` with this prompt:

"First action: call `POST http://127.0.0.1:8612/context` with:
`{\"agent\":\"evaluator-agent\",\"task_description\":\"verify research coverage for [WORKSPACE_ID]\",\"workspace_path\":\"[WORKSPACE_ABS]\"}`

Then read `[WORKSPACE_ABS]/research-brief.md`. Verify:
1. At least one source per angle has Tier A or Tier B
2. The Coverage Summary has at least one High or Medium confidence angle
3. No source in the approved list is silently missing from the Sources table
4. The detected domain matches the ticket content

Output:
| Check | Result | Verdict (CONFIRMED/NEEDS_EVIDENCE) |

Flag NEEDS_EVIDENCE items. Under 400 tokens. End with ## Summary."

Surface any NEEDS_EVIDENCE items before the final report.

---

## Phase 7: Final Report

```
Research complete for workspace/[WORKSPACE_ID]

  Domain          : [detected domain]
  Topics          : [entity list]
  Sources indexed : N (Tier A: N, Tier B: N, N failed)
  Converted docs  : knowledge/ ([N] files)
  Research brief  : workspace/[WORKSPACE_ID]/research-brief.md

  Coverage:
    ✓ [angle 1]   — N sources
    ✓ [angle 2]   — N sources
    ⚠ [angle 3]   — no authoritative source found
    ...

  Agents get research as Tier 3c context automatically when spawned
  with workspace_path="[WORKSPACE_ABS]"
```

---

## Notes

- All collected URLs are logged to `$WORKSPACE_ABS/discovery-log.md` for audit purposes. URLs are never saved as standalone files — only the converted content goes in `knowledge/`.
- Re-running `/research-task` on the same workspace is incremental — unchanged sources are skipped automatically.
- Domain detection is automatic but you can override it by stating the domain in the ticket: "This is a legal research task about..."
- For cross-domain tasks (e.g. GDPR compliance in a web app), note both domains in the ticket — primary drives angle selection, secondary adds supplementary angles.
- Converted documents in `knowledge/` are clean markdown — agents can read them directly or find them via semantic search.
- `research-brief.md` is for human and agent reading; the `knowledge/` folder is the actual indexed content.
- `mode=graph` only works on `scope=codebase` — research scope always uses vector internally.
- **Passing URLs directly**: `/research-task my-workspace https://example.com/law.pdf` — URLs are auto-detected and trigger manual approval mode.
