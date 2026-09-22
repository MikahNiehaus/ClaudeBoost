# quick-cop's dispatch trigger has no mechanical anchor, so it does not fire

- **Kind:** architecture-addon
- **Area:** hooks (a new hook) + the prose in CLAUDE.md / quick-cop.md / quick-cop's SKILL.md that currently carries the whole rule
- **Found by:** bad-cop (instruction-layer review) on 2026-09-07
- **Why it was not fixed in place:** the fix is a new hook file plus a new piece of
  session state (a way to know whether quick-cop already ran this turn before a
  Stop fires), which is a new architectural layer, not a bounded text edit. The
  bar in `spec/README.md` names exactly this: "Adding a new dependency, or a new
  architectural layer."

## What is there now

Three places state the rule, and all three phrase it as a standing exhortation,
none as a mechanically checked condition:

`CLAUDE.md:196-203` (root), identical in `~/.claude/CLAUDE.md:177-184`
and `clean-rag/portable/CLAUDE.md:150-157`:

> "**Use quick-cop far more than you currently do.** Every time you say
> something is done, fixed, verified, confirmed, or has no gaps, that sentence
> is exactly the trigger quick-cop exists for (see its own agent description).
> Dispatch it liberally and backgrounded, meaning fire it and keep working, do
> not block waiting on it. This includes your own claims after a bad-cop or
> good-cop run: their self reported "VERIFIED" or "all tests green" is still a
> claim, so hand it to quick-cop to independently confirm rather than repeating
> it to the user as settled fact."

`clean-rag/portable/agents/quick-cop.md:3` (identical text in
`~/.claude/agents/quick-cop.md:3`, confirmed byte-identical by
`diff`):

> "description: 'Cheap claim checker. Given a claim that something is done,
> working, finished, or covered, it reads the actual code and reports whether
> the claim is true. Non blocking, stamps nothing, never satisfies any gate.
> Dispatch it liberally and backgrounded whenever you say you finished
> something, including a plan or a spec with no gaps. ...'"

`clean-rag/portable/skills/quick-cop/SKILL.md:3` (identical in the global
copy):

> "description: Spawn quick-cop on a claim. Cheap check that you actually did
> what you just said you did. Non blocking, stamps nothing, never satisfies the
> verifier gate and never replaces bad-cop. Use it liberally, backgrounded,
> every time you say something is done, finished, complete, or has no gaps."

All three are consistent with each other in wording (no contradiction between
them), and all three ask for the same thing: notice your own natural-language
claim, then act on it. None of them is wrong as prose. The defect is that
nothing outside the model's own text-generation loop ever checks whether this
happened, and the confirmed evidence is that it does not: the live session that
spawned this review made at least six done/fixed/verified/byte-identical
claims and dispatched quick-cop zero times.

## Why it is a problem

Compare this to the two mechanisms in the same codebase that solve the
identical shaped problem — "did the model actually do the thing it was told
to do before code changes or before ending a turn" — and both of those work:

**The research gate** (`clean-rag/hooks/research-gate.py`, PreToolUse on
Edit/Write/MultiEdit) fires on a real tool call. Editing a file is a
structured event the harness itself intercepts; the hook does not have to
infer from English text that an edit is about to happen, it is handed the
tool call directly. Its `PostToolUse` counterpart (`research-record.py`)
stamps a record when `swiper`/`researcher` (a named `subagent_type` in a
`Task` call) actually completes — again a structured event, not a claim
parsed from prose.

**The verifier gate** (`clean-rag/hooks/verifier-gate.py`, Stop hook) fires on
a real lifecycle event (`Stop`), and what it checks is also structured: it
calls `turn_edits.edited_code_files()` to see which files actually changed
(via git, not via reading what the model said it changed), and
`verifier_state.check_file_verified()` to see whether a `PostToolUse` stamp
exists for those exact files. Nothing about its trigger depends on the model
noticing its own sentence.

quick-cop's trigger is categorically different from both: **"you say
something is done" is not a tool call.** There is no `PreToolUse` or
`PostToolUse` event that fires when a model emits the word "verified" in its
own prose. The only event in the whole Claude Code hook surface that could
even see that text is `Stop` (via `transcript_path`), and nothing reads it
today. Confirmed by directory listing:

```
$ ls clean-rag/hooks/ | grep -i "quick\|claim\|done"
quick-cop-bash-guard.py
```

`quick-cop-bash-guard.py` is a `PreToolUse` guard on quick-cop's own Bash tool
calls once quick-cop is already running (it restricts what quick-cop can
execute). It does nothing to detect that quick-cop *should* be spawned. There
is no `quick-cop-gate.py`, no `quick-cop-nudge.py`, no Stop hook of any kind
for this agent. The asymmetry is exact: research coverage and verifier
coverage are both auditable after the fact (a stamp exists or it does not);
quick-cop dispatch is not auditable at all, because nothing writes anything
when it should have happened and did not.

Three compounding reasons the miss is invisible rather than merely rare:

1. **No re-injection at the moment of the claim.** `research-gate.py` prints
   its nudge to stderr at the exact moment of every Edit/Write call, so the
   reminder is back in context right when it matters. The quick-cop paragraph
   is read once, at session start (as part of `CLAUDE.md`), and nothing
   resurfaces it when the model is mid-sentence typing "this is verified."
   By the time the claim is made, the instruction is thousands of tokens
   back in context, competing with everything the session has done since.
2. **No audit trail.** `research_state.py` and `verifier_state.py` both
   persist whether coverage happened, so a human (or a hook) can check
   later. Nothing persists whether quick-cop should have fired. The failure
   mode described by the human — "I know for certain does not work" — could
   only be discovered by a human manually reading a transcript and counting,
   which is exactly what happened to produce the confirmed evidence above.
   A mechanism that can only be audited by hand is not a mechanism.
3. **The trigger is a judgement call layered on a judgement call.** The
   paragraph asks the model to (a) notice it made a completion-style claim,
   which is itself a fuzzy natural-language classification, and (b) weigh
   that against the standing, repeatedly-stated bias elsewhere in the same
   file toward not spawning agents ("Spawn agents when they add value... Do
   the work directly when they don't. A one line fix doesn't need an
   agent." — root/global/portable `CLAUDE.md`, "Agent Spawning" section).
   quick-cop's own text tries to except itself from that bias ("cheap",
   "seconds", "constantly"), but the exception lives in a different section
   than the general bias, and nothing forces the model to resolve the two
   at the actual moment of speaking. The human's own words name exactly this
   difficulty: "only when needed not to overuse it or underuse it, which is
   stupidly hard to get it to do." Calibration by unaided self-monitoring is
   the failure mode; the research gate and verifier gate do not ask a model
   to self-monitor at all, they ask a hook to check a fact.

This has already cost real review value: six unverified completion claims in
one session, zero cheap checks run, with no signal anywhere (to the model,
the orchestrator, or the human) that the rule had gone unused.

## What to do instead

Give quick-cop the same shape of mechanism the other two gates already have:
a `Stop` hook that inspects a structured fact instead of asking the model to
police its own prose, in the nudge-not-block style this repo has already
settled on twice (`verifier-gate.py`'s own docstring records two reverted
attempts at a hard block elsewhere in this family).

Rough shape, for whoever picks this up:

1. **A new Stop hook**, e.g. `clean-rag/hooks/quick-cop-nudge.py`, registered
   the same way `verifier-gate.py` is. It reads `transcript_path` from the
   Stop payload (the correction already recorded in `CLAUDE.md`: "the Stop
   payload carries `transcript_path` but no changed files list") and looks at
   the assistant's own last message(s) since the previous user turn.
2. **A fixed, narrow keyword/regex set**, matching the exact vocabulary the
   prose already commits to: `\bdone\b`, `\bfixed\b`, `\bverified\b`,
   `\bconfirmed\b`, `\bno gaps\b`, `\bbyte-identical\b`, and similar, anchored
   at sentence boundaries to reduce false positives on incidental uses (e.g.
   "the ticket says this feature is done" reporting someone else's claim, not
   making one). Getting this list right is real editorial work; ship it
   narrow and expand from real misses rather than guessing broadly up front.
3. **A structured signal for whether quick-cop already ran**, analogous to
   `research_state.py`'s turn record: something a `PostToolUse` hook on
   `Task` with `subagent_type: quick-cop` can stamp, so the Stop hook can
   tell "a completion claim was made AND quick-cop did not run this turn"
   apart from "a completion claim was made and quick-cop already checked
   it." Without this, the nudge fires every single Stop regardless of
   whether the rule was actually followed, which is noise, not a nudge.
4. **Nudge to stderr, never block.** Same posture as `research-gate.py` and
   `verifier-gate.py`: exit 0 always, print what claim it thinks it saw and
   suggest `/quick-cop`, and rate-limit repeats the way
   `verifier-gate.py::MAX_BLOCKS_PER_SESSION` caps its own nudge (currently
   6) so an ignored nudge goes quiet instead of adding noise forever.
5. **This still cannot catch the claim before the human reads it.** A Stop
   hook fires after the turn's text has already been sent. Nothing in the
   current Claude Code hook surface can intercept or veto text mid-generation
   the way a `PreToolUse` hook can flag a tool call before it executes. This
   is a real, permanent limitation of this approach, not an implementation
   detail to fix later: the best available mechanism turns this into a
   "flag it for next turn" corrector, the same limitation the research gate
   already accepts for the identical reason ("recoverable, so it earns an
   audit trail rather than a refusal").

## What it would break

- `clean-rag/hooks/quick-cop-bash-guard.py` is unaffected; it guards a
  different moment (quick-cop's own tool calls once running) and would
  coexist with a new dispatch-trigger hook rather than replace it.
- A new hook adds to the set of hooks Claude Code re-runs on every `Stop`
  event, alongside `verifier-gate.py`, `auto-test-gate.py`, and
  `stop-context-guard.py`. `verifier-gate.py`'s own docstring already flags
  the loop-safety requirement for a Stop hook (`stop_hook_active`); a new one
  needs the same guard from day one, and a test proving it, the same way
  `auto-test-gate.py` proves its own cap.
- If the keyword list is too broad, this becomes exactly the noisy annoyance
  `verifier-gate.py`'s own comment warns about ("a reminder that prints on
  every Stop stops being read"). Tune conservatively and measure before
  widening.

## Open questions

- Should the "did quick-cop already run" state live in a new small module
  (`quick_cop_state.py`, mirroring `research_state.py`/`verifier_state.py`),
  or is a lighter-weight signal enough (e.g. checking the transcript itself
  for a `Task` call with `subagent_type: quick-cop` since the last user
  turn, with no separate state file at all)? The transcript-only approach
  avoids adding a fourth piece of session state to reason about, at the cost
  of re-parsing the transcript on every Stop.
- Is Stop the right event, or should this also fire on `PreToolUse` for
  `AskUserQuestion` / the tool that ends a turn with a user-facing summary,
  to nudge slightly earlier? Untested; flagging rather than guessing.
- No decision on the exact keyword list is made here. It needs real
  false-positive testing against a corpus of real transcripts (this
  session's own transcript, once available, is one such corpus) before it
  ships, not a list authored from first principles.
- No prose-only fix was found. The three descriptions of the rule (CLAUDE.md,
  quick-cop.md, quick-cop's SKILL.md) are consistent with each other and
  correctly worded; the defect is that none of them can be mechanically
  checked, which prose cannot fix by itself.
