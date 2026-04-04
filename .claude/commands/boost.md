---
description: Activate ClaudeBoost - load RAG, verify GT, and prime the session
allowed-tools: Bash, Read, Glob
---

# ClaudeBoost Activation

## Step 0: Launch Animation and Show Banner

**This is the VERY FIRST thing you do — before ANY other tool calls or checks.**

Run this EXACT bash command FIRST, alone. Do NOT modify it. Do NOT use powershell or Start-Process:
```bash
BOOST_TMP="$TEMP" && echo "" > "$BOOST_TMP/claudeboost_status.txt" && wt.exe -w last new-tab --title "CLAUDE BOOST" python "C:/Users/grayw/OneDrive/prj/ClaudeBoost/scripts/matrix-boost.py"
```

This opens the Matrix animation as a NEW TAB in the SAME Windows Terminal window (not a new window). The tab closes automatically when done.

**NEVER use `powershell Start-Process` or `cmd start` — those open separate windows.**

Do NOT run any other tool calls until this completes.

## Step 1: Verify Privacy

Mark checking, then verify telemetry and training protections:

```bash
BOOST_TMP="$TEMP" && echo "PRIVACY:checking" >> "$BOOST_TMP/claudeboost_status.txt"
```

Check and AUTO-FIX privacy environment variables:
```bash
BOOST_TMP="$TEMP" && FIXED="" && if [ -z "$DISABLE_TELEMETRY" ]; then powershell -Command "[System.Environment]::SetEnvironmentVariable('DISABLE_TELEMETRY', '1', 'User')"; export DISABLE_TELEMETRY=1; FIXED="$FIXED DISABLE_TELEMETRY"; fi && if [ -z "$DISABLE_ERROR_REPORTING" ]; then powershell -Command "[System.Environment]::SetEnvironmentVariable('DISABLE_ERROR_REPORTING', '1', 'User')"; export DISABLE_ERROR_REPORTING=1; FIXED="$FIXED DISABLE_ERROR_REPORTING"; fi && if [ -n "$FIXED" ]; then echo "Auto-set:$FIXED"; fi && echo "PRIVACY:ready" >> "$BOOST_TMP/claudeboost_status.txt" && echo "RAG:checking" >> "$BOOST_TMP/claudeboost_status.txt"
```

If any vars were missing, they are automatically set permanently (User scope). Mention what was fixed in the output.

## Step 2: Check RAG

```bash
BOOST_TMP="$TEMP" && echo "RAG:checking" >> "$BOOST_TMP/claudeboost_status.txt"
```

Call `rag_status` (MCP tool).

After rag_status returns, write result:
```bash
BOOST_TMP="$TEMP" && echo "RAG:ready" >> "$BOOST_TMP/claudeboost_status.txt" && echo "GT:checking" >> "$BOOST_TMP/claudeboost_status.txt"
```

(Use "RAG:failed" if it didn't work.)

## Step 3: Check Gas Town

GT is already marked "checking" from Step 2. Now check:
```bash
BOOST_TMP="$TEMP" && if command -v gt &>/dev/null; then gt prime 2>&1 | head -3; echo "GT:ready" >> "$BOOST_TMP/claudeboost_status.txt"; else echo "GT:failed" >> "$BOOST_TMP/claudeboost_status.txt"; fi && echo "RULES:checking" >> "$BOOST_TMP/claudeboost_status.txt"
```

GT is "ready" if installed (even if not in a GT workspace). Use "GT:failed" only if `gt` command not found.

## Step 4: Check Rules

RULES is already marked "checking". Verify CLAUDE.md exists:
```bash
BOOST_TMP="$TEMP" && head -5 ~/.claude/CLAUDE.md 2>/dev/null && echo "RULES:ready" >> "$BOOST_TMP/claudeboost_status.txt" && echo "AGENTS:ready" >> "$BOOST_TMP/claudeboost_status.txt"
```

If CLAUDE.md doesn't exist, write "RULES:failed" and still write "AGENTS:ready".

## Step 5: Activate and Report

If all checks passed, create the activation marker so the status line lights up:
```bash
BOOST_TMP="$TEMP" && touch "$BOOST_TMP/claudeboost_active"
```

Output a single line:

"ClaudeBoost is live. Ask me anything or use /spawn-agent to delegate."

If any check failed, mention what failed and do NOT create the marker file.
