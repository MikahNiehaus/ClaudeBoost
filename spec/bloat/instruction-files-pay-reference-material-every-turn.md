# The instruction files pay for reference material on every turn

- **Kind:** bloat
- **Area:** docs
- **Found by:** audit of the skill and capability surface, 2026-09-11
- **Why it was not fixed in place:** moving sections between a file loaded every
  turn and a file loaded on demand changes what the orchestrator knows by
  default, which is a judgement about defaults rather than a repair.

## What is there now

Four instruction files, three of which are injected into a session:

```
~/.claude/CLAUDE.md                 735 lines   every session
CLAUDE.md                           664 lines   every session in this repo
clean-rag/CLAUDE.md                 268 lines
clean-rag/portable/CLAUDE.md        569 lines   the shipped copy
```

The global file was 629 lines five days before this was written and is 735 now.
It grew 106 lines, 17 percent, in under a week. That is the trend this item is
about, and it is why the split between rule and record matters more than any one
section that could be moved out.

Some of it is operative and needed every turn: the research gate, the verify by
running rule, Decision Flow, Collaborative Mode, the Hard Rules.

Some of it is a record, useful once. "Recorded decision: no blocking external
model reviewer on Stop" is a design postmortem with citations to
`abiswas97/gemini-plugin-cc` and `hamelsmu/claude-review-loop`, explaining why a
thing was not built. The "Two corrections to the advice that prompted this"
paragraph is a footnote correcting an earlier draft. The fan-out section's
`state/audit-in-progress.json` paragraph names four hook files, a removed
installer flag and a 2026-07-06 proof log date, all of which matter only to
someone debugging that gate.

That is roughly 60 to 70 lines of the 735, read on every turn, needed when
someone proposes rebuilding a specific hook.

**A dead claim sits in all three copies.** The Model Routing section:

```
CLAUDE.md:469                     - **Opus**: architect-agent, reviewer-agent,
~/.claude/CLAUDE.md:495              ticket-analyst-agent, good-cop.
clean-rag/portable/CLAUDE.md:411
```

Three of those four agents do not exist.
`spec/bloat/docs-phantom-agent-roster.md` already files this, and this audit
adds one thing it does not cover: the line is triplicated, so a fix has to land
in three files or the mtime gated sync in
`spec/architecture-changes/docs-instruction-file-duplication.md` will silently
leave two of them wrong.

## Why it is a problem

The phantom Opus routing is the concrete cost. A spawn of `architect-agent`
does not error. It resolves to a generic agent while the session believes it got
a specialist, which is the failure mode the roster spec already names.

The reference material is a smaller, steadier cost, and it is the one that
grows. Every postmortem worth writing gets written into the file that is already
loaded, because that is where it will be seen. Nothing in the file distinguishes
a rule from a record, so the distinction has to be made by a reader every time.

## What to do instead

Correct the Model Routing line in all three copies to the six agents that exist:
Opus for good-cop, Sonnet for research-agent, researcher, swiper, bad-cop,
quick-cop.

Move the recorded decisions and the correction footnotes to `docs/decisions/`,
and leave a pointer. The pointer has to name the decision, not just the file,
because the whole value of that section is stopping someone from rebuilding a
thing that was reverted twice. A bare filename will not do that.

Files: the three CLAUDE.md copies, plus a new `docs/decisions/`.

## What it would break

Nothing mechanical. No hook parses these files. `clean-rag/hooks/research-gate.py`
and `verifier-gate.py` read state, not prose.

The real risk runs the other way. A future session proposing a blocking Stop
reviewer will not see "already built and reverted twice" unless it follows the
pointer. `clean-rag/hooks/verifier-gate.py` records both reverts in its own
docstring, so the warning survives in the code either way, which is the argument
for moving it.

## Open questions

Whether the shipped `clean-rag/portable/CLAUDE.md` at 569 lines should be a copy
of the project file at all, or a much shorter file that installs alongside it.
The two are close enough to drift and far enough apart to have already drifted.

Which copy is authoritative for the cop loop. The agent files describe it from
the inside and are what a spawned agent is graded against. The CLAUDE.md copies
describe it from the orchestrator's side. Both are needed; nothing says which
wins when they disagree, and they currently do not disagree only by luck.
