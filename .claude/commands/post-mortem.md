---
description: Generate a filled post-mortem document from workspace and git context after an incident, failed deploy, or production issue
argument-hint: [brief description of what went wrong - e.g. "deploy broke auth on prod"]
allowed-tools: Read, Bash, Glob, Grep
---

# /post-mortem - Post-Mortem Generator

Generate a filled, blameless post-mortem for **$ARGUMENTS** (if blank, you'll ask for a
one-line incident description).

---

## Phase 1: Gather context

**1a - Resolve incident description.**

If `$ARGUMENTS` is non-empty, use it as the incident description.
If blank, ask:
```
What happened? Give a one-line summary (e.g. "login broke after 3pm deploy, affected 40% of users for 2 hours").
```

**1b - Read workspace context.**

Check for an active workspace that might contain ticket or context files:
```bash
ls workspace/*/ticket.md 2>/dev/null | head -5
ls workspace/*/context.md 2>/dev/null | head -5
```

Read any matching `ticket.md` and `context.md`. These provide ticket background, acceptance
criteria, and decision notes that belong in the post-mortem.

**1c - Read git history.**

```bash
git rev-parse --abbrev-ref HEAD
git log --oneline -20
git log --oneline --since="2 days ago"
```

Identify:
- The most recent deploy commit(s) - look for merge commits, version bumps, or commits
  referencing the feature in the incident description
- Who made the changes (author names)
- When the change landed

**1d - Find any error evidence in workspace.**

```bash
ls workspace/*/screenshots/ 2>/dev/null | head -10
ls workspace/*/logs/ 2>/dev/null | head -5
ls workspace/*/bug\ fix/ 2>/dev/null | head -5
```

Note any evidence files found - reference them in the Supporting Information section.

**1e - Detect project type and service name.**

```bash
git rev-parse --show-toplevel
git remote get-url origin 2>/dev/null || echo "no remote"
```

Extract the repo/project name from the git remote URL or directory name. Use it as the
affected service name.

---

## Phase 2: Determine severity

Based on the incident description, classify severity:

- **SEV-1** - complete outage, all users affected, revenue impact, data loss
- **SEV-2** - major degradation, significant user segment affected, core feature broken
- **SEV-3** - partial or minor degradation, workaround exists, limited user impact

If you cannot determine severity from context, default to SEV-2 and add a note.

---

## Phase 3: Generate the post-mortem

Build a filled post-mortem using this structure. Pull every field from gathered context
where possible; use `[unknown - fill in]` for fields you cannot determine.

### Writing rules (CRITICAL)
- **Blameless language always.** Never write "X made a mistake" or "Y caused the outage."
  Write "the deployment introduced a regression" or "the config change triggered a failure."
- **Prose sections are plain text.** No bullet lists, no bold inside paragraphs, no dashes.
  Each paragraph is one continuous line, no manual line breaks.
- **Action items must have an owner and due date.** If unknown, write `[assign owner]` and
  `[set due date]` so the reader knows to fill them in.
- **Timeline entries use UTC or local time consistently.** Note which.
- **No em-dashes.** Use commas or a new sentence.
- **No AI-voice words.** No "seamless", "robust", "leverage", "utilize", "facilitate".

---

## Phase 4: Output

Output the filled template as a raw markdown code block.

Format:
```
**Post-Mortem: [service name] - [incident description]**

```markdown
[filled template]
```
```

The title is outside the code block. The full template is inside triple backticks so it
pastes cleanly into any doc system.

**Self-check before outputting:**
1. Does any prose paragraph contain a dash? Replace with a comma or period.
2. Does any action item lack an owner? Mark `[assign owner]`.
3. Is the root cause section blameless? Re-read it. Remove any personal attribution.
4. Is the timeline in chronological order? Sort it.
5. Did you use `[unknown - fill in]` for every gap? Good - don't invent data.

---

## Template

```markdown
# Post-Mortem: [service/feature name]

**Date:** [YYYY-MM-DD]
**Authors:** [names of people involved in writing this]
**Severity:** [SEV-1 / SEV-2 / SEV-3]
**Status:** [Draft / Under Review / Complete]
**Ticket:** [Jira/Linear ticket URL, or "none"]

---

## Summary

[One to two sentences: what happened, how long it lasted, total impact. Plain prose, no bullets.]

---

## Impact

| Metric | Value |
|--------|-------|
| Duration | [e.g. 2h 14m] |
| Users affected | [e.g. ~8,000 / 40% of active users / all users] |
| Features affected | [list the broken features] |
| Error rate | [e.g. 503 rate peaked at 62%] |
| Revenue / SLA impact | [if known, otherwise "under investigation"] |

---

## Timeline

All times [UTC / local timezone]:

| Time | Event |
|------|-------|
| [time] | [Contributing factor began, e.g. "PR #123 merged to main"] |
| [time] | [Deployment to production completed] |
| [time] | [First sign of failure, e.g. "error rate began climbing"] |
| [time] | [Issue detected, e.g. "on-call alerted by PagerDuty / user report received"] |
| [time] | [Response began - engineer started investigation] |
| [time] | [Root cause identified] |
| [time] | [Mitigation applied, e.g. "rollback deployed"] |
| [time] | [Service fully restored] |
| [time] | [Incident declared resolved] |

---

## Root Cause

[Describe what failed technically and why. Focus on the system, process, or configuration
that created the conditions for failure. Use "the system", "the config", "the code path",
"the deployment" as subjects, not people's names. Plain prose, one paragraph.]

**Trigger:** [The specific action or event that activated the failure, e.g. "deployment of
commit abc123 which changed the session token expiry logic."]

**Underlying cause:** [The deeper reason this could happen at all, e.g. "no integration test
covered the token expiry path under the new config format."]

---

## Detection

[How the issue was discovered: automated alert, user report, manual check during on-call,
etc. Include the time between the issue starting and detection. Plain prose.]

---

## Resolution

**Immediate mitigation:** [What stopped the bleeding, e.g. "rolled back to the previous
release tag."]

**Long-term fix:** [What actually fixes the root cause, if known. If still in progress,
write the planned fix and link the ticket.]

---

## What Went Well

- [Something that worked as expected during the incident response]
- [e.g. "The rollback procedure executed cleanly in under 5 minutes"]
- [e.g. "On-call rotation was reachable immediately"]

---

## What Went Wrong

- [Something that slowed response or worsened impact]
- [e.g. "Alerting did not fire until 18 minutes after error rate spiked"]
- [e.g. "Runbook for this service was out of date"]

---

## Action Items

| Action | Type | Owner | Due | Status |
|--------|------|-------|-----|--------|
| [Specific fix or improvement] | prevent | [assign owner] | [set due date] | TODO |
| [Monitoring or alerting improvement] | detect | [assign owner] | [set due date] | TODO |
| [Runbook or process update] | process | [assign owner] | [set due date] | TODO |
| [Test coverage addition] | prevent | [assign owner] | [set due date] | TODO |

---

## Supporting Information

- [Link to relevant logs, dashboards, or monitoring screenshots]
- [Link to the PR or commit that triggered the incident]
- [Link to the rollback PR or hotfix commit]
- [Workspace screenshots directory: workspace/[ticket-id]/screenshots/ if applicable]
- [Any additional context, IRC/Slack threads, runbook links]
```
