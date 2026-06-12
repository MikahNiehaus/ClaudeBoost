# ClaudeBoost Key Architectural Decisions

## HTTP REST API over MCP for RAG

**Decision**: RAG server uses HTTP REST (`127.0.0.1:8612`), not MCP tools.

**Why**: MCP tools require an active Claude Code session with MCP configured. HTTP
works from scripts, hooks, CI, external tools, and sessions without MCP. The RAG
server is now usable even when the session is not boosted.

**Impact**: All agent spawn prompts include a `curl` or `urllib.request` call to
`POST http://127.0.0.1:8612/context` as their first action. Hooks call the HTTP
API directly. No MCP tool dependency.

---

## Hook Exit Codes: 0 / 1 / 2 (not true/false)

**Decision**: Exit 2 = hard block, exit 0 = pass, exit 1 = non-blocking warning.
Most hooks use only 0 and 2.

**Why**: Claude Code maps exit codes to behavior. Exit 1 shows the stderr message
but doesn't stop execution. Exit 2 stops Claude Code and shows the message. This
gives hooks fine-grained control without requiring separate "warning" vs "error"
code paths.

**Impact**: Any hook using `sys.exit(1)` for blocking is wrong — it only warns.
Use `sys.exit(2)` to actually stop behavior.

---

## Guards Must Fail Open (Return 0) When RAG is Offline

**Decision**: If `_rag_is_live()` returns False, guards that depend on RAG must
return 0 (allow) rather than blocking.

**Why**: Guards that block when RAG is offline prevent legitimate work when the
server hasn't started yet. The user can't debug if all file reads are blocked.
RAG being offline means degraded context, not a security violation.

**Impact**: Every RAG-gated guard starts with `if not _rag_is_live(): return 0`.

---

## Behavior Tracker: Machine-Agnostic Base File

**Decision**: Guards read from `state/behavior-tracker.json` (no machine suffix).
Machine-specific files (`behavior-tracker-MikahsGaminPC.json`) are for compaction
history, not live tracking.

**Why**: Hooks run in-process and don't know the machine name. The base file is
the authoritative live state.

**Impact**: The rag-read-guard, context-nudge, and evaluator-routing gate all read
`state/behavior-tracker.json`. Resetting reads_since_rag in the machine-specific
file has no effect on these guards.

---

## No Multiline python -c in Bash Commands

**Decision**: bash-guard blocks multiline `python -c "..."` and `cat > file << 'EOF'`.
Use the Write tool to create a temp file, then `python "path/to/file.py"`.

**Why**: Claude Code's built-in safety scanner prompts on newlines in quoted args,
even when the command is in the allow list. This generates spurious permission prompts
that interrupt the user.

**Impact**: All hook scripts and skill files must use `Write` + `python "path"` for
any Python logic longer than one line.

---

## Workspace per Task, Not per Session

**Decision**: Each task gets its own `workspace/[task-id]/` directory with context.md,
plan.md, and optionally goal.md/ticket.md. Sessions share access to the same workspace.

**Why**: Supports /handoff (context survives /clear), multi-session tasks, and parallel
workspaces. The workspace is the unit of task continuity.

**Impact**: `state/active-workspace.json` always points to the current workspace.
context.md is updated after every significant finding, not just at session end.

---

## Agents Read Their Own XML, Not CLAUDE.md

**Decision**: Agent behavior is defined in `agents/[name]-agent.xml`. The orchestrator's
rules in CLAUDE.md do NOT propagate to spawned agents.

**Why**: Spawned agents are separate Claude Code instances (subagents). They don't
inherit the parent session's CLAUDE.md context unless it's explicitly included in
the spawn prompt or loaded via RAG.

**Impact**: Every agent XML must include a `<rag-enforcement>` block with all RAG rules
(POST /context first, fail if offline, POST /search vector and graph). Rules in CLAUDE.md
alone are insufficient.

---

## Graph RAG Degrades to Vector When graph.db Absent

**Decision**: `POST /search scope=codebase mode=graph` falls back to vector results if
no `graph.db` exists for the project.

**Why**: Not all indexed projects have graph analysis enabled. Degrading to vector search
is more useful than an error.

**Impact**: `mode=graph` is always safe to call — it never fails, it degrades.
