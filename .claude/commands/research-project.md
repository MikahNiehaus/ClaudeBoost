---
argument-hint: [project-path] [topic]
description: Expand the project knowledge base — detects gaps, researches missing pieces, and indexes results permanently into .claudeboost/knowledge/
allowed-tools: Read, Write, Edit, Bash, Glob, Grep, WebSearch, WebFetch
---

# /research-project — Project Knowledge Base Builder

Arguments: `[project-path] [topic]`

Builds and expands the persistent knowledge base at `<project>/.claudeboost/knowledge/`.
Unlike `/research-task` (per-workspace, ephemeral), this KB accumulates across every
session and workspace. Every agent working on the project benefits from it permanently.

Run this when:
- Starting work on a project for the first time
- Adding a new dependency, API, or technology to the project
- An agent produced a finding that revealed a gap in project knowledge
- You want to capture an architectural decision for future agents

---

## Phase 0 — Resolve Project Path

If `project-path` is given, use it. Otherwise use the current working directory.

Set `PROJECT_PATH` = resolved absolute path.
Set `KB_DIR` = `$PROJECT_PATH/.claudeboost/knowledge/`
Set `KB_INDEX` = `$PROJECT_PATH/.claudeboost/.rag-index/`

Check if `$KB_DIR` exists:
- **Yes** → announce "Expanding existing project KB at `$KB_DIR`"
- **No** → announce "Initializing new project KB at `$KB_DIR`" then `mkdir -p "$KB_DIR"`

---

## Phase 1 — Read Existing KB

Read all `.md` files in `$KB_DIR`. For each, note:
- File name and size
- Topics covered (first 200 chars of each file)

If KB is empty or missing files: all standard topics are gaps.
If KB has content: extract what's already covered so we don't duplicate it.

Standard KB files (create missing ones as empty):
- `architecture.md` — project structure, main modules, entry points
- `patterns.md` — coding patterns this codebase actually uses
- `decisions.md` — key architectural decisions and the reasons behind them
- `stack.md` — language/framework specifics for this project (not generic guides)
- `gotchas.md` — edge cases, bugs, and quirks found in past sessions

---

## Phase 2 — Detect Gaps

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

List gaps explicitly before proceeding.

---

## Phase 3 — Research Missing Pieces

For each gap that benefits from external docs (stack specifics, APIs, frameworks):

Run 2–3 targeted `WebSearch` queries:
- Official docs for the specific library/framework version in use
- Security considerations if the topic is auth, data handling, or external APIs
- Migration guides if the project is upgrading a dependency

Source tiers:
- **Tier A** (official docs, GitHub, arxiv, MDN, OWASP): auto-include
- **Tier B** (Stack Overflow, engineering blogs): include if highly relevant
- **Tier C** (Medium, personal blogs): skip unless no Tier A/B sources exist

For gaps that come from the codebase itself (architecture, patterns):
- Read the relevant source files directly — don't search the web
- Summarize what you find into the appropriate KB file

---

## Phase 4 — Update KB Files

For each gap found:
1. Append findings to the correct KB file (never overwrite existing content)
2. Use clear headings so future additions don't duplicate topics
3. Keep entries concrete — actual patterns from this project, not generic advice

Example format for `stack.md`:
```markdown
## React (v18) — hooks pattern
This project uses custom hooks in `src/hooks/`. State lives in hooks, not components.
Never use class components — the codebase has none and tests assume functional components.

## API calls
All API calls go through `src/services/api.ts`. Direct `fetch()` in components is banned.
```

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

Report: `N files indexed, M chunks total`.

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

Indexed: M chunks total

KB files are indexed alongside the project codebase. When relevant to the query, they
surface in POST /context Tier 4 results. Run /research-project again any time you add
a new dependency or technology.
```

---

## Notes

- This KB is per-project and persistent — it survives across workspaces and sessions.
- `/research-task` is still useful for ticket-specific external docs (API references,
  migration guides for a one-off task). Think of it as: `/research-project` for what the
  project always needs to know, `/research-task` for what this ticket specifically needs.
- The `.claudeboost/` folder can be committed to git — agents on other machines or in CI
  get the same accumulated knowledge.
- Never store secrets or credentials in KB files — they are indexed and surfaced to agents.
