---
description: Activate ClaudeBoost - load RAG, verify GT, and prime the session
allowed-tools: Bash, Read, Glob
---

# ClaudeBoost Activation

## Step 0: Launch Animation and Show Banner

**This is the VERY FIRST thing you do — before ANY other tool calls or checks.**

Run this bash command FIRST, alone:
```bash
echo "" > "/tmp/claudeboost_status.txt" && powershell -Command "Start-Process python -ArgumentList 'C:/Users/grayw/OneDrive/prj/ClaudeBoost/scripts/matrix-boost.py'"
```

The Matrix animation window IS the banner — no need to duplicate it in Claude Code.

Do NOT run any other tool calls until this completes.

## Step 1: Check RAG

Mark checking, then call rag_status, then mark result. Combine the status writes:

```bash
echo "RAG:checking" >> "/tmp/claudeboost_status.txt"
```

Call `rag_status` (MCP tool).

After rag_status returns, write result:
```bash
echo "RAG:ready" >> "/tmp/claudeboost_status.txt" && echo "GT:checking" >> "/tmp/claudeboost_status.txt"
```

(Use "RAG:failed" if it didn't work.)

## Step 2: Check Gas Town

GT is already marked "checking" from Step 1. Now check:
```bash
gt prime 2>&1 | head -3; echo "GT:ready" >> "/tmp/claudeboost_status.txt" && echo "RULES:checking" >> "/tmp/claudeboost_status.txt"
```

GT is "ready" if installed (even if not in a GT workspace). Use "GT:failed" only if `gt` command not found.

## Step 3: Check Rules

RULES is already marked "checking". Verify CLAUDE.md exists:
```bash
head -5 ~/.claude/CLAUDE.md 2>/dev/null && echo "RULES:ready" >> "/tmp/claudeboost_status.txt" && echo "AGENTS:ready" >> "/tmp/claudeboost_status.txt"
```

If CLAUDE.md doesn't exist, write "RULES:failed" and still write "AGENTS:ready".

## Step 4: Activate and Report

If all checks passed, create the activation marker so the status line lights up:
```bash
touch /tmp/claudeboost_active
```

Output a single line:

"ClaudeBoost is live. Ask me anything or use /spawn-agent to delegate."

If any check failed, mention what failed and do NOT create the marker file.
