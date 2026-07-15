---
name: swiper
description: Spawn swiper directly on a task, no /start sequence attached. Use when you already know what needs checking (does this exist, what's the exact code or repo or StackOverflow answer to use) and don't need researcher's structural pass first.
---

# /swiper

Direct spawn, for when you already know the question and don't need
researcher's codebase map and standards pass ahead of it. `/start` runs
researcher then swiper together for a new build or feature; this is the
narrower tool for just the swipe check on its own.

## What to do

`$ARGUMENTS` is the task or question. If it's empty, use whatever the user
was just describing.

Spawn `swiper` (foreground, `run_in_background: false`, never backgrounded).
Give it the task broken into 3 to 5 aspects, each a question a search can
really answer, plus which project it concerns and its git root if any, so it
can read the import graph and search the project index. Remind it that
aspect zero always applies: does this already exist, in the project, the
stdlib, an installed dependency, or on GitHub or StackOverflow.

Wait for it. Report what it actually found: the exact code, the exact repo
and file, or the exact StackOverflow answer, plus `MATCH_STRATEGY` and
`COVERS:`. It never writes anything into the project itself, only reports;
placing what it found is the next step, not part of this one.

## What this is not

Not a substitute for researcher when the task is a new build or feature and
nobody has mapped the codebase yet. Run `/start` for that instead, it
sequences both. This is for the narrower "just check what's swipeable" case.
