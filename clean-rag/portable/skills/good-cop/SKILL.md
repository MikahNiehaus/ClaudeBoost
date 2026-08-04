---
name: good-cop
description: Spawn good-cop directly, only after /bad-cop found something real. Researches the root cause of bad-cop's findings, fixes it, gets every test green, and stamps the verifier gate with VERIFIED. Skip this entirely if bad-cop found nothing, it already stamped VERIFIED itself.
---

# /good-cop

Direct spawn of the fix half of post write verification. Only runs after
`/bad-cop` found something real, handed its findings. If bad-cop found
nothing, it already stamped `VERIFIED:` itself; don't spawn this.

## What to do

`$ARGUMENTS` is bad-cop's findings, or empty to mean "whatever bad-cop just
reported." Spawn `good-cop` (foreground, `run_in_background: false`, never
backgrounded). Give it four things and only four: the requirements, the
correctness properties, the diff, and bad-cop's findings with their real
execution output. Not the original author's reasoning for the change.

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

Not a rubber stamp on bad-cop's findings. If a finding turns out not to be
real on closer inspection, good-cop says so plainly with the evidence that
disproves it, rather than fixing something that was never actually broken.
