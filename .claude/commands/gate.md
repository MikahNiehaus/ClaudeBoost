---
description: Compliance gate check — run mandatory pre-task compliance verification before proceeding
---

# Compliance Gate Check

Run this mandatory compliance gate before proceeding with any task.

## Phase 0: Load RAG Context (MANDATORY FIRST ACTION)

Call `rag_context(agent="workflow-agent", task_description="compliance gate check before proceeding", max_tokens=3000)`.

This loads relevant knowledge before any work begins. If `rag_context` fails: stop and tell the user "RAG is not connected. Run /boost before using this skill."

---

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
- If NO: Run Planning Checklist (ALL 9 domains) before proceeding
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

## Final Step: Evidence Verification

After all gates have produced their PASS/FAIL results but before printing the OVERALL verdict line, spawn a single `evaluator-agent` with this prompt:

"Read the GATE CHECK RESULTS above. Verify:
1. Each PASS result cites what was actually checked — not just 'PASS' alone (e.g., 'Gate 2: PASS — workspace/my-task/context.md exists' is evidence; 'Gate 2: PASS' alone is not).
2. All 5 gates are present in the results — no gate was silently skipped.
3. The OVERALL verdict is consistent with individual gate results: OVERALL PASS is only valid if all 5 gates show PASS.

Output a simple table:
| Gate | Evidence cited? | Consistent with OVERALL? | Verdict (CONFIRMED/NEEDS_EVIDENCE) |

Flag any NEEDS_EVIDENCE items. Under 500 tokens."

Surface any NEEDS_EVIDENCE items alongside the gate results before the user acts on the OVERALL verdict.

## When to Run

- At start of EVERY new task
- Before spawning ANY agent
- Before ANY code modification
- When resuming after context compaction
