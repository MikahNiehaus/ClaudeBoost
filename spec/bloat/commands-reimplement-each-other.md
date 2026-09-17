# The planning commands reimplement each other instead of calling each other

- **Kind:** bloat
- **Area:** cli
- **Found by:** audit of the skill and capability surface, 2026-09-11
- **Why it was not fixed in place:** merging whole commands, and one item needs
  a product decision about which of two review pipelines is authoritative.

## What is there now

36 commands, 12229 lines. The nine largest are 8601 of them, 70 percent. A
command file is read into context when invoked, so a line here is paid on every
invocation.

**`/graph`'s scope map is pasted into `/workspace`.** `graph.md:97-183` extracts
entities from a ticket, runs `mode: graph` search per entity, and writes a
`## Files in Scope (Graph Map)` table. `workspace.md:528-554` does the same
thing, and the table headers at `graph.md:164,177` and `workspace.md:544` are
identical. `/graph` alone has Phases 5 and 6 (structural gap analysis,
acceptance criteria cross check, `graph.md:184-407`), which is its real value
and is not duplicated.

`graph.md:1-16` also restates policy CLAUDE.md already applies globally: "Vector
search finds semantically similar code; graph search finds structural
neighbours... Together they give a starting navigation map that either mode
alone misses." CLAUDE.md's clean-rag section already says to use `mode: "both"`
on every code search. The command exists to do what every search already does.

**`/explore` and `/workspace` are the same pipeline twice.** `explore.md`
Phase 0-4 runs workspace init, ticket analysis, indexing, code exploration, then
writes `plan.md`. `workspace.md` Phase 1-5 creates a workspace, classifies the
work, maps capabilities, then writes `plan.md`. Same target file, different
templates: `explore.md:398-438` versus `workspace.md:585-617`.

`workspace.md:606` gives `/explore my-workspace-id` as an example step inside a
workspace plan. The intended architecture is composition. The files do not do it.

**`/xray` is a second reviewer with no relationship to the first.**
`xray.md:487-596` runs 15 review passes and `xray.md:636-677` spawns an Opus
evaluator that emits `Grade: A/B/C/D/F`, `BLOCKERS`, `WARNINGS`, `NITS`.

It contains zero occurrences of `VERIFIED:`, and
`clean-rag/hooks/verifier_state.py:39` sets `VERIFIER_MARKER = "VERIFIED:"`. So
an `/xray` run produces nothing the verifier gate recognises.

It names no cop except one `quick-cop` spawn at `xray.md:214`, used to check its
own evidence. bad-cop and good-cop, the pair CLAUDE.md mandates for a code
review, appear zero times. Two complete review systems, two vocabularies, and
nothing says which one answers "review my diff".

**`/qa` is 3220 lines holding two pipelines.** General Mode (`qa.md:2515-3004`,
about 490 lines) is a code QA pipeline sharing only Phase 0 with the browser QA
pipeline around it. `qa.md:2215-2353` restates the bad-cop evidence-judge
contract that CLAUDE.md already states as global policy for any QA session.

**`/visualize` inlines 513 lines of JavaScript.** `visualize.md:519-1032` is a
CSS, HTML and audio engine pasted into the prompt. It is read on every
`/visualize` call whether or not narration is wanted.

**`/estimate` describes a gate that has not existed for two generations.**
`estimate.md:151` and `estimate.md:288` say "the clean-rag research gate blocks
the edit until a triage-agent or research-agent has run this turn". The gate
exits 0 on every path, and CLAUDE.md records that the triage tier was removed.
`/estimate` never edits code, so the gate is irrelevant to it either way.

## Why it is a problem

Duplicated mechanism drifts. The `/graph` table now has two maintenance points,
and `/workspace`'s copy already lacks the gap analysis that makes the original
worth running.

Two review pipelines is the sharper one. A person asking for a code review gets
`/xray`'s letter grade or bad-cop's stamp depending on which they typed, and the
verifier gate only recognises one of them. `clean-rag/hooks/verifier_state.py`
stamps on `VERIFIED:`. An `/xray` run producing `Grade: A` satisfies nothing,
and nothing tells the user that.

## What to do instead

Have `/workspace` call `/graph` at its Phase 4.6 instead of reimplementing it,
and cut `graph.md:97-183` down to a worked example, keeping Phases 5 and 6.

Make `/explore` a thin front end for `/workspace`'s ticket analysis, or merge
it. Delete one of the two `plan.md` templates. `.claude/commands/walkthrough.md`
is the shape to copy: 23 lines that parse arguments and hand off to the skill
holding the real logic.

Split `/qa`'s General Mode into its own command. `debug.md:666,677` points at
`/qa --code` and `workspace.md:829` invokes `/qa`, so both entry points have to
survive.

Move `visualize.md:519-1032` to a file on disk and reference it.

Delete `estimate.md:151` and `estimate.md:288`.

Decide `/xray`. Either its 15 pass architecture becomes how bad-cop works, or
CLAUDE.md names it as the alternative and says what its grade does and does not
satisfy. Leaving both undocumented against each other is the current state and
the worst of the three.

## What it would break

`workspace.md:606` names `/explore` as a callable step, and `workspace.md:829`
and `:838` invoke `/qa` and `/visualize` in an auto execution pipeline. Every
merge has to keep those entry points resolving.

`debug.md:666,677` recommends `/qa --code`.

`/graph` has Phases 5 and 6 that `/workspace` never had. Merging toward
`/workspace`'s copy would lose them, so the merge has to go the other way.

## Open questions

Which of `/xray` and the cop loop is authoritative. This is a product decision,
not a code one, and the audit could not settle it. `/xray`'s 15 passes are
genuine capability that bad-cop does not have; bad-cop's stamp is what the
verifier gate reads. Whoever decides should say what an `/xray` grade is worth
when the Stop hook asks for a stamp.

Whether `/graph` survives as its own command once the scope map is folded in.
Phases 5 and 6 might belong to `researcher`, which already owns the import graph.
