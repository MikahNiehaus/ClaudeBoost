---
argument-hint: <agent-name> <task-id>
description: Spawn an agent with full compliance validation and context
allowed-tools: Read, Glob, Task
---

# Agent Spawn Request: $ARGUMENTS

## Validation Checklist

Before spawning, verify:
1. Agent definition exists at `agents/$1-agent.md`
2. Task workspace will be created at `workspace/$2/`
3. Relevant knowledge base identified

## Instructions

Read the agent definition file `agents/$1-agent.md` and identify the required knowledge base from its "Knowledge Base" section.

Then spawn the agent using the Task tool with:
- Full agent definition (Role, Goal, Backstory, Capabilities)
- Full knowledge base content
- Task context path: `workspace/$2/context.md`
- Clear task instructions
- Required output format with Status field (COMPLETE/BLOCKED/NEEDS_INPUT)

If the agent file doesn't exist, list available agents from the `agents/` directory.

## Agent Definition
@agents/$1-agent.md

## Task Context (if exists)
@workspace/$2/context.md
