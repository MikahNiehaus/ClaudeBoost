---
description: Generate a filled ticket handoff document for a human colleague - covers vacation coverage, tickets bouncing back after review, or passing work to another developer
argument-hint: [reason - e.g. "vacation", "QA failed", "passing to John"]
allowed-tools: Read, Bash, Glob, Grep
---

# /ticket-handoff - Ticket Handoff Generator

Generate a filled handoff document for **$ARGUMENTS** so a colleague can pick up the work
without hunting you down for context.

Handles three scenarios:
- **Vacation** - you're out, someone else needs to cover an in-progress ticket
- **Bounce-back** - ticket was completed but came back from QA or code review with issues
- **Peer handoff** - you're passing a ticket to another dev mid-sprint for any reason

---

## Phase 1: Determine scenario

**1a - Detect scenario from arguments.**

Parse `$ARGUMENTS`:
- Contains "vacation", "leave", "out", "PTO", "holiday" → **SCENARIO = vacation**
- Contains "QA", "failed", "bounce", "rework", "issues", "came back", "returned" → **SCENARIO = bounce-back**
- Contains a person's name or "John", "passing to", "handoff to" → **SCENARIO = peer**
- Blank or unrecognised → ask:
  ```
  What's the reason for the handoff?
  1. Vacation / leave - you'll be out, someone needs to cover
  2. Ticket came back - QA or review flagged issues, someone else is picking it up
  3. Passing to a colleague - any other reason
  ```
  Set scenario based on answer.

**1b - Ask for the receiving person's name (if not already in arguments).**

If a name isn't obvious from `$ARGUMENTS`, ask:
```
Who is this handoff for? (name or "team")
```

---

## Phase 2: Read ticket and workspace context

**2a - Find the active workspace.**

```bash
ls workspace/*/ticket.md 2>/dev/null | head -5
ls workspace/*/context.md 2>/dev/null | head -5
```

Read any matching `ticket.md` and `context.md`. Extract:
- Ticket ID and title
- Acceptance criteria
- Any open questions or blockers noted in context.md
- Decisions made (so the next person doesn't re-litigate them)

**2b - Read the current branch and recent commits.**

```bash
git rev-parse --abbrev-ref HEAD
git log --oneline -15
git diff main...HEAD --stat 2>/dev/null || git diff master...HEAD --stat 2>/dev/null || git diff HEAD~5 --stat
```

Extract:
- What files have been changed
- What the recent commit messages describe (summarize into "work completed")
- Whether the branch has unmerged commits

**2c - Check for open/uncommitted work.**

```bash
git status --short
```

If there are uncommitted changes, note them prominently. The next dev needs to know the
branch isn't clean.

**2d - For bounce-back scenario: find evidence of the failure.**

```bash
ls workspace/*/screenshots/ 2>/dev/null | head -10
ls workspace/*/bug\ fix/ 2>/dev/null | head -5
```

Note any screenshots or logs that document the failure. Reference their paths.

**2e - Detect how to run the project.**

Look for common run instructions in order:
1. README.md at repo root - check for "Getting Started", "Running locally", "Development"
2. package.json `scripts` section
3. Makefile targets

Read the first one found; extract the run/dev/test commands. Include them in the handoff.

---

## Phase 3: Ask for any gaps (one round)

After reading context, check what's still unknown. Ask ONE consolidated question for any
of these you couldn't determine:

- Specific blockers the colleague needs to know about
- For vacation: your return date and whether you're reachable at all
- For bounce-back: exact steps to reproduce the failure
- For peer: why the ticket is being handed off (context matters for the next person)

Example combined ask:
```
A few quick questions before I write the handoff:
1. Are there any blockers or open questions the next person needs to know about?
2. [vacation only] What are your dates out, and are you reachable for urgent questions?
3. [bounce-back only] What are the exact steps to reproduce the failure?
```

Do not ask about things you already found in context or git.

---

## Phase 4: Generate the handoff

Build the filled document. Pull every field from gathered context where possible; use
`[fill in]` for fields you can't determine.

### Writing rules
- **Concrete, not vague.** "PR #47 added the filter query to the endpoint" beats "some work
  was done on the API."
- **Prose sections are plain text.** No dashes inside paragraphs. No bold mid-sentence.
  Each paragraph is one continuous line.
- **No AI-voice.** No "seamless", "leverage", "robust", "comprehensive".
- **Short beats long.** The next dev is in a hurry. Put the most important things first.
- **No em-dashes.** Use commas or a new sentence.

---

## Phase 5: Output

Output the filled template as a raw markdown code block.

Format:
```
**Handoff: [ticket ID/title] → [recipient name or "team"]**

```markdown
[filled template]
```
```

**Self-check before outputting:**
1. Is the "status" field accurate to what you found in git?
2. Does the "work remaining" section tell the next person what to actually do next, not
   just a vague description?
3. Does the "how to run" section have real commands, not just "see the README"?
4. For vacation: are the dates and contact preference filled in?
5. For bounce-back: are the reproduction steps specific enough to follow?
6. Did you use `[fill in]` for every gap instead of guessing?

---

## Template

Include only the scenario section that matches SCENARIO. Do not include both.

```markdown
# Ticket Handoff: [Ticket ID] - [Ticket Title]

**Handoff from:** [your name]
**Handoff to:** [recipient name or "team"]
**Date:** [YYYY-MM-DD]
**Reason:** [Vacation: [dates] / QA bounce-back / Passing to colleague]
**Branch:** [branch name]
**Ticket link:** [Jira/Linear URL or "none"]

---

## Status at a Glance

**Ticket status:** [In Progress / Completed, needs rework / Blocked / Ready for review]

[One paragraph: where things stand right now, what works, and what doesn't. Plain prose.
No bullets. This is the first thing the next person reads - make it count.]

---

## Acceptance Criteria

- [criterion 1]
- [criterion 2]
- [criterion 3]

---

## Work Completed

[What has been done so far. Reference PR numbers, commit hashes, or branch names where
useful. Plain prose is fine; a short bullet list is also acceptable here.]

- [e.g. "PR #47 - added the filter endpoint to the API"]
- [e.g. "Wrote unit tests for the happy path in UserFilterService"]
- [e.g. "UI component wired up, but data is still mocked"]

**Key files changed:**
- [file path] - [one-line description of what changed]
- [file path] - [one-line description]

---

## Work Remaining

[What still needs to be done. Be specific. The next person should be able to read this and
know exactly what to work on first. Plain prose or a short checklist.]

- [ ] [specific next task]
- [ ] [specific next task]
- [ ] [specific next task]

---

## How to Run and Test

```bash
# Install / set up (if needed)
[install command]

# Start the dev server
[dev command]

# Run the relevant tests
[test command]
```

[Any additional notes about running this specific feature, e.g. which env vars to set or
which seed data to load.]

---

## Blockers and Risks

[List anything that is currently blocking progress or that the next person should be careful
about. If nothing is blocked, write "None currently." Plain prose or short bullets.]

- [blocker or risk - and suggested way around it]
- [or "None currently"]

---

## Decisions Made

[Decisions about approach, architecture, or product scope that were made during this ticket.
This prevents the next person from re-litigating them. If no decisions were made, delete
this section.]

- [Decision: e.g. "Chose to use optimistic updates because the backend response is slow"]
- [Decision: e.g. "Scoped out dark mode for this ticket, tracked in [ticket]"]

---

## [BOUNCE-BACK ONLY] What Failed

**Failure summary:** [One sentence: what QA or review said was wrong.]

**Steps to reproduce:**
1. [exact step]
2. [exact step]
3. [exact step]

**Expected:** [what should have happened]
**Actual:** [what actually happened]
**Evidence:** [link to screenshot, log, or workspace/[ticket]/screenshots/]

**Severity:** [Blocker / Major / Minor]

**What was tried:** [Any fix attempts that didn't work, so the next dev doesn't repeat them.
If nothing was tried, write "no fix attempted."]

```
