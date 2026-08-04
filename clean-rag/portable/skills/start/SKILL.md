---
name: start
description: Kick off a new build or feature the deliberate way. Spawns researcher first (codebase structure plus real engineering standards), then swiper informed by that (what can be swiped, never written by swiper itself), then consults the user with real options before any code gets written.
---

# /start

For an edit intent task, a new build or feature, not a question. For a
question with no edit involved, use `/research` instead.

`researcher`, `swiper`, `bad-cop`, and `good-cop` each also have their own
direct skill now, for spawning one of them on its own. `/start` is not a
macro that blindly fires all four in fixed order regardless of the task.
Deciding when each one actually gets sent out, and what to hand it, is the
job here, same as it always was; the standalone skills exist for a manual,
one-off spawn, not to turn this into a dumb pipe.

## What to do

`$ARGUMENTS` is the task. If it's empty, use whatever the user was just
describing, and say what you took it to mean.

Researcher and swiper both still run in full for a genuine new build or
feature; that's the same "no cheap triage tier" rule swiper already follows,
just applied one level up: don't pre filter whether research happens based on
a guess that the task looks small. What you use judgment on is everything
downstream of what they actually report: if researcher's findings already
make swiper's answer obvious, say so plainly rather than padding the report,
still spawn it (its job is checking whether something can be swiped, that
doesn't get skipped), but don't manufacture ceremony neither of them found a
reason for. bad-cop follows the standing verify policy: it runs after any
real code change, the same as it would if the verifier gate nudged for it
directly, not as an optional extra tacked onto `/start` specifically.
good-cop only runs when bad-cop actually found something; a clean adversarial
pass closes itself out.

**1. Spawn `researcher`** (foreground). Give it the task and, if you already
know some, 3 to 5 aspects. It indexes and searches the project itself
(triggering `/index-project` if needed), reads both the vector and import
graph, reaches for the `graphrag` skill on a genuinely cross file behavior
question, and checks the general standard for this class of change against a
real source, not memory. Wait for it.

**2. Spawn `swiper`** (foreground), only after researcher reports. Hand it
researcher's findings along with the task, so it doesn't recommend swiping
something the project already has a pattern for. Swiper checks whether this
already exists (project, stdlib, a dependency, GitHub, StackOverflow) and
reports the exact code, the exact repo and file, or the exact StackOverflow
answer to use. It never writes anything into the project itself, it only
reports, with `MATCH_STRATEGY` and `COVERS:`.

**2a. Read the reference block before forming options.** If swiper's report
contains a `GITHUB_FILE_READ:` line and a quoted code block, read that block
before constructing the CONSULT options. Not the repo name alone — the actual
quoted code. The block is there so you do not consult from memory of what the
reference "probably does"; consulting from a description of it is the same
failure mode the snippet-forwarding rule in CLAUDE.md was written to prevent
at the bad-cop/good-cop handoff. If the block is absent despite a
`MATCH_STRATEGY: clone-and-patch` declaration, treat the strategy as
`pattern-only` until the block is produced.

**2b. Write a visible summary of both reports before forming options.** After
researcher and swiper finish, write a summary to the user in the conversation
before the `AskUserQuestion` call. This is not internal processing — it is a
visible report so the user can see the reasoning before they are asked to
choose. It must include:

- Researcher: key structural findings, blast radius (what breaks if this
  changes), what the general engineering standard says about this class of
  change, and the COVERS scope it declared
- Swiper: what it found (or didn't), which repo/file, the MATCH_STRATEGY it
  declared, and if `clone-and-patch`, the relevant quoted code block it
  brought back
- Your read of each: do the findings line up, are there tensions, what do they
  imply for the options

A consult option you cannot trace to a specific researcher or swiper finding
is skipped reasoning, not CONSULT. The summary is how you prove you read both
reports before forming the options. "Based on research findings" is not a
summary — name the actual findings.

**3. Consult before writing anything.** Read both reports and turn them into
a small set of concrete options: what to swipe from where, what the
structural risk is, what the plan costs in each direction. When swiper
reported a `MATCH_STRATEGY: clone-and-patch`, one option must name the
reference explicitly as "full swap from [repo/file]" — not just "use the
pattern from X". The user is choosing whether to commit to that starting
point; they can only do that if the option names it. Use
`AskUserQuestion` to put those options in front of the user before a single
line gets written. This is the standing CONSULT mode behavior, just wired
explicitly into this sequence so it can't get skipped by momentum.

**4. Write the code.** Once the user picks, you place it, using swiper's
`COVERS:` clearance from this turn. If `MATCH_STRATEGY` was
`clone-and-patch`, that's a hard ceiling on the diff: copy the quoted
reference as the literal starting point and make only the smallest changes
actually required to fit, nothing more.

**5. Close it out.** Spawn `bad-cop`, the same way the verifier gate would
ask for it after any real code change: adversarial tests and logging, real
provable findings. After bad-cop reports, write a visible summary to the
user: what tests it wrote and ran, what the output was, and what (if
anything) it found. If it finds nothing real and stamps `VERIFIED:` itself,
relay that to the user and you're done. Only if it finds real findings,
relay each one clearly — file, line, what the test showed — then spawn
`good-cop` with those findings. After good-cop reports, write a visible
summary of what it fixed and that the suite is green. Then spawn bad-cop
again for a final adversarial re-check on good-cop's fix. Write a visible
summary of that re-check too. If bad-cop finds nothing and stamps
`VERIFIED:`, the loop ends. If it finds more issues, relay them and spawn
good-cop again. The loop (bad-cop → good-cop → bad-cop) continues until
bad-cop stamps `VERIFIED:` on a clean pass — that is the only terminal
condition. The user should never have to ask what happened in QA; each
round's output should be visible in the conversation before the turn ends.

## What this is not

Not a way to skip the consult step because the options seem obvious. If
researcher and swiper both come back thin (nothing structural, nothing worth
swiping), say so and consult anyway; "here's the plan, nothing external
mattered" is still a real option to put in front of the user, not a reason to
skip asking.

Not a substitute for `/ps` on something genuinely trivial. If the task turns
out to be a one line fix once researcher and swiper report, say so and
recommend `/ps` for this kind of change next time, the same way swiper
already flags an over researched trivial change.
