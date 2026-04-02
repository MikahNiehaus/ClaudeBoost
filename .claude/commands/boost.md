---
description: Activate ClaudeBoost - load RAG, verify GT, and prime the session
allowed-tools: Bash, Read, Glob
---

# ClaudeBoost Activation

## Step 1: Verify RAG Server

Call `rag_status` to confirm the RAG MCP server is running and indexed.

If it shows collections with chunks (knowledge, agents), RAG is ready.
If it fails, the RAG server may not be registered. Tell the user to run:
```
install.bat from their ClaudeBoost directory
```

## Step 2: Check Gas Town

Run this to check if GT is available:
```bash
gt prime 2>&1 | head -3
```

If GT is installed and Dolt is running, report GT status.
If GT is not installed or Dolt is down, that's fine — ClaudeBoost works standalone.

If Dolt is not running but GT is installed:
```bash
gt dolt start
```

## Step 3: Load CLAUDE.md Rules

Read the global CLAUDE.md for orchestration rules:
```bash
cat ~/.claude/CLAUDE.md 2>/dev/null | head -5
```

If it exists, confirm ClaudeBoost rules are active (agent roster, RAG instructions, verify gate, hard rules).

## Step 4: Report Status

Output a status summary:

```
ClaudeBoost Active
  RAG:      [ready / not available] — [X] knowledge, [Y] agents chunks
  GT:       [running / not installed / Dolt down]
  Rules:    [loaded / missing CLAUDE.md]
  Agents:   21 specialists available (use /spawn-agent or /list-agents)
  Commands: /list-agents, /spawn-agent, /plan-task, /review, /gate
```

If everything is ready, say: "ClaudeBoost is live. RAG is searching across [X] knowledge chunks. Ask me anything or use /spawn-agent to delegate."
