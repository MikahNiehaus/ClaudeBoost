# Compliance Gate Check

Run this mandatory compliance gate before proceeding with any task.

## Gate Execution Sequence

Execute each gate in order. If ANY gate fails, HALT and fix before proceeding.

### Gate 1: Task Classification
- Is this a read-only question? If YES, skip to direct answer.
- Does this require action/code/agents? If YES, continue.

### Gate 2: Workspace Verification
Check: Does `workspace/[task-id]/context.md` exist?
- If NO: Create task workspace NOW before proceeding
- If YES: READ context.md to resume context

### Gate 3: Planning Verification
Check: Is the "Plan" section in context.md populated?
- If NO: Run Planning Checklist (ALL 7 domains) before proceeding
- If YES: Continue

### Gate 4: TodoWrite Verification
Check: Does task have 2+ steps?
- If YES: Verify TodoWrite exists. Create if missing.
- If NO: Continue

### Gate 5: Pre-Action Validation
Before ANY agent spawn or code edit:
- [ ] Correct agent type selected?
- [ ] Model correctly assigned (Opus for architect/ticket-analyst/reviewer)?
- [ ] Agent prompt uses READ pattern?
- [ ] Context.md will be updated after?

## Output Format

```
GATE CHECK RESULTS
==================
Gate 1 (Classification): [PASS/FAIL] - [reason]
Gate 2 (Workspace):      [PASS/FAIL] - [reason]
Gate 3 (Planning):       [PASS/FAIL] - [reason]
Gate 4 (TodoWrite):      [PASS/FAIL] - [reason]
Gate 5 (Pre-Action):     [PASS/FAIL] - [reason]

OVERALL: [ALL GATES PASSED / BLOCKED AT GATE N]

[If blocked: Action required before proceeding]
```

## When to Run

- At start of EVERY new task
- Before spawning ANY agent
- Before ANY code modification
- When resuming after context compaction
