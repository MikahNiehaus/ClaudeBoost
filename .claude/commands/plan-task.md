---
argument-hint: <task-id> <description>
description: Execute planning phase for a task (without execution)
---

# Planning Phase: $ARGUMENTS

## Phase 0: Load RAG Context (MANDATORY FIRST ACTION)

Call `POST http://127.0.0.1:8612/context with agent="workflow-agent", task_description="implementation planning for current task", max_tokens=3000`.

This loads relevant knowledge before any work begins. If `POST http://127.0.0.1:8612/context` fails: stop and tell the user "RAG is not connected. Run /boost before using this skill."

---

## Instructions

Execute the PLANNING PHASE ONLY for this task. Do NOT proceed to execution.

**Task ID**: $1
**Description**: $2 (or derive from context if not provided)

### Step 1: Create Task Workspace

1. Create `workspace/$1/` folder if it doesn't exist
2. Initialize `context.md` with the Plan section template
3. Set State to PLANNING

### Step 2: Run Planning Checklist

For EACH domain, READ the knowledge base and evaluate whether this task triggers the criteria:

| Domain | Knowledge Base | Evaluate Against |
|--------|---------------|------------------|
| Testing | `knowledge/testing.xml` | Does task involve code changes, bug fixes, behavior modifications? |
| Documentation | `knowledge/documentation.xml` | Does task add/change APIs, configs, user features? |
| Security | `knowledge/security.xml` | Does task involve auth, user input, sensitive data, DB, HTTP? |
| Architecture | `knowledge/architecture.xml` | Does task add components, change boundaries, require design? |
| Performance | `knowledge/performance.xml` | Does task involve loops, DB queries, caching, hot paths? |
| Review | `knowledge/pr-review.xml` | Will task produce code ready for merge? |
| Clarity | `knowledge/ticket-understanding.xml` | Is the request vague or missing acceptance criteria? |
| Browser Testing | `knowledge/playwright.xml` | Does task require interactive UI or end-to-end browser testing? |
| Observability | `knowledge/observability.xml` | Does task involve service methods, error handling, external calls, or data mutations? |

### Step 3: Generate Subtasks

For each domain marked "Yes":
1. Create a subtask with:
   - **Objective**: What this subtask accomplishes
   - **Output Format**: Expected deliverable
   - **Boundaries**: In scope / Out of scope
   - **Success Criteria**: How to verify completion
   - **Dependencies**: What must be done first

2. Apply Three Principles:
   - **Solvability**: Each subtask achievable by single agent
   - **Completeness**: All subtasks together address the request
   - **Non-Redundancy**: No overlap between subtasks

### Step 4: Determine Execution Strategy

- **Sequential**: If subtasks have dependencies
- **Parallel**: If subtasks are independent
- **Hybrid**: Mix of both

### Step 5: Update context.md

Populate the Plan section with:
- Planning Checklist Results table
- Subtasks table
- Execution Strategy
- Approval Status (set to Pending)

### Step 5.5: Anti-Hallucination Verification

Before presenting the plan for review, run `/audit` on the plan content in `context.md` with:
- Input type: `process`
- Stated goal: the task description (`$2` or the description from `context.md`)
- Dimensions: P1 Correctness, P5 Completeness, P6 Completion Coverage, O3 Goal Alignment

If verdict is VERIFIED or PARTIALLY VERIFIED: present the plan as normal.
If verdict is UNVERIFIED: surface the specific gaps identified by the audit alongside the plan so the user can see what's missing before approving.

### Step 6: Present Plan for Review

Display the completed plan and ask:
"Plan ready for task $1. Approve to proceed, or request modifications?"

## Output Format

Present the plan summary:
```
## Plan Summary: $1

### Checklist Results
[Table of domains and whether needed]

### Subtasks
[Numbered list with agents and dependencies]

### Execution Strategy
[Pattern and rationale]

Ready to execute? Say "approve" or request changes.
```

## Notes

- This command generates the plan ONLY
- Execution begins only after explicit approval
- Use this to review plans before committing to execution
