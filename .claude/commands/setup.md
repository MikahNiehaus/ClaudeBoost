---
description: Full ClaudeBoost setup and verification — works for fresh installs and git pull updates
allowed-tools: Bash, Read, Write, Glob, mcp__rag-server__rag_index, mcp__rag-server__rag_status
---

# /setup — ClaudeBoost Setup & Verification

Installs ClaudeBoost (if needed) then verifies every component in a loop with auto-repair.

**Two scenarios this covers:**
- **Fresh computer** — No previous ClaudeBoost install. setup.ps1 creates everything from scratch: hooks, MCP config, RAG server, state files, Python deps.
- **After `git pull`** — Existing install. setup.ps1 picks up new hooks and deps idempotently (never duplicates). New slash commands are already in the repo. Re-index refreshes the RAG so new agents/knowledge are searchable.

Safe to re-run anytime — all operations preserve existing user settings.

---

## Phase 0: Locate ClaudeBoost Home

```bash
echo "CLAUDEBOOST_HOME=$CLAUDEBOOST_HOME"
```

If `$CLAUDEBOOST_HOME` is set, proceed to Phase 1.

If `$CLAUDEBOOST_HOME` is empty:

1. Try extracting from `~/.claude/settings.json`:
   ```bash
   python -c "import json,os; d=json.load(open(os.path.expanduser('~/.claude/settings.json'))); print(d.get('env',{}).get('CLAUDEBOOST_HOME','MISSING'))" 2>/dev/null || echo "MISSING"
   ```
2. If a valid path is returned: run `export CLAUDEBOOST_HOME=<path>` so Phase 1 can use it.
3. If `MISSING` (settings.json absent, or exists but has no `CLAUDEBOOST_HOME` key): ask the user:
   > "This appears to be a fresh install. What is the full path to your ClaudeBoost repo?"
   Then run: `export CLAUDEBOOST_HOME=<user-provided-path>`

Announce: `ClaudeBoost home: <path>`

---

## Phase 1: Run Setup Script

Installs hooks, registers MCP server, seeds state files, installs Python deps. All steps are idempotent.

```bash
powershell -ExecutionPolicy Bypass -File "$CLAUDEBOOST_HOME/scripts/setup.ps1"
```

Read the output. Summarize:
- `[OK]` items: newly installed or verified
- `[SKIP]` items: already present (existing settings preserved)
- `[WARN]` items: non-fatal issues that may need attention

---

## Phase 2: Verification Loop

**Loop protocol:** For each check, run it, check the result. On failure, run the repair, then retry immediately. Repeat up to **3 attempts** per check. Move on only after passing or exhausting retries.

**IMPORTANT: Re-index is Step 0 of every loop iteration.** Run it unconditionally — even if you think the index is current. After a git pull, new agents and knowledge files must be in the RAG before any other check runs.

---

### Step 0 — Re-index ClaudeBoost RAG (MANDATORY, runs every time)

Call `rag_index(force=true)` to force a full re-index of all ClaudeBoost agents and knowledge bases.

Report: "Re-indexed: N files, M chunks."

This ensures every subsequent check and all future sessions see the latest agents, knowledge, and slash commands.

---

### Check 1 — RAG Server Health

```bash
python "$CLAUDEBOOST_HOME/scripts/check-rag-health.py"; echo "EXIT=$?"
```

| Exit | Meaning | Repair |
|------|---------|--------|
| 0 | **PASS** | — |
| 2 | Dependency drift (tokenizers/transformers mismatch) | `python "$CLAUDEBOOST_HOME/scripts/reinstall-rag.py"` then retry |
| 3 | Wrong install path | `python "$CLAUDEBOOST_HOME/scripts/reinstall-rag.py"` then retry |
| 1 | Unknown error | Mark FAIL, include output — manual fix needed |

---

### Check 2 — Required Hooks

All seven hook types must be registered in `~/.claude/settings.json`:

```bash
for hook in SessionStart SessionEnd PreToolUse PostToolUse PreCompact UserPromptSubmit Stop; do
  python "$CLAUDEBOOST_HOME/scripts/check-hooks.py" "$hook" && echo "OK: $hook" || echo "MISSING: $hook"
done
```

If any are MISSING: re-run `setup.ps1` (hooks are additive — re-running never duplicates), then retry.

---

### Check 3 — State Files

```bash
ls "$CLAUDEBOOST_HOME/state/"
```

Required: `claudeboost-mode.json`, `session-approvals.json`, `speak-state.json`

If any are missing: re-run `setup.ps1` (it seeds missing files while preserving existing ones), then retry.

Also verify that `claudeboost-mode.json` contains `"mode": "CONSULT"`:

```bash
python -c "import json,os; d=json.load(open(os.path.join(os.environ['CLAUDEBOOST_HOME'],'state','claudeboost-mode.json'))); print('mode =', d.get('mode','MISSING'))"
```

If mode is not `CONSULT`: re-run `setup.ps1` — it now resets any non-CONSULT value back to CONSULT automatically.

---

### Check 4 — edge-tts (for /speak)

```bash
python -c "import edge_tts; print('ok')"
```

If FAIL: repair → `pip install edge-tts`, then retry.

---

### Check 5 — Global CLAUDE.md

```bash
head -3 ~/.claude/CLAUDE.md 2>/dev/null || echo "MISSING"
```

If missing: **do not auto-copy** — the project CLAUDE.md documents ClaudeBoost internals and must not be used as the global user file. Instead, warn the user:

> "~/.claude/CLAUDE.md is missing. Create it with your personal global rules (shell conventions, security standards, coding preferences). See the ClaudeBoost docs for an example of what to include. Once created, re-run /setup to verify."

Mark as WARN (not FAIL) and continue. Do not retry — this requires manual user action.

---

### Check 6 — statusLine

```bash
python -c "
import json, os
p = os.path.expanduser('~/.claude/settings.json')
s = json.load(open(p))
sl = s.get('statusLine', {})
cmd = sl.get('command', '')
print('PRESENT' if 'ClaudeBoost' in cmd else 'MISSING')
"
```

If MISSING: re-run `setup.ps1` — it now creates the statusLine on fresh installs. Then run `/mcp` to reconnect.

---

### Check 7 — Global slash commands synced

Project `.claude/commands/` only load when Claude Code's cwd is inside the ClaudeBoost repo. `setup.ps1` mirrors every command to `~/.claude/commands/` so all skills (`/workspace`, `/explore`, `/audit`, etc.) are available in **every** Claude instance regardless of directory. Verify the global dir has the full set:

```bash
SRC=$(ls "$CLAUDEBOOST_HOME/.claude/commands/"*.md 2>/dev/null | wc -l)
DST=$(ls ~/.claude/commands/*.md 2>/dev/null | wc -l)
echo "project=$SRC global=$DST"
comm -23 <(ls "$CLAUDEBOOST_HOME/.claude/commands/" 2>/dev/null | sort) <(ls ~/.claude/commands/ 2>/dev/null | sort)
```

If the `comm` output lists any files (commands present in the repo but missing globally), re-run `setup.ps1` — section 2b syncs them. Then **restart any other Claude instances** for them to pick up the new commands (the command list is read at startup).

---

## Phase 3: Report

Print a final status table:

```
=== ClaudeBoost Setup Status ===
Scenario : Fresh install / Update after git pull
Home     : <path>

Step/Check               Result
─────────────────────────────────────────
Re-index ClaudeBoost RAG : OK (N files, M chunks)
RAG server health        : OK / FAIL (<reason>)
Required hooks           : OK (7/7) / MISSING: <list>
State files              : OK (3/3) / MISSING: <list>
edge-tts                 : OK / FAIL
CLAUDE.md                : OK / MISSING
statusLine               : OK / MISSING (run `/mcp` after setup.ps1)
Global commands synced   : OK (N/N) / MISSING: <list> (restart other instances)

─────────────────────────────────────────
```

**If ALL checks pass:**
> "Setup complete. All systems operational."
> - **Fresh install:** "Run `/mcp` to reconnect, then run `/boost`."
> - **After git pull:** "Run `/boost` to activate the updated ClaudeBoost for this session."

**If any checks fail after all retries:**
> "N check(s) could not be auto-repaired. See above for manual steps. Run `/setup` again after fixing."
