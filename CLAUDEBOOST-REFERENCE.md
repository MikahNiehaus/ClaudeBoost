# ClaudeBoost Reference Manual

**Generated:** 2026-05-08  
**Coverage:** All 17 hook registrations, 22 agent XMLs + orchestrator, 43 knowledge XMLs, 20 slash commands, settings.json hooks registration, all state files, MCP RAG server code.

---

## Table of Contents

1. [Hook Scripts](#1-hook-scripts)
2. [End-to-End Workflow Traces](#2-end-to-end-workflow-traces)
3. [Agents](#3-agents)
4. [Knowledge Files](#4-knowledge-files)
5. [Slash Commands](#5-slash-commands)
6. [Hook Registration (settings.json)](#6-hook-registration)
7. [Configuration & State Files](#7-configuration--state-files)
8. [MCP RAG Server](#8-mcp-rag-server)

---

## 1. Hook Scripts

### 1.1 agent-spawn-gate.py

**File:** `scripts/agent-spawn-gate.py`  
**Event:** PreToolUse  
**Tool matcher:** `Task`  
**Type:** Command hook  

**Behavior:**
- Reads spawn prompt from `stdin` as JSON (`{"tool_input": {"prompt": "..."}}`)
- Checks (case-insensitive) for `rag_context` OR `mcp__rag-server__rag_context` in the prompt
- If missing: writes a 4-line nudge to `stderr`
- Also checks that `project_path` is present in the prompt
- For `architect-agent` specifically: checks for the literal string `PROPOSAL_ONLY` AND at least 2 `file:line` citations via regex `[\w./\\-]+\.[\w]+:\d+(?:-\d+)?`
- Always exits `0` — this is a nudge, not a hard block

**Exit codes:** `0` always  
**stdin format:** JSON with `tool_input.prompt` field  
**stderr:** Nudge text if rag_context missing  

**Key invariant:** "It is a nudge, not a gate." Agent spawns always proceed.

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
**Tool matcher:** `Always`  
**Type:** Command hook  

**Behavior:**
1. Reads all `workspace/*/context.md` files
2. Extracts summaries from each
3. Archives summaries to `state/compaction-history/` with timestamp filename
4. Saves memo to `state/compaction-memo.json` as `{session_id, compaction_number, timestamp, memo}`
5. Resets `state/compaction-tracker.json` to `{"edit_count": 0}`

**stdout:** Nothing (or success message)  
**Files read:** `workspace/*/context.md`  
**Files written:** `state/compaction-memo.json`, `state/compaction-history/<timestamp>.json`, `state/compaction-tracker.json`  

---

### 1.4 compaction-restore.py

**File:** `scripts/compaction-restore.py`  
**Event:** SessionStart  
**Tool matcher:** `Always`  
**Type:** Command hook  

**Behavior:**
- Only fires when `hook_input.get("source") == "compact"` (i.e., after a compaction, not on fresh session start)
- Reads `state/compaction-memo.json`
- Emits `{"additionalContext": "POST-COMPACTION CONTEXT RESTORATION\n..."}` to stdout

**stdout:** JSON with `additionalContext` key containing the restored memo  
**Files read:** `state/compaction-memo.json`  

**Key invariant:** No-ops on regular session starts; only activates after compaction.

---

### 1.5 consult-gate.py

**File:** `scripts/consult-gate.py`  
**Event:** PreToolUse  
**Tool matcher:** `Edit|Write|MultiEdit`  
**Type:** Command hook  

**Behavior:**
1. Reads `state/claudeboost-mode.json`
2. If mode is not CONSULT, exits 0 (no-op)
3. If CONSULT, checks the file path against exempt fragments:
   - `/workspace/`, `/.claude/`, `/knowledge/`, `/plans/`, `/docs/`, `/mayor/`, `/polecats/`, `/refinery/`, `/witness/`, `/crew/`
4. If the path is exempt, exits 0
5. Checks `state/session-approvals.json` for existing approval
6. If path is non-exempt AND not approved: writes 4-line nudge to `stderr`
7. Always exits `0` — never blocks

**Exit codes:** `0` always  
**Files read:** `state/claudeboost-mode.json`, `state/session-approvals.json`  

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

### 1.10 check-rag-health.py

**File:** `scripts/check-rag-health.py`  

**Exit codes:**
- `0` = healthy
- `2` = dependency drift (ImportError — tokenizers/transformers mismatch)
- `3` = wrong path (RAG server installed from unexpected location)
- `1` = other failure

Used by `/boost` Step 2 to determine if auto-repair is needed.

---

### 1.11 reinstall-rag.py

**File:** `scripts/reinstall-rag.py`  
Runs `pip install -e <rag_server_path>` and upgrades `sentence-transformers`. Used for auto-repair during `/boost`.

---

### 1.12 check-hooks.py

**File:** `scripts/check-hooks.py`  
**Args:** `<hook_event_name>` (e.g., `PreToolUse`)  
Reads `settings.json` (user-level) and asserts that the specified hook event is registered. Used by `/boost` Step 4.

---

### 1.13 check-rag-path.py

**File:** `scripts/check-rag-path.py`  
Prints `rag_server.__file__` — the filesystem path where rag_server is installed. Used to verify correct installation location.

---

### 1.14 matrix-boost.py

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

### 1.15 visualize-extract.py

**File:** `scripts/visualize-extract.py`  
**Args:** `<source_dir> <output_graph_json>`  

**Behavior:**
- Reads `agents/*.xml` (skipping files prefixed with `_`)
- Builds a layered `graph.json` with 5 layers: user, core, agents, knowledge, enforcement
- Each node has: id, label, kind, purpose, layer
- Each edge has: from, to, kind, label

Used by `/visualize` Step 2a (self-map mode).

---

### 1.16 changes_core.py + changes-viewer.py

**Files:** `scripts/changes_core.py`, `scripts/changes-viewer.py`  
**Framework:** Textual (Python TUI library)  

**Architecture:**
- `BaseChangesViewer` — base class with common change-viewing logic
- `HudChangesViewer` — subclass with heads-up display overlay
- Reads `changes.json` produced by `/changes` command
- Opens in a Windows Terminal tab via `wt.exe -w 0 new-tab`
- Has a chat input box; questions are written to `$TEMP/claudeboost/changes_chat.json`

---

### 1.17 chat-watcher.py

**File:** `scripts/chat-watcher.py`  
Polls `$TEMP/claudeboost/changes_chat.json` every 3 seconds for up to 15 minutes, waiting for a question from the TUI's chat input.

---

### 1.18 project-rag-flag.py

**File:** `scripts/project-rag-flag.py`  
**Event:** PostToolUse  
**Tool matcher:** `mcp__rag-server__rag_index_project`  
**Type:** Command hook  

**Behavior:**
1. Reads tool output from stdin (PostToolUse JSON payload)
2. Extracts tool result from `tool_response`, `output`, `result`, or root payload (handles all Claude Code payload shapes)
3. If result contains `files_indexed` key → writes `$TEMP/claudeboost_project_rag_ok` (indicates active Project RAG index)
4. Otherwise (error or unexpected output) → deletes `$TEMP/claudeboost_project_rag_ok` to clear stale flag

**Exit codes:** `0` always  
**Purpose:** Lets the status line show "Project RAG" independently from "Boost RAG"  
**Files written:** `$TEMP/claudeboost_project_rag_ok`  
**Timeout:** 3000ms  

---

## 2. End-to-End Workflow Traces

### 2.1 Compaction Lifecycle

```
User triggers compaction (context ~60% used — CLAUDE_AUTOCOMPACT_PCT_OVERRIDE=60)
    │
    ▼
PreCompact hooks fire:
    ├── prompt hook: "CONTEXT PRESERVATION — quality-first routing..."
    └── command hook: compaction-save.py
        ├── Reads workspace/*/context.md
        ├── Archives to state/compaction-history/<timestamp>.json
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
Architectural trigger detected (new endpoint, class, table, dep, middleware, etc.)
    │
    ▼
User or orchestrator attempts Edit|Write|MultiEdit on non-exempt path
    │
    ▼
PreToolUse fires:
    └── command hook: consult-gate.py
        ├── Reads state/claudeboost-mode.json
        ├── If AUTO: exits 0 (no-op)
        ├── If CONSULT:
        │   ├── Checks path against exempt fragments
        │   ├── Checks state/session-approvals.json
        │   └── If non-exempt and no approval: writes stderr nudge
        └── Always exits 0 (never blocks)
    │
    ▼
Orchestrator (alerted by nudge) should:
    1. rag_search(feature keywords) + read 2-3 project files
    2. Spawn architect-agent (Opus) with PROPOSAL_ONLY + file:line citations
    3. Present options via AskUserQuestion
    4. Log approval to state/session-approvals.json
    5. Implement approved design
```

---

### 2.4 Agent Spawn Enforcement

```
Orchestrator builds spawn prompt and calls Task tool
    │
    ▼
PreToolUse fires:
    └── command hook: agent-spawn-gate.py
        ├── Reads spawn prompt from stdin JSON
        ├── Checks for "rag_context" in prompt (case-insensitive)
        ├── If missing: writes nudge to stderr
        ├── Checks project_path is present
        ├── If agent is architect-agent:
        │   ├── Checks for literal "PROPOSAL_ONLY"
        │   └── Checks for >= 2 file:line citations (regex)
        └── Always exits 0
    │
    ▼
Agent spawns regardless; nudge is advisory
    │
    ▼
Agent starts execution:
    Step 1 (MANDATORY): rag_context(agent=..., task_description=..., project_path=..., max_tokens=..., weight=...)
    Step 2: Read ticket.md if exists
    Step 3: Read workspace/[task-id]/context.md
    Step 4: Execute task
    Step 5: Self-critique + Teaching sections (for code-producing agents)
    Step 6: Status report (COMPLETE|BLOCKED|NEEDS_INPUT)
    │
    ▼
PostToolUse fires after Task completes:
    └── prompt hook: "VERIFY GATE: Scan agent output for BLOCKER/HIGH/MEDIUM findings..."
        └── If findings exist: spawn evaluator-agent to verify
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
    └── Findings present → spawn evaluator-agent:
        - Receives: specific findings list + cited file:line locations
        - Step 1: rag_context (lightweight)
        - Reads each cited file:line
        - For each finding:
        │   ├── Code matches claim → VERIFIED (keep)
        │   └── Code does not match → FALSE POSITIVE (drop)
        └── Returns: only verified findings with evidence
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

### 2.7 Mode Switching (CONSULT ↔ AUTO)

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
consult-gate.py resumes checking all non-exempt writes
```

---

### 2.8 RAG Context Loading (rag_context tiered system)

```
Agent calls rag_context(agent=..., task_description=..., project_path=..., max_tokens=..., weight=...)
    │
    ▼
MCP RAG server: _build_context()
    │
    ├── Tier 0: Agent definition
    │   └── Reads agents/<agent-name>.xml from ChromaDB "agents" collection
    │
    ├── Tier 1: Universal guardrails (skipped if weight=lightweight)
    │   └── GUARDRAIL_FILES: security.xml, observability.xml, coding-standards.xml, scope-governance.xml
    │       Up to 40% of token budget
    │
    ├── Tier 2: Declared knowledge bases
    │   └── Reads <knowledge-base> elements from agent XML
    │       Up to 50% of remaining budget
    │
    ├── Tier 3: Semantic search
    │   └── rag_search(query=task_description, scope="all", min_score=0.4)
    │       Results ranked by similarity score
    │
    └── Tier 4: Project codebase (if project_path provided and indexed)
        └── Per-project ChromaDB at <project>/workspace/.rag-index/
            Budget capped at min(400, remaining_tokens)
    │
    ▼
Returns assembled context string to agent
Agent reads and internalizes before taking any action
```

---

## 3. Agents

### Model Routing
- **Opus:** architect-agent, ticket-analyst-agent, reviewer-agent
- **Sonnet (default):** all others

### Spawn Template Types
- **Full** (reviewer, security, performance): verify gate + evaluator after completion
- **Standard** (workflow, refactor, debug, test, ui, architect, ticket-analyst, browser, evaluator): no verify gate
- **Lightweight** (explore, research, docs, estimator): minimal ceremony

---

### 3.1 _orchestrator (not spawned — the orchestrator itself)

**File:** `agents/_orchestrator.xml`  
**Role:** Lead agent coordinating all specialist agents  
**Key behaviors:**
- Ticket detection: 2+ of 6 heuristic signals → save verbatim to `workspace/[task-id]/ticket.md`
- NORMAL mode (default) vs PERSISTENT mode (never auto-enable, ask user)
- Pre-planning questions across 4 sections: Risk, Options, Justification, Scope
- Planning checklist: 9 domains (Testing, Docs, Security, Architecture, Performance, Review, Clarity, Browser Testing, Observability)
- Workspace structure: `ticket.md`, `context.md`, `mockups/`, `outputs/`, `snapshots/`
- Pre-completion verification: all criteria → build passes → tests pass → lint clean → todo items complete

---

### 3.2 architect-agent

**File:** `agents/architect-agent.xml`  
**Model:** Opus  
**Role:** System design, SOLID principles, design patterns  
**Key behaviors:**
- **PROPOSAL_ONLY contract:** Returns BLOCKED if prompt does not contain literal "PROPOSAL_ONLY" AND at least 2 `file:line` citations
- Output: Required-by-standards + 2-3 grounded options with trade-offs + recommendation
- Handoff: via AskUserQuestion; approval logged to `state/session-approvals.json`
- Knowledge: `architecture.xml`, `coding-standards.xml`

---

### 3.3 reviewer-agent

**File:** `agents/reviewer-agent.xml`  
**Model:** Opus  
**Role:** PR review, code quality gate  
**Key behaviors:**
- 11-pass trigger-conditional checklist (see pr-review.xml)
- FULL spawn template — always followed by evaluator-agent for BLOCKER/HIGH findings
- Required: Best Practices Assessment (SOLID + GoF + OOP + Clean Code + Metrics)
- Outputs grade A-F with PASS/FAIL/SKIP verdict

---

### 3.4 ticket-analyst-agent

**File:** `agents/ticket-analyst-agent.xml`  
**Model:** Opus  
**Role:** Requirements analysis, scope clarification  
**Key behaviors:**
- 5 understanding levels: Literal → Intent → Context → Implicit → Constraint
- Must use EXACT wording from `ticket.md` — never paraphrase
- INVEST criteria, Given-When-Then format
- Scope creep prevention: 4-step response when out-of-scope requests detected

---

### 3.5 security-agent

**File:** `agents/security-agent.xml`  
**Model:** Sonnet  
**Role:** OWASP Top 10 assessment, secure code review  
**Key behaviors:**
- FULL spawn template — findings require evaluator verification
- Output: Executive Summary → Vulnerabilities → Checklist → Priority table
- OWASP Top 10 2021 coverage: A01 Broken Access Control through A10 SSRF
- Behavioral guidelines: assume breach, defense in depth, least privilege, fail secure
- Knowledge: `security.xml`, `architecture.xml`

---

### 3.6 performance-agent

**File:** `agents/performance-agent.xml`  
**Model:** Sonnet  
**Role:** Profiling, bottleneck identification, optimization  
**Key behaviors:**
- FULL spawn template
- Latency targets: p50 < 100ms, p90 < 200ms, p99 < 500ms
- Knowledge: `performance.xml`

---

### 3.7 workflow-agent

**File:** `agents/workflow-agent.xml`  
**Model:** Sonnet  
**Role:** Complex multi-step implementations  
**Key behaviors:**
- STANDARD spawn template
- 5 failure patterns to avoid: premature stopping, test manipulation, context drift, scope creep, skipping verification
- Plan-then-execute: Explore → Plan → Implement → Commit
- Circuit breaker: 5 attempts max before escalating
- Knowledge: `workflow.xml`, `observability.xml`

---

### 3.8 debug-agent

**File:** `agents/debug-agent.xml`  
**Model:** Sonnet  
**Role:** Bug investigation, root cause analysis  
**Key behaviors:**
- STANDARD spawn template
- 5 debugging frameworks: CoT, ReAct, Self-Ask, Five Whys, Structured Prompt
- Failure indicators: 2-3 iterations without progress, repetition loop
- 20-30 minute time box
- Knowledge: `debugging.xml`

---

### 3.9 test-agent

**File:** `agents/test-agent.xml`  
**Model:** Sonnet  
**Role:** TDD, test writing, coverage  
**Key behaviors:**
- STANDARD spawn template
- TDD: Red-Green-Refactor
- Required categories: happy path, edge cases, error conditions, state transitions, async edge cases
- Mock guidance: external APIs/DB/filesystem/time — never mock the subject
- Production safety: never use production URLs/keys/destructive SQL without WHERE
- Knowledge: `testing.xml`

---

### 3.10 refactor-agent

**File:** `agents/refactor-agent.xml`  
**Model:** Sonnet  
**Role:** Code smells, cleanup, technical debt  
**Key behaviors:**
- STANDARD spawn template
- Trigger thresholds: >40 lines / complexity>10 / params>4 / class>300 / duplication>3
- Safe process: ensure tests → commit → one change → run tests → commit → repeat
- Knowledge: `refactoring.xml`

---

### 3.11 ui-agent

**File:** `agents/ui-agent.xml`  
**Model:** Sonnet  
**Role:** UI/frontend implementation  
**Key behaviors:**
- STANDARD spawn template
- jQuery BANNED — use React hooks or vanilla JS
- Reuse-first protocol: search → component library → shared hooks → create new
- Images first in prompts, XML spec structure
- Knowledge: `ui-implementation.xml`

---

### 3.12 docs-agent

**File:** `agents/docs-agent.xml`  
**Model:** Sonnet  
**Role:** Documentation writing  
**Key behaviors:**
- LIGHTWEIGHT spawn template
- 80% WHY / 15% WHAT / 5% HOW ratio
- Never restate code line-by-line
- Knowledge: `documentation.xml`

---

### 3.13 estimator-agent

**File:** `agents/estimator-agent.xml`  
**Model:** Sonnet  
**Role:** Story points, effort estimation  
**Key behaviors:**
- LIGHTWEIGHT spawn template
- Fibonacci scale: 1/2/3/5/8/13 (must-split at 13)
- 9 complexity multipliers
- Knowledge: `story-pointing.xml`

---

### 3.14 explore-agent

**File:** `agents/explore-agent.xml`  
**Model:** Sonnet  
**Role:** Codebase understanding  
**Key behaviors:**
- LIGHTWEIGHT spawn template
- 4 workflows: Quick Overview (<5 min), Feature Understanding (5-15 min), Dependency Analysis (10-20 min), Architecture Discovery (20-30 min)
- Knowledge: `code-exploration.xml`

---

### 3.15 research-agent

**File:** `agents/research-agent.xml`  
**Model:** Sonnet  
**Role:** Web research, fact verification  
**Key behaviors:**
- LIGHTWEIGHT spawn template
- Methodology: Planning → Execution → Verification → Synthesis
- Source credibility tiers: 1=High Authority, 2=Medium, 3=Requires Verification
- Never present unverified information as fact
- Knowledge: `research.xml`

---

### 3.16 browser-agent

**File:** `agents/browser-agent.xml`  
**Model:** Sonnet  
**Role:** Interactive browser testing via Playwright  
**Key behaviors:**
- STANDARD spawn template
- Always use `mcp__playwright__*` MCP tools directly (never write Playwright code unless explicitly asked)
- Auto-allow: localhost, 127.0.0.1, OAuth domains; ask for external URLs
- Package: `@playwright/mcp`
- Knowledge: `playwright.xml`

---

### 3.17 evaluator-agent

**File:** `agents/evaluator-agent.xml`  
**Model:** Sonnet  
**Role:** Output verification, quality gate  
**Key behaviors:**
- STANDARD spawn template
- Receives specific findings + file:line citations
- Reads actual code at each cited location
- Verdicts: VERIFIED (keep) / FALSE POSITIVE (drop)
- Cost: ~1000-2000 tokens vs ~5000-10000 tokens rework from false findings

---

## 4. Knowledge Files

### 4.1 api-design.xml
**Triggers:** API, REST, GraphQL, endpoint, status code, versioning, rate limiting  
**Domain:** API design patterns  
**Content:** REST vs GraphQL decision matrix; HTTP status codes (RFC 9457 error format); versioning strategies (URI, header, query param); rate limiting headers (`X-RateLimit-*`); GraphQL schema patterns

---

### 4.2 architecture.xml
**Triggers:** architecture, design, SOLID, patterns, clean architecture, DDD, coupling  
**Domain:** System and code architecture  
**Content:** SOLID principles with violation signs and examples; Clean Architecture layers; DDD concepts (Entity, Value Object, Aggregate, Bounded Context); GoF patterns (Creational/Structural/Behavioral); quality metrics (cyclomatic complexity ranges 1-4=simple, 5-7=moderate, 8-10=complex, 11+=refactor); anti-patterns; ADR template

---

### 4.3 branching-strategy.xml
**Triggers:** git branch, trunk, release, feature branch, conventional commits  
**Domain:** Git workflow  
**Content:** Three-tier branching (trunk ← release ← feature); Jira ticket ID must be UPPERCASE; conventional commit format with ticket in body (not subject); cherry-pick must go through new feature branch + PR (never direct to team branch — Shane's PE PR #437 correction); cross-repo coordination (PantryEasy + Nectar)

---

### 4.4 code-critique.xml
**Triggers:** critique, review, self-review, code quality, checklist  
**Domain:** Code review methodology  
**Content:** Line-by-line checklist (Purpose/Simplicity/Correctness/Abstraction/Safety); required output sections (Line-by-Line Review Table, Assumptions Made, Edge Cases Not Covered, Trade-offs Accepted); confidence guidelines

---

### 4.5 code-exploration.xml
**Triggers:** explore, codebase, understand, find, architecture, navigate  
**Domain:** Codebase navigation  
**Content:** 4 exploration workflows with durations; glob patterns; entry-point patterns by language; grep patterns for common searches; dependency metrics (afferent/efferent coupling, instability); layer identification; large codebase strategies

---

### 4.6 code-teaching.xml
**Triggers:** teach, explain, why, learn, decision, alternative, pattern  
**Domain:** Educational code explanations  
**Content:** Every code change must include a Teaching section; required sections (Why This Approach, Alternatives Considered, Key Concepts, What You Should Learn, Questions); teaching by code type (Bug Fixes, Refactoring, New Features, Tests); techniques (Progressive Disclosure, Concrete Before Abstract); quick template

---

### 4.7 coding-standards.xml
**Triggers:** standards, SOLID, GoF, jQuery, complexity, code quality  
**Domain:** Code quality standards  
**Content:** Priority hierarchy (Security > Correctness > Maintainability > Performance > Simplicity); SOLID with checklists; GoF patterns with when-to-use/avoid; hard limits (complexity ≤10, method ≤40 lines, class ≤300, params ≤4, nesting ≤3, inheritance ≤3); **jQuery BANNED** (detection: `$()`, `jQuery`, CDN tags); Standards Compliance Check template with PASS/PASS_WITH_WARNINGS/FAIL verdicts

---

### 4.8 completion-verification.xml
**Triggers:** completion, verify, done, criteria, persistent, finish  
**Domain:** Task completion checking  
**Content:** 4 verification types (Count-Based, Threshold-Based, State-Based, Composite); verification protocol (Before Starting, After Each Iteration, On Resume); verification commands by category; implicit criteria (always check: compiles, tests pass, no new lint errors, no secrets); checkpoint protocol; anti-premature completion rules

---

### 4.9 consult-mode.xml
**Triggers:** CONSULT, AUTO, architect, proposal, approval, consult gate  
**Domain:** Collaborative mode protocol  
**Content:** CONSULT = default (missing file = CONSULT); 8 architectural triggers; not-triggers list; 5-step consultation protocol; additive-not-gatekeeping principle; session-approvals.json format; `state/claudeboost-mode.json` as state store

---

### 4.10 context-engineering.xml
**Triggers:** context, token, attention, memory, compress, isolate, scratchpad  
**Domain:** Context window management  
**Content:** Four pillars (Write/Select/Compress/Isolate); per-agent token budgets (lightweight: 3K init/1K output; standard: 8K/3K; heavy: 15K/5K; orchestrator: 25K/5K); token efficiency techniques; attention priority levels (high/medium/low); anti-patterns (Context Dumping, Kitchen Sink Tools)

---

### 4.11 database.xml
**Triggers:** database, SQL, schema, migration, index, query, N+1  
**Domain:** Database design and operations  
**Content:** Schema design (normalization 1NF-BCNF, naming conventions); indexing types (B-tree/Hash/Composite/Partial/Covering/GIN); N+1 prevention; expand-contract zero-downtime migration pattern; ACID + isolation levels; deadlock prevention; connection pool formula (2×cores+1); parameterized queries mandatory; audit logging template; WAL archiving for PITR

---

### 4.12 debugging.xml
**Triggers:** debug, bug, error, root cause, investigate  
**Domain:** Debugging methodology  
**Content:** 78% accuracy on complex multi-file debugging; 81% failure rate on semantic-preserving changes; 60% location bias in first 25% of code; 5 debugging frameworks; failure indicators; 20-30 minute time box

---

### 4.13 devops.xml
**Triggers:** CI/CD, pipeline, Docker, GitHub Actions, deployment, Terraform  
**Domain:** DevOps and deployment  
**Content:** 7-stage pipeline (fail-fast order); Docker multi-stage builds; GitHub Actions (pin to SHA, OIDC for credentials); deployment strategies (blue-green/canary/rolling/feature flags); Terraform remote state; health checks (liveness=cheap, readiness=check deps); graceful shutdown SIGTERM pattern; DORA metrics

---

### 4.14 documentation.xml
**Triggers:** docs, documentation, comments, README, API docs  
**Domain:** Documentation writing  
**Content:** 80% WHY / 15% WHAT / 5% HOW; never restate code line-by-line; language conventions (Python Google-style, JS TSDoc, Java Javadoc, C++ Doxygen); inline comment rules; active voice; quality checklist

---

### 4.15 error-handling.xml
**Triggers:** error, exception, handling, retry, fault tolerance, catch  
**Domain:** Error design patterns  
**Content:** Fail Fast / Be Specific / Include Context / Don't Swallow principles; error hierarchy (ApplicationError → ValidationError/BusinessError/IntegrationError/SystemError); exceptions vs result types; recovery patterns (Retry with Backoff: `min(base_delay × 2^attempt, max_delay) + jitter`; Circuit Breaker: CLOSED/OPEN/HALF_OPEN; Fallback; Graceful Degradation); RFC 9457 error format; language-specific patterns (Python, JS/TS, Go)

---

### 4.16 error-recovery.xml
**Triggers:** error, failure, stuck, blocked, retry, recovery, self-healing  
**Domain:** Agent error recovery  
**Content:** 5-level error taxonomy (Memory/Reflection/Planning/Action/System); detect-decide-act protocol; recovery protocols per level; escalation matrix (1=retry same, 2=adjust, 3=different approach, 4=ask user, 5+=BLOCKED); model escalation (Haiku→Sonnet→Opus→user); health metrics (recovery rate >80%, first-try success >90%, BLOCKED rate <10%)

---

### 4.17 file-editing-windows.xml
**Triggers:** file edit, write file, unexpectedly modified, edit error, windows  
**Domain:** Windows-specific file editing  
**Content:** Bug: "File has been unexpectedly modified" error (GitHub issues #7443, #7457, #10437, #12462, #12805); root causes (timestamp resolution, CRLF/LF conversion, VSCode background processes); workarounds in priority order: (1) relative paths (2) retry immediately after read (3) Bash/sed fallback (4) new-file+rename; RULE-011 (WARN severity)

---

### 4.18 memory-management.xml
**Triggers:** memory, context, compact, compaction, session, persist  
**Domain:** Context and memory persistence  
**Content:** Auto-compact at ~95% (`CLAUDE_AUTOCOMPACT_PCT_OVERRIDE=60` overrides to 60%); memory hierarchy (Enterprise/Project/User/Local/Task); persistence strategies; PERSISTENT mode checkpoint format; parallel agent hard limits (context <50%: 3 agents; 50-75%: 2 agents; >75%: 1 agent); batch pattern; background agent advantages; token estimation

---

### 4.19 model-selection.xml
**Triggers:** model, opus, sonnet, haiku, escalate, complexity  
**Domain:** Model routing  
**Content:** Always-Opus: architect/ticket-analyst/reviewer; Sonnet for 15 others; decision tree; 5 escalation trigger categories (Agent Type, Complexity, Stakes, Ambiguity, Reasoning Depth, Mid-Task); complexity scoring dimensions; mid-task escalation scenarios; model characteristics

---

### 4.20 multi-agent-failures.xml
**Triggers:** multi-agent, failure, MAST, coordination, cascade  
**Domain:** Multi-agent failure patterns  
**Content:** MAST taxonomy from 1600+ traces: System Design Issues (32%), Inter-Agent Misalignment (28% most common), Task Verification Gaps (24%), Infrastructure Issues (16%); 14 failure modes total; error cascading prevention (Validation at Boundaries, Error Isolation, Result Validation); health metrics

---

### 4.21 observability.xml
**Triggers:** logging, metrics, tracing, observability, monitoring, SLO  
**Domain:** System observability  
**Content:** Three pillars (logs/metrics/traces); structured logging format; log levels (TRACE/DEBUG/INFO/WARN/ERROR/FATAL) with decision tree; anti-patterns (Log-and-Forget, No Context, Logging Secrets, Log Flooding); metric types (Counter/Gauge/Histogram/Summary); RED/USE methods; SLOs/SLIs

---

### 4.22 organization.xml
**Triggers:** organize, workspace, task folder, artifact, context  
**Domain:** Workspace organization  
**Content:** Folder structure (`workspace/[task-id]/{ticket.md,mockups/,outputs/,snapshots/,context.md}`); task ID naming (ticket number > date-based fallback); XML-format context.md template (full schema with all sections); status definitions; context lifecycle rules; size limits (<30 KB file, <10 active contributions, <20 parallel findings); Quick Resume protocol (update after EVERY agent)

---

### 4.23 performance.xml
**Triggers:** performance, latency, bottleneck, caching, optimization, profiling  
**Domain:** Performance engineering  
**Content:** Measure before optimizing; latency targets (p50<100ms, p90<200ms, p99<500ms); bottleneck types; 4 caching levels + 3 patterns + 3 invalidation strategies; load test types (Smoke/Load/Stress/Soak/Spike); database optimization; connection pool formula (cores×2+spindle); thread pool sizing

---

### 4.24 playwright.xml
**Triggers:** Playwright, browser, e2e, interactive, MCP  
**Domain:** Browser automation  
**Content:** Always use MCP tools interactively (never write code unless asked); correct package `@playwright/mcp` (not `@anthropic-ai/mcp-playwright`); auto-allow localhost + OAuth domains; must restart Claude Code after install; URL access policy

---

### 4.25 pr-review.xml
**Triggers:** PR review, code review, pull request, reviewer  
**Domain:** Pull request review methodology  
**Content:** 11-pass trigger-conditional checklist; ASC-1171 incident reference for convention compliance; approval criteria; review depth guide; FULL spawn template applies

---

### 4.26 process-kill-safety.xml
**Triggers:** kill, pkill, killall, taskkill, Stop-Process  
**Domain:** Process management safety  
**Content:** BANNED commands: `pkill NAME`, `pkill -f NAME`, `killall NAME`, `Stop-Process -Name NAME`, `taskkill /IM NAME.exe`; Safe alternatives: `kill PID`, `Stop-Process -Id PID`, `taskkill /PID pid`; If only name pattern available: STOP and ask user; enforced via PreToolUse hook on Bash matching kill patterns

---

### 4.27 prompting-patterns.xml
**Triggers:** prompt, quality, improve, response, chain of thought  
**Domain:** Prompt engineering  
**Content:** 5 core quality rules; reasoning patterns (Chain of Thought, Self-Critique, Adversarial Thinking, Rubber Duck Debugging); output patterns (Structured Output, Confidence Scoring, Verification Steps); task-specific patterns; meta-prompting techniques; Think Tool Pattern (54% improvement on complex tasks)

---

### 4.28 refactoring.xml
**Triggers:** refactor, code smell, technical debt, cleanup  
**Domain:** Code refactoring  
**Content:** Trigger thresholds; safe refactoring process; strangler-fig for legacy; code smells by category (Bloaters/Dispensables/Couplers); tech debt P0-P3 prioritization

---

### 4.29 research.xml
**Triggers:** research, search, investigate, verify, citation, source  
**Domain:** Web research methodology  
**Content:** 4-phase methodology (Planning/Execution/Verification/Synthesis); source credibility tiers (High/Medium/Low); anti-hallucination rules; confidence language by level; report structure; common failure categories

---

### 4.30 rule-enforcement.xml
**Triggers:** rule, enforce, compliance, violation, check, validate  
**Domain:** Rule enforcement mechanism  
**Content:** Rule format (ID/TRIGGER/CONDITION/ACTION/SEVERITY); enforcement mechanisms (Soft Enforcement with trigger points, Periodic Audits every ~10 actions, Constitutional Principles); RULE-001 through RULE-008 implementation details plus RULE-019 (Verify Gate - Evidence Required, BLOCK); pre-action validation template; self-correction 4-step protocol

---

### 4.31 rules.xml
**Triggers:** rule, RULE-, violation, compliance, block, warn  
**Domain:** Complete rule catalog  
**Content:** 20 system rules:
- **BLOCK:** RULE-001 (Agent Spawn for code), RULE-002 (TodoWrite multi-step), RULE-003 (Planning required), RULE-004 (Agent status validation), RULE-005 (Context logging), RULE-010 (Playwright MCP tools), RULE-012 (Self-reflection), RULE-014 (No stopping in PERSISTENT), RULE-015 (Ask before migrations/deployments), RULE-016 (Critique+Teaching required), RULE-017 (Coding standards compliance), RULE-021 (Visual Communication Framework Annotation), RULE-022 (Mandatory Best Practices Review)
- **WARN:** RULE-006 (Research agent), RULE-007 (Security agent), RULE-008 (Token efficient spawning), RULE-009 (Browser URL policy), RULE-011 (Windows file edit), RULE-013 (Model selection), RULE-018 (Parallel agent limits)

---

### 4.32 scope-governance.xml
**Triggers:** scope, boundaries, creep, out of scope, creative intent  
**Domain:** Scope discipline  
**Content:** "Add X does not mean make everything consistent with X" (creative intent rule); collaboration protocol (mechanical=just do; creative=share first; adjacent=suggest before); completion vs expansion distinction; consult-mode integration

---

### 4.33 security.xml
**Triggers:** security, OWASP, auth, injection, XSS, vulnerability  
**Domain:** Application security  
**Content:** CIA triad; OWASP Top 10 2021 (A01=Broken Access Control, A02=Cryptographic Failures, A03=Injection, A04=Insecure Design, A05=Security Misconfiguration, A06=Vulnerable Components, A07=Auth Failures, A08=Data Integrity Failures, A09=Security Logging and Monitoring Failures, A10=SSRF); allowlist input validation strategy; session rules; secrets management (never hardcode/commit/log/URL); CI/CD security gates; security headers; incident response 6-step

---

### 4.34 self-reflection.xml
**Triggers:** confidence, reflection, uncertainty, calibration  
**Domain:** Agent self-assessment  
**Content:** Confidence levels (HIGH: known good patterns, MEDIUM: reasonable assumption, LOW: uncertain — must flag); model selection costs (Opus 4.5 $5/$25, Sonnet 4.5 $3/$15, Haiku 4.5 $1/$5); orchestration pattern; context length guidance

---

### 4.35 story-pointing.xml
**Triggers:** story points, estimation, Fibonacci, sprint, complexity  
**Domain:** Agile estimation  
**Content:** Fibonacci scale (1/2/3/5/8/13, must-split at 13); 9 complexity multipliers (each elevate 1-2 levels); spike creation criteria; decomposition strategies; reference stories

---

### 4.36 teaching.xml
**Triggers:** teach, learn, explain, tutor, Socratic, scaffold, hint  
**Domain:** Pedagogical methodology  
**Content:** Socratic Method with 5 question types; Metacognitive Scaffolding (Planning/Monitoring/Evaluation); Zone of Proximal Development detection and adjustment; Progressive Disclosure (4 levels); 3 teaching protocols; user types (Beginner/Intermediate/Advanced); research foundation (24% critical thinking improvement with Socratic AI)

---

### 4.37 testing.xml
**Triggers:** test, TDD, coverage, mock, pytest, jest, unit test  
**Domain:** Testing methodology  
**Content:** TDD Red-Green-Refactor; required test categories; AAA pattern; mocking guidance; production safety; FIRST principles

---

### 4.38 ticket-understanding.xml
**Triggers:** ticket, requirements, scope, acceptance criteria, user story  
**Domain:** Requirements analysis  
**Content:** 5 understanding levels; exact-wording rule (paraphrasing = interpretation drift); chain-of-thought template; INVEST criteria; Given-When-Then format; scope creep prevention; red flags

---

### 4.39 tool-design.xml
**Triggers:** tool, MCP, tool definition, API, function, parameter  
**Domain:** MCP tool design  
**Content:** 4 core principles (Clear Naming, Self-Documenting Parameters, Actionable Error Messages, Token-Efficient Responses); pagination design; format control; tool scope (when to split vs combine); namespacing; error categories with actions; token budget (tool definition: 100-300 tokens, each parameter: 20-50 tokens); refinement cycle

---

### 4.40 ui-implementation.xml
**Triggers:** UI, frontend, component, React, mockup, design  
**Domain:** UI development  
**Content:** Images first in prompts; XML spec structure; jQuery BANNED; reuse-first protocol; visual feedback loop; responsive mobile-first; accessibility (ARIA, keyboard nav, 4.5:1 contrast ratio)

---

### 4.41 verify-gate.xml
**Triggers:** verify, finding, hallucination, evaluator, evidence, file:line  
**Domain:** Finding verification  
**Content:** "Finding REAL things is the goal" principle; 4 enforcement layers (Spawn Template — verify gate instructions injected by orchestrator template at Step 4b; PostToolUse nudge — LLM reminder to orchestrator; Output Format; Evaluator Escalation); evidence format (file:line + code quote = VERIFIED; "probably" + no line = bad); status values (VERIFIED/NEEDS_VERIFICATION/UNVERIFIED); cost justification

---

### 4.42 visual-communication.xml
**Triggers:** explain, diagram, visual, architecture, show me, structure, flow  
**Domain:** ASCII diagram communication  
**Content:** 8 design frameworks (SOLID, GoF, OOP Four Pillars, TDD, DDD, CIA Triad, GRASP, Clean Code, KISS-DRY-YAGNI); 4 architecture ASCII diagrams (Clean Architecture, Hexagonal, CQRS, Event Sourcing); 7 diagram templates (layered-architecture, request-flow, component-interaction, security-box, comparison-matrix, before-after, di-flow); annotation formats; RULE-021 integration: every explanation must include at least one framework annotation

---

### 4.43 workflow.xml
**Triggers:** workflow, implementation, plan, execute, failure patterns  
**Domain:** Implementation workflow  
**Content:** 5 failure patterns; plan-then-execute 4 phases; circuit breaker (5 attempts max); database safety matrix (READ/WRITE/DESTRUCTIVE/SCHEMA per dev/staging/prod)

---

## 5. Slash Commands

### 5.1 /boost
**File:** `.claude/commands/boost.md`  
**Description:** Activate ClaudeBoost — load RAG + GT and prime the session  
**Tools:** Bash, Read, Glob  
**Steps:**
1. Launch matrix-boost.py animation (new WT tab), clear `__pycache__`
2. Verify privacy env vars (`DISABLE_TELEMETRY`, `DISABLE_ERROR_REPORTING`) — auto-fix if missing
3. Activate RAG: `check-rag-health.py` → auto-repair if exit 2 or 3 → call `rag_context` to prime
4. Activate Gas Town: `gt prime` → auto-init (`gt init`) if not a GT workspace
5. Check enforcement hooks via `check-hooks.py` for PreToolUse and PreCompact
6. Verify `~/.claude/CLAUDE.md` exists
7. Read CONSULT/AUTO mode, clear `session-approvals.json`
8. Scan `workspace/*/context.md` for active tasks
9. Write `$TEMP/claudeboost_active`, write `BOOST:done` to status file
10. Report: Systems Status + Active Workspaces + Session Directives + Collaborative Mode + Ready

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
4. Launch via `wt.exe -w 0 new-tab`
5. Report node/edge counts, keyboard shortcuts
6. Monitor `$TEMP/claudeboost/visualize_chat.json` for chat questions

---

### 5.6 /changes [scope]
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

### 5.7 /spawn-agent <agent-name> <task-id>
**File:** `.claude/commands/spawn-agent.md`  
**Description:** Spawn an agent with RAG knowledge loading  
**Tools:** Read, Glob, Task  
**Steps:**
1. Validate agent file exists at `agents/$1-agent.xml`
2. Run `pwd` for project_path (literal string for Tier 4 RAG)
3. Build spawn prompt with: agent name, task description, rag_context Step 1, project_path, context path, output format
4. Route weight: lightweight/standard/full by agent type
5. PreToolUse agent-spawn-gate.py fires before spawn

---

### 5.8 /review [--staged | --branch | --pr <url>]
**File:** `.claude/commands/review.md`  
**Description:** Structured A-F grade code review  
**Tools:** Bash(git diff, gh pr diff)  
**Steps:**
1. Resolve diff source (uncommitted+staged / staged only / branch diff / PR diff)
2. Review for CRITICAL (security, data loss, correctness), MAJOR (logic errors, missing error handling), MINOR (style, naming)
3. Grade: A=no issues, B=MINOR only, C=MAJOR present, D=CRITICAL present, F=unreviewable
4. Output structured review with file:line for each issue

---

### 5.9 /index-project [path or name] [languages] [force]
**File:** `.claude/commands/index-project.md`  
**Description:** Index a project's codebase for semantic search (Project RAG)  
**Steps:**
1. Health check: `rag_status()` first
2. Resolve project path: empty=cwd, full path=as-is, short name=fuzzy match in `C:/Development/`
3. Parse language filters and `force` flag
4. Scan: `rag_scan(project_path, languages)` — show summary table
5. Confirmation gate if files_to_index > 500
6. Index: `rag_index_project(project_path, ...)`
7. Verify with `rag_search(query="main entry point", scope="codebase", project_path=...)`

---

### 5.10 /plan-task <task-id> <description>
**File:** `.claude/commands/plan-task.md`  
**Description:** Execute planning phase only (no execution)  
**Steps:**
1. Create `workspace/$1/` and init context.md with PLANNING state
2. Run 7-domain planning checklist (Testing/Docs/Security/Architecture/Performance/Review/Clarity)
3. Generate subtasks (Solvability + Completeness + Non-Redundancy principles)
4. Determine execution strategy (Sequential/Parallel/Hybrid)
5. Update context.md with full plan
6. Present plan and ask for approval

---

### 5.11 /gate
**File:** `.claude/commands/gate.md`  
**Description:** Compliance gate check (5 gates)  
**Gates:**
1. Task Classification: read-only → skip; action → continue
2. Workspace Verification: context.md exists → read it; missing → create
3. Planning Verification: Plan section populated → continue; missing → run checklist
4. TodoWrite Verification: 2+ steps → verify TodoWrite exists
5. Pre-Action Validation: agent type, model assignment, READ pattern, context.md update plan
**When to run:** Every new task, before spawning any agent, before code modification, after compaction

---

### 5.12 /agent-status <task-id>
**File:** `.claude/commands/agent-status.md`  
**Description:** Display task status, agent contributions, and next steps  
**Output:** Task, Status, Last Agent, Next Steps, Blockers, Artifacts count  
**References:** `@workspace/$1/context.md`

---

### 5.13 /check-task <task-id>
**File:** `.claude/commands/check-task.md`  
**Description:** Validate task folder structure and completeness  
**Checks:** Structure, context.md required sections, agent output compliance, content validation (not just headers), context health (<30 KB, <10 contributions)  
**Output:** VALID/INVALID with list of issues

---

### 5.14 /check-completion [task-id]
**File:** `.claude/commands/check-completion.md`  
**Description:** Verify completion criteria status  
**Steps:** Find task context → read criteria → run verification commands → update status → report  
**Output:** Criteria table with Expected vs Actual vs Status, COMPLETE/IN PROGRESS/BLOCKED

---

### 5.15 /set-mode <normal|persistent> [task-id]
**File:** `.claude/commands/set-mode.md`  
**Description:** Set execution mode for a task  
**PERSISTENT mode:** Requires completion criteria definition; prompts user if missing  
**Updates:** context.md Execution Mode section

---

### 5.16 /compact-review
**File:** `.claude/commands/compact-review.md`  
**Description:** Preview critical state before context compaction  
**Output:** Active tasks table, task context summaries (last agent, findings, next steps), pending user decisions, Compaction Summary Template

---

### 5.17 /done [--status COMPLETED|ESCALATED|DEFERRED] [--pre-verified]
**File:** `.claude/commands/done.md`  
**Description:** Signal work complete and submit to Gas Town merge queue  
**Steps:** Pre-flight (git status clean, at least 1 commit) → `gt done $ARGUMENTS`  
**Statuses:** COMPLETED (default), ESCALATED (blocker), DEFERRED (pause work)

---

### 5.18 /handoff [message]
**File:** `.claude/commands/handoff.md`  
**Description:** Hand off to a fresh session  
**Steps:** `gt handoff -s "HANDOFF: Session cycling" -m "message"` or `gt handoff` if no message  
**Effect:** New session auto-primes via SessionStart hook and finds handoff mail

---

### 5.19 /list-agents
**File:** `.claude/commands/list-agents.md`  
**Description:** List all available agents with expertise domains  
**Output:** Agent summary table (22 agents), quick decision guide

---

### 5.20 /update-docs
**File:** `.claude/commands/update-docs.md`  
**Description:** Generate project documentation in `docs/` folder  
**Note:** docs/ is gitignored; run after completing features  
**Output:** README.md, architecture.md, api.md (as applicable to the project)

---

## 6. Hook Registration

**Source file:** `~/.claude/settings.json`  
**Project settings:** `.claude/settings.json` (only `includeCoAuthoredBy: false`)  

### 6.1 SessionStart

| Matcher | Type | Script/Prompt | Purpose |
|---------|------|---------------|---------|
| Always | prompt | Quality-first routing reminder | Route correctly: full/standard/lightweight |
| Always | prompt | CONSULT mode protocol | Inject CONSULT vs AUTO decision flow |
| Always | prompt | Codebase RAG reminder | Include project_path in rag_context calls |
| Always | command | `compaction-restore.py` (timeout: 5000ms) | Restore compaction memo if post-compaction |

### 6.2 PreToolUse

| Matcher | Type | Script/Prompt | Purpose |
|---------|------|---------------|---------|
| `Bash(mkdir*workspace*)` | prompt | Workspace creation check | Remind to call rag_search + gt prime |
| `Task` | command | `agent-spawn-gate.py` | Verify rag_context in spawn prompt |
| `Edit\|Write\|MultiEdit` | command | `consult-gate.py` | Check CONSULT mode approval |
| `Bash(pkill*)\|Bash(killall*)\|...` | prompt | Process kill safety | Block broad name-pattern kills |
| `Bash` | command | `bash-guard.py` | Block co-author trailer, cd&&, backslash paths |

### 6.3 PostToolUse

| Matcher | Type | Script/Prompt | Purpose |
|---------|------|---------------|---------|
| `Task` | prompt | VERIFY GATE | Remind orchestrator to spawn evaluator for BLOCKER/HIGH/MEDIUM findings |
| `.*` | command | `context-nudge.py` (timeout: 3000ms) | Nudge context.md update every 20 tool uses (workspace mode); once at 60 uses (no-workspace mode) |
| `mcp__rag-server__rag_index_project` | command | `project-rag-flag.py` (timeout: 3000ms) | Write `$TEMP/claudeboost_project_rag_ok` on successful project index; clear on error |

### 6.4 PreCompact

| Matcher | Type | Script/Prompt | Purpose |
|---------|------|---------------|---------|
| Always | prompt | Context preservation reminder | Quality routing + GT awareness |
| Always | command | `compaction-save.py` (timeout: 5000ms) | Archive workspace state |

### 6.5 UserPromptSubmit

| Matcher | Type | Script | Purpose |
|---------|------|--------|---------|
| (none) | command | `speak-stop.py` (timeout: 3000ms) | Stop TTS when user types |

### 6.6 Stop

| Matcher | Type | Script | Purpose |
|---------|------|--------|---------|
| (none) | command | `speak-tts.py` | Speak Claude's response via edge-tts |

---

## 7. Configuration & State Files

### 7.1 Environment Variables (user settings.json `env` section)

| Variable | Value | Purpose |
|----------|-------|---------|
| `CLAUDEBOOST_HOME` | `C:/Development/ClaudeBoost` | Root path for all ClaudeBoost scripts/state |
| `DISABLE_TELEMETRY` | `1` | Disable Claude Code telemetry |
| `DISABLE_ERROR_REPORTING` | `1` | Disable error reporting |
| `DISABLE_FEEDBACK_COMMAND` | `1` | Hide feedback prompt |
| `CLAUDE_CODE_DISABLE_FEEDBACK_SURVEY` | `1` | Disable survey |
| `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE` | `60` | Auto-compact at 60% context usage (not default 95%) |
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
- Read by `consult-gate.py` to check for existing approvals

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
- **Project RAG** (cyan bold): shown only when `$TEMP/claudeboost_project_rag_ok` exists (written by `project-rag-flag.py` hook when `rag_index_project` completes successfully; cleared on error)
- **GT** (yellow bold): shown only when `gt` binary is on PATH (live `command -v` check — no flag file needed)

### 7.8 Global Settings

| Setting | Value | Effect |
|---------|-------|--------|
| `model` | `sonnet` | Default model for all interactions |
| `alwaysThinkingEnabled` | `true` | Extended thinking always on |
| `effortLevel` | `high` | High reasoning effort |
| `voice.enabled` | `true` | Voice input enabled |
| `voice.mode` | `hold` | Hold-to-speak mode |

---

## 8. MCP RAG Server

**Source directory:** `mcp-rag-server/src/rag_server/`  
**Transport:** stdio (MCP protocol)  
**Installed at:** `mcp-rag-server/` via `pip install -e`

### 8.1 Tools (6 total)

| Tool | Purpose |
|------|---------|
| `rag_search` | Semantic search across knowledge collections |
| `rag_index` | Index ClaudeBoost agents/knowledge files |
| `rag_status` | Check server health and indexed chunk counts |
| `rag_index_project` | Index a project's source code (per-project) |
| `rag_scan` | Scan project files without indexing (preview) |
| `rag_context` | Build full tiered agent context |

### 8.2 Configuration (config.py)

| Setting | Value |
|---------|-------|
| `EMBEDDING_MODEL` | `sentence-transformers/all-MiniLM-L6-v2` |
| `CHROMA_DIR` | `PROJECT_ROOT/mcp-rag-server/.rag-index/chroma` |
| `SCOPES` | `knowledge` (knowledge/*.md + *.xml → "knowledge" collection), `agents` (agents/*.md + *.xml → "agents" collection) |

### 8.3 Tiered Context (server.py `_build_context()`)

| Tier | Name | Source | Token Budget | Conditions |
|------|------|--------|--------------|-----------|
| 0 | Agent definition | agents/<name>.xml from ChromaDB "agents" collection | Priority | Always |
| 1 | Universal guardrails | security.xml, observability.xml, coding-standards.xml, scope-governance.xml | Up to 40% | Skip if `weight=lightweight` |
| 2 | Declared KBs | `<knowledge-base>` elements from agent XML | Up to 50% of remaining | Always |
| 3 | Semantic search | rag_search(task_description, scope="all", min_score=0.4) | Remaining | Always |
| 4 | Project codebase | Per-project ChromaDB at `<project>/workspace/.rag-index/` | min(400, remaining) | Only if `project_path` provided and indexed |

### 8.4 Two Distinct RAG Indexes

| Term | Location | Tools | Scope |
|------|----------|-------|-------|
| **ClaudeBoost RAG** | `mcp-rag-server/.rag-index/chroma` | `rag_search scope=agents/knowledge/all`, `rag_index`, `rag_context` | agents/ + knowledge/ files |
| **Project RAG** | `<project>/workspace/.rag-index/` | `rag_index_project`, `rag_search scope=codebase` | Project source code |

`rag_context` combines both: Tiers 0-3 pull from ClaudeBoost RAG, Tier 4 pulls from Project RAG.

### 8.5 Weight Parameter

| Weight | Tier 1 (Guardrails) | Token Budget |
|--------|---------------------|--------------|
| `lightweight` | Skipped | Minimal |
| `standard` | Included | Normal |
| `full` | Fully included | Maximum |

**Agent routing:**
- `full`: reviewer-agent, security-agent, performance-agent
- `standard`: workflow, refactor, debug, test, ui, architect, ticket-analyst, browser, evaluator
- `lightweight`: explore, research, docs, estimator

---

*End of ClaudeBoost Reference Manual*
