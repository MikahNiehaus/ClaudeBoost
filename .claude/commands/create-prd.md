---
description: Create a PRD and task checklist in workspace — Phase 1 generates prd.md, Phase 2 generates tasks.md
argument-hint: "<task-id> [feature description]"
allowed-tools: Read, Write, Bash, Glob, Grep, mcp__rag-server__rag_context, mcp__rag-server__rag_search
---

# /create-prd

Two-phase command: generate a Product Requirements Document, then break it into an implementation task checklist — both saved to the ClaudeBoost workspace.

## Phase 0: Load Context

Call `rag_context(agent="architect-agent", task_description="create PRD for $ARGUMENTS", max_tokens=4000)` as your FIRST action. This loads organization, architecture, and workflow knowledge.

Feature or task: **$ARGUMENTS**

---

## When to Use

Use this command when:
- A feature affects more than 10 files
- You are building a new subsystem or major component
- Requirements are unclear or need stakeholder alignment
- The work will span multiple sessions

Skip for: single-file changes, bug fixes with clear scope, refactoring with defined boundaries.

---

## Phase 1: Generate PRD

### Step 1: Check Project Context

Before asking questions:
1. Read `CLAUDE.md` in the current project for tech stack, architecture patterns, and existing conventions
2. Scan the codebase for related existing code, database schemas, and API patterns
3. Check `workspace/` for any existing task folders that overlap with this feature

### Step 2: Ask Clarifying Questions

Ask only the questions needed to write a useful PRD. Adapt based on the feature type. Provide numbered options where possible for easy responses.

Core areas to cover:
1. **Problem and goal** — what user problem does this solve? What is the primary goal?
2. **Target users** — end users, admins, both, or other?
3. **Core functionality** — must-haves vs nice-to-haves
4. **Acceptance criteria** — how will we know this is successfully implemented?
5. **Out of scope** — what should this explicitly NOT do?
6. **Integration points** — existing features, third-party services, data dependencies
7. **Security and data** — sensitive data involved? Auth required? Compliance requirements?

Do not ask about implementation approach — that is for the developer and agents to determine.

### Step 3: Determine Task ID

If the user provided a ticket ID (e.g. `JIRA-123`, `GH-456`), use it as the task ID. Otherwise, generate one: `YYYY-MM-DD-[feature-slug]`.

Create the workspace folder:
```
workspace/[task-id]/
```

### Step 4: Generate PRD

Write `workspace/[task-id]/prd.md` with these sections:

```markdown
# PRD: [Feature Name]

**Task ID**: [task-id]
**Date**: [YYYY-MM-DD]
**Status**: Draft

---

## Introduction

[What this feature is, what problem it solves, primary goal in 2-3 sentences.]

## Goals

1. [Specific, measurable objective]
2. [...]

## User Stories

**US-001**: As a [user type], I want to [action] so that [benefit].
**US-002**: ...

## Functional Requirements

### [Area]
FR-001: The system must [requirement]
FR-002: ...

## Non-Goals

- [What this feature will NOT include — be explicit]
- [Deferred items]

## Technical Considerations

### Tech Stack
[Relevant existing stack elements to integrate with]

### Architecture Notes
[Key patterns, file organization, dependencies to add]

### Security Requirements
[Input validation, auth, data privacy requirements]

## Design Considerations

[UI/UX requirements, user flows, accessibility notes — omit if backend-only]

## Success Metrics

- [How success will be measured — technical and business metrics]

## Open Questions

1. [Any remaining unknowns that need resolution before or during implementation]
```

Validate the PRD against these before saving:
- [ ] Security requirements covered (input validation, parameterized queries, auth)
- [ ] Acceptance criteria are testable
- [ ] Out-of-scope items explicitly listed
- [ ] Tech stack references match the actual project

### Step 5: Save and Verify

Save the file. Before asking the user to proceed, run `/audit workspace/[task-id]/prd.md` with:
- Input type: `document`
- Dimensions: D1 Factual Accuracy, D3 Completeness & Gaps, D2 Internal Consistency

If verdict is VERIFIED or PARTIALLY VERIFIED: inform the user the PRD is ready.
If verdict is UNVERIFIED: surface the specific gaps identified by the audit alongside the PRD so the user can review before proceeding to Phase 2.

Inform the user:
```
PRD saved to workspace/[task-id]/prd.md

Ready to generate the implementation task list? Reply "go" to proceed to Phase 2, or review the PRD first.
```

**Do not start implementing.** Wait for user confirmation before Phase 2.

---

## Phase 2: Generate Task List

Run this phase after the user confirms the PRD is ready (responds with "go" or equivalent).

### Step 1: Read and Analyze the PRD

Read `workspace/[task-id]/prd.md` fully. Identify:
- All functional requirements
- Integration points and dependencies
- Security and testing requirements
- Files that will need to be created or modified

### Step 2: Assess Current Codebase

Scan relevant parts of the project:
- Existing directory structure and naming patterns
- Similar features already implemented
- Reusable utilities, components, or services
- Test file patterns and coverage approach

Summarize findings briefly before generating tasks.

### Step 3: Generate Parent Tasks

Create 4-7 high-level tasks representing logical phases of implementation. Order by dependency (typically: data/schema → backend logic → API layer → frontend → tests → docs).

Present to the user:
```markdown
## Implementation Phases

- [ ] 1.0 [Phase name]
- [ ] 2.0 [Phase name]
- [ ] ...

Ready to break these into detailed sub-tasks? Reply "go" to proceed.
```

Wait for confirmation before generating sub-tasks.

### Step 4: Generate Detailed Sub-Tasks

Break each parent task into 3-8 sub-tasks. Each sub-task should be:
- **Atomic**: Completable in one session, one commit
- **Specific**: Clear action verb + what + any key constraints
- **Testable**: Has an implicit or explicit success criterion

Sub-task naming: use present-tense verbs — "Create", "Implement", "Add", "Update", "Test".

Include agent assignments for non-trivial sub-tasks. Use the ClaudeBoost agent roster:

| Work type | Agent |
|-----------|-------|
| Architecture decisions | architect-agent |
| Tests and TDD | test-agent |
| Security implementation | security-agent |
| UI components | ui-agent |
| Database schema/migrations | database-agent |
| Documentation | docs-agent |
| Performance optimization | performance-agent |

### Step 5: Add Implementation Notes

After the task list, include:

```markdown
## Implementation Notes

### Testing
[Coverage targets, test file naming conventions, what must be tested]

### Security Checklist
- [ ] All user inputs validated
- [ ] Queries parameterized (never string concatenation)
- [ ] Environment variables for secrets
- [ ] Auth/authz checked on endpoints

### Common Pitfalls
[Project-specific or domain-specific things to avoid]
```

### Step 6: Save tasks.md

Write `workspace/[task-id]/tasks.md`:

```markdown
# Tasks: [Feature Name]

**PRD**: [prd.md](./prd.md)
**Task ID**: [task-id]
**Date**: [YYYY-MM-DD]

---

## Task List

- [ ] 1.0 [Parent task]
  - [ ] 1.1 [Sub-task] — [agent if applicable]
  - [ ] 1.2 [Sub-task]
- [ ] 2.0 [Parent task]
  - [ ] 2.1 [Sub-task]
  ...

## Relevant Files

| File | Action | Notes |
|------|--------|-------|
| [path] | Create/Modify | [why] |

[Implementation Notes section]
```

### Step 6.5: Verify tasks.md

Before informing the user, run `/audit workspace/[task-id]/tasks.md` with:
- Input type: `process`
- Stated goal: the Functional Requirements from `workspace/[task-id]/prd.md`
- Dimensions: P1 Correctness, P5 Completeness, P6 Completion Coverage

If verdict is VERIFIED or PARTIALLY VERIFIED: inform the user as normal.
If verdict is UNVERIFIED: surface the specific gaps identified by the audit alongside the task list so the user can see what's missing before starting implementation.

Inform the user:
```
Task list saved to workspace/[task-id]/tasks.md

To start implementation, say "start task 1.1" or spawn the relevant agent.
Each task should be completed, tested, and committed before moving to the next.
```
