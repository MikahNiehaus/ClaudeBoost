---
description: Activate ClaudeBoost - always load RAG + GT and prime the session
allowed-tools: Bash, Read, Glob
---

# ClaudeBoost Activation

## Step 0: Launch Animation and Clear Caches

**This is the VERY FIRST thing you do — before ANY other tool calls or checks.**

Run this EXACT bash command FIRST, alone. Do NOT modify it. Do NOT use powershell or Start-Process:
```bash
BOOST_TMP="$TEMP" && echo "" > "$BOOST_TMP/claudeboost_status.txt" && find "$CLAUDEBOOST_HOME/mcp-rag-server" -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null; wt.exe -w 0 new-tab --title "CLAUDE BOOST" python "$CLAUDEBOOST_HOME/scripts/matrix-boost.py"
```

This clears Python bytecode caches (so RAG server loads fresh code on next restart) and opens the Matrix animation as a NEW TAB in the SAME Windows Terminal window. The animation reads the status file live and shows each system coming online as checks complete. The tab closes automatically when all systems are online.

**NEVER use `powershell Start-Process` or `cmd start` — those open separate windows.**

Do NOT run any other tool calls until this completes.

## Step 1: Verify Privacy (auto-fix)

Mark checking, then auto-fix if needed:
```bash
BOOST_TMP="$TEMP" && echo "PRIVACY:checking" >> "$BOOST_TMP/claudeboost_status.txt" && FIXED="" && if [ -z "$DISABLE_TELEMETRY" ]; then powershell -Command "[System.Environment]::SetEnvironmentVariable('DISABLE_TELEMETRY', '1', 'User')"; export DISABLE_TELEMETRY=1; FIXED="$FIXED DISABLE_TELEMETRY"; fi && if [ -z "$DISABLE_ERROR_REPORTING" ]; then powershell -Command "[System.Environment]::SetEnvironmentVariable('DISABLE_ERROR_REPORTING', '1', 'User')"; export DISABLE_ERROR_REPORTING=1; FIXED="$FIXED DISABLE_ERROR_REPORTING"; fi && if [ -n "$FIXED" ]; then echo "Auto-fixed:$FIXED"; fi && echo "PRIVACY:ready" >> "$BOOST_TMP/claudeboost_status.txt"
```

This auto-sets missing privacy env vars permanently. If any were fixed, mention it briefly in your output.

## Step 2: Activate RAG (MANDATORY — verify, auto-fix, and load)

Mark RAG as checking, then run the full health check. This verifies BOTH that
`rag_server` installs from the right path AND that `sentence-transformers`
actually loads — catching the tokenizers/transformers version-drift crash
that the path-only check misses. Exit code 2 or 3 triggers auto-repair:
```bash
BOOST_TMP="$TEMP" && echo "RAG:checking" >> "$BOOST_TMP/claudeboost_status.txt" && python "$CLAUDEBOOST_HOME/scripts/check-rag-health.py"; RC=$?; if [ $RC -eq 0 ]; then echo "RAG: healthy"; elif [ $RC -eq 2 ] || [ $RC -eq 3 ]; then echo "RAG: needs repair (exit $RC) — running reinstall..."; python "$CLAUDEBOOST_HOME/scripts/reinstall-rag.py" && python "$CLAUDEBOOST_HOME/scripts/check-rag-health.py" && echo "RAG: repaired" || echo "RAG: repair failed — run setup.ps1"; else echo "RAG: unknown failure (exit $RC) — run setup.ps1"; fi
```

Call `rag_status` (MCP tool) to verify the server is running and has indexed content.

Then **actively load RAG context** — this is not just a check, it primes the session:
```
rag_context(agent="debug-agent", task_description="test", max_tokens=2000)
```

Check the response for `tier_summary`:
- If `tier_summary` exists with `guardrails > 0` AND `declared > 0`: tiered RAG is working, mark ready
- If `tier_summary` is missing or all zeros: auto-fix attempt — clear `__pycache__` and report "RAG needs restart to load tiered context"
- If rag_status fails entirely: mark failed, tell user to run `setup.ps1`

After checks, write result:
```bash
BOOST_TMP="$TEMP" && echo "RAG:ready" >> "$BOOST_TMP/claudeboost_status.txt" && echo "GT:checking" >> "$BOOST_TMP/claudeboost_status.txt"
```

Use "RAG:failed" if rag_status fails entirely. Use "RAG:ready" if it works even if tiered context isn't loaded yet (but warn the user).

**RAG is non-negotiable.** If RAG fails, boost activation is incomplete — tell the user to fix it.

## Step 3: Activate Gas Town (MANDATORY — always prime, auto-init if needed)

GT is already marked "checking". Check if `gt` exists, try `gt prime`, and
**auto-init the rig if the current directory is a git repo but not yet a GT
workspace**. Without auto-init, every new repo has to be `gt init`'d by hand
before `gt prime`/`gt status`/`gt sling` will work:
```bash
BOOST_TMP="$TEMP" && if command -v gt &>/dev/null; then echo "GT INSTALLED: $(gt --version 2>&1 | head -1)"; echo "--- Running gt prime ---"; GT_OUT=$(gt prime 2>&1); GT_RC=$?; echo "$GT_OUT"; if [ $GT_RC -ne 0 ] && echo "$GT_OUT" | grep -q "not in a Gas Town workspace"; then if [ -d .git ] || git rev-parse --git-dir >/dev/null 2>&1; then echo "--- Not a GT workspace; running gt init ---"; gt init 2>&1 | tail -5; echo "--- Re-running gt prime ---"; gt prime 2>&1 | head -5; fi; fi; echo "GT:ready" >> "$BOOST_TMP/claudeboost_status.txt"; else echo "GT NOT FOUND in PATH"; echo "GT:failed" >> "$BOOST_TMP/claudeboost_status.txt"; fi && echo "RULES:checking" >> "$BOOST_TMP/claudeboost_status.txt"
```

GT is "ready" if `command -v gt` succeeds. "failed" ONLY if `gt` is not on PATH.
**Read the bash output carefully** — if it prints "GT INSTALLED:" then GT is available. Do NOT report "GT not installed" when the check passed.

`gt init` is idempotent and only runs when `gt prime` explicitly reports the cwd is not a workspace AND the cwd is a git repo. It creates `polecats/`, `witness/`, `refinery/`, `mayor/`, `crew/` — all auto-added to `.git/info/exclude`, so nothing is committed.

**GT is mandatory.** If GT is not on PATH, warn the user to install it — do NOT silently skip it. Both RAG and GT must be active for a fully boosted session.

## Step 4: Check Enforcement Hooks

Verify that PreToolUse and PreCompact hooks are configured in settings.json:
```bash
BOOST_TMP="$TEMP" && HOOKS_OK=true && if python "$CLAUDEBOOST_HOME/scripts/check-hooks.py" PreToolUse 2>/dev/null; then true; else echo "PreToolUse hooks: MISSING"; HOOKS_OK=false; fi && if python "$CLAUDEBOOST_HOME/scripts/check-hooks.py" PreCompact 2>/dev/null; then true; else echo "PreCompact hooks: MISSING"; HOOKS_OK=false; fi && if [ "$HOOKS_OK" = false ]; then echo "[WARN] Enforcement hooks missing - run setup.ps1 to install"; fi
```

If hooks are missing, warn the user to run `setup.ps1`. This is not a blocking failure — boost continues.

## Step 5: Check Rules

RULES is already marked "checking". Verify CLAUDE.md exists:
```bash
BOOST_TMP="$TEMP" && head -5 ~/.claude/CLAUDE.md 2>/dev/null && echo "RULES:ready" >> "$BOOST_TMP/claudeboost_status.txt" && echo "AGENTS:ready" >> "$BOOST_TMP/claudeboost_status.txt"
```

If CLAUDE.md doesn't exist, write "RULES:failed" and still write "AGENTS:ready".

## Step 5b: Read CONSULT/AUTO Mode

Read the current collaborative mode so you can report it to the user:
```bash
if [ -f "$CLAUDEBOOST_HOME/state/claudeboost-mode.json" ]; then cat "$CLAUDEBOOST_HOME/state/claudeboost-mode.json"; else echo "mode file missing — defaulting to CONSULT"; fi
```

Also clear the session-approvals scratchpad (approvals do not carry across sessions):
```bash
if [ -f "$CLAUDEBOOST_HOME/state/session-approvals.json" ]; then echo '{"sessionId":"","approvals":[]}' > "$CLAUDEBOOST_HOME/state/session-approvals.json"; fi
```

## Step 6: Workspace Discovery

Scan for active workspaces and reconnect to in-progress work:
```bash
if [ -d "workspace" ]; then for d in workspace/*/; do if [ -f "${d}context.md" ]; then echo "WORKSPACE: $d"; head -5 "${d}context.md"; echo "---"; fi; done; else echo "No workspace/ directory found"; fi
```

If workspaces are found:
- List each task ID and its current status (read from context.md)
- Note which ones have recent activity (check git log for last modified)
- If exactly one workspace exists, read its full `context.md` to restore session state

If no workspaces found, that's fine — this may be a fresh session.

## Step 7: Activate and Report

If all checks passed, create the activation marker and signal the animation to close:
```bash
BOOST_TMP="$TEMP" && touch "$BOOST_TMP/claudeboost_active" && echo "BOOST:done" >> "$BOOST_TMP/claudeboost_status.txt"
```

**Report format — include ALL of these sections:**

### Systems Status
- RAG: ready/failed (chunk counts)
- GT: ready/failed (version)
- Hooks: PreToolUse + PreCompact present/missing
- Rules: CLAUDE.md loaded/missing

### Active Workspaces
- List any discovered workspaces with task IDs and status
- If resuming work: "Resuming task [id] — last status was [X]"
- If fresh session: "No active workspaces"

### Session Directives
**Always include ALL of these reminders in your report — both RAG and GT are mandatory:**
- "RAG is active. I will call `rag_context` as Step 1 when spawning agents, and `rag_search` when I need knowledge."
- "Gas Town is active. I will use `gt prime` for workspace init, `gt sling` for cross-session delegation, and `gt handoff` for session transitions."
- If GT check failed: append "(GT not found on PATH — install or add to PATH to enable)" but still include the GT directive above.

### Collaborative Mode
Report the current CONSULT/AUTO mode from state/claudeboost-mode.json:
- **CONSULT (default)**: "I will research, propose via architect-agent (Opus), and ask before any architectural decision. Use `/auto` to bypass for trivial work."
- **AUTO**: "I am in autonomous mode — I will proceed on architectural decisions without consulting. Use `/consult` to re-enable consultation."

### Ready
- If everything passed: "ClaudeBoost is live. Ask me anything or use /spawn-agent to delegate."
- If tiered RAG isn't loaded: mention it needs a restart
- If privacy was auto-fixed: mention what was set
- If anything failed: explain what and how to fix it

Do NOT create the marker file if critical checks (RAG, GT, Rules) failed. Both RAG and GT must be active for full boost.
