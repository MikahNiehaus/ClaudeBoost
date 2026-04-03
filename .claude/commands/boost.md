---
description: Activate ClaudeBoost - load RAG, verify GT, and prime the session
allowed-tools: Bash, Read, Glob
---

# ClaudeBoost Activation

## Step 0: Launch Animation and Show Banner

**This is the VERY FIRST thing you do — before ANY other tool calls or checks.**

Run this bash command FIRST, alone:
```bash
BOOST_TMP="$LOCALAPPDATA/Temp" && echo "" > "$BOOST_TMP/claudeboost_status.txt" && powershell -NoProfile -ExecutionPolicy Bypass -File "C:/Development/ClaudeBoost/scripts/boost-capture.ps1" && powershell -NoProfile -Command "Start-Process powershell -ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-File','C:/Development/ClaudeBoost/scripts/boost-launcher.ps1' -WindowStyle Hidden"
```

Phase 1 (inline): captures the Claude Code terminal position and minimizes it.
Phase 2 (detached): launches the Matrix animation at the same position, tracks it, and restores Claude Code when done — even if you move/resize the animation window.

Do NOT run any other tool calls until this completes.

## Step 1: Verify Privacy

Mark checking, then verify telemetry and training protections:

```bash
BOOST_TMP="$LOCALAPPDATA/Temp" && echo "PRIVACY:checking" >> "$BOOST_TMP/claudeboost_status.txt"
```

Check privacy environment variables:
```bash
BOOST_TMP="$LOCALAPPDATA/Temp" && PRIVACY_OK=true && if [ -z "$DISABLE_TELEMETRY" ]; then echo "⚠ DISABLE_TELEMETRY not set"; PRIVACY_OK=false; fi && if [ -z "$DISABLE_ERROR_REPORTING" ]; then echo "⚠ DISABLE_ERROR_REPORTING not set"; PRIVACY_OK=false; fi && echo "PRIVACY:ready" >> "$BOOST_TMP/claudeboost_status.txt" && echo "RAG:checking" >> "$BOOST_TMP/claudeboost_status.txt"
```

If any privacy var is missing, still mark ready but **warn the user**:
- "Set `DISABLE_TELEMETRY=1` and `DISABLE_ERROR_REPORTING=1` in your environment for full privacy."
- "If on a consumer plan (Free/Pro/Max), also opt out of training at claude.ai/settings/data-privacy-controls"
- API/Team/Enterprise users are already protected from training by default.

## Step 2: Check RAG

```bash
BOOST_TMP="$LOCALAPPDATA/Temp" && echo "RAG:checking" >> "$BOOST_TMP/claudeboost_status.txt"
```

Call `rag_status` (MCP tool).

After rag_status returns, write result:
```bash
BOOST_TMP="$LOCALAPPDATA/Temp" && echo "RAG:ready" >> "$BOOST_TMP/claudeboost_status.txt" && echo "GT:checking" >> "$BOOST_TMP/claudeboost_status.txt"
```

(Use "RAG:failed" if it didn't work.)

## Step 3: Check Gas Town

GT is already marked "checking" from Step 2. Now check:
```bash
BOOST_TMP="$LOCALAPPDATA/Temp" && gt prime 2>&1 | head -3; echo "GT:ready" >> "$BOOST_TMP/claudeboost_status.txt" && echo "RULES:checking" >> "$BOOST_TMP/claudeboost_status.txt"
```

GT is "ready" if installed (even if not in a GT workspace). Use "GT:failed" only if `gt` command not found.

## Step 4: Check Rules

RULES is already marked "checking". Verify CLAUDE.md exists:
```bash
BOOST_TMP="$LOCALAPPDATA/Temp" && head -5 ~/.claude/CLAUDE.md 2>/dev/null && echo "RULES:ready" >> "$BOOST_TMP/claudeboost_status.txt" && echo "AGENTS:ready" >> "$BOOST_TMP/claudeboost_status.txt"
```

If CLAUDE.md doesn't exist, write "RULES:failed" and still write "AGENTS:ready".

## Step 5: Activate and Report

If all checks passed, create the activation marker so the status line lights up:
```bash
BOOST_TMP="$LOCALAPPDATA/Temp" && touch "$BOOST_TMP/claudeboost_active"
```

Output a single line:

"ClaudeBoost is live. Ask me anything or use /spawn-agent to delegate."

If any check failed, mention what failed and do NOT create the marker file.
