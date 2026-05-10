---
description: Full ClaudeBoost setup and verification — works for fresh installs and git pull updates
allowed-tools: Bash, Read, Write, Glob
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

If `$CLAUDEBOOST_HOME` is empty, read `~/.claude/settings.json` and extract `env.CLAUDEBOOST_HOME`. Use that path as `$BOOST` for all subsequent steps. If settings.json doesn't exist yet, this is a fresh install — continue with Phase 1.

Announce: `ClaudeBoost home: <path>` (or "Fresh install — no existing config detected")

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

All six hook types must be registered in `~/.claude/settings.json`:

```bash
for hook in SessionStart PreToolUse PostToolUse PreCompact UserPromptSubmit Stop; do
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

If missing: copy from ClaudeBoost:
```bash
cp "$CLAUDEBOOST_HOME/CLAUDE.md" ~/.claude/CLAUDE.md && echo "Copied CLAUDE.md"
```
Then retry.

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
Required hooks           : OK (6/6) / MISSING: <list>
State files              : OK (3/3) / MISSING: <list>
edge-tts                 : OK / FAIL
CLAUDE.md                : OK / MISSING

─────────────────────────────────────────
```

**If ALL checks pass:**
> "Setup complete. All systems operational."
> - **Fresh install:** "Restart Claude Code for MCP changes to take effect, then run `/boost`."
> - **After git pull:** "Run `/boost` to activate the updated ClaudeBoost for this session."

**If any checks fail after all retries:**
> "N check(s) could not be auto-repaired. See above for manual steps. Run `/setup` again after fixing."
