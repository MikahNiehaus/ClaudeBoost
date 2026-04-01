---
argument-hint: <task-id>
description: Validate task folder structure and completeness
allowed-tools: Read, Glob
---

# Task Validation: $ARGUMENTS

## Instructions

Validate the task workspace at `workspace/$1/` for completeness and correctness.

## Validation Checklist

### 1. Structure Check
Verify these directories/files exist:
- [ ] `workspace/$1/` - Task root folder
- [ ] `workspace/$1/context.md` - Task context file
- [ ] `workspace/$1/mockups/` - Input designs (optional)
- [ ] `workspace/$1/outputs/` - Generated artifacts (optional)
- [ ] `workspace/$1/snapshots/` - Progress screenshots (optional)

### 2. Context.md Validation
Check that context.md contains required sections:
- [ ] **Task ID** and description
- [ ] **Status** (ACTIVE/BLOCKED/COMPLETE)
- [ ] **Created** timestamp
- [ ] **Agent Contributions** section
- [ ] **Key Findings** section
- [ ] **Next Steps** section

### 3. Agent Output Compliance
For each agent contribution in context.md:
- [ ] Status field present (COMPLETE/BLOCKED/NEEDS_INPUT)
- [ ] If BLOCKED, blocker is documented
- [ ] Handoff notes present for sequential agents
- [ ] Context Acknowledgment present (for agents after first)

### 4. Content Validation (CRITICAL)
Verify context.md sections are actually populated (not just headers):
- [ ] **Status.State** has value (ACTIVE/BLOCKED/COMPLETE) - not empty
- [ ] **Quick Resume** is current (mentions last agent that contributed)
- [ ] **Next Steps** has at least one item defined
- [ ] **Key Files** lists at least one relevant file
- [ ] If BLOCKED: **Blocked Resolution** section is filled out

### 5. Context Health Check
- [ ] File size < 30 KB (check with file stats)
- [ ] Agent Contributions < 10 (if more, suggest archiving)
- [ ] Quick Resume matches last Agent Contribution timestamp

## Output Format

```
Task: $1
─────────────────────────────
Structure:      [PASS/FAIL] - [details]
Context.md:     [PASS/FAIL] - [missing sections]
Content:        [PASS/FAIL] - [empty/stale fields]
Agent Outputs:  [PASS/FAIL] - [compliance issues]
Context Health: [PASS/WARN/FAIL] - [size/staleness issues]
─────────────────────────────
Overall:        [VALID/INVALID]
Issues:         [list of issues to fix]
Warnings:       [non-blocking concerns]
```

## Task Files
@workspace/$1/context.md
