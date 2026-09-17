# ClaudeBoost Reference Manual

**Generated:** 2026-05-08 (counts updated 2026-07-05)
**Coverage:** All 16 hook registrations, 25 agent XMLs (including _orchestrator), 109 knowledge XMLs (55 domain + 21 lang + 33 framework), 36 slash commands, settings.json hooks registration, all state files, MCP RAG server code.

---

## Table of Contents

1. [Hook Scripts](#1-hook-scripts)
2. [End-to-End Workflow Traces](#2-end-to-end-workflow-traces)
3. [Agents](#3-agents)
4. [Knowledge Files](#4-knowledge-files)
5. [Slash Commands](#5-slash-commands)
6. [Hook Registration (settings.json)](#6-hook-registration)
7. [Configuration & State Files](#7-configuration--state-files)
8. [Search backend](#8-search-backend)

---

## 1. Hook Scripts

### 1.1 agent-spawn-gate.py

**File:** `clean-rag/hooks/agent-spawn-gate.py`
**Event:** PreToolUse
**Matcher:** `Task`
**Type:** Command hook

**Behavior on this branch: none.** The file is 27 lines, a docstring and
`sys.exit(0)`. It reads no stdin, checks no prompt, and writes nothing.

It exists so a branch switch cannot brick Claude Code. Hook commands are
registered in `~/.claude/settings.json`, which does not change when you check
out a different branch, while the scripts they point at live in the repo. A
branch missing a registered script leaves the hook pointing at nothing, python
exits 2, and Claude Code reads exit 2 from a PreToolUse hook as "block this tool
call". Every Edit, Write and Bash is then refused until you switch back. A file
that exits 0 makes that harmless. `scripts/agent-spawn-gate.py` is a second stub
of the same idea in the other location; only the clean-rag one is registered.

The real implementation lives on `feat/uninstall-and-bash-guard` and
`feature/workspace-better-understanding-active-2026-06-15`, where it blocks an
agent spawn that has not loaded RAG context first. This branch enforces research
at the edit instead, in `clean-rag/hooks/research-gate.py`.

**Exit codes:** `0` always

This entry used to describe the other branch's version, against port 8612 and
special casing `architect-agent`. 8612 was deleted and architect-agent does not
exist.

---

### 1.2 bash-guard.py

**File:** `scripts/bash-guard.py`  
**Event:** PreToolUse  
**Tool matcher:** `Bash`  
**Type:** Command hook  

**Behavior:** Three safety checks:
1. Co-author trailer — blocks if commit message contains `Co-Authored-By:` (anti-co-author policy)
2. `cd && command` compound — blocks `cd` followed by `&&` (path safety)
3. Backslash-escaped spaces in paths — blocks `path\ with\ spaces` patterns

**Exit codes:**
- `0` = allow
- `2` = block (Claude Code interprets exit 2 as permission denial)

**stdin format:** JSON with the bash command  

---

### 1.3 compaction-save.py

**File:** `scripts/compaction-save.py`  
**Event:** PreCompact  
**Matcher:** omitted — `PreCompact` matches `manual` or `auto`, and omitting the key runs the hook for both.  
**Type:** Command hook  

**Behavior:**
1. Reads all `workspace/*/context.md` files
2. Extracts summaries from each
3. Archives the previous compaction memo to `state/compaction-history/` with filename `<session_id[:16]>-compact-<n>.json`
4. Saves new memo to `state/compaction-memo.json` as `{session_id, compaction_number, timestamp, memo}`
5. Resets `state/compaction-tracker.json` to `{"edit_count": 0}`

**stdout:** Nothing (or success message)  
**Files read:** `workspace/*/context.md`, `state/compaction-memo.json`, `state/claudeboost-mode.json`  
**Files written:** `state/compaction-memo.json`, `state/compaction-history/<session_id>-compact-<n>.json`, `state/compaction-tracker.json`  

---

### 1.4 compaction-restore.py

**File:** `scripts/compaction-restore.py`  
**Event:** SessionStart  
**Matcher:** omitted — `SessionStart` matches `startup`, `resume`, `clear` or `compact`, and omitting the key runs the hook for all four.  
**Type:** Command hook  

**Behavior — two activation paths:**

*`source="compact"` (auto-compact or /compact):*
- Reads `state/handoff-latest.json`; falls back to `state/compaction-memo.json`
- Emits `{"additionalContext": "POST-COMPACTION CONTEXT RESTORATION\n..."}` to stdout

*`source="clear"` (after /clear):*
- Reads `state/handoff-latest.json`
- **Age guard**: rejects if handoff timestamp > 30 minutes old (`AGE_GUARD_SECONDS=1800`)
- **CWD guard**: rejects if handoff `cwd` doesn't match current session cwd (prevents injecting wrong project's context)
- If both guards pass: emits `{"additionalContext": "POST-CLEAR TRANSITION CONTEXT RESTORATION\n..."}`

*All other sources (regular session start):* no-op, exits 0.

**stdout:** JSON with `additionalContext` key containing restored memo + conversation highlights  
**Files read:** `state/handoff-latest.json`, `state/compaction-memo.json` (fallback)  

**Key invariant:** No-ops on regular session starts. Only fires after compaction or /clear.

---

### 1.5 consult-gate.py

**File:** `scripts/consult-gate.py`  
**Event:** PreToolUse  
**Tool matcher:** `Edit|Write|MultiEdit|Bash`  
**Type:** Command hook  

**Behavior:**
1. Reads `state/claudeboost-mode.json`
2. If mode is AUTO, exits 0 (no-op)
3. Fires on `Edit`, `Write`, and `MultiEdit` — Bash and all read-only tools exit 0 immediately
4. Checks the file path(s) against exempt fragments: `workspace/`, `state/`, `.claudeboost/`, `plans/`, `docs/` (note: `/.claude/` is NOT exempt)
5. If all targets are exempt, exits 0
6. Loads `state/spec-sheet.json` and reads `approved_files` (relative paths, suffix-matched against incoming absolute paths)
7. If spec-sheet.json does not exist: outputs `{"permissionDecision":"ask","reason":"No spec sheet found..."}` — prompts Claude to produce a spec sheet first
8. If any non-exempt target is not in `approved_files`: outputs `{"permissionDecision":"ask","reason":"'<file>' is not in the approved spec sheet..."}` — blocks until the spec is extended and approved

**Exit codes:** `0` always (pass or triggers ask permission dialog)  
**Files read:** `state/claudeboost-mode.json`, `state/spec-sheet.json`  

---

### 1.6 context-nudge.py

**File:** `scripts/context-nudge.py`  
**Event:** PostToolUse  
**Tool matcher:** `.*` (all tools)  
**Type:** Command hook  

**Behavior — two modes:**

*Workspace present (any `workspace/*/context.md` exists):*
1. Reads and increments `state/compaction-tracker.json` `edit_count`
2. Every `NUDGE_INTERVAL=20` tool uses: prints `{"additionalContext": "CONTEXT CHECKPOINT: ..."}` to stdout reminding Claude to update context.md with (1) code changes and (2) important user statements (decisions, preferences, constraints)

*No workspace:*
1. Reads and increments `edit_count`
2. At exactly `edit_count == 60`: prints once suggesting workspace creation, then loop continues from 61

**stdout:** JSON with `additionalContext` at trigger points  
**Files read/written:** `state/compaction-tracker.json`  
**Timeout:** 3000ms  

---

### 1.7 speak-tts.py

**File:** `scripts/speak-tts.py`  
**Event:** Stop  
**Tool matcher:** (no matcher — fires on every stop)  
**Type:** Command hook  

**Behavior:**
1. Reads `state/speak-state.json`
2. If TTS not enabled or `stop_hook_active`, exits immediately
3. Filters response text: `strip_markdown` → `redact_secrets` → `condense_for_speech`
4. Writes filtered text to `$TEMP/claudeboost_tts_text.txt`
5. Kills any existing player: writes stop file + SIGTERM by PID (reads from `$TEMP/claudeboost_tts.pid`)
6. Spawns `speak-play.py` as a detached process using `DETACHED_PROCESS=0x00000008` (Windows)

**Files read:** `state/speak-state.json`, `$TEMP/claudeboost_tts.pid`  
**Files written:** `$TEMP/claudeboost_tts_text.txt`, `$TEMP/claudeboost_tts.stop`  

---

### 1.8 speak-play.py

**File:** `scripts/speak-play.py`  
**Invocation:** Detached background process, spawned by speak-tts.py  
**Args:** `text_file voice temp_dir`  

**Behavior:**
1. Writes own PID to `claudeboost_tts.pid`
2. Synthesizes audio: `asyncio.run(edge_tts.Communicate(text, voice).save(mp3_path))`
3. Plays via Windows `mciSendString` API
4. Polls stop file + space key every 150ms while playing
5. Cleans up temp files on exit

**Dependencies:** `edge-tts` Python package, Windows MCI  

---

### 1.9 speak-stop.py

**File:** `scripts/speak-stop.py`  
**Event:** UserPromptSubmit (also manual)  
**Type:** Command hook  

**Behavior:**
1. Writes `claudeboost_tts.stop` stop file
2. Reads PID from `$TEMP/claudeboost_tts.pid`
3. Kills the player process

**Exit codes:** `0` always  

---

### 1.10 check-hooks.py

**File:** `scripts/check-hooks.py`  
**Args:** `<hook_event_name>` (e.g., `PreToolUse`)  
Reads `settings.json` (user-level) and asserts that the specified hook event is registered. Used by `/boost` Step 4.

---

### 1.11 check-rag-path.py

**File:** `scripts/check-rag-path.py`  
Prints the filesystem path where rag_server is installed (`__file__`, or the first `__path__` entry when it is a namespace package). Exit 0 means a path was printed; exit 1 means it could not be resolved, with the reason on stderr. Used to verify correct installation location.

---

### 1.12 matrix-boost.py

**File:** `scripts/matrix-boost.py`  
**Invocation:** `wt.exe -w 0 new-tab python matrix-boost.py` (via `/boost`)  

**Behavior:**
- Renders a matrix rain animation in the terminal
- Reads `$TEMP/claudeboost_status.txt` every 5 animation frames
- Parses lines of format `SYSTEM:status` and shows each system coming online
- Exits when `BOOST:done` appears in file AND `all_online_since` counter exceeds 40 frames
- Supports `--quick` flag for 3-second reveal

**Status keys monitored:** `PRIVACY`, `RAG`, `GT`, `RULES`, `AGENTS`, `BOOST`

---

### 1.13 changes_core.py + changes-viewer.py

**Files:** `scripts/changes_core.py`, `scripts/changes-viewer.py`  
**Framework:** Textual (Python TUI library)  

**Architecture:**
- `BaseChangesViewer` — base class with common change-viewing logic
- `HudChangesViewer` — subclass with heads-up display overlay
- Reads `changes.json` produced by `/changes` command
- Opens in a Windows Terminal tab via `wt.exe -w 0 new-tab`
- Has a chat input box; questions are written to `$TEMP/claudeboost/changes_chat.json`

---

### 1.14 chat-watcher.py

**File:** `scripts/chat-watcher.py`  
Polls `$TEMP/claudeboost/changes_chat.json` every 3 seconds for up to 15 minutes, waiting for a question from the TUI's chat input.

---

### 1.15 session-clear-save.py

**File:** `scripts/session-clear-save.py`  
**Event:** SessionEnd  
**Matcher:** omitted — the source gate lives in the script, not in `settings.json`.  
**Type:** Command hook  

**Behavior:**
- Gates on `source == "" or source == "clear"` — no-ops on other sources
- Detects active workspace: reads `state/active-workspace.json` first; falls back to most recently modified `workspace/*/context.md`
- Extracts scoped workspace memo from the active workspace's `context.md` only (not all workspaces)
- Parses transcript via `handoff_core.extract_conversation()` to collect: user messages (up to 15), assistant snippets (up to 10), file paths touched (up to 20)
- Writes `state/handoff-latest.json` with trigger `"SessionEnd(clear)"`, timestamp, cwd, workspace memo, and conversation highlights
- Also updates `state/compaction-memo.json` for backward compatibility
- Resets `state/compaction-tracker.json` and `state/behavior-tracker.json` to zero so the new session starts clean
- Emits `{"additionalContext": "[Clear Handoff] Context saved — N user turns, M files touched. Restore path: ..."}` to stdout

**Exit codes:** `0` always (SessionEnd cannot block termination)  
**Files read:** `state/active-workspace.json`, `state/claudeboost-mode.json`, `workspace/*/context.md`, transcript JSONL  
**Files written:** `state/handoff-latest.json`, `state/compaction-memo.json`, `state/compaction-tracker.json`, `state/behavior-tracker.json`  

**Key invariant:** Scoped restore — saves only the active workspace, not all workspaces. The next session via `compaction-restore.py` therefore restores only relevant context.

---

### 1.16 stop-context-guard.py

**File:** `scripts/stop-context-guard.py`  
**Event:** Stop  
**Matcher:** omitted — `Stop` takes no matcher.  
**Type:** Command hook  

**Behavior:**
- Reads `state/compaction-tracker.json` for current `edit_count`
- **Threshold gate**: only activates when `edit_count > THRESHOLD (40)` AND `(edit_count - THRESHOLD) % FIRE_EVERY (20) == 0`
- Finds the most recently modified `workspace/*/context.md`
- If `context.md` age > `STALE_MINUTES (20)`: blocks Claude's stop with a `{"decision": "block", "reason": "..."}` message listing exactly what to document
- Block message reminds to run `/clear-safe` if at a natural stopping point

**Exit codes:**
- `0` = allow stop (below threshold, or context is fresh)
- `2` = block stop (high tool count + stale context.md)

**Files read:** `state/compaction-tracker.json`, `workspace/*/context.md`  
**Thresholds:** `THRESHOLD=40`, `FIRE_EVERY=20`, `STALE_MINUTES=20`  

---

### 1.17 handoff_core.py

**File:** `scripts/handoff_core.py`  
**Invocation:** Shared library — imported by `session-clear-save.py`  
**Type:** Utility module (not a hook)  

**Functions:**
- `extract_conversation(transcript_path, ...)` — parses Claude Code JSONL transcript; collects user messages, assistant snippets, file paths from `tool_use` blocks; deduplicates near-duplicates (>85% similarity); guards against timeout by capping at last 2000 lines
- `format_conversation_md(conversation)` — formats the dict as a markdown block for `additionalContext`

**Key behaviors:**
- Accepts both Unix (`/`) and Windows (`C:\`) absolute paths in `_is_file_path()`
- Rejects shell injection patterns (`&&`, `|`, `$(`, `` ` ``)
- Returns `None` if transcript unreadable or yields no content

**Renamed from:** `handoff-core.py` — hyphen made Python `import` impossible (silent fail); renamed to use underscore.

---

## 2. End-to-End Workflow Traces

### 2.1 Compaction Lifecycle

```
User triggers compaction (context ~90% used — CLAUDE_AUTOCOMPACT_PCT_OVERRIDE=90)
    │
    ▼
PreCompact hooks fire:
    ├── prompt hook: "CONTEXT PRESERVATION — quality-first routing..."
    └── command hook: compaction-save.py
        ├── Reads workspace/*/context.md
        ├── Reads state/claudeboost-mode.json (includes mode in memo)
        ├── Archives to state/compaction-history/<session_id>-compact-<n>.json
        ├── Saves memo to state/compaction-memo.json
        └── Resets state/compaction-tracker.json to {"edit_count": 0}
    │
    ▼
[Claude compacts conversation]
    │
    ▼
SessionStart hooks fire (source="compact"):
    ├── 3x prompt hooks (quality routing, CONSULT protocol, codebase RAG)
    └── command hook: compaction-restore.py
        ├── Checks hook_input["source"] == "compact"
        ├── Reads state/compaction-memo.json
        └── Emits {"additionalContext": "POST-COMPACTION CONTEXT RESTORATION\n..."}
    │
    ▼
Claude receives restored context and resumes work
```

---

### 2.2 Context Nudge

```
Any tool used (matcher: .*)
    │
    ▼
PostToolUse fires:
    └── command hook: context-nudge.py
        ├── Reads state/compaction-tracker.json
        ├── Increments edit_count
        ├── Writes back incremented count
        ├── If workspace/*/context.md exists:
        │   └── If edit_count % 20 == 0:
        │       └── Prints {"additionalContext": "CONTEXT CHECKPOINT: update context.md with code changes AND user statements"}
        └── If no workspace:
            └── If edit_count == 60:
                └── Prints {"additionalContext": "No workspace — consider creating one if this is getting complex"}
    │
    ▼ (every 20th tool use in workspace mode)
Claude receives checkpoint nudge reminding it to update context.md
```

---

### 2.3 CONSULT Gate

```
Claude receives a task (any Edit|Write|MultiEdit on a non-exempt path)
    │
    ▼
Before touching any file, Claude produces a spec sheet:
    ├── What This Does (2-3 plain-language sentences)
    └── Approved Changes table (file | operation | specific change description)
    │
    ▼
Claude stops and waits for user approval
    │
    ▼
User approves → Claude writes state/spec-sheet.json:
    {
      "task": "...",
      "approved_files": ["path/to/file.py", ...],
      "changes": [...]
    }
    │
    ▼
Claude implements — on every Edit|Write|MultiEdit, PreToolUse fires:
    └── command hook: consult-gate.py
        ├── Reads state/claudeboost-mode.json
        ├── If AUTO: exits 0 (no-op)
        ├── If CONSULT:
        │   ├── Checks path(s) against exempt fragments (workspace/, state/, plans/, docs/, .claudeboost/)
        │   ├── Loads state/spec-sheet.json → approved_files list
        │   ├── If no spec-sheet.json: permissionDecision:ask → "produce a spec sheet first"
        │   └── If file not in approved_files: permissionDecision:ask → "extend the spec first"
        └── Always exits 0
    │
    ▼
If a new file is needed mid-implementation:
    1. Claude stops before editing it
    2. Tells user: "I need to also change <file> because <reason>. Should I add it to the spec?"
    3. User approves → Claude updates approved_files in spec-sheet.json → proceeds
```

---

### 2.4 Agent Spawn Enforcement

```
Orchestrator builds spawn prompt and calls Task tool
    │
    ▼
PreToolUse fires:
    └── command hook: agent-spawn-gate.py
        └── stub on this branch: exits 0, reads nothing, writes nothing
    │
    ▼
Agent spawns regardless; nudge is advisory
    │
    ▼
Agent starts execution:
    Step 1: search with POST http://127.0.0.1:8613/search, {"sources":["project:<abs>"],"mode":"both"}
    Step 2: Read ticket.md if exists
    Step 3: Read workspace/[task-id]/context.md
    Step 4: Execute task
    Step 5: Self-critique + Teaching sections (for code-producing agents)
    Step 6: Status report (COMPLETE|BLOCKED|NEEDS_INPUT)
    │
    ▼
PostToolUse fires after Task completes:
    └── prompt hook: "VERIFY GATE: Scan agent output for BLOCKER/HIGH/MEDIUM findings..."
        └── If findings exist: spawn quick-cop to verify
```

---

### 2.5 Verify Gate

```
Finding-producing agent (reviewer, security, performance) completes
    │
    ▼
PostToolUse prompt hook fires:
    "VERIFY GATE: Scan agent output for BLOCKER/HIGH/MEDIUM findings..."
    │
    ▼
Orchestrator scans agent output for BLOCKER/HIGH/MEDIUM findings
    │
    ├── No findings → present results directly to user
    │
    └── Findings present → spawn quick-cop:
        - Receives: specific findings list + cited file:line locations
        - Step 1: search the project on 8613 if it needs context
        - Reads each cited file:line
        - For each finding:
        │   ├── Code matches claim → CONFIRMED (keep)
        │   └── Code does not match → FALSE_POSITIVE (drop)
        └── Returns: only confirmed findings with evidence
    │
    ▼
Present only verified findings to user
(Cost: evaluator ~1000-2000 tokens vs rework from false findings ~5000-10000 tokens)
```

---

### 2.6 TTS (Text-to-Speech)

```
Claude finishes response (Stop event fires)
    │
    ▼
Stop hook: speak-tts.py
    ├── Reads state/speak-state.json
    ├── If disabled: exit immediately
    ├── Filter response text:
    │   ├── strip_markdown (remove formatting)
    │   ├── redact_secrets (hide keys/tokens)
    │   └── condense_for_speech (shorten)
    ├── Write filtered text to $TEMP/claudeboost_tts_text.txt
    ├── Kill existing player:
    │   ├── Write $TEMP/claudeboost_tts.stop
    │   └── SIGTERM by PID from $TEMP/claudeboost_tts.pid
    └── Spawn speak-play.py (detached, DETACHED_PROCESS=0x00000008)
    │
    ▼
speak-play.py (background):
    ├── Write own PID to claudeboost_tts.pid
    ├── Synthesize: edge_tts.Communicate(text, voice).save(mp3_path)
    ├── Play via Windows mciSendString
    └── Poll stop file + space key every 150ms
    │
    ▼
User starts typing → UserPromptSubmit fires:
    └── speak-stop.py:
        ├── Write claudeboost_tts.stop
        └── Kill player by PID
```

---

### 2.7 Clear-Safe → Clear → Restore Lifecycle

```
User runs /clear-safe
    │
    ▼
Slash command clear-safe.md:
    1. Read state/active-workspace.json (field: workspace)
       If missing/invalid: auto-detect via most recently modified workspace/*/context.md
    2. Read active workspace's context.md — audit for 4 checks:
       ├── Status section present and non-empty?
       ├── Next step present and actionable?
       ├── Key decisions documented?
       └── File modified within last 60 minutes?
       If any check fails: DRAFT the missing sections from session context — do not block.
       Re-run checks. If still failing: ask user only about the specific missing field.
    3. Print survival summary:
       ┌─────────────────────────────┐
       │ Active workspace : [task-id]│
       │ context.md age   : N min ago│
       │ Status    : [one-liner]     │
       │ Next step : [next action]   │
       │ Decisions : N documented    │
       └─────────────────────────────┘
    4. Write state/active-workspace.json: {"workspace": "[task-id]"}
    5. Tell user: "Pre-flight complete. Type /clear to proceed."
    │
    ▼
User types /clear
    │
    ▼
SessionEnd hook fires:
    └── command hook: session-clear-save.py
        ├── Gate: source == "" or source == "clear" (no-op otherwise)
        ├── Read state/active-workspace.json → resolve active workspace task-id
        ├── Extract scoped workspace memo from workspace/[task-id]/context.md only
        ├── Parse transcript via handoff_core.extract_conversation():
        │   ├── User messages (up to 15, deduped)
        │   ├── Assistant snippets (up to 10, deduped)
        │   └── File paths from tool_use blocks (up to 20)
        ├── Write state/handoff-latest.json (trigger: "SessionEnd(clear)")
        ├── Update state/compaction-memo.json (backward compat)
        ├── Reset state/compaction-tracker.json + state/behavior-tracker.json to 0
        └── Emit {"additionalContext": "[Clear Handoff] Context saved — N turns, M files"}
    │
    ▼
[Context cleared — new session starts]
    │
    ▼
SessionStart hook fires (source="clear"):
    └── command hook: compaction-restore.py
        ├── source == "clear" path:
        │   ├── Read state/handoff-latest.json
        │   ├── Age guard: reject if timestamp > 30 minutes ago
        │   ├── CWD guard: reject if handoff cwd ≠ current session cwd
        │   └── If both guards pass: emit {"additionalContext": "POST-CLEAR TRANSITION CONTEXT RESTORATION\n...workspace_memo + conversation"}
        └── No-op if guards fail (prevents injecting stale or wrong-project context)
    │
    ▼
Claude receives scoped context:
    - Active workspace memo (only the workspace that was active at /clear time)
    - Recent user messages + files touched from last session
    - Resume instructions pointing to workspace/[task-id]/context.md
```

**Key design properties:**
- Scoped restore: injects ONLY the active workspace's context, not all workspaces
- Age guard prevents stale handoff injection if /clear was run long ago
- CWD guard prevents injecting ClaudeBoost context into unrelated projects
- Drafting (not blocking) in /clear-safe means the audit never stalls the workflow

---

### 2.8 Mode Switching (CONSULT ↔ AUTO)

```
User runs /auto [reason]
    │
    ▼
Slash command auto.md:
    1. Read state/claudeboost-mode.json
    2. Write: {"mode": "AUTO", "setAt": ..., "setBy": "user /auto", "reason": ...}
    3. Confirm to user
    │
    ▼
consult-gate.py now reads mode=AUTO and exits 0 on all file edits
SessionStart CONSULT hook reads AUTO and skips consultation workflow
    │
    ▼
User runs /consult
    │
    ▼
Slash command consult.md:
    1. Read state/claudeboost-mode.json
    2. Write: {"mode": "CONSULT", "setAt": ..., "setBy": "user /consult", ...}
    3. Confirm to user
    │
    ▼
consult-gate.py resumes checking all non-exempt edits and writes against spec-sheet.json
```

---

## 3. Agents

Six agents are installed. They live in `~/.claude/agents/*.md`, and
`clean-rag/portable/agents/` holds the copies the installer ships. There is no
`agents/` directory at the repo root, and no agent anywhere is defined in XML.
Other directories named `agents/` exist further down the tree: the portable
copy above, the OpenCode port, two vendored knowledge corpora, and a cloned
third party repo under `workspace/`. None of them holds an XML agent.

This section used to describe 25 agents over 380 lines, each citing a file at
`agents/<name>.xml`. Two of them existed. A reader following it would try to
spawn architect-agent, reviewer-agent, ticket-analyst-agent or any of the other
23 and get nothing back.

### 3.1 The orchestrator

Not an agent and not spawnable. It is the main session, running under
`~/.claude/CLAUDE.md` plus the project's own `CLAUDE.md`.

### 3.2 The research pair, before the edit

| Agent | Model | Does | Satisfies the research gate |
|---|---|---|---|
| `researcher` | Sonnet | Codebase structure through clean-rag's index and import graph, plus the general engineering standard for this class of change. Also replaces an ad hoc codebase exploring subagent. | yes |
| `swiper` | Sonnet | Whether the thing already exists: the project, the stdlib, a dependency, GitHub, StackOverflow. Reports the exact lines to take. Never writes to the project. | yes |

Order matters. `swiper` runs after `researcher` because it needs those findings
to avoid recommending a swipe for something the project already has.

`RESEARCH_AGENTS` in `clean-rag/hooks/research_state.py` is the list the gate
actually checks, and it holds exactly these two names.

### 3.3 research-agent

**Model:** Sonnet. **Satisfies the research gate:** no.

Web research on untrusted pages. It cannot write files and its Bash is caged to
the local clean-rag server. That capability removal, rather than input
sanitising, is the defense against a prompt injection arriving in a fetched
page. It is the only agent in this codebase with web fetch, deliberately.

### 3.4 The cops, after the edit

| Agent | Model | Runs when | Stamps |
|---|---|---|---|
| `bad-cop` | Sonnet | after any real code change | `VERIFIED:` on a clean pass, `NITS:` on nit severity only, `HANDOFF:` on Critical or High |
| `good-cop` | Opus | only after `HANDOFF:` | `VERIFIED:` once everything is green |
| `quick-cop` | Sonnet | any single "it is done" claim | nothing, and it satisfies no gate |

`bad-cop` writes tests aimed at breaking the change, runs them, and reports with
real execution output. It never fixes. `good-cop` reproduces each finding before
fixing it, and only execution output may overturn execution output.

The loop ends when `bad-cop` stamps `VERIFIED:` itself, never when `good-cop`
says it is done. `bad-cop` has a second mode, `MODE: evidence-judge`, which
judges a finished `/qa` session's artifacts and stamps `FULLY VERIFIED` or
`TEST AGAIN`.

`clean-rag/hooks/verifier_state.py` invalidates a stamp once the file's mtime
moves past it, which is why `bad-cop` does not stamp on a nit only run.

## 4. Knowledge Files

There are none, and there is no topic knowledge base.

This section used to list knowledge files over 317 lines, every one an `.xml`
under `knowledge/`. The repo contains no `.xml` knowledge file. The topic
knowledge base was deleted along with the 8612 server on measured evidence, and
this section is what survived that deletion.

Two directories are named `knowledge/` and neither is what this section
described:

| Path | What is actually in it |
|---|---|
| `.claudeboost/knowledge/` | markdown research notes on specific topics, gathered from real sources |
| `clean-rag/knowledge/` | markdown, filed under subject directories |

Neither is a registered project, so a `project:` source naming one returns
nothing. Read them directly.

Search itself runs over indexed projects and the live web:

| Route | What it searches |
|---|---|
| `POST http://127.0.0.1:8613/search` | your indexed projects. `sources: ["project:<abs path>"]`, `mode: "both"` |
| `POST http://127.0.0.1:8613/web-search` | DuckDuckGo, source ranked, GitHub and StackOverflow first |
| `POST http://127.0.0.1:8613/github-search`, `/github-file` | GitHub code and single files |
| `POST http://127.0.0.1:8613/stackoverflow-search` | StackOverflow |

`clean-rag/CLAUDE.md` carries the full route table, and
`clean-rag/tests/test_skill_rag_routes.py` fails if a skill names a route the
server does not serve.

## 5. Slash Commands

### 5.1 /boost
**File:** `.claude/commands/boost.md`  
**Description:** Activate ClaudeBoost — load RAG and prime the session  
**Tools:** Bash, Read, Glob  
**Steps:**
1. Launch matrix-boost.py animation (new WT tab), clear `__pycache__`, clear Boost RAG and Project RAG flag files
2. Verify privacy env vars (`DISABLE_TELEMETRY`, `DISABLE_ERROR_REPORTING`) — auto-fix if missing
3. Activate RAG: `scripts/boost-run.py` checks the clean-rag server on port 8613 and reports ready or NOT READY
3.5. Index the ClaudeBoost codebase: `POST http://127.0.0.1:8613/index-project` against CLAUDEBOOST_HOME, which keeps its own source searchable
4. Check all 6 hook types via `check-hooks.py` (SessionStart, PreToolUse, PostToolUse, PreCompact, UserPromptSubmit, Stop)
5. Verify `~/.claude/CLAUDE.md` exists
6. Read CONSULT/AUTO mode, clear `session-approvals.json`
7. Scan `workspace/*/context.md` for active tasks
8. Write `$TEMP/claudeboost_active`, write `BOOST:done` to status file
9. Report: Systems Status + Active Workspaces + Session Directives + Collaborative Mode + Ready

---

### 5.2 /auto [reason]
**File:** `.claude/commands/auto.md`  
**Description:** Enter AUTO mode — Claude acts autonomously without consulting on architecture  
**Tools:** Read, Write, Edit, Bash  
**Steps:** Read mode file → write `{"mode": "AUTO", ...}` → confirm to user

---

### 5.3 /consult
**File:** `.claude/commands/consult.md`  
**Description:** Enter CONSULT mode (default) — research + propose + ask before architectural decisions  
**Tools:** Read, Write, Edit, Bash  
**Steps:** Read mode file → write `{"mode": "CONSULT", ...}` → confirm with triggers/not-triggers list

---

### 5.4 /speak [on|off|voice <name>|voices|status]
**File:** `.claude/commands/speak.md`  
**Description:** Toggle text-to-speech  
**Tools:** Read, Write, Bash  
**Subcommands:**
- Empty/`status`: display current state
- `on`: set `enabled: true`, verify edge-tts installed
- `off`: set `enabled: false`
- `voice <name>`: update voice name
- `voices`: list en-US voices via `python -m edge_tts --list-voices`

---

### 5.5 /visualize
**File:** `.claude/commands/visualize.md`  
**Description:** Interactive architecture board opened in browser  
**Steps:**
1. Detect mode: self-map (has agents/ + knowledge/) or project-map
2a. Self-map: run `visualize-extract.py` to build `graph.json`
2b. Project-map: analyze repo manually, build graph.json following template
3. Save to workspace, render `visualize.html` via `render.py`
4. Open HTML board in default browser via `cmd.exe /c start` (Windows path conversion via `cygpath -w`)
5. Report node/edge counts, keyboard shortcuts

---

### 5.6 /walkthrough <url> <feature description> [--output <dir>]
**File:** `.claude/commands/walkthrough.md`  
**Skill:** `skills/walkthrough/SKILL.md`  
**Description:** Generate an interactive step by step tutorial with annotated screenshots  
**Tools:** Read, Write, Edit, Bash, Glob, Grep, Agent, Playwright MCP (navigate, snapshot, click, type, take_screenshot, evaluate, fill_form, select_option, wait_for, press_key, console_messages, resize, close, hover, find)  
**Steps:**
1. Parse arguments: URL (localhost only), feature description, optional output dir
2. Plan 5 to 15 steps, save plan, show to user for approval
3. For each step: navigate/act, wait for stability, inject annotations (Driver.js popovers, numbered badges, arrows, highlight boxes) via `browser_evaluate`, capture screenshot via `browser_take_screenshot`, clean up injected DOM, perform the action
4. Assemble markdown doc with embedded screenshots at `{OUTPUT_DIR}/{SLUG}.md`
5. Verify all screenshot paths exist and step numbering is sequential

**Annotation types:** Driver.js spotlight+popover (CDN injected at runtime, re-injected on navigation), numbered callout badges, directional arrows with labels, highlight boxes. Falls back to pure DOM injection when CDN is unreachable.  
**Safety:** Localhost only. Headed browser. Read only intent (no app code changes). Cleans up all injected DOM.

---

### 5.7 /changes [scope]
**File:** `.claude/commands/changes.md`  
**Description:** Interactive change explorer with AI-generated explanations  
**Tools:** Read, Write, Bash, Glob, Grep  
**Steps:**
1. Resolve scope (auto-detect unstaged/staged/last commit if empty)
2. Get full diff (size gate: ask if >30 files)
3. Agent attribution from recent git log
4. Read `changes-template.json`, fill all fields per `_field_guide`
5. Save `changes.json` + `changes.md` to workspace
6. Launch TUI via `wt.exe -w 0 new-tab python changes-viewer.py`
7. Monitor `$TEMP/claudeboost/changes_chat.json` for TUI chat questions

---

### 5.8 /xray [--deep] [--staged | --branch | --pr <url>]
**File:** `.claude/commands/xray.md`  
**Description:** Quick A-F grade code review by default; add `--deep` for the full 16-pass parallel review with deterministic pre-scan, test execution, and Opus evaluator  
**Tools:** Bash(git diff, gh pr diff), Task (--deep mode)  
**Steps (default):**
1. Resolve diff source (uncommitted+staged / staged only / branch diff / PR diff)
2. Review for CRITICAL (security, data loss, correctness), MAJOR (logic errors, missing error handling), MINOR (style, naming)
3. Grade: A=no issues, B=MINOR only, C=MAJOR present, D=CRITICAL present, F=unreviewable
4. Output structured review with file:line for each issue

**Steps (--deep):**
1-4 as above, then additionally: deterministic pre-scan grep checks, then 15 parallel passes batched covering logic, security, performance, tests, dead code, debug artifacts, banned patterns, pattern consistency, caller impact (graph search), ticket alignment, async patterns, and more; Evaluator Opus agent (always last) classifies every finding (BLOCKER/WARNING/NIT/FALSE POSITIVE)  
**Output:** Grade (A-F), BLOCKERS, WARNINGS, NITS, FALSE POSITIVES

---

### 5.9 /index-project [path or name] [languages] [force]
**File:** `.claude/commands/index-project.md`  
**Description:** Index a project's codebase for semantic search (Project RAG)  
**Steps:**
1. Health check: `GET http://127.0.0.1:8613/status` first
2. Resolve project path: empty=cwd, full path=as-is, short name=fuzzy match in parent of current git root (`dirname $(git rev-parse --show-toplevel)`)
3. Parse language filters and `force` flag
4. Preview what would be indexed and show a summary table
5. Confirmation gate if files_to_index > 500
6. Index: `POST http://127.0.0.1:8613/index-project` with `{"project_path":"<abs>"}`, which also adds the path to the registry at `clean-rag/state/projects.json` so the auto reindex sweep keeps it fresh
7. Verify with `POST http://127.0.0.1:8613/search` with `{"sources":["project:<abs>"],"mode":"both"}`

---

### 5.10 /done
**File:** `.claude/commands/done.md`  
**Description:** Verify work is clean and push to remote  
**Steps:** Pre-flight (git status clean, at least 1 commit) → `git push` (or `git push -u origin HEAD` if no upstream)

---

### 5.11 /handoff [message]
**File:** `.claude/commands/handoff.md`  
**Description:** Save session state and prepare for a fresh context  
**Steps:** Runs `session-clear-save.py` to snapshot active workspace → optionally stores message in handoff-latest.json → instructs user to `/clear` then `/boost` in next session (SessionStart hook restores context automatically)

---

### 5.12 /qa [target-url] [scope]
**File:** `.claude/commands/qa.md`  
**Description:** Full QA session — learns the project via RAG + graph traversal, auto-detects or starts the dev server, builds a complete app inventory, writes a risk-prioritized test plan, executes browser tests with annotated screenshot evidence, and reports what was AND was not tested  
**Argument:** optional `<target-url>` (localhost only; auto-detected if omitted) + optional `scope` (auth|crud|nav|errors|responsive|all|quick; default: all) + `--no-debug` + `--fresh`  
**Agents:** `researcher` for the codebase analysis, `bad-cop` with `MODE: evidence-judge` to judge the evidence at the end  
**Phases:**
- Phase 0: Parse args, auto-detect URL (context.md Dev URL → port probe → package.json/launchSettings → ask), hard-stop on staging/prod, derive task ID with project slug, create workspace, load RAG knowledge, index project; Phase 0g builds **complete app inventory** via 6 parallel RAG searches (routes, mutations, auth, entities, jobs, integrations) → writes `app-inventory.md`
- Phase 1: Browser crawl (nav links + snapshot-only); then **inventory cross-reference** — navigates every route in app-inventory.md not yet visited, classifying each as accessible/auth-blocked/broken; builds component registry and App Map
- Phase 2: Journey-based test plan — derived from app-inventory entities (completeness gate), ticket content, and browser discoveries; risk-scored journeys; flow-map.md written before any TCs; quick-cop removes unverified TCs; PAUSE for user approval
- Phase 3: Test execution — browser MCP tools only; snapshot-first; red-box annotation gate; mcp-debugger step-through; coverage gap analysis (compares executed TCs against inventory — writes `coverage-gaps.md`); screenshot evaluator audit
- Phase 4: Report with explicit "What Was NOT Tested" and "QA Observations" sections  
**Key outputs:** `app-inventory.md`, `flow-map.md`, `plan.md`, `coverage-gaps.md`, `report.md`, `screenshots/proof-*/`  
**Anti-cheat enforcement:** No Bash DB queries, no API bypasses, no fabricated PASS — honest FAIL is the output  
**Hard stops:** Production/staging URLs blocked; coverage gaps must be explicitly listed in report — no silent omissions

---

### 5.13 /clear-safe

**File:** `.claude/commands/clear-safe.md`  
**Description:** Pre-flight verified context clear — verifies workspace state is captured before you type /clear  
**Tools:** Read, Write  
**Steps:**
1. Read `state/active-workspace.json`; if missing, auto-detect most recently modified `workspace/*/context.md`
2. Audit context.md for 4 checks: Status present, Next step present, Key decisions documented, file < 60 min old
   - If any check fails: **draft** the missing sections from session knowledge, write them to context.md, re-check
   - Only ask the user if a section genuinely cannot be inferred
3. Show survival summary: active workspace, context.md age, Status/Next step/Decisions count, scoped-restore notice
4. Write `state/active-workspace.json: {"workspace": "[task-id]"}`
5. Tell user to type `/clear`; SessionEnd hook saves state automatically

**Key behavior:** Does NOT call /clear — user types it themselves after seeing the summary.  
**Scoped restore:** The next session via `compaction-restore.py` restores ONLY the active workspace, not all workspaces.  
**Related hooks:** `session-clear-save.py` (SessionEnd), `stop-context-guard.py` (Stop), `compaction-restore.py` (SessionStart)

---

## 6. Hook Registration

**Global settings:** `~/.claude/settings.json` — 46 registrations.
**Project settings:** `C:\Development\ClaudeBoost\.claude\settings.json` — 6 registrations.
**Total:** 52, spread across seven events.

Both files are the source of truth. This section deliberately does not list
every registration: the table that used to sit here listed 14 of them, named
three hooks that Claude Code refuses to load, and described the project file as
carrying no hooks at all. Read the settings files instead; `scripts/setup.py`
is what writes them.

### 6.1 Matcher values, per event

Getting this wrong is silent. An unrecognised matcher string does not raise;
the hook simply never fires, and nothing in the transcript says why.

| Event | Valid matcher values | Omitting the key |
|---|---|---|
| `PreToolUse` / `PostToolUse` | a tool name or a regex over tool names, for example `Task`, `Bash`, `Edit\|Write` | matches every tool |
| `SessionStart` | `startup`, `resume`, `clear`, `compact` | matches every source |
| `PreCompact` | `manual`, `auto` | matches both |
| `SessionEnd` | the session end source | matches every source |
| `Stop` / `UserPromptSubmit` | no matcher | n/a |

**`Always` is not a matcher value on any event.** It reads like one, which is
why it survived in this document and in `setup.py` for as long as it did. A
`SessionStart` entry carrying `"matcher": "Always"` matched no source, so
`compaction-restore.py` and the rest of the session restore chain stopped
running. That is the defect this table exists to prevent, not a hypothetical.

### 6.2 Prompt-type hooks

`SessionStart` does not accept them. Claude Code rejects the registration with
"prompt-type hooks are not supported for SessionStart events (no conversation
context is available)". Three used to be listed here. Use a command hook that
writes `additionalContext` to stdout instead.

## 7. Configuration & State Files

### 7.1 Environment Variables (user settings.json `env` section)

| Variable | Value | Purpose |
|----------|-------|---------|
| `CLAUDEBOOST_HOME` | `C:/path/to/ClaudeBoost` | Root path for all ClaudeBoost scripts/state |
| `DISABLE_TELEMETRY` | `1` | Disable Claude Code telemetry |
| `DISABLE_ERROR_REPORTING` | `1` | Disable error reporting |
| `DISABLE_FEEDBACK_COMMAND` | `1` | Hide feedback prompt |
| `CLAUDE_CODE_DISABLE_FEEDBACK_SURVEY` | `1` | Disable survey |
| `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE` | `90` | Auto-compact at 90% context usage — raised to give more working room before auto-compact fires as a safety-net fallback |
| `ENABLE_PROMPT_CACHING_1H` | `1` | Enable 1-hour prompt caching |

### 7.2 state/claudeboost-mode.json

```json
{
  "mode": "CONSULT",
  "setAt": "2026-04-10T00:00:00Z",
  "setBy": "default",
  "reason": "ClaudeBoost default"
}
```

- `mode`: `CONSULT` or `AUTO`
- Missing file = CONSULT (default)
- Updated by `/auto` and `/consult` commands

### 7.3 state/compaction-tracker.json

```json
{"edit_count": 203}
```

- Incremented by `context-nudge.py` on every tool use (matcher: `.*`)
- Reset to 0 by `compaction-save.py` on PreCompact
- Every 20th tool use triggers context checkpoint (workspace mode); once at 60 uses triggers workspace-creation suggestion (no-workspace mode)

### 7.4 state/session-approvals.json

```json
{"sessionId": "", "approvals": []}
```

- Cleared by `/boost` at session start
- Written when user approves an architectural decision via AskUserQuestion

### 7.5 state/speak-state.json

```json
{
  "enabled": false,
  "voice": "en-US-AndrewNeural",
  "setAt": "<ISO 8601>",
  "setBy": "user /speak on"
}
```

- Read by `speak-tts.py` on every Stop event
- Updated by `/speak` command

### 7.6 state/compaction-memo.json

```json
{
  "session_id": "<id>",
  "compaction_number": 1,
  "timestamp": "<ISO 8601>",
  "memo": "<extracted workspace summaries>"
}
```

- Written by `compaction-save.py` on PreCompact
- Read by `compaction-restore.py` on SessionStart (when source="compact")

### 7.7 statusLine

The user settings.json includes a status line command:
```bash
printf '\033[32;1m> ClaudeBoost\033[0m'; [ -f "$TEMP/claudeboost_rag_ok" ] && printf ' \033[2m|\033[0m \033[32;1mBoost RAG\033[0m'; [ -f "$TEMP/claudeboost_project_rag_ok" ] && printf ' \033[2m|\033[0m \033[36;1mProject RAG\033[0m'; command -v gt >/dev/null 2>&1 && printf ' \033[2m|\033[0m \033[33;1mGT\033[0m'
```

Four independent indicators:
- **ClaudeBoost** (green bold): always shown — ClaudeBoost is globally registered
- **Boost RAG** (green bold): shown only when `$TEMP/claudeboost_rag_ok` exists (written by `/boost` Step 2 on RAG health check success; cleared at Step 0 of next `/boost` run)
- **Project RAG** (cyan bold): shown only when `$TEMP/claudeboost_project_rag_ok` exists. `project-rag-flag.py` used to write it and that script no longer exists in `scripts/` or `clean-rag/hooks/`, and is registered in neither settings file, so nothing writes the flag now. `/boost` still clears it at its Step 0.
- **GT** (yellow bold): shown only when `gt` binary is on PATH (live `command -v` check — no flag file needed)

### 7.8 state/active-workspace.json

```json
{"workspace": "clear-instead-of-compact"}
```

- Written by `/clear-safe` Step 4 — records which workspace is active before /clear
- Read by `session-clear-save.py` (SessionEnd) to scope the handoff to one workspace
- Falls back to most recently modified `workspace/*/context.md` if missing or invalid
- Write `{"workspace": ""}` if no active workspace

---

### 7.9 Global Settings

| Setting | Value | Effect |
|---------|-------|--------|
| `model` | `sonnet` | Default model for all interactions |
| `alwaysThinkingEnabled` | `true` | Extended thinking always on |
| `effortLevel` | `high` | High reasoning effort |
| `voice.enabled` | `true` | Voice input enabled |
| `voice.mode` | `hold` | Hold-to-speak mode |

---

### 7.10 Context Threshold (CLAUDE_AUTOCOMPACT_PCT_OVERRIDE)

Set `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE` to control when auto-compact fires:

```
CLAUDE_AUTOCOMPACT_PCT_OVERRIDE=90
```

Default is ~75-83% (Claude Code version dependent). Setting to 90 gives
more working room before auto-compact fires as a safety-net fallback.
Do not set above 95 — the compaction process needs a token buffer to build
its summary, and too little buffer causes compaction to fail.

**To update:** Add or change the value in `~/.claude/settings.json` under
the `env` key. Takes effect on next Claude Code start.

**Why 90 and not higher:** With the clear-instead-of-compact system installed,
auto-compact is a safety net only. The primary path is Claude manually running
`/clear` at a natural stopping point when `context-nudge.py` fires the
CONTEXT HEALTH CHECK nudge (at 100+ tool uses). Setting to 90 ensures there
is always enough buffer for the compaction LLM to summarize if `/clear` is
not run in time.

**Clear-instead-of-compact state files:**

| File | Written by | Read by | Purpose |
|------|-----------|---------|---------|
| `state/handoff-latest.json` | `compaction-save.py` (PreCompact), `session-clear-save.py` (SessionEnd) | `compaction-restore.py` (SessionStart) | Unified handoff for both compact and /clear paths |
| `state/compaction-memo.json` | `compaction-save.py`, `session-clear-save.py` | `compaction-restore.py` (fallback) | Backward-compat memo; kept for external tooling |

`state/handoff-latest.json` schema:
```json
{
  "session_id": "...",
  "timestamp": "2026-05-12T18:00:00+00:00",
  "trigger": "PreCompact | SessionEnd(clear)",
  "cwd": "C:/path/to/ClaudeBoost",
  "workspace_memo": "# Active Workspaces\n...",
  "conversation": {
    "user_messages": ["..."],
    "assistant_snippets": ["..."],
    "files_touched": ["..."]
  }
}
```

---

## 8. Search backend

**One server, port 8613.** `clean-rag/`, started by
`clean-rag/cli/server_ctl.py start` or `/rag`. It runs headed so you can watch
it.

There is no MCP RAG server and no `mcp-rag-server/` directory. This section used
to document one as "Installed at: `mcp-rag-server/` via `pip install -e`", along
with `rag_search`, `rag_index`, `rag_context`, a `scope=` parameter, agent
definitions read from `agents/<name>.xml`, and guardrail files named
`security.xml` and `coding-standards.xml`. All of it belonged to the 8612 server
that was deleted with its topic knowledge base. Calling any of it gets you
connection refused rather than an error you would notice.

### 8.1 The one route that matters

```
POST http://127.0.0.1:8613/search
{"query":"how does auth work","sources":["project:C:/abs/path"],"mode":"both","limit":8}
```

`sources`, not `scope`. A list of `project:<absolute path>`; several at once is
fine, and each is queried with the embedding model its own index was built with.

`mode: "both"` on every code search. Vector similarity and import graph
traversal surface different files, and one without the other leaves a gap. Graph
results carry `relation` (imports, inherits, implements, calls) and `seed_file`.

A source only works if that path is a registered project. A directory of
markdown you never indexed returns nothing, silently. `stale_projects` in the
response with `served: false` means the index exists but was refused, and the
reason field says why. Zero results plus that field is a broken index, not an
empty codebase.

### 8.2 Other routes

`/index-project`, `/reindex-file`, `/status`, `/projects`, `/web-search`,
`/github-search`, `/github-file`, `/stackoverflow-search`, `/run-tests`,
`/mutation-test`, `/security-scan`.

`clean-rag/CLAUDE.md` has the full table with request shapes.
`clean-rag/tests/test_skill_rag_routes.py` fails if any skill names a route the
server does not serve, so this list cannot drift again without a red test.

### 8.3 Indexes

One kind, per project. `/index-project` builds it, and it reindexes itself after
every edit plus a full sweep every 10 minutes for outside changes.

The old two index split (a "ClaudeBoost RAG" over `agents/` and `knowledge/`,
beside a "Project RAG") went with the 8612 server. Only the project index
remains.

---

*End of ClaudeBoost Reference Manual*
