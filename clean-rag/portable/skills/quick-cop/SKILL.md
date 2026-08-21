---
name: quick-cop
description: Spawn quick-cop on a claim. Cheap check that you actually did what you just said you did. Non blocking, stamps nothing, never satisfies the verifier gate and never replaces bad-cop. Use it liberally, backgrounded, every time you say something is done, finished, complete, or has no gaps.
allowed-tools: Agent
---

# /quick-cop

Cheap claim check. Use it constantly.

## What to do

`$ARGUMENTS` is the claim to check, or empty to mean "the thing I just said I
finished". Spawn `quick-cop` and hand it three things: the claim in the exact
words it was made, where to look, and nothing else. Not your reasoning for
believing the claim, for the same reason bad-cop never gets it.

**Background it** (`run_in_background: true`). That is the point. It reports
while you keep working, and when it comes back you either carry on or you fix
what it found. Nothing waits on it, because nothing it produces is a stamp.

Dispatch it on anything you asserted, not just code: a finished spec with no
gaps left, a migration that covers every call site, a config that is wired,
tests that cover the branch you said they cover.

It returns `CLAIM:` / `ACTUAL:` / `MATCHES:` per part of the claim, and one
`QUICK CHECK:` line at the end. When a part does not hold, fix it or tell the
user it does not hold. Do not quietly restate the original claim.

## What this is not

**Not the verifier.** quick-cop emits no `VERIFIED:` line and is deliberately
absent from `VERIFIER_AGENTS` in `clean-rag/hooks/verifier-record.py`, so it
cannot clear a gate and cannot end a turn. A real code change still wants
`/bad-cop`. If quick-cop comes back clean, that is not verification, it is one
cheap read agreeing with you.

**Not a reason to skip bad-cop.** If quick-cop finds something serious it will
say so and name bad-cop. Take that seriously rather than treating the cheap
pass as the whole review.

**Not the removed triage-agent.** That one decided whether work needed research
without reading the code, and was deleted for guessing wrong. quick-cop always
reads first, and never decides whether deeper work happens.

## Note on backgrounded reports

A backgrounded agent's output can come back empty
(`anthropics/claude-code#21352`, reported repeatedly). Since nothing blocks on
quick-cop, a lost report costs a respawn rather than a stuck turn. If it comes
back with nothing, spawn it again or move on.
