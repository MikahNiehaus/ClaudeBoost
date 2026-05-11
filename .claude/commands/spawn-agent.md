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

**Before writing the spawn prompt**, run `pwd` to get the current working directory.
This is the `project_path` — embed it as a literal string in the spawn prompt so the
agent can load project-specific codebase context (Tier 4 RAG).

Include in the agent's prompt:
- Agent name: `$1-agent`
- Task description (clear and specific — RAG uses this to find relevant knowledge)
- Instruction to call `rag_context` as Step 1 (per the initialization sequence in `_orchestrator.xml`)
- `project_path`: the literal cwd path from `pwd` (e.g. `"C:/Development/PantryEasy"`)
- Task context path: `workspace/$2/context.md`
- Required output format with Status field (COMPLETE/BLOCKED/NEEDS_INPUT)

The agent calls `rag_context(agent="$1-agent", task_description="...", project_path="<cwd>", weight="...")` itself.
This returns its definition + global knowledge chunks + project codebase results (if indexed).
You do NOT need to pre-fetch or embed knowledge in the spawn prompt.

## Weight Routing

Pass the correct `weight` parameter to `rag_context` based on agent type:
- **lightweight**: explore, research, docs, estimator, rag-indexing, research-rag (skips guardrails)
- **standard**: workflow, refactor, debug, test, ui, database, devops, observability, standards-validator, architect, ticket-analyst, browser, compliance, evaluator
- **full**: reviewer, security, performance (full guardrails + verify gate)

## Hook Enforcement

A `PreToolUse` hook on `Task` fires before every agent spawn to verify:
1. The agent prompt includes `rag_context` as Step 1
2. Workspace reference is included if one exists
3. Gas Town (`gt sling`) is considered for cross-session work

This hook is a nudge, not a gate — it always exits 0 and cannot block the spawn. If your spawn prompt is missing `rag_context` instructions, the hook will remind you via stderr before the spawn proceeds.

If the agent file doesn't exist, list available agents from the `agents/` directory.

## Task Context (if exists)
@workspace/$2/context.md
