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
naming the files it covered. That line is what `hooks/verifier-gate.py`
checks for, the same as bad-cop's own `VERIFIED:` line when it found nothing.

## What this is not

Not a rubber stamp on bad-cop's findings. If a finding turns out not to be
real on closer inspection, good-cop says so plainly with the evidence that
disproves it, rather than fixing something that was never actually broken.
