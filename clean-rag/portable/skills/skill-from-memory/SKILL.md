---
name: skill-from-memory
description: Mine the project's memory store for recurring issues, then SWIPE an existing published skill that solves each one instead of writing a new skill by hand. Use when the user asks to turn memory, feedback, or recurring issues into skills, to find a skill for something that keeps coming up, or to check whether a published skill already solves a problem this project keeps hitting. Also use for "what should be a skill", "mine my memory", or "find me a skill for X". Reports and installs nothing without two explicit approvals.
allowed-tools: Read, Glob, Grep, Bash, WebFetch, AskUserQuestion
---

# /skill-from-memory

Turn recurring issues in the memory store into installed skills, taken from the
public registry rather than written here. Hand authoring a skill is the failure
this exists to prevent.

## The rule that makes this different

**Most memory entries must NOT become skills.** A preference about how the user
wants work done is already in the right place. No published skill will ever
solve "never commit without asking". Searching the registry for one wastes a
turn and produces a bad match.

So the classifier is the whole job. Everything else is plumbing.

## Phase 1: read the store

The memory directory for this project. Claude Code exposes it directly (a
system reminder or your own prior turns will have already named it); it lives
under `~/.claude/projects/<mangled cwd>/memory/`, where the mangling replaces
every non alphanumeric character in the working directory's path with a dash
(very long paths are truncated and hashed instead), for example
`C:/Users/foo/.claude/projects/C--prj-ClaudeBoost/memory/` for a project at
`C:\prj\ClaudeBoost`. Never hardcode a specific machine's path here.

Glob `*.md`. Read `MEMORY.md` first: its section headings are a human's existing
clustering and are more reliable than anything you would recompute. Each other
file is one fact with YAML frontmatter carrying `name`, `description`, and
`metadata.type` of `user`, `feedback`, `project`, or `reference`.

Do not build an embedding or clustering pipeline. At this size the model reading
the files IS the clustering step, and the index already did the grouping.

## Phase 2: classify every cluster (the part that matters)

Two buckets, and only one continues.

**Preference or decision. STOP HERE.** How the user wants work done, a recorded
project decision, a credential or path reference. These are correctly stored
already. Report them as "already in the right place", never search for them.
Examples of this bucket: never commit without asking, always propose first,
safety is global, advisory not blocking, RAG terminology.

**Capability gap. CONTINUE.** The user or Claude keeps doing something by hand
that a tool could do. The signal is a repeated manual workaround, not a repeated
instruction. If you cannot name the manual work being repeated, it is a
preference, so put it in bucket one.

A rule of thumb that holds well: rewrite the entry as "I keep having to ___".
If the blank fills with an action, it is a capability gap. If it fills with
"remember to", it is a preference.

Expect bucket one to be most of the store. On the store as it stands, 12 of 17
fact files are `type: feedback` behavioural rules. A run that classifies almost
everything as preference and searches for almost nothing is CORRECT, not broken.

## Phase 3: the recurrence bar

A capability gap earns a registry search only when both hold:

- It appears in **2 or more distinct memory files**, not one file worded
  strongly.
- The files describe the same underlying missing capability, not merely the same
  topic area.

Adopted from `pskoett/pskoett-ai-skills@self-improvement`, whose promotion rule
reads:

```
Recurrence-Count >= 3
Seen across at least 2 distinct tasks
Occurred within a 30-day window
```

Two deliberate changes, because copying it as written would be wrong here:

- **Count lowered from 3 to 2.** That rule governs a high volume append only
  session log. This store holds 17 curated files, where three separate entries
  on one missing capability essentially never happens. Three would make the bar
  unreachable.
- **The 30 day window is dropped.** Only 2 of 18 files carry a date at all, and
  file mtimes span more than four months. A 30 day window would reject nearly
  the whole store for being old, when age here means settled, not stale.

Keep the "distinct sources" half exactly as it is. One emphatic file is the
failure mode this bar exists to catch.

## Phase 4: swipe, do not write

For each gap that clears the bar, search the registry. Use `Bash`:

```
npx -y skills find "<keywords>" </dev/null
```

Redirect stdin from `/dev/null`. Without it `find` goes interactive and hangs.

Results are ranked by real install counts. Rank on that, not on repo stars.

Then, in order, and stopping at any refusal:

1. **Report the ranked candidates** with install counts. If the search returns
   nothing, say so plainly and stop on that gap. An empty result is a real
   finding. Never soften it into a weak match, and never silently drop the gap.
2. **Ask for approval to inspect.** On yes, print the body without installing:
   ```
   npx -y skills use OWNER/REPO@SKILL </dev/null
   ```
3. **The human reads the body.** Not you summarising it for them. A skill body
   is a stranger's instructions that will run inside their session.
4. **Ask for approval to install.** Only then:
   ```
   npx -y skills add OWNER/REPO@SKILL -g
   ```
   `-g` installs to `~/.claude/skills/`, which is where this project's skills
   live.

Never combine steps 2 and 4 into one question. Inspect and install are separate
consents because the body is what the second one is judged on.

## Install count is popularity, never safety

A high install count means many people fetched it. It does not mean anyone
audited it. The registry's own guidance only suggests preferring widely
installed skills from reputable owners, which is a quality heuristic and not a
security control. The human reading the body is the actual control.

Do not adopt any tool that ships session content or memory contents to a third
party backend. This store contains project credentials and local URLs.

## Prerequisites

`npx` is required and is not checked for you. If `npx --version` fails, report
that and stop. Do not fall back to `gh skill`, which is a preview command and is
not installed on this machine.

## Honest outcomes

All three of these are successful runs:

- Every cluster is a preference, nothing is searched. Report that.
- A gap clears the bar and the registry has nothing. Report the empty result.
- A gap clears the bar, a candidate is found, and the human declines it.

The failure mode is manufacturing a match so the run has something to show.

## What this is not

**Not a skill author.** If nothing suitable exists, say so and stop. Writing the
skill here is the outcome this skill exists to avoid. Hand authoring is a
separate, explicit decision for the user to make.

**Not `/self-improve`.** That one audits this codebase and flags memory entries
by age. It edits this project's own source. This one classifies memory and pulls
in third party skills, a different job with a different trust boundary.

**Not a verifier.** It stamps nothing and satisfies no gate.
