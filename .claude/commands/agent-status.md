---
argument-hint: <task-id>
description: Display task status, agent contributions, and next steps
allowed-tools: Read, Glob
---

# Task Status: $ARGUMENTS

## Instructions

Display the current status of task `$1` by reading:

1. **Task Context**: `workspace/$1/context.md`
   - Current status (ACTIVE/BLOCKED/COMPLETE)
   - Agent contributions and handoffs
   - Key findings
   - Next steps

2. **Task Artifacts**: List contents of `workspace/$1/` directory
   - mockups/ - Input designs
   - outputs/ - Generated artifacts
   - snapshots/ - Progress screenshots

## Summary Format

```
Task: $1
Status: [status from context.md]
Last Agent: [most recent agent that contributed]
Next Steps: [from context.md]
Blockers: [if any]
Artifacts: [count of files in outputs/]
```

## Context File
@workspace/$1/context.md
