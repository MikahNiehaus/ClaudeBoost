# bad-cop is two agents in one file, and every spawn loads both

- **Kind:** bloat
- **Area:** hooks
- **Found by:** audit of the skill and capability surface, 2026-09-11
- **Why it was not fixed in place:** splitting an agent changes the spawn
  contract that CLAUDE.md and every QA caller uses.

## What is there now

`clean-rag/portable/agents/bad-cop.md` is 1308 lines. It holds two agents,
selected by a string in the spawn prompt.

Mode A is lines 1 to 1036: adversarial QA on a diff, stamping `VERIFIED:`,
`NITS:` or `HANDOFF:`.

Mode B starts at line 1037, `# Mode B: QA evidence judge`. Entry is gated on the
spawn prompt saying `MODE: evidence-judge`. It judges a finished `/qa` session's
artifacts and stamps `FULLY VERIFIED:` or `TEST AGAIN:`. 272 lines.

The file says the two are disjoint. Line 1262: "Never emit a `VERIFIED:` or a
`HANDOFF:` line in" Mode B. The stamp vocabularies do not overlap, the inputs do
not overlap, and neither mode's method is useful to the other.

Roughly, within Mode A:

| Part | Lines | Share |
|---|---|---|
| Core method: scope resolution, operating rules, verification, output format | 39-234, 433-514, 845-878 | 27% |
| Surface checklists: UI, auth, money, SQL, subprocess, concurrency, migrations, templates, retry, static analysis | 262-432, 567-795 | 32% |
| Policy already stated in CLAUDE.md | 796-835, 879-907, 928-982 | 13% |

Lines 928-982 restate the three stamp contract nearly sentence for sentence
from `CLAUDE.md:79-155`.

## Why it is a problem

An agent definition is loaded in full on every spawn. So every `/qa` evidence
judge spawn reads 1036 lines of adversarial testing method it will not use, and
every code review spawn reads 272 lines of artifact auditing it will not use.
That is paid per spawn, and bad-cop is the most frequently spawned agent in the
system by design, since CLAUDE.md calls for it after any real code change.

The restated policy is worse than merely redundant. It is a second copy that can
drift from the first, on the one contract the verifier gate mechanically depends
on. `clean-rag/hooks/verifier_state.py:39` sets `VERIFIER_MARKER = "VERIFIED:"`,
so if the two copies ever disagree about when that line is emitted, the gate
follows whichever one the agent happened to read.

## What to do instead

Split Mode B into its own agent file. The cost is one call site convention,
changing a `MODE:` string into an agent name. `CLAUDE.md` names the current
contract in both copies ("spawn `bad-cop` with `MODE: evidence-judge`"), and
`/qa` spawns it that way.

Cut 928-982 to the mechanical fact and a pointer: the stamp is invalidated once
the file's mtime passes it, see `verifier_state.py`. Leave the policy in
CLAUDE.md, which is the copy the orchestrator reads.

Consider moving the surface checklists to a preloaded skill, the way
`researcher.md` preloads `codebase-understanding`. Skills sync by
`shutil.copytree` rather than the mtime gated path that
`spec/architecture-changes/docs-instruction-file-duplication.md` found silently
skips hand edited files, so a skill is less drift prone here than inline prose,
not more.

Files: `clean-rag/portable/agents/bad-cop.md`, both `CLAUDE.md` copies,
`.claude/commands/qa.md`.

## What it would break

Every caller passing `MODE: evidence-judge`. At minimum both CLAUDE.md copies'
"Every QA session ends with bad-cop judging it" section, and `/qa`.

The split must keep `FULLY VERIFIED:` and `TEST AGAIN:` as the new agent's only
stamps, since `verifier_state.py:48-50` already distinguishes the two modes'
markers and treats neither Mode B stamp as satisfying the code verifier gate.

Shrinking the CLAUDE.md copy of the loop has a real tradeoff in the other
direction. Agent files load only when that agent spawns, so the orchestrator's
own reason for handing off to good-cop rather than self fixing lives only in
CLAUDE.md. Cutting it there removes the reasoning from the only context that
reads it.

## Open questions

Whether the surface checklists belong in bad-cop at all or in a skill both cops
preload. good-cop needs the same knowledge of what makes auth or money code
dangerous, and currently has its own shorter version.

Whether a 1308 line agent definition is followed in full. The audit measured
size, not compliance. Nothing here shows which sections a spawned bad-cop
actually acts on, and that would need a real measurement rather than a reading.
