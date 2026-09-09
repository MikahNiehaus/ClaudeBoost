# OpenCode's research gate reintroduces an unbounded hard block the Python gate tried and reverted twice

- **Kind:** architecture-change
- **Area:** opencode
- **Found by:** bad-cop on 2026-09-07
- **Why it was not fixed in place:** the two ways to close this both change the
  gate's enforcement contract (whether it blocks at all, or how many times),
  not a single file's implementation detail, and the right answer depends on a
  tradeoff between OpenCode's own platform limits and a policy this project
  already recorded a decision about on the other platform.

## What is there now

`clean-rag/opencode/plugin/research-gate.js`'s `tool.execute.before` throws a
JavaScript `Error` to block an edit outside the researched scope, with no cap
on how many times it can fire in one session:

```js
// clean-rag/opencode/plugin/research-gate.js:353-367
throw new Error(
  "BLOCKED by clean-rag research gate: this file is not in a researched scope.\n\n" +
  ...
);
```

The file's own comments explain why: OpenCode gives a plugin no way to print a
passive nudge, only a thrown error in `tool.execute.before`:

```js
// clean-rag/opencode/plugin/research-gate.js:30-36
// SECOND HARD LIMIT: OpenCode has no message injection API (PR #19519 closed
// unmerged). Claude Code's passive verify after edit nudge is impossible here. The
// only model visible text a plugin can produce is a thrown error in
// tool.execute.before. So the "verify by running a test" reminder cannot be a
// passive note. It rides along on the next block message instead.
```

Nothing in this file counts how many times it has thrown for a session, and
nothing lets a stuck session get past it, unlike its two Python siblings:

```python
# clean-rag/hooks/auto-test-gate.py:41
MAX_BLOCKS_PER_SESSION = 2
```

```python
# clean-rag/hooks/verifier-gate.py:94
MAX_BLOCKS_PER_SESSION = 6
```

The Python research gate does not block at all, by an explicit, recorded
decision, and the project's own CLAUDE.md documents that decision as reached
the hard way:

> This hook is a nudge on purpose, and it stays one. It blocked once, and the
> per-turn scoping wiped coverage on every follow-up message, so a file swiper
> had just covered needed covering again the moment another message arrived.
> (`clean-rag/hooks/research-gate.py:15-19`)

> This repo has also run the blocking version twice and reverted it twice:
> the research gate's per-turn block was removed as too disruptive, and
> verify-gate-cmd.py records a forced-response hook that stalled batch work.
> (`clean-rag/hooks/verifier-gate.py:8-10`)

The user's own project memory restates the same policy independently:

> project_advisory_not_blocking.md: "Research/verifier gates nudge, never
> block."

## Why it is a problem

`research-gate.js` blocks on every OpenCode platform, unconditionally, with no
escape hatch, which is exactly the shape of hook this project has twice found
disruptive enough to revert on the other platform. Two concrete failure modes
follow directly from having no cap:

1. **A new file that a research-agent's `COVERS:` line does not name.** The
   file's own comment at `research-gate.js:316-324` acknowledges a research
   agent can predict a nested layout while the builder writes a flat one, and
   treats an existing `COVERS:` line from anywhere in the session as enough to
   unblock a *new* file for exactly this reason. But an *existing* file still
   needs an exact per-file `COVERS:` match (`fileInScope`, line 305), and nothing
   stops the same file from being rejected on every retry if the agent keeps
   guessing a `COVERS:` scope that never matches the literal path being edited.
2. **The known OpenCode subagent bug** (`research-gate.js:23-28`,
   `sst/opencode#5894`) means a subagent's edit is never intercepted at all,
   while the primary agent's retry of the *same* edit after a subagent already
   made it can still throw, with no state tracking that the file was already
   handled moments ago by a path this plugin cannot see.

Both are the same shape as the two documented Python reverts: a hard block
whose escape condition depends on a model behavior (guessing the right
`COVERS:` scope, or noticing a subagent already wrote the file) that the block
itself cannot verify or wait out.

## What to do instead

Two directions, and they are genuinely different policies, not two
implementations of the same one:

**A. Add a session-scoped circuit breaker**, mirroring
`auto-test-gate.py`'s and `verifier-gate.py`'s `MAX_BLOCKS_PER_SESSION`. The
file already keeps in-memory, session-keyed state
(`coveredScopes`, `ragProject`, `untestedCode`, `testsPassed` at
`research-gate.js:216-224`), so a `blockCount` `Map` fits the same pattern.
After N blocks for one session, stop throwing and let the edit through,
the same "an ignored nudge should get out of the way" reasoning
`verifier-gate.py:363-374` already states for its own cap. Touches one file.

**B. Match the Python gate's decision exactly and never block**, accepting
that OpenCode's missing injection API means the "verify by running" and
"spawn research-agent" reminders can only ever ride along on a different
tool's output (already how `untestedCode` works, `research-gate.js:290-296`),
never guaranteed to reach the model at the moment of the edit. This makes
`research-gate.js` strictly weaker than the Python gate as an enforcement
mechanism, in exchange for matching its recorded policy and its failure mode.

## What it would break

- Direction A changes user-visible behavior: an edit that is currently always
  refused until researched would, after N attempts, go through unresearched.
  Anyone relying on the current hard-block behavior in an OpenCode session
  would see a change in how many retries it takes before an edit lands.
- Direction B removes the only enforcement OpenCode's integration has today.
  `clean-rag/opencode/AGENTS.md` and `ITERATION_FAILURES.md` were not read as
  part of this review (out of the reviewed partition's time budget) and may
  describe reliance on the current hard-block behavior; check them before
  choosing B.
- Neither direction changes `coveredScopes`, `fileInScope`, or
  `extractCoveredFiles`, so no caller outside this one file is affected either
  way.

## Open questions

- Does `clean-rag/opencode/AGENTS.md` or `ITERATION_FAILURES.md` document a
  reason OpenCode's gate was deliberately made stricter than the Python one,
  rather than this being an oversight from porting the logic without porting
  the cap? Neither file was read for this item.
- If direction A is chosen, what should N be? `auto-test-gate.py` uses 2 for a
  gate that blocks on an objective test failure; `verifier-gate.py` uses 6 for
  a purely advisory nudge. This gate sits in between: it blocks (like
  auto-test-gate), but on a judgment call about scope coverage (more like
  verifier-gate's subject matter). No existing precedent in this codebase
  settles which cap fits it.
