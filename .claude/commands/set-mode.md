---
argument-hint: <normal|persistent> [task-id]
description: Set execution mode for a task (NORMAL or PERSISTENT)
allowed-tools: Read, Edit, Glob
---

# Set Execution Mode: $ARGUMENTS

## Instructions

1. **Parse arguments**:
   - Mode: `$1` (must be "normal" or "persistent")
   - Task ID: `$2` (optional - if not provided, use current active task)

2. **Validate mode**:
   - "normal" or "persistent" are valid
   - Any other value should be rejected with helpful message

3. **Find task context**:
   - If task ID provided: `workspace/$2/context.md`
   - If not provided: List `workspace/` folders and find most recently modified ACTIVE task

4. **Update context.md**:
   - Set Mode in Execution Mode section
   - Set "Set By" to "User request"
   - Set "Set At" to current timestamp

5. **For PERSISTENT mode**:
   - Check if Completion Criteria are defined
   - If NOT defined, prompt user:
     "PERSISTENT mode requires completion criteria. Please specify:
     - What does 'done' look like?
     - How can we verify completion (command/metric)?"
   - Add criteria to the Completion Criteria table

6. **Confirm change**:
   - Report the mode change
   - If PERSISTENT: Show the completion criteria

## Mode Definitions

| Mode | Behavior |
|------|----------|
| NORMAL | Stop after each logical step, report to user |
| PERSISTENT | Continue automatically until all completion criteria are met |

## Task Context
@workspace/$2/context.md

## Example Updates

### Setting NORMAL mode:
```markdown
## Execution Mode
- **Mode**: NORMAL
- **Set By**: User request
- **Set At**: 2025-12-11 15:30
```

### Setting PERSISTENT mode:
```markdown
## Execution Mode
- **Mode**: PERSISTENT
- **Set By**: User request
- **Set At**: 2025-12-11 15:30

### Completion Criteria
| # | Criterion | Verification Command | Threshold | Status |
|---|-----------|---------------------|-----------|--------|
| 1 | [user-provided] | [user-provided] | [user-provided] | pending |
```
