---
argument-hint: <agent-name> <task-id>
description: Spawn an agent with RAG knowledge loading
allowed-tools: Read, Glob, Task
---

# Agent Spawn Request: $ARGUMENTS

## Validation Checklist

Before spawning, verify:
1. Agent definition exists at `agents/$1-agent.xml`
2. Task workspace exists or will be created at `workspace/$2/`

## Instructions

Spawn the agent using the Task tool. The agent will load its own knowledge via RAG.

Include in the agent's prompt:
- Agent name: `$1-agent`
- Task description (clear and specific — RAG uses this to find relevant knowledge)
- Instruction to call `rag_context` as Step 1 (per the initialization sequence in `_orchestrator.xml`)
- Task context path: `workspace/$2/context.md`
- Required output format with Status field (COMPLETE/BLOCKED/NEEDS_INPUT)

The agent calls `rag_context(agent="$1-agent", task_description="...")` itself.
This returns its definition + semantically matched knowledge chunks.
You do NOT need to pre-fetch or embed knowledge in the spawn prompt.

If the agent file doesn't exist, list available agents from the `agents/` directory.

## Task Context (if exists)
@workspace/$2/context.md
