# The bad-cop / good-cop loop has no round cap, and the counter that looks like one is not

- **Kind:** architecture-addon
- **Area:** hooks
- **Found by:** session review of the bad-cop / good-cop loop, 2026-09-11
- **Why it was not fixed in place:** adds a second terminal condition to a loop
  that currently has exactly one, which is a contract change. The number itself
  is a human decision, and the enforcement point has to be chosen from two that
  behave differently.

The loop's only stopping condition is bad-cop stamping `VERIFIED:` on a clean
pass. Nothing bounds how many rounds it takes to get there. The constant that
reads like a cap counts something else.

## What is there now

`clean-rag/hooks/verifier-gate.py:94` sets `MAX_BLOCKS_PER_SESSION = 6`. Its own
docstring, lines 54 to 59, says what that number actually does:

```
MAX_BLOCKS_PER_SESSION keeps its old name and no longer caps a block, since
there is none to cap. It caps how many times the nudge repeats in one round; a
round that ends in a stamp (NITS: or good-cop's VERIFIED:) resets it, so the cap
counts rounds that went nowhere rather than the whole session.
```

`_bump_block_count` is called at `verifier-gate.py:387`, immediately before the
nudge is printed, so it increments once per Stop event that produced a nudge. A
round that ends in a stamp resets it. A loop making apparent progress therefore
clears the counter every round and can run indefinitely.

Nothing else bounds it. `verifier_state.py` records stamps keyed by file and
mtime and holds no round or invocation count. Both `CLAUDE.md` copies state the
terminal condition as a single condition: the loop "continues until bad-cop
stamps `VERIFIED:`, that is the only terminal condition, not good-cop claiming
done." No ceiling is named anywhere.

**The harness will not do it either.** `maxTurns` caps tool-use round trips
inside one subagent invocation, not how many times the orchestrator spawns a new
`Task`. The bad-cop then good-cop then bad-cop loop is separate `Task` calls made
by the parent session, which no harness level counter observes. `maxTurns` is
also currently unreliable inside its own scope: `anthropics/claude-code#41143`
reports it unenforced on subagents, with an agent running 72 turns under
`maxTurns: 10`.

**The project already solved this once, for a different loop.**
`clean-rag/portable/skills/workshop/SKILL.md:247-273` caps its own critic loop:
"Three rounds is the normal shape. Five is a stop and ask", with gates for
circling, stalling, trivial branching and drift. It cites LangGraph's
`recursion_limit`, LangChain's `max_iterations` and the OpenAI Agents SDK's
`max_turns`. That loop spawns bad-cop and good-cop as critics too, but it is
invoked by `/workshop`, is enforced as prose in a skill file, and is not wired to
`verifier-gate.py`. The standard verify loop inherits none of it.

## Why it is a problem

The loop is the one place in this system where cost scales without a ceiling.
Each round is a Sonnet bad-cop pass that writes and runs tests, and on a
`HANDOFF:` an Opus good-cop pass on top of it. Two agents per round, one of them
on the expensive model, repeating until an adversarial agent finds nothing.

The failure shape is not a crash. It is a loop that keeps making apparent
progress: bad-cop finds something real, good-cop fixes it and stamps, bad-cop
finds something else real. Every round is legitimate, every round resets the
nudge counter at `verifier-gate.py:190`, and nothing anywhere is counting. From
inside the session it reads as the process working.

The established practice names this directly. AutoGen's reflection pattern pairs
a generator and a critic with `max_round`, and the standard framing is that
convergence needs a stopping criterion, a quality threshold **or** an iteration
budget, to prevent over-editing or oscillation. This loop has the first and not
the second. `spec/architecture-changes/opencode-research-gate-block-policy.md`
already records this project's view that an unbounded enforcement loop with no
session cap is the shape to avoid, on a different gate.

No runaway has been recorded. The absence is structural rather than observed.

## What to do instead

**Read the count from state that already exists.** `verifier_state.py`'s
`record_verifier()` appends every bad-cop and good-cop stamp, with agent and
timestamp, to `state/verifier/session-<hash>.json`. The number of rounds this
session is already answerable from that list. A second counter would be a second
source of truth for the same fact, which is the bug this hook family exists to
avoid.

**Make the cap surface the pathological case, not define done.** The terminal
condition stays bad-cop's clean stamp. The cap exists to catch a loop that is not
converging and hand it to the human, which is what `workshop/SKILL.md` already
does with "stop and ask" rather than "stop".

**Follow the number the project already picked.** Three rounds normal, five stop
and ask, from `workshop/SKILL.md:247-273`. Reusing it keeps one convention across
both loops instead of inventing a second.

Files: `clean-rag/hooks/verifier-gate.py`, both `CLAUDE.md` copies for the
terminal condition wording, and `clean-rag/portable/` twins.

## What it would break

**The stated contract.** Both `CLAUDE.md` copies say bad-cop's clean stamp is
"the only terminal condition". A cap makes that false as written, and that
sentence exists to stop the orchestrator accepting good-cop's own "done". The
replacement wording has to keep that meaning while admitting a second exit, or it
reopens the failure it was written to close.

**A cap that stops rather than asks hides a real bug.** A loop reaching round
five has found five rounds of real problems. Ending it silently ships code with
known findings outstanding. The exit has to be a handoff to the human with the
findings attached.

**Counting stamps is not counting rounds.** A `NITS:` run produces no stamp by
design, because `verifier_state.py` invalidates a stamp once the file's mtime
passes it. A round where the orchestrator fixed nits and re-ran bad-cop is a real
round that leaves no entry in the stamps list. Counting stamps undercounts by
exactly those rounds.

**Session scoping.** The count lives per session hash. A loop resumed after a
compaction or a `--continue` may read a fresh count and start over, which is the
same class of problem `research_state.py`'s `TURN_MAX_AGE_S` already had to
answer for coverage.

**Nothing tests it.** No test asserts anything about loop rounds, so this breaks
no test and gains no coverage without one written for it.

## Open questions

**Where does the cap live?** `verifier-gate.py` is a Stop hook, so it only sees
turns that end. A loop running several rounds inside one turn never reaches it,
and that is the runaway case. The alternative is the PostToolUse hook on `Task`
that already records stamps, which sees every spawn but is not where a refusal
belongs. Neither is obviously right.

**Does it nudge or block?** `verifier-gate.py` returns 0 on every path today, and
this codebase has reverted a hard block on this surface twice. A nudge at round
five is a sentence the orchestrator may ignore, which for a cost ceiling is
weaker than the case for nudging a review verdict.

**Is five right for this loop?** `workshop/SKILL.md` set three and five for
workshopping an idea, where a round is cheap. A round here is two agent
invocations, one on Opus. The right number may be lower, and nothing has measured
what a normal round count actually looks like in practice.

**Does a `NITS:` round need its own record?** Fixing the undercount above means
recording something for a round that deliberately produces no stamp. That is a
new field in the session record and a decision about what it means.
