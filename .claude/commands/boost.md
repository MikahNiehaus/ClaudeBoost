---
description: Activate ClaudeBoost - load RAG, verify GT, and prime the session
allowed-tools: Bash, Read, Glob
---

# ClaudeBoost Activation

## Step 0: Launch Animation and Clear Caches

**This is the VERY FIRST thing you do — before ANY other tool calls or checks.**

Run this EXACT bash command FIRST, alone. Do NOT modify it. Do NOT use powershell or Start-Process:
```bash
BOOST_TMP="$TEMP" && echo "" > "$BOOST_TMP/claudeboost_status.txt" && find "$CLAUDEBOOST_HOME/mcp-rag-server" -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null; wt.exe -w 0 new-tab --title "CLAUDE BOOST" python "$CLAUDEBOOST_HOME/scripts/matrix-boost.py"
```

This clears Python bytecode caches (so RAG server loads fresh code on next restart) and opens the Matrix animation as a NEW TAB in the SAME Windows Terminal window. The tab closes automatically when done.

**NEVER use `powershell Start-Process` or `cmd start` — those open separate windows.**

Do NOT run any other tool calls until this completes.

## Step 1: Verify Privacy (auto-fix)

Mark checking, then auto-fix if needed:
```bash
BOOST_TMP="$TEMP" && echo "PRIVACY:checking" >> "$BOOST_TMP/claudeboost_status.txt" && FIXED="" && if [ -z "$DISABLE_TELEMETRY" ]; then powershell -Command "[System.Environment]::SetEnvironmentVariable('DISABLE_TELEMETRY', '1', 'User')"; export DISABLE_TELEMETRY=1; FIXED="$FIXED DISABLE_TELEMETRY"; fi && if [ -z "$DISABLE_ERROR_REPORTING" ]; then powershell -Command "[System.Environment]::SetEnvironmentVariable('DISABLE_ERROR_REPORTING', '1', 'User')"; export DISABLE_ERROR_REPORTING=1; FIXED="$FIXED DISABLE_ERROR_REPORTING"; fi && if [ -n "$FIXED" ]; then echo "Auto-fixed:$FIXED"; fi && echo "PRIVACY:ready" >> "$BOOST_TMP/claudeboost_status.txt"
```

This auto-sets missing privacy env vars permanently. If any were fixed, mention it briefly in your output.

## Step 2: Check RAG (verify and auto-fix)

Mark RAG as checking, then verify the module loads from the right path:
```bash
BOOST_TMP="$TEMP" && echo "RAG:checking" >> "$BOOST_TMP/claudeboost_status.txt" && RAG_PATH=$(python -c "import rag_server; print(rag_server.__file__)" 2>/dev/null) && if echo "$RAG_PATH" | grep -q "ClaudeBoost"; then echo "RAG path OK: $RAG_PATH"; else echo "RAG path wrong: $RAG_PATH — reinstalling..."; cd "$CLAUDEBOOST_HOME/mcp-rag-server" && pip install -e . 2>&1 | tail -1; fi
```

Call `rag_status` (MCP tool) to verify the server is running and has indexed content.

Then call `rag_context` with a quick test to verify tiered context is working:
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

## Step 3: Check Gas Town

GT is already marked "checking". Check if `gt` command exists:
```bash
BOOST_TMP="$TEMP" && if command -v gt &>/dev/null; then gt prime 2>&1 | head -3; echo "GT:ready" >> "$BOOST_TMP/claudeboost_status.txt"; else echo "GT:failed" >> "$BOOST_TMP/claudeboost_status.txt"; fi && echo "RULES:checking" >> "$BOOST_TMP/claudeboost_status.txt"
```

GT is "ready" if installed (even if not in a GT workspace). "failed" only if `gt` command not found.

## Step 4: Check Enforcement Hooks

Verify that PreToolUse and PreCompact hooks are configured in settings.json:
```bash
BOOST_TMP="$TEMP" && HOOKS_OK=true && if python -c "import json; s=json.load(open('$HOME/.claude/settings.json')); assert 'PreToolUse' in s.get('hooks',{})" 2>/dev/null; then echo "PreToolUse hooks: OK"; else echo "PreToolUse hooks: MISSING"; HOOKS_OK=false; fi && if python -c "import json; s=json.load(open('$HOME/.claude/settings.json')); assert 'PreCompact' in s.get('hooks',{})" 2>/dev/null; then echo "PreCompact hooks: OK"; else echo "PreCompact hooks: MISSING"; HOOKS_OK=false; fi && if [ "$HOOKS_OK" = false ]; then echo "[WARN] Enforcement hooks missing - run setup.ps1 to install"; fi
```

If hooks are missing, warn the user to run `setup.ps1`. This is not a blocking failure — boost continues.

## Step 5: Check Rules

RULES is already marked "checking". Verify CLAUDE.md exists:
```bash
BOOST_TMP="$TEMP" && head -5 ~/.claude/CLAUDE.md 2>/dev/null && echo "RULES:ready" >> "$BOOST_TMP/claudeboost_status.txt" && echo "AGENTS:ready" >> "$BOOST_TMP/claudeboost_status.txt"
```

If CLAUDE.md doesn't exist, write "RULES:failed" and still write "AGENTS:ready".

## Step 6: Activate and Report

If all checks passed, create the activation marker:
```bash
BOOST_TMP="$TEMP" && touch "$BOOST_TMP/claudeboost_active"
```

Report what happened — be honest about what's working and what needs attention:
- If everything passed: "ClaudeBoost is live. Ask me anything or use /spawn-agent to delegate."
- If tiered RAG isn't loaded: mention it needs a restart
- If privacy was auto-fixed: mention what was set
- If anything failed: explain what and how to fix it

Do NOT create the marker file if critical checks (RAG, Rules) failed.
