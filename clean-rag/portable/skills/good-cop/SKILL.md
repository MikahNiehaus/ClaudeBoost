---
name: good-cop
description: Spawn good-cop directly, only after /bad-cop found something Critical or High. Researches the root cause of bad-cop's findings, fixes it, gets every test green, and stamps the verifier gate with VERIFIED. Skip this entirely when bad-cop emitted VERIFIED (it found nothing) or NITS (nit severity only, which you fix directly).
---

# /good-cop

Direct spawn of the fix half of post write verification. Only runs after
`/bad-cop` ended with `HANDOFF:`, which it emits only when at least one
finding is Critical or High.

Two bad-cop outcomes skip this skill entirely. `VERIFIED:` means it found
nothing and already stamped. `NITS:` means everything it found is Nit
severity, which is non blocking by definition: apply those fixes yourself,
then re-run bad-cop for the re-check that earns the stamp. Don't spawn an
Opus fix pass for polish.

## What to do

`$ARGUMENTS` is bad-cop's findings, or empty to mean "whatever bad-cop just
reported." Spawn `good-cop` (foreground, `run_in_background: false`, never
backgrounded). Give it five things and only five: bad-cop's `REVIEW SCOPE:`
line and resolved file list copied verbatim, the requirements, the correctness
properties, the diff or code under review, and bad-cop's findings with their
real execution output. Not the original author's reasoning for the change.

The resolved file list matters and is not optional. good-cop works the same
surface bad-cop reviewed, and it does not re-derive that list from the human's
original sentence: two agents resolving the same phrase separately produce two
different lists, and the fix then lands outside what was reviewed. The list
bounds where a root cause is allowed to live. It does not widen what good-cop
may change, which stays at what the findings actually require.

Wait for it. It researches why each finding actually happened, fixes the
root cause rather than the symptom bad-cop's test caught, and reruns
bad-cop's new tests plus the existing suite until everything is actually
green, not just the one repro that was originally flagged. It ends with a
`VERDICT:` line and, only once everything is green, a `VERIFIED:` line
naming the files it covered. After good-cop stamps `VERIFIED:`, spawn
bad-cop again for a final adversarial re-check on the fix. If bad-cop finds
nothing on that re-check, it stamps `VERIFIED:` itself and the loop ends.
If it finds more issues, spawn good-cop again. The loop (bad-cop → good-cop
→ bad-cop) continues until bad-cop stamps `VERIFIED:` on a clean pass —
that is the only terminal condition, not good-cop claiming done.

## What this is not

Not a rubber stamp on bad-cop's findings. good-cop reproduces each finding
before fixing it, quoting the command and output that confirm the failure. A
finding that does not reproduce is reported as a false positive with the
evidence that disproves it, never fixed on a guess, and never dismissed on
reading alone: only execution output overturns execution output.
