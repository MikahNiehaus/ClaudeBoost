---
argument-hint: [target] [focus — code | security | tests | quality | docs | enforcement | xml | counts | rag | rules | memory | all] — OR — hooks [enable|disable|status] [workspace-path]
description: Self-improvement audit — ClaudeBoost internals (default), any workspace, or any project path. Also manages per-workspace protocol hooks.
allowed-tools: Read, Write, Edit, Bash, Glob, Grep, Agent, AskUserQuestion
---

# /self-improve — Dynamic Self-Improvement Audit

Arguments: **$ARGUMENTS**
Format: `[target] [focus]`  — OR — `hooks [enable|disable|status] [workspace-path]`

- **target** (optional):
  - Omitted or `self` → **SELF mode**: ClaudeBoost internals audit (original behavior)
  - A workspace ID (e.g. `add-dark-mode-2026-05-14`) → **WORKSPACE mode**: audit that workspace's implementation
  - An absolute path (e.g. `/home/user/myapp` or `C:/Development/MyApp`) → **PROJECT mode**: audit any project codebase
  - `hooks` → **HOOKS mode**: manage per-directory protocol enforcement hooks (see section below)
- **focus** (optional, default: `all`):
  - SELF mode: `docs | enforcement | xml | counts | rag | rules | memory | all`
  - WORKSPACE mode: `code | security | tests | quality | docs | all`
  - PROJECT mode: `code | security | tests | quality | docs | all`

---

## Phase 0: Parse + Setup

**Workspace detection (run before any other action):**

Run `get-active-workspace.py` to get the active workspace for this Claude
instance — matches the blue "WS XXXX" status bar (per-instance, not the
stale shared global file):
```bash
"${CLAUDEBOOST_PYTHON}" "${CLAUDEBOOST_HOME}/scripts/get-active-workspace.py"
```

Store `project_path` as `PROJECT_PATH` and `workspace_path` as `WORKSPACE_PATH`.
If `PROJECT_PATH` is empty: fall back to current working directory (`pwd`).

**Collision check:** if your context or memory references a different workspace
than what the script returned, print:
`[self-improve] Conflict: status bar shows <X>, context/memory says <Y>. Which workspace should I use?`
Wait for the user's answer — the user is always the source of truth.

If `WORKSPACE_PATH` is empty: note it and continue.

Include `workspace_path="<WORKSPACE_PATH>"` in ALL agent spawn prompts and `/context` calls.



**0a — Detect MODE and parse arguments.**

Split `$ARGUMENTS` on whitespace. Examine the first token:

- **`hooks`** → `MODE = HOOKS` — jump immediately to the **Hooks Mode** section at the bottom. Do NOT run any audit phases.
- Empty or `self` → `MODE = SELF`
- Contains `/` or `\` or starts with a drive letter (e.g. `C:`) → `MODE = PROJECT`, `PROJECT_PATH = first token`
- Otherwise, check: does `$CLAUDEBOOST_HOME/workspace/<first-token>/` exist?
  ```bash
  ls "${CLAUDEBOOST_HOME}/workspace/<first-token>/" 2>/dev/null
  ```
  - If yes → `MODE = WORKSPACE`, `WORKSPACE_ID = first token`, `WORKSPACE_ABS = $CLAUDEBOOST_HOME/workspace/$WORKSPACE_ID`
  - If no → assume it's a partial path or typo; ask:
    ```
    AskUserQuestion: "I couldn't find workspace '<first-token>'. Did you mean a workspace ID (I can list available ones), a project path (provide the full absolute path), or ClaudeBoost self-audit (say 'self')?"
    ```

Second token (or first token if no target was given) → `FOCUS`. Valid values per mode listed above. Default: `all`.

Announce: `Starting self-improve — MODE: [SELF|WORKSPACE|PROJECT], Target: [target or "ClaudeBoost"], Focus: [FOCUS]`

**0b — Call POST http://127.0.0.1:8612/context.**

```
POST http://127.0.0.1:8612/context with 
  agent="reviewer-agent",
  task_description="self-improvement audit in [MODE] mode on [target], focus: [FOCUS]",
  max_tokens=5000
)
```

**0c — Read round state (find N).**

- **SELF**: read `$CLAUDEBOOST_HOME/workspace/self-improvement/context.md` — find last `### R[N]` entry. If file missing, N = 0.
- **WORKSPACE**: read `$WORKSPACE_ABS/context.md` — look for `## Self-Improve Log` section, count entries. If section missing, N = 0.
- **PROJECT**: read `$PROJECT_PATH/workspace/.self-improve-log.md` if it exists. If missing, N = 0.

Announce: `Round R[N+1]`

---

## Phase 1: Index

**SELF mode:**
1. `POST http://127.0.0.1:8612/index with force=true, scope=all)` — rebuilds ClaudeBoost RAG (agents + knowledge
2. `POST http://127.0.0.1:8613/index-project {"project_path":"$CLAUDEBOOST_HOME","force":true}` — rebuilds project RAG (codebase

Report: "Indexed X files (ClaudeBoost RAG), Y files (project RAG)"

**WORKSPACE mode:**
1. Read `$WORKSPACE_ABS/goal.md` and `$WORKSPACE_ABS/plan.md`.
2. Extract `**Project**:` line from plan.md — this is the project path the workspace is working on.
3. If a valid project path is found:
   - `POST http://127.0.0.1:8613/index-project {"project_path":"$PROJECT_PATH","force":true}`
   - Report: "Indexed Y files (project: $PROJECT_PATH)"
4. If no project path found or path is "N/A":
   - Skip project indexing. Note: "No project path in workspace plan — code audit will use grep/glob only."

**PROJECT mode:**
1. `POST http://127.0.0.1:8613/index-project {"project_path":"$PROJECT_PATH","force":true}`
2. Report: "Indexed Y files (project: $PROJECT_PATH)"

---

## Phase 1.5: Research

Spawn a `research-agent` to surface external knowledge that could reveal gaps the audit would otherwise miss. This step runs BEFORE the audit so findings can inform what to look for.

**SELF mode:**

Spawn `research-agent` with this task:
```
Search for recent improvements in: RAG retrieval quality, knowledge graph techniques,
LLM agent orchestration patterns, vector search accuracy, and self-improving AI systems.
Focus on practical techniques applicable to a local Python RAG server.
Return: top 3-5 concrete improvement ideas with enough detail to act on.
End your response with ## Summary (≤300 words): key findings and which ones are actionable.
```

After the agent completes, extract its top findings and note any that match the current `FOCUS`.
Write a **Research Findings** block to `workspace/self-improvement/context.md`:
```
### R[N+1] Research Findings — [date]
[1-3 sentences per finding, labelled as ACTIONABLE or INFORMATIONAL]
```

**WORKSPACE mode:**

Spawn `research-agent` with the workspace goal extracted from `goal.md`:
```
Research best practices and common pitfalls for: [goal keywords].
Focus on security, correctness, and code quality patterns.
Return: top 3-5 concrete risks or improvement patterns the implementation might have missed.
End your response with ## Summary (≤300 words).
```

Use findings to seed the Phase 2 `code` and `security` lenses.

**PROJECT mode:**

Spawn `research-agent` with the project type (inferred from package.json / pyproject.toml / etc.):
```
Research common bugs and quality issues in [project type] projects.
Return: top 3-5 patterns to look for in a code audit.
End your response with ## Summary (≤300 words).
```

Use findings as extra audit checklist items in Phase 2.

---

## Phase 2: Audit

Every finding **MUST** cite `file:line` — no citation = drop the finding.
Use POST http://127.0.0.1:8612/search to locate files before reading them. Never guess file paths.

### SELF mode lenses

| FOCUS | Lenses to run |
|-------|--------------|
| `docs` | Count accuracy: stated agent/knowledge/command counts in CLAUDE.md, README.md, docs/SETUP-GUIDE.md, docs/CLAUDEBOOST-REFERENCE.md vs actual file counts |
| `enforcement` | Phase gates (prose-only vs file-read gates); hook exit codes vs documented claims; REQUIRED/MUST language vs actual behavior |
| `xml` | Well-formedness of all agents/*.xml and knowledge/*.xml; cross-reference resolution (`<knowledge-base file>` attrs) |
| `counts` | Count agents/*.xml, knowledge/*.xml, .claude/commands/*.md; compare to all docs stating a number |
| `rag` | Vector search: knowledge scope (ST-07) + agents scope (ST-08). Graph search: codebase mode=graph (ST-13) — confirms graph index exists and augments results. Chunk health: `GET /status` total > 700 (ST-10). Context pipeline: `POST http://127.0.0.1:8612/context` with project_path — check tier_summary.codebase > 0 and no tier_errors (ST-14). |
| `rules` | CLAUDE.md rule staleness: for each Hard Rule, verify at least one file:line still reflects it |
| `memory` | Memory staleness: read `~/.claude/projects/C--Development-ClaudeBoost/memory/MEMORY.md`; flag entries older than 60 days |
| `all` | All of the above |

### WORKSPACE mode lenses

First, determine the **workspace scope** (what files the workspace touched):
1. Read `$WORKSPACE_ABS/plan.md` — extract all `**Output artifact**:` lines to build a file list.
2. Run both searches to find related files (both calls are mandatory):
   - `POST http://127.0.0.1:8613/search` with `{"query":"[goal keywords from goal.md]","sources":["project:$PROJECT_PATH"],"mode":"vector","limit":10}`
   - `POST http://127.0.0.1:8613/search` with `{"query":"[goal keywords from goal.md]","sources":["project:$PROJECT_PATH"],"mode":"graph","limit":10}`
3. Only audit files in scope. Do not audit the entire project.

| FOCUS | Lenses to run |
|-------|--------------|
| `code` | Does the implementation follow the plan steps? Are planned output artifacts present? Any obvious code quality issues (hardcoded values, missing error handling at system boundaries, duplicate logic)? Cite file:line for every flag. |
| `security` | OWASP top 10 scan on files in workspace scope. Focus on new endpoints, data flows, and user input handling. Use knowledge/security.xml via POST http://127.0.0.1:8612/search. |
| `tests` | Are tests present for new/changed code? For each output artifact that is a source file, check whether a corresponding test file exists. List gaps. |
| `quality` | Consistency with project conventions: naming, error handling, logging (logger.error in catch blocks), no secrets in source. |
| `docs` | Are new functions/APIs documented? Is `$WORKSPACE_ABS/context.md` Status field current? Is plan.md still accurate? |
| `all` | All of the above |

### PROJECT mode lenses

Use `POST http://127.0.0.1:8613/search` with `{"query":"...","sources":["project:$PROJECT_PATH"],"mode":"vector"|"graph","limit":10}` to locate files. Run both `mode=vector` and `mode=graph` on each query — never guess, never run only one mode.

| FOCUS | Lenses to run |
|-------|--------------|
| `code` | Code quality sweep: complexity hotspots, duplicate logic, obvious smells. Use `POST http://127.0.0.1:8613/search` with `{"sources":["project:$PROJECT_PATH"],"mode":"vector"}` and same with `"mode":"graph"` to find largest/most-referenced files and spot-check them. Cite file:line. |
| `security` | OWASP top 10 scan across project entry points and data flows. Grep for raw SQL string concatenation, eval() on user input, secrets in source. |
| `tests` | Find source files with no corresponding test file. Report ratio of tested vs untested modules. |
| `quality` | Consistency: error handling patterns, logging (logger.error in catch), naming conventions. Sample 5-10 files via `POST http://127.0.0.1:8613/search` with `{"sources":["project:$PROJECT_PATH"],"mode":"vector"}` and `"mode":"graph"`. |
| `docs` | README present and complete? Public API surface documented? Undocumented exports? |
| `all` | All of the above |

---

## Phase 3: Self-Tests

### SELF mode tests (run all)

| ID | Check | Pass condition |
|----|-------|----------------|
| ST-01 | `ls agents/*.xml \| wc -l` | Count matches stated count in CLAUDE.md |
| ST-02 | `ls knowledge/*.xml \| wc -l` | Count matches stated count in CLAUDE.md |
| ST-03 | `ls .claude/commands/*.md \| wc -l` | Count matches CLAUDEBOOST-REFERENCE.md section 5 |
| ST-04 | `xmllint --noout agents/*.xml 2>&1` | Zero parse errors |
| ST-05 | `xmllint --noout knowledge/*.xml 2>&1` | Zero parse errors |
| ST-06 | Each `<knowledge-base file="...">` attr in agents/*.xml | All referenced files exist |
| ST-07 | `POST http://127.0.0.1:8612/search with "OWASP SQL injection", scope="knowledge"` | security.xml in top 3 |
| ST-08 | `POST http://127.0.0.1:8612/search with "playwright browser testing", scope="agents"` | playwright.xml or e2e-testing.xml in top 3 |
| ST-09 | Each .claude/commands/*.md has `description:` in frontmatter | No commands missing description |
| ST-10 | `GET /status` | ClaudeBoost chunks (knowledge + agents combined) > 700. Note: `GET /status` only covers knowledge/agents scopes — project codebase chunk count is not reported here; verify via POST /index output instead |
| ST-11 | Memory file staleness (INFO only) | No linked memory file older than 60 days without a confirmed reason |
| ST-12 | Hard Rules in CLAUDE.md have codebase citations (INFO only) | Each rule has at least one file:line OR is documented as aspirational |
| ST-13 | `POST http://127.0.0.1:8613/search` with `{"query":"rag search implementation","sources":["project:$CLAUDEBOOST_HOME"],"mode":"graph","limit":5}` | graph_augmented=true and results > 0. Only run for `rag` focus — confirms graph.db is present and neighbour expansion works. |
| ST-14 | `POST http://127.0.0.1:8612/context with agent="explore-agent", task_description="RAG pipeline health", max_tokens=3000, project_path=$CLAUDEBOOST_HOME` | tier_summary.codebase > 0, no tier_errors key in result. Only run for `rag` focus. |
| ST-15 | Graph resolution quality: `POST http://127.0.0.1:8613/index-project {"project_path":"$CLAUDEBOOST_HOME"}` — read `graph.unresolved`. Compute rate: `unresolved / edges`. | unresolved / edges < 0.15 (less than 15% of edges truly unresolved. External deps don't count as unresolved. |
| ST-16 | Neighbor relevance spot-check: `POST http://127.0.0.1:8613/search` with `{"query":"build_context tier4 codebase","sources":["project:$CLAUDEBOOST_HOME"],"mode":"graph","limit":5}` — inspect the structural neighbours returned. | graph_augmented=true AND at least one neighbour file is in the same subsystem as the seed (e.g., both in `tools/` or both in `adapters/`. Confirms graph edges connect semantically related files, not random ones. |
| ST-17 | CodeSearchNet MRR benchmark: `python "$RAG_BENCHMARKS_PATH/codesearchnet_benchmark.py" --sample 100 --lang python --no-index` where `$RAG_BENCHMARKS_PATH` is your local clone of the rag-benchmarks repo. Only for `rag` focus — takes ~2 min. Requires `pip install datasets` (one-time) and a pre-built corpus index (run once without `--no-index` to build). Dataset: `code-search-net/code_search_net`. Use `--no-index` on repeated runs — RAG server holds the chroma files open so force-wipe always fails; the corpus is already indexed. **Caveat**: benchmark uses `whole_func_string` (code+docstring) which is easier than the published CodeBERT task (code-only). Use for trend tracking only — not a direct comparison to Microsoft baselines. | MRR@10 > 0.50. Below 0.50 = retrieval is worse than a tuned keyword search (BM25 baseline). Save result with `--save results/latest.json` for trend tracking across rounds. |

### WORKSPACE mode tests (run all)

| ID | Check | Pass condition |
|----|-------|----------------|
| WT-01 | `$WORKSPACE_ABS/goal.md` exists | File present |
| WT-02 | `$WORKSPACE_ABS/plan.md` exists | File present |
| WT-03 | `$WORKSPACE_ABS/context.md` exists | File present |
| WT-04 | context.md Status field | Not stuck on PLAN_READY if work has started (should be IN_PROGRESS or COMPLETE) |
| WT-05 | Plan output artifacts exist | Each step's `**Output artifact**:` file exists on disk OR step is explicitly marked incomplete |
| WT-06 | Project RAG indexed (if project path exists) | POST /index output from Phase 1 shows `files_indexed + files_unchanged > 0`; OR run `/rag-health project` and confirm no FAIL on checks 3b/3c |
| WT-07 | No unresolved NEEDS_VERIFICATION findings in context.md | All findings are CONFIRMED, DROPPED, or escalated |
| WT-08 | Tests planned → test files exist | If plan includes a test-agent step, at least one test file is present |

### PROJECT mode tests (run all)

| ID | Check | Pass condition |
|----|-------|----------------|
| PT-01 | README exists | File present at project root |
| PT-02 | Project RAG indexed | POST /index output from Phase 1 shows `files_indexed + files_unchanged > 0`; OR run `/rag-health project` and confirm no FAIL on checks 3b/3c |
| PT-03 | Raw SQL string concatenation | Zero occurrences (grep for string-concatenated query patterns) |
| PT-04 | Secrets in source | Zero hardcoded API keys, passwords, tokens in non-.env source files |
| PT-05 | logger.error in catch blocks | Sample 10 catch blocks via grep; flag any missing error logging (INFO, not FAIL) |

**PHASE 3 GATE:** If more than 3 tests FAIL (INFO items don't count), STOP. Print: "Self-test gate: N failures. Fix before proceeding." Diagnose before continuing.

---

## Phase 4: Pre-Fix Gate

For each finding from Phase 2 with a `file:line` citation, spawn a fresh `evaluator-agent` (Sonnet) with ONLY:
- The finding text
- The cited `file:line` reference
- No other context from this session

Evaluator returns: **CONFIRMED** (finding is real at that location) or **UNVERIFIED** (not found).

Drop all UNVERIFIED findings.

Print: "Pre-fix gate: N confirmed, M dropped as unverified."

If zero confirmed findings: skip to Phase 7.

---

## Phase 5: Fix

Apply minimal targeted changes for CONFIRMED findings only.

Rules:
- One finding = one fix. Do not bundle unrelated changes.
- No scope creep — do not improve surrounding code while fixing.
- WORKSPACE mode: never modify `goal.md` or `plan.md` — only the implementation files listed as artifacts.
- Document each fix: "Fixed: [finding] at [file:line]"

---

## Phase 6: Post-Fix Verify

1. Re-run the Phase 3 tests for this mode — all must pass.
2. Spawn fresh `evaluator-agent` on each changed file:
   - Pass: file path + the change made
   - Evaluator returns: CORRECT or NEEDS_IMPROVEMENT
3. If NEEDS_IMPROVEMENT: rework, re-run evaluator.

---

## Phase 7: Document + Loop

**7a — Write round log to the right location.**

| MODE | Log target |
|------|-----------|
| SELF | Append to `$CLAUDEBOOST_HOME/workspace/self-improvement/context.md` (create if missing) |
| WORKSPACE | Append to `$WORKSPACE_ABS/context.md` under a `## Self-Improve Log` section (create section if missing) |
| PROJECT | Append to `$PROJECT_PATH/workspace/.self-improve-log.md` (create file if missing) |

Log entry format:
```
### R[N+1] — [date]
**Mode:** [SELF | WORKSPACE | PROJECT]
**Target:** [workspace ID or project path or "ClaudeBoost"]
**Focus:** [FOCUS]
**Tests:** N passed / M total
**Findings:** N confirmed, M dropped as unverified
**Fixes applied:**
- [list each fix with file:line, or "none"]
**Status:** CLEAN | FIXED
```

Also update `$WORKSPACE_ABS/context.md` Status field to COMPLETE if all WT tests pass (WORKSPACE mode only).

**7b — Loop control.**

- If any confirmed findings were fixed: print "Changes made — starting R[N+2]" → return to Phase 1.
- If zero confirmed findings: print "R[N+1] clean — self-improvement complete."

---

## Non-Destructive Guarantee

All tests are read-only. The only writes are:
- **SELF**: `workspace/self-improvement/context.md` (round log, append only)
- **WORKSPACE**: appends to `$WORKSPACE_ABS/context.md` (never modifies goal.md or plan.md)
- **PROJECT**: `$PROJECT_PATH/workspace/.self-improve-log.md` (round log, append only)

Source files modified only in Phase 5 (Fix), only for CONFIRMED findings, only within the appropriate scope.

---

## Usage Examples

```
/self-improve                              # ClaudeBoost self-audit (original behavior)
/self-improve self                         # Same as above, explicit
/self-improve self counts                  # Check only agent/knowledge/command counts

/self-improve add-auth-2026-05-14          # Audit workspace 'add-auth-2026-05-14'
/self-improve add-auth-2026-05-14 security # Security-only audit of that workspace
/self-improve add-auth-2026-05-14 tests    # Check test coverage for that workspace

/self-improve /home/user/myapp             # Audit entire project (Linux/Mac)
/self-improve C:/Development/MyApp         # Audit entire project (Windows)
/self-improve C:/Development/MyApp quality # Quality-only audit of the project

/self-improve hooks enable                 # Enable protocol gate for current session
/self-improve hooks disable                # Disable protocol gate (allow edits freely)
/self-improve hooks status                 # Show gate state and round progress
/self-improve hooks enable C:/path/to/ws  # Enable gate for a specific workspace path
```

---

## Hooks Mode

**Trigger**: first argument is exactly `hooks`.

### How the gate works

A `PreToolUse` hook is permanently installed in `settings.local.json` for the current machine. It fires on every Edit/Write tool call but exits immediately (exit 0, no effect) unless:
1. The file being edited is `run_swebench_eval.py` inside a `coir-submission` workspace
2. A `.protocol_gate_enabled` flag file exists in that workspace

This means: **other projects are completely unaffected** — the hook reads the file path and exits 0 in < 1ms for anything outside coir-submission.

Enable/disable is just creating or deleting the flag file. There is no hook to install or uninstall per session.

### Parse sub-command

Second token: `enable` | `disable` | `status`. Default if omitted: `status`.

Third token (optional): absolute path to the workspace. Default: `${CLAUDEBOOST_HOME}/workspace/coir-submission` (resolve `CLAUDEBOOST_HOME` via `echo "${CLAUDEBOOST_HOME}"` if needed).

Set `GATE_DIR` to the resolved workspace path.
Set `FLAG_FILE = GATE_DIR/.protocol_gate_enabled`.
Set `STATE_FILE = GATE_DIR/rounds/current_round.json`.

### enable

```bash
# Create the flag file — gate becomes active immediately for this directory
python -c "
import pathlib
f = pathlib.Path('$GATE_DIR/.protocol_gate_enabled')
f.touch()
print('Protocol gate ENABLED for', '$GATE_DIR')
print('The gate will block edits to run_swebench_eval.py until P0+P1 are logged.')
print('Disable anytime: /self-improve hooks disable')
"
```

Then check if an active round exists:
```bash
python -c "
import json, pathlib, sys
sf = pathlib.Path('$STATE_FILE')
if sf.exists():
    s = json.loads(sf.read_text())
    print(f'Active round: {s[\"round\"]}')
    for p in [\"p0_research\",\"p1_hypothesis\"]:
        print(f'  {\"✓\" if s.get(p) else \"✗\"}  {p}')
else:
    print('No active round. Run: python rounds/start_round.py <round-id>  (e.g. s06)')
"
```

Report to user:
```
Protocol gate ENABLED — coir-submission only, this session.
[round status or 'no active round' message]
To start a round: python rounds/start_round.py s06
To mark phases done: python rounds/advance_phase.py p0_research
To disable: /self-improve hooks disable
```

### disable

```bash
python -c "
import pathlib
f = pathlib.Path('$GATE_DIR/.protocol_gate_enabled')
if f.exists():
    f.unlink()
    print('Protocol gate DISABLED — edits to run_swebench_eval.py are unrestricted.')
else:
    print('Gate was already disabled.')
"
```

### status

```bash
python -c "
import json, pathlib, sys
gate_dir = pathlib.Path('$GATE_DIR')
flag = gate_dir / '.protocol_gate_enabled'
state_file = gate_dir / 'rounds' / 'current_round.json'
print('Gate:', 'ENABLED' if flag.exists() else 'DISABLED')
print('Workspace:', gate_dir)
if state_file.exists():
    s = json.loads(state_file.read_text())
    print(f'Round: {s[\"round\"]}')
    phases = ['p0_research','p1_hypothesis','p2_implemented','p3_benchmarked','p4_audited','p5_observed','p6_logged']
    for p in phases:
        print(f'  {\"✓\" if s.get(p) else \"✗\"}  {p}')
else:
    print('Round: none active')
"
```

### Round workflow (shown after enable)

```
Start a round:    python rounds/start_round.py s06
Log P0 research:  write to rounds/s06/p0_research.md  →  python rounds/advance_phase.py p0_research
Log P1 hypothesis: write to rounds/s06/p1_hypothesis.md → python rounds/advance_phase.py p1_hypothesis
[gate now allows editing run_swebench_eval.py]
After benchmark:  python rounds/advance_phase.py p3_benchmarked
```
