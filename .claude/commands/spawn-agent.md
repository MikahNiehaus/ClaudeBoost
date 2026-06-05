---
argument-hint: <agent-name> <task-id>
description: Spawn an agent with RAG knowledge loading
allowed-tools: Read, Glob, Task
---

# Agent Spawn Request: $ARGUMENTS

## Phase 0: Load RAG Context (MANDATORY FIRST ACTION)

**0a — Collect paths (before loading context):**

1. **project_path** — Check `$CLAUDEBOOST_HOME/state/active-workspace.json` for `project_path`. Fall back to current working directory if not found.
2. **workspace_path** — Check `$CLAUDEBOOST_HOME/state/active-workspace.json` for `workspace_path`. Fall back to `$CLAUDEBOOST_HOME/workspace/$2/` if `$2` resolves to an existing directory. Omit if no workspace exists for this task.

Call `POST http://127.0.0.1:8612/context with agent="workflow-agent", task_description="agent spawn with RAG knowledge loading: $ARGUMENTS", project_path="<PROJECT_PATH>", workspace_path="<WORKSPACE_PATH>", max_tokens=3000`.

Omit `workspace_path` from the context call if no workspace was found.

This loads relevant knowledge before any work begins. If `POST http://127.0.0.1:8612/context` fails: stop and tell the user "RAG is not connected. Run /rag before using this skill."

---

## Validation Checklist

Before spawning, verify:
1. Agent definition exists at `agents/$1-agent.xml`
2. Task workspace exists or will be created at `workspace/$2/`

## Instructions

Spawn the agent using the Task tool. The agent will load its own knowledge via RAG.

The paths collected in Phase 0 flow directly into the spawn prompt.

Include in the agent's prompt:
- Agent name: `$1-agent`
- Task description (clear and specific — RAG uses this to find relevant knowledge)
- Instruction to call `POST http://127.0.0.1:8612/context` as Step 1
- `project_path`: the literal project path string (e.g. `"/home/user/projects/my-app"` on Linux/Mac, `"C:/Development/MyApp"` on Windows)
- `workspace_path`: the literal workspace path when one exists (enables Tier 3c task research)
- Task context path: `workspace/$2/context.md`
- Required output format with Status field (COMPLETE/BLOCKED/NEEDS_INPUT)

The agent's Step 1 context call:
```json
{
  "agent": "$1-agent",
  "task_description": "...",
  "project_path": "<cwd>",
  "workspace_path": "<workspace-abs-path>"
}
```
This returns: agent definition + guardrails + general knowledge + stack-specific practices + task research (Tier 3c) + project codebase (Tier 4).
You do NOT need to pre-fetch or embed knowledge in the spawn prompt.

## Weight Routing

Pass the correct `weight` parameter to `POST http://127.0.0.1:8612/context` based on agent type:
- **lightweight**: explore, research, docs, estimator, rag-indexing, research-rag (skips guardrails)
- **standard**: workflow, refactor, debug, test, ui, database, devops, observability, standards-validator, architect, ticket-analyst, browser, compliance, evaluator
- **full**: reviewer, security, performance (full guardrails + verify gate)

## Hook Enforcement

A `PreToolUse` hook on `Task` fires before every agent spawn to verify:
1. The agent prompt includes `POST http://127.0.0.1:8612/context` as Step 1
2. Workspace reference is included if one exists

This hook is a hard gate — spawns without `POST http://127.0.0.1:8612/context` in the prompt are blocked (exit 2). Include `POST http://127.0.0.1:8612/context` as the agent's first action or the spawn will not proceed.

If the agent file doesn't exist, list available agents from the `agents/` directory.

## Task Context (if exists)
@workspace/$2/context.md
