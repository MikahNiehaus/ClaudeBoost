# ClaudeBoost Collaborative Mode (CONSULT / AUTO)

## Context

Claude Code currently makes architectural decisions unilaterally — picks validation approach, middleware, auth model, DB schema — and only surfaces them when the code is already written. Rework from wrong architecture costs far more than one 30-second conversation.

The user wants a structurally enforced **CONSULT** mode that makes Claude announce its architectural proposal **before** writing code, so the user can extend, constrain, or redirect it. This is not "ask permission to act" — RAG standards (security, logging, validation) are still always applied. It's "tell me the shape of what you're doing so I can add constraints I care about."

Concrete example the user gave: Claude says "I'll use the ORM to prevent SQL injection." The user adds "good, also cap upload size at 1MB and reject non-ASCII input." Claude then implements both. That back-and-forth is the whole point — and it must happen **before** the first Edit, not after.

Intended outcome: default behavior is collaborative. `/auto` exists as a one-command bypass for prototyping and trivial work. A stronger reasoning model (Opus via `architect-agent`) generates the proposals so they're worth the user's time.

## Design decisions (locked)

- **Mode names:** `CONSULT` (default) / `AUTO` (bypass). Matches existing `NORMAL`/`PERSISTENT` register in `set-mode.md`.
- **Approval memory:** session-scoped. Approved decisions logged to a scratchpad; Claude only re-consults when a **new** architectural axis appears.
- **Consultation is additive, not gatekeeping.** Claude presents its proposal with RAG-sourced defaults already applied; the user adds constraints on top. Required security/logging/validation standards are NOT up for discussion — they happen regardless.
- **Research-first is structural.** `architect-agent` refuses to generate a proposal unless the spawn prompt contains cited `file:line` references from the target project.
- **Meta-dirs exemption:** `workspace/`, `.claude/`, `knowledge/`, `plans/`, `docs/` bypass CONSULT (ClaudeBoost self-iteration).

## What counts as an "architectural decision"

**Triggers consultation** (any one of):
1. New HTTP endpoint / RPC handler / CLI command / exported library function
2. New DB table, migration, collection, cache namespace, queue/topic, or schema change
3. New top-level module/package directory or new stateful class
4. New dependency (package.json, requirements.txt, Cargo.toml, go.mod, pyproject.toml)
5. Cross-cutting concern: auth/authz, validation strategy, error handling, logging shape, rate limiting, caching, retry/backoff, serialization
6. New middleware / interceptor / pipeline stage
7. New config surface: new env var, new config key, new feature flag
8. New concurrency primitive: workers, threads, queues, event loops

**Does NOT trigger** (proceeds silently):
- Typo / copy / comment / doc changes
- Single-file bugfix with no signature change
- Test-only additions/refactors
- Formatting, lint, import reorder
- Value-only config tweaks (existing keys)
- Renames within one file
- Edits under meta-dirs (`workspace/`, `.claude/`, `knowledge/`, `plans/`, `docs/`)

## Architecture — three layered hooks + architect-agent contract

Reuses the existing verify-gate pattern (layered enforcement in `scripts/setup.ps1` lines 92–140).

### Hook 1 — `SessionStart` (appended entry)
Loads the full CONSULT protocol into every session's context so Claude knows the rules before the first tool call.

### Hook 2 — `PreToolUse` matcher `Edit|Write|MultiEdit` (new matcher, appended to existing PreToolUse array)
Fires at the exact moment of violation. Terse classification check: "Is this architectural? NO → proceed. YES → STOP, check mode file, run protocol." Meta-dirs exempted inline.

### Hook 3 — `PreToolUse` matcher `Task` (modify existing entry)
Append one paragraph about `architect-agent` PROPOSAL_ONLY contract so the main agent spawns it correctly.

### Hook 4 — `PreCompact` (append one line)
Re-injects the CONSULT/AUTO rule after context compaction so it doesn't drift out.

### Research-first enforcement (architect-agent.xml contract)
New `<consultation-mode>` block in `agents/architect-agent.xml`:
- **Trigger:** spawn prompt contains literal `PROPOSAL_ONLY`
- **Requirement:** spawn prompt must include ≥2 `file:ext:line-range — what it shows` citations
- **Refusal:** if citations missing, return `status=BLOCKED` with message "Main agent did not research first. Call `rag_search`, read 2–3 relevant files, respawn with citations."
- **Output shape:** 2–3 options, each referencing a cited file, plus a "required by standards" section listing the non-negotiable RAG-sourced constraints Claude will apply regardless

This makes research a contract, not a suggestion — if the main agent skips `rag_search`, `architect-agent` bounces the spawn.

## Consultation flow

```
user asks for feature
    │
    ▼
main agent classifies: architectural? ──NO──► proceed normally
    │ YES
    ▼
read $CLAUDEBOOST_HOME/state/claudeboost-mode.json
    │
    ├── mode=AUTO ──► proceed autonomously (but still cite sources)
    │
    └── mode=CONSULT
            │
            ▼
   check session scratchpad for already-approved decisions on this axis
            │
            ├── already approved ──► proceed with approved choice
            │
            └── new axis
                    │
                    ▼
        STEP 1 — rag_search(feature keywords)
                    rag_context(architect-agent + task)
                    Read 2–3 relevant project files
                    Draft spawn prompt with file:line citations
                    │
                    ▼
        STEP 2 — Task(architect-agent, "PROPOSAL_ONLY … citations: …")
                    Opus generates 2–3 grounded options + "required by standards" section
                    │
                    ▼
        STEP 3 — AskUserQuestion(
                    question: "Architectural decision: <what>",
                    options: [A, B, C with 1-sentence tradeoffs]
                 )
                    User picks, edits, or writes in "actually, do D — also enforce X, Y"
                    │
                    ▼
        STEP 4 — Log approved decision to session scratchpad
                    Implement approved option + added constraints
                    RAG-required standards applied automatically throughout
```

The **"required by standards"** section is what makes consultation additive rather than gatekeeping: validation, security, logging requirements from RAG are presented as already-handled, and the user's role is to *add* constraints on top ("also cap size", "also ASCII-only"), not to debate whether to validate at all.

## Mode state — file location and format

**Path:** `$CLAUDEBOOST_HOME/state/claudeboost-mode.json`

```json
{
  "mode": "CONSULT",
  "setAt": "2026-04-10T14:32:00Z",
  "setBy": "default",
  "reason": "ClaudeBoost default"
}
```

Why this location:
- NOT `workspace/[task-id]/context.md` — need global, not per-task
- NOT `~/.claude/settings.json` — would require restart to flip
- NOT env var — frozen at process start
- Plain JSON file = hot-reloadable; slash commands rewrite it, next hook fire sees new state
- Missing file ⇒ safe default (`CONSULT`)

**Session scratchpad** for approved decisions: `$CLAUDEBOOST_HOME/state/session-approvals.json` — written by main agent after each approval, read at Step "check already-approved" above. Cleared on SessionStart.

```json
{
  "sessionId": "<claude-code session id>",
  "approvals": [
    {"axis": "input-validation", "choice": "Zod + size cap 1MB + ASCII-only", "at": "..."},
    {"axis": "error-handling", "choice": "Result<T,E> discriminated union", "at": "..."}
  ]
}
```

## Files to create / modify

**Create:**
- `.claude/commands/consult.md` — switches to CONSULT mode, reassures user of defaults
- `.claude/commands/auto.md` — switches to AUTO mode, prints the "rework costs more" warning
- `knowledge/consult-mode.xml` — long-form protocol, RAG-indexable so agents can rediscover it
- `state/claudeboost-mode.json` — seeded by `setup.ps1` on first install
- `state/session-approvals.json` — seeded empty, rewritten per session

**Modify:**
- `scripts/setup.ps1`
  - New block before hooks section: create `state/` dir, seed both state files
  - **IMPORTANT:** existing PreToolUse/SessionStart idempotency check is `if (-not $settings.hooks.PSObject.Properties["PreToolUse"])` which SKIPS entirely on upgrade. Must change to: if the property exists, scan the array for a sentinel string (e.g., `"CONSULT GATE"`) and append new matchers only if absent. Same fix for SessionStart.
  - Append new `Edit|Write|MultiEdit` matcher to PreToolUse array
  - Append CONSULT rule entry to SessionStart array
  - Append architect-agent PROPOSAL_ONLY paragraph to existing `Task` PreToolUse entry
  - Append one-line CONSULT reminder to PreCompact entry
- `agents/architect-agent.xml` — add `<consultation-mode>` block (refusal contract)
- `knowledge/scope-governance.xml` — cross-reference `consult-mode.xml` so the existing soft guidance becomes hook-backed
- `.claude/commands/boost.md` — after "all systems online," print the current mode from state file so every boost session shows it
- `CLAUDE.md` (project + ClaudeBoost root) — document CONSULT/AUTO in a new section alongside existing mode guidance

## Draft hook prompt strings (the actual text to inject)

**SessionStart append (full protocol):**
```
CLAUDEBOOST MODE — CONSULT vs AUTO:

Read $CLAUDEBOOST_HOME/state/claudeboost-mode.json at the start of each task.
Field: "mode". Default CONSULT.

If mode=CONSULT, for any architectural decision you MUST:
  1. rag_search(feature keywords) + read 2-3 project files. Cite file:line.
  2. Spawn architect-agent (Opus) with "PROPOSAL_ONLY — citations: ..."
  3. Present 2-3 options via AskUserQuestion. User picks/edits/adds.
  4. Log approval to $CLAUDEBOOST_HOME/state/session-approvals.json
  5. Implement. RAG-required standards apply automatically.

Architectural = new endpoint, new class/module, new DB table, new dep,
new middleware, auth/validation/error/logging strategy, new public API,
new config surface, new concurrency model.

NOT architectural = typo, 1-line fix, test, doc, value-only config tweak,
rename in one file, edits under workspace/ .claude/ knowledge/ plans/ docs/.

Consultation is ADDITIVE not gatekeeping. Present what RAG requires as
already-handled; invite the user to ADD constraints (size caps,
character allowlists, rate limits). Do not debate whether to validate.

Check session-approvals.json before spawning architect-agent — if this
axis was already decided, proceed with the approved choice.

If mode=AUTO: proceed autonomously, still cite sources.
```

**PreToolUse `Edit|Write|MultiEdit` (new matcher):**
```
CONSULT GATE — quick check before this Edit/Write:

Is this architectural? (new file others import, new dep, new endpoint,
new table, new middleware, new validation/auth/error strategy, new
config surface)

- NO → proceed.
- YES → STOP. Read $CLAUDEBOOST_HOME/state/claudeboost-mode.json.
  If mode=CONSULT and you have not: (a) rag_search'd, (b) spawned
  architect-agent with PROPOSAL_ONLY + citations, (c) logged user
  approval to session-approvals.json — do those now in order. No code yet.
  If mode=AUTO, proceed and cite the pattern you're following.

Exempt: edits under workspace/, .claude/, knowledge/, plans/, docs/.
```

**PreToolUse `Task` append (to existing entry):**
```
If spawning architect-agent in CONSULT mode for a proposal:
- Prompt MUST include "PROPOSAL_ONLY" and ≥2 file:line citations
- Opus model required — do not substitute
- architect-agent returns 2-3 options + "required by standards" section
- Main agent (not architect) presents via AskUserQuestion
- Main agent logs approval to state/session-approvals.json before implementing
```

**PreCompact append (one line):**
```
Also: CONSULT/AUTO mode file at $CLAUDEBOOST_HOME/state/claudeboost-mode.json — re-check after compact.
```

## Risks and tradeoffs

- **Hook noise on every Edit/Write.** Mitigation: "NO → proceed" exit at the top of the prompt, meta-dirs exempted, prompt kept <200 tokens.
- **Classification is prompt-enforced, not code-enforced.** False negatives are possible (Claude proceeds when it shouldn't). The enumerated trigger list in the hook is the best available lever short of parsing diffs, which isn't feasible from a hook.
- **Architect-agent cost.** Opus spawn per architectural decision. Real cost, but dwarfed by rework from wrong architecture. AUTO mode exists for exploration where cost > benefit.
- **Existing users on upgrade.** `setup.ps1` idempotency check currently SKIPS when hook properties exist — new matchers won't install on upgrade without the fix described above (sentinel-string append pattern). This is the single biggest implementation gotcha.
- **Session scratchpad staleness.** If Claude forgets to clear it on SessionStart, approvals leak across sessions. Mitigation: SessionStart hook explicitly overwrites `session-approvals.json` with empty state.
- **Meta-dir exemption gap.** Editing `.claude/agents/*.xml` IS architectural for ClaudeBoost itself, but we exempt it so developers iterating on the harness aren't gated. Accepted as a known gap.
- **AskUserQuestion unavailability.** Some environments may not have it. Fallback: plain-text "STOP — pick A, B, or C" message baked into hook prompt.

## Verification plan

1. **Fresh install test:** clone ClaudeBoost, run `setup.ps1`, confirm `state/claudeboost-mode.json` exists with `"mode": "CONSULT"`, both slash command files exist, `~/.claude/settings.json` has the four new/modified hook entries. Run `setup.ps1` a second time; confirm no duplicate entries (sentinel check works).

2. **CONSULT positive test:** new session, ask "add a `/health` endpoint." Expect: `rag_search` called → project files read → `architect-agent` spawned with `PROPOSAL_ONLY` + citations → Opus returns 2–3 options with "required by standards" section → `AskUserQuestion` presents them → NO `Write` until user picks → approval logged to `session-approvals.json` → implementation proceeds.

3. **CONSULT negative test:** "fix the typo in README.md line 42." Expect: immediate edit, no research, no architect spawn, one-line confirmation that this is not architectural.

4. **AUTO bypass test:** `/auto "prototyping"`, then ask for a new endpoint. Expect: state file shows `"mode": "AUTO"`, Claude proceeds without architect spawn, still cites patterns in notes.

5. **Return to CONSULT:** `/consult`, ask for another endpoint. Full protocol runs again.

6. **Approval memory test:** in CONSULT mode, ask for endpoint A, approve "Zod for validation." Then ask for endpoint B. Expect: Claude checks `session-approvals.json`, sees validation already decided, does NOT re-spawn architect-agent for validation — but DOES consult on any new axis (e.g., auth model if B differs).

7. **Research refusal test:** manually craft a Task spawn to `architect-agent` with `PROPOSAL_ONLY` but no citations. Expect: `architect-agent` returns `status=BLOCKED` with refusal message.

8. **Compact survival test:** force `/compact`, confirm CONSULT rule reappears via `PreCompact` hook line.

9. **Missing state file test:** delete `claudeboost-mode.json`, trigger a hook, confirm safe default is CONSULT.

10. **Meta-dir exemption test:** edit a file under `.claude/agents/` — no consult fires. Edit a file under `src/` that adds a new exported function — consult fires.

11. **Additive-not-gatekeeping test:** ask for an endpoint that takes user input. Expect architect-agent's "required by standards" section to list parameterized queries, input validation, `logger.error` in catch blocks — presented as already-applied, not as options. User is only asked about add-on constraints (size caps, charset, rate limit).

## Critical files (for execution phase)

- `C:\Users\grayw\OneDrive\prj\ClaudeBoost\scripts\setup.ps1` — hook installer (the idempotency-pattern fix is here)
- `C:\Users\grayw\OneDrive\prj\ClaudeBoost\agents\architect-agent.xml` — PROPOSAL_ONLY refusal contract
- `C:\Users\grayw\OneDrive\prj\ClaudeBoost\.claude\commands\consult.md` (new)
- `C:\Users\grayw\OneDrive\prj\ClaudeBoost\.claude\commands\auto.md` (new)
- `C:\Users\grayw\OneDrive\prj\ClaudeBoost\knowledge\consult-mode.xml` (new, RAG-indexable)
- `C:\Users\grayw\OneDrive\prj\ClaudeBoost\state\claudeboost-mode.json` (seeded)
- `C:\Users\grayw\OneDrive\prj\ClaudeBoost\state\session-approvals.json` (seeded empty)
- `C:\Users\grayw\OneDrive\prj\ClaudeBoost\.claude\commands\boost.md` — add mode status line
- `C:\Users\grayw\OneDrive\prj\ClaudeBoost\CLAUDE.md` — document CONSULT/AUTO

## Reused existing patterns (do not reinvent)

- **Verify-gate layered hook pattern** (`scripts/setup.ps1:92–140`) — model for SessionStart + PreToolUse enforcement
- **Prompt-injection hook type** (`type: "prompt"` in setup.ps1) — the exact mechanism used for all hooks
- **Slash command frontmatter** (`.claude/commands/plan-task.md`, `set-mode.md`) — template for `consult.md` and `auto.md`
- **Mode table format** (`set-mode.md` lines 40–45) — extend with CONSULT/AUTO rows
- **rag_context Step-1 requirement** (already enforced by existing Task PreToolUse hook) — inherited for free
