---
description: Preview critical state before context compaction
allowed-tools: Read, Glob
---

# Pre-Compaction State Review

## Instructions

Before context compaction occurs, review and summarize all critical state that must survive compaction.

## Critical State to Preserve

### 1. Active Tasks
List `workspace/` folders and read each `context.md` to find tasks with status ACTIVE or BLOCKED:

| Task ID | Description | Status | Workspace |
|---------|-------------|--------|-----------|

### 2. Task Context Files
For each active task, read `workspace/[task-id]/context.md` and extract:
- Current status
- Last contributing agent
- Key findings (bullet points)
- Next steps
- Blocking issues

### 3. Agent Handoff State
Document any in-progress agent collaborations:
- Which agent was last active
- What it was working on
- What the next agent needs to know

### 4. Pending User Decisions
List any NEEDS_INPUT items awaiting user response

## Compaction Summary Template

```markdown
# Post-Compaction Resume State

## Active Tasks
- [task-id]: [status] - [one-line summary]

## Immediate Next Steps
1. [First thing to do]
2. [Second thing to do]

## Key Context
- [Critical fact 1]
- [Critical fact 2]

## Blocking Issues
- [Blocker requiring resolution]

## Files to Re-Read
- workspace/[task-id]/context.md
- [other critical files]
```

## Files to Review

Glob for all context.md files in workspace/*/ and read each one to find active tasks.
