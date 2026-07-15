---
name: researcher
description: Spawn researcher directly on a task, no /start sequence attached. Use for a pure codebase structure or standards question, what breaks if this changes, what does good code for this look like here, without needing swiper's swipe check afterward.
---

# /researcher

Direct spawn, for a structural or standards question on its own, when you
don't need swiper's swipe check to follow it. `/start` runs researcher then
swiper together for a new build or feature; this is the narrower tool for
just the codebase and standards pass.

## What to do

`$ARGUMENTS` is the task or question. If it's empty, use whatever the user
was just describing.

Spawn `researcher` (foreground, `run_in_background: false`, never
backgrounded). Give it the task and, if you already know some, 3 to 5
aspects. It indexes and searches the project itself (triggering
`/index-project` if the index is missing or stale), reads both the vector
and import graph, reaches for the `graphrag` skill on a genuinely cross file
behavior question, and checks the general standard for this class of change
against a real source.

Wait for it. Report the structural picture (what this touches, what breaks
if it changes) and the standards findings, with sources. No `COVERS:` line;
researcher doesn't unlock any edit gate, its report is context for whatever
comes next, a plan, a consult, or a decision.

## What this is not

Not a codebase grep substitute for something you can answer in one Read or
Grep call yourself. It's for when the question is genuinely structural
("what depends on this", "is there a cross file flow here") or a standards
check research would actually ground, not a stand in for looking at the file.
