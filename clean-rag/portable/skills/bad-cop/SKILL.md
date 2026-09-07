---
name: bad-cop
description: Spawn bad-cop directly on a diff that already passed its tests. Adversarial QA, writes tests aimed at breaking it, runs the code, adds logging, reports real provable failures. Reports only, fixes nothing. Stamps VERIFIED itself when it finds nothing, emits NITS when everything it found is nit severity (you fix those yourself), and only hands off to /good-cop when it found something Critical or High.
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

Its last line is one of three, and it tells you what to do next.

**`VERIFIED:` means it found nothing** and you're done. Don't spawn
`/good-cop` just to have it re-confirm a clean pass.

**`NITS:` means everything it found is Nit severity**, no Critical and no
High. good-cop is not spawned for those. A nit is non blocking by
definition, and an Opus fix pass costs more than the findings are worth, so
you apply them yourself, then spawn bad-cop again for the re-check that
earns the stamp. bad-cop deliberately does not stamp on a nit only run:
`verifier_state.py` invalidates a stamp when the file's mtime advances past
it, so a stamp written before your fixes land would erase itself.

**`HANDOFF:` means it found at least one Critical or High.** Hand those
findings to `/good-cop`, don't fix them yourself in this context, that
inherits your own blind spot the same way reading the author's reasoning
would. After good-cop stamps `VERIFIED:`, spawn bad-cop again for a final
re-check on the fix. If it finds nothing, it stamps `VERIFIED:` itself and
the loop ends. If it finds more, spawn good-cop again.

The terminal condition is always bad-cop stamping `VERIFIED:` on a clean
pass, never good-cop claiming done and never you deciding the nits are
handled.

## What this is not

Not a fixer. If you already know the fix, spawning bad-cop first anyway
still gets you real proof the bug exists before good-cop touches it, but if
speed matters more than that proof for something genuinely trivial, that's
a `/ps` call, not this skill's to make for you.
