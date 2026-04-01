---
argument-hint: [task-id]
description: Verify completion criteria status for a task
allowed-tools: Read, Bash, Glob
---

# Check Completion Status: $ARGUMENTS

## Instructions

1. **Find task context**:
   - If task ID provided: `workspace/$1/context.md`
   - If not provided: List `workspace/` folders and find most recently modified ACTIVE task

2. **Read context.md** and extract:
   - Execution Mode (NORMAL/PERSISTENT)
   - Completion Criteria table
   - Progress Tracker

3. **For each completion criterion**:
   - Run the verification command
   - Compare result against threshold
   - Update status: pending → met or pending → failed

4. **Generate report**:
   - Show each criterion with current value vs threshold
   - Calculate overall completion percentage
   - Estimate remaining work

5. **Update context.md** with:
   - Current criterion status
   - Updated Progress Tracker
   - Checkpoint timestamp

## Task Context
@workspace/$1/context.md

## Output Format

```markdown
## Completion Status Report

### Task: [task-id]
### Mode: [NORMAL/PERSISTENT]
### Checked At: [timestamp]

### Criteria Status

| # | Criterion | Command | Expected | Actual | Status |
|---|-----------|---------|----------|--------|--------|
| 1 | [name] | [cmd] | [threshold] | [value] | [MET/NOT MET] |
| 2 | [name] | [cmd] | [threshold] | [value] | [MET/NOT MET] |

### Progress

- **Criteria Met**: X / Y
- **Overall Status**: [COMPLETE / IN PROGRESS / BLOCKED]

### Remaining Work

- [Criterion 1]: [what's needed to meet it]
- [Criterion 2]: [what's needed to meet it]

### Recommendation

[If PERSISTENT mode and criteria not met: Continue automatically]
[If NORMAL mode: Summarize status and await user decision]
```

## Common Verification Commands

```bash
# Count files by extension
find . -name "*.ext" -not -path "./node_modules/*" | wc -l

# Check TypeScript compilation
npx tsc --noEmit; echo "Exit code: $?"

# Check test coverage
npm run coverage -- --json | jq '.total.lines.pct'

# Run tests
npm test; echo "Exit code: $?"

# Check lint errors
npm run lint 2>&1 | grep -c "error" || echo "0"
```
