# ClaudeBoost Architecture

## Top-Level Layout

```
ClaudeBoost/
  agents/          XML agent definitions (25 files) — read by spawned agents at runtime
  knowledge/       XML knowledge bases (107 files) — indexed in RAG, never read directly
  scripts/         Python hook scripts (~53 files) + scripts/tests/ (pytest suite)
  mcp-rag-server/  Starlette HTTP server (port 8612) — semantic search + indexing
  .claude/
    commands/      Markdown skill files (slash commands)
    settings.json  Hook registrations + permission allow/deny lists
  state/           Runtime JSON files (active workspace, behavior tracker, etc.)
  workspace/       Per-task workspace directories (gitignored)
  docs/            User-facing docs
  references/      Reference materials (not indexed by default)
```

## Hook System

Hooks are Python scripts registered in `.claude/settings.json`. Claude Code calls them
at specific lifecycle events and passes a JSON payload on stdin. The script exits with:
- `0` — allow / pass silently
- `1` — non-blocking warning (stderr shown to user, does not block)
- `2` — hard block (stderr shown, Claude Code stops and shows the message)

### Registered Hooks (as of 2026-06-12)

| Event | Script | Role |
|-------|--------|------|
| SessionStart | `rag-session-reset.py` | Reset RAG heartbeat for new session |
| SessionStart | `reindex-check.py` | Warn if project index is stale |
| SessionStart | `compaction-restore.py` | Restore workspace state after /clear |
| UserPromptSubmit | `session-primer.py` | Inject standing orders + workspace dashboard |
| PostToolUse | `context-nudge.py` | Remind to update context.md after every 5 reads |
| PreToolUse(Agent) | `agent-spawn-gate.py` | Block spawns missing RAG context call or project_path |
| PreToolUse(Bash mkdir*workspace*) | `workspace-boost-gate.py` | Require /boost before workspace creation |
| PreToolUse(Grep) | `rag-read-guard.py` | Block Grep after 2 consecutive non-RAG file searches |
| PreToolUse(Read) | `rag-read-guard.py` | Block Read after 2 consecutive non-RAG file searches |
| PreCompact | `compaction-save.py` | Save workspace state before /clear |
| PreCompact | `compaction-primer.py` | Inject summary for post-compaction recovery |
| SessionEnd | `session-clear-save.py` | Save state on session exit |
| Stop | `stop-context-guard.py` | Check for unsaved context before stopping |
| Stop | `human-voice-guard.py` | Warn if response contains AI-speak vocabulary |

## RAG Server

HTTP REST API on `127.0.0.1:8612`. Serves two distinct indexes:

- **ClaudeBoost RAG** — agents/ + knowledge/ XML files, indexed at `mcp-rag-server/.rag-index/`
- **Project RAG** — any external project's source code, indexed per-project
- **Graph RAG** — structural import/inheritance graph stored in `graph.db` alongside project index

Key endpoints:
- `GET /status` — health check, returns collection sizes + indexed_projects
- `POST /context` — load agent knowledge (tiers 0–4b, max_tokens limited)
- `POST /search` — semantic/graph search (scope: agents|knowledge|codebase|research|all)
- `POST /index` — index a project codebase
- `POST /index_research` — index external URLs/PDFs into workspace research index

## State Files (state/)

| File | Purpose |
|------|---------|
| `active-workspace.json` | Current workspace ID + paths |
| `behavior-tracker.json` | Counters: reads_since_rag, tasks_since_evaluator |
| `needs-verification.json` | Set when a NEEDS_VERIFICATION finding is flagged |
| `audit-in-progress.json` | Set during /audit to bypass evaluator gate |
| `boost-injection.json` | Controls session-primer injection mode (false/true/verify) |
| `claudeboost-mode.json` | CONSULT vs AUTO mode |
| `workspaces.json` | Registry of all known workspaces + project paths |

## Workspace Structure

```
workspace/[task-id]/
  goal.md        — verbatim user input (immutable after creation)
  ticket.md      — verbatim ticket text (only when full ticket was pasted)
  context.md     — live session state (updated after every significant finding)
  plan.md        — step-by-step implementation plan
  gap-audit.md   — (optional) exploration artifacts from agents
  .rag-index/
    research/    — per-task research index (indexed URLs/PDFs)
```
