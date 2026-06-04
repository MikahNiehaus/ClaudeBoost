---
description: Build a workspace-scoped research RAG from web searches seeded by ticket entities
---

# /research-task — Task Research Builder

Arguments: `[workspace-id]`

Finds relevant external sources for a task and indexes them into a workspace-scoped research RAG. Once indexed, every agent spawned with `workspace_path` automatically gets the research as Tier 3c context — up to 400 tokens of task-relevant documentation alongside the codebase and general knowledge.

Run this after creating a workspace but before delegating to implementation agents.

---

## Phase 0: Resolve Workspace

Parse `[workspace-id]` from arguments.

If not provided: check `$CLAUDEBOOST_HOME/state/active-workspace.json` for the current workspace. If still not found, ask the user.

Resolve:
- `WORKSPACE_ID` = the workspace slug (e.g. `ASC-1199`, `knowledge-tiers-2026-06-03`)
- `WORKSPACE_ABS` = absolute path. Check in order:
  1. `$CLAUDEBOOST_HOME/workspace/$WORKSPACE_ID/` (ClaudeBoost meta-work)
  2. `state/workspaces.json` registry lookup (project workspaces)

If neither exists: error — "workspace $WORKSPACE_ID not found".

**0b — Verify project is indexed** (required for codebase search to work):

Detect the project path:
1. Read `$CLAUDEBOOST_HOME/state/workspaces.json` — use the `project_path` from the entry whose `workspace_path` was most recently modified
2. Fall back to current working directory if no registry entry found

Call `GET http://127.0.0.1:8612/status` and check `indexed_projects` for the detected path.

- **Indexed**: note file/chunk counts and continue.
- **Not indexed**: run `Skill(skill="index-project", args="<project_path>")` immediately. Do not continue until indexing completes.
- **RAG offline**: stop and tell the user to run `/rag` first.

---

## Phase 1: RAG Health Check

Call `GET http://127.0.0.1:8612/status`. If it fails: stop and tell the user to run `/rag`.

---

## Phase 2: Extract Research Topics

Read `$WORKSPACE_ABS/ticket.md` (fall back to `context.md` if ticket.md absent).

Extract the key technical dimensions of this task:

1. **Primary pattern/approach** — what is being implemented? (e.g. "email notifications via SMTP", "feature flag gating a UI dropdown", "JWT token issuance")
2. **Frameworks and libraries** — specific versions if mentioned (e.g. "ASP.NET Core 8", "Entity Framework Core 8", "React 18")
3. **Domain concepts** — business domain patterns involved (e.g. "enrollment status filtering", "multi-tenant data isolation")
4. **External APIs or services** — if any (e.g. "SendGrid email API", "Tableau Embedded Analytics")

Produce **3–6 targeted research queries**. Be specific — "ASP.NET Core IHostedService background job pattern" beats "background jobs". Avoid generic queries like "best practices" alone.

If the ticket is very simple (single-file change, pure UI tweak) and no external patterns are involved: print "No external research needed for this task — ticket is self-contained." and stop.

---

## Phase 3: Web Search for Sources

For each research query, run a web search and identify **1–2 high-quality sources**:

**Prefer:**
- Official documentation (learn.microsoft.com, developer.mozilla.org, go.dev, docs.python.org, reactjs.org)
- Well-known reference sites (owasp.org, martin fowler's blog, web.dev)
- GitHub README/docs for specific libraries being used

**Avoid:**
- Random blog posts, Medium articles, Stack Overflow answers (use official docs instead)
- Login-required or paywalled pages
- Pages older than 5 years for rapidly changing topics (unless canonical/stable)

Collect a final deduplicated list of **6–12 URLs**.

---

## Phase 4: Index Research

Call `POST http://127.0.0.1:8612/index_research` with:
```json
{
  "sources": ["<url-1>", "<url-2>", ...],
  "workspace_path": "<WORKSPACE_ABS>"
}
```

Wait for the result. Note any failed sources.

---

## Phase 5: Verify Context

Do a quick sanity check to confirm the index was populated:

```python
import json, urllib.request
body = json.dumps({
    "query": "<primary_pattern_from_phase_2>",
    "scope": "research",
    "workspace_path": "<WORKSPACE_ABS>",
    "limit": 3
}).encode()
req = urllib.request.Request(
    "http://127.0.0.1:8612/search",
    data=body,
    headers={"Content-Type": "application/json"}
)
with urllib.request.urlopen(req, timeout=15) as r:
    results = json.loads(r.read())
print(f"Research hits: {len(results.get('results', []))}")
```

If 0 results: report the failure. Don't pretend it worked.

---

## Phase 6: Report

```
Research RAG built for workspace/$WORKSPACE_ID

  Topics researched : N
  Sources indexed   : N/N (N failed)
  Research context  : WORKSPACE_ABS/.rag-index/research/

  Indexed sources:
    ✓ https://...
    ✓ https://...
    ✗ https://... (failed: reason)

  Agents now get this research as Tier 3c context automatically when spawned
  with workspace_path="$WORKSPACE_ABS". No extra steps needed.

  Verification: N research chunks found for "<primary_pattern_query>"
```

---

## Notes

- Re-running `/research-task` on the same workspace is incremental — only new or changed sources are re-indexed.
- Research content is task-specific. General best practices live in `knowledge/` and are always available via Tier 3.
- Quality beats quantity: 6 authoritative docs > 20 blog posts.
- If the task involves a specific library version, prefer the versioned docs URL (e.g. `/en/v8.0/` not `/en/latest/`).
