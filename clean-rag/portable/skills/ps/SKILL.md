---
name: ps
description: Quick mode for this turn. Use when you (the human) already know a change or question is trivial and needs no research or verification. Starting a turn with /ps deterministically stands down the research gate and the verifier for that turn, so a rename, a one line fix, a comment tweak, or a quick question skips the full ceremony.
---

# /ps

Quick mode. You decided this turn doesn't need the full ceremony, so the research
gate and the verifier are already standing down for it. `rag-enforce.py` saw the
leading `/ps` on the raw prompt and marked the turn quick before the model started,
so nothing here depends on the model remembering to, and nothing the model does can
fake it the other way.

That the decision is the human's is the whole point. No agent gets to decide a
change is trivial, because a model guessing "this is fine" is the ungrounded call
this system removed when it deleted the triage agent. `/ps` is how a person, who
can see the whole picture, makes that call instead.

## What to do

`$ARGUMENTS` is the task or question. Just do it, directly and concisely:

- No research-agent. The gate won't block edits this turn, so don't spawn one.
- No verifier-agent. The Stop hook won't nudge for one this turn.
- Still leave a runnable check if you write real logic. Quick doesn't mean reckless:
  `/ps` skips the research and the review, not basic care. Something with a branch or
  a loop still gets the one small assert that proves it.
- If partway in this turns out NOT to be trivial (it touches auth, a query, a
  subprocess, money, or a real design decision), STOP and say so. Quick mode was the
  wrong call; tell the user and let them re-run without `/ps` rather than push an
  unreviewed real change through the hole they opened for a typo.

## What this is not

Not a way to skip verification on work that deserves it. It's a per turn choice a
human makes with eyes open, and it's still logged in the audit chain like any other
allow. If you find yourself wanting `/ps` to get past a gate that is correctly
stopping you, that's the gate working.
