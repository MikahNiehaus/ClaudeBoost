---
name: bad-cop
description: Spawn bad-cop directly on a diff that already passed its tests. Adversarial QA, writes tests aimed at breaking it, runs the code, adds logging, reports real provable failures. Reports only, fixes nothing. Stamps VERIFIED itself when it finds nothing; only spawn /good-cop when it actually found something.
---

# /bad-cop

Direct spawn of the adversarial QA half of post write verification. Runs
after tests pass, before good-cop fixes anything.

## What to do

`$ARGUMENTS` is the diff or change to test, or empty to mean "whatever
changed this session." Spawn `bad-cop` (foreground, `run_in_background:
false`, never backgrounded). Give it three things and only three: the
requirements, the correctness properties the change is supposed to satisfy,
and the actual diff. Not your reasoning for the change, that's exactly what
biases a reviewer into agreeing with it.

Wait for it. It writes new tests aimed at breaking the change, runs the
code, adds temporary logging where it needs to actually see behavior, checks
the diff against `workspace/<task-id>/ticket.md` or `goal.md` if a workspace
is active (did it actually do what was asked, nothing silently skipped,
nothing bundled in that wasn't requested), and reports every provable issue
with real execution output attached, never a description of what should
happen. It never touches the destructive path for real to prove a finding
(no actually dropping a table, no actually deleting real data); a safe
demonstration or a traced but unexecuted call is the standard. It fixes
nothing itself either way.

**If it found nothing real**, it stamps `VERIFIED:` itself, last line, and
you're done: don't spawn `/good-cop` just to have it re-confirm a clean pass.
**If it found something**, it emits no `VERIFIED:` line and ends with
`HANDOFF:` instead; hand its findings to `/good-cop` then, don't fix them
yourself in this context, that inherits your own blind spot the same way
reading the author's reasoning would.

## What this is not

Not a fixer. If you already know the fix, spawning bad-cop first anyway
still gets you real proof the bug exists before good-cop touches it, but if
speed matters more than that proof for something genuinely trivial, that's
a `/ps` call, not this skill's to make for you.
