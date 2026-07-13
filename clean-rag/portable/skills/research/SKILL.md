---
name: research
description: Send out the research agent on a question, with no code edit involved. Use when you want depth and breadth research on a decision, a design question, a "what's the best way to X", or "does this already exist" before committing to anything.
---

# /research

Spawn research on demand, for a message rather than an edit.

The research gate only fires on code edits. That leaves a hole: a design question,
a "which approach should we take", a "does a library already do this" gets
answered from whatever I happen to remember. This closes it on request.

## What to do

`$ARGUMENTS` is the question. If it's empty, use whatever the user was just
asking about, and say which question you took.

**1. Decide if this needs the full agent or just triage.**

Spawn `triage-agent` first when the question is small or might not need research
at all. It answers in about 15 seconds. If it says `NONE`, tell the user that and
answer directly instead of burning a full research run.

Skip triage and go straight to `research-agent` when the question is obviously
substantial: an architecture decision, a library choice, "what's the best way to
build X", anything where being wrong is expensive.

**2. Spawn `research-agent`** with the question broken into aspects. Give it:

- The actual question, verbatim.
- 3 to 5 aspects, each one a question a search could really answer.
- Which project it concerns, if any, and its git root, so it can read the import
  graph and search the project index.
- An explicit reminder that aspect zero always applies: **does this already
  exist?** In the project, in the stdlib, in an installed dependency, on GitHub.

The agent handles depth versus breadth routing itself. That's in its preloaded
skill, so don't restate it.

**3. Wait for it.** Don't answer the question while it's running and then paste
the findings underneath. That defeats the point, and you'll anchor on whatever
you already believed.

**4. Report what it actually found**, not what you expected it to find. If it
contradicts you, say so plainly. If it found the thing already exists, lead with
that. If it found nothing useful, say that too. "I searched and found nothing, so
building it is the right call" is a real answer and worth reporting.

## Aspect quality

Bad aspects are topic headings: "performance", "security", "testing".

Good aspects are questions a search can answer:

- "What breaks when two processes append to the same JSON file, and what's the
  standard fix on Windows?"
- "Is there a maintained library that does hash chained audit logs in Python, or
  is this a 40 line hand roll?"
- "What do people get wrong when building a rate limiter, specifically?"

## What this is not

Not a substitute for reading the code. If the answer is in the repo, grep for it.
Research is for things the repo can't tell you.

Not a way to look thorough. If you already know the answer and it's cheap to
check, check it and move on. Spawning an agent to confirm something obvious wastes
the user's tokens and their time.
