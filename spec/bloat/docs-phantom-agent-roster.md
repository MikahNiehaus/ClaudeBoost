# The documented agent roster is mostly agents that do not exist

**Status:** README corrected. `CLAUDE.md` and `docs/CLAUDEBOOST-REFERENCE.md`
still wrong, and both are load bearing.

## What exists

Six, in `~/.claude/agents/`, installed from `clean-rag/portable/agents/`:

```
bad-cop  good-cop  quick-cop  research-agent  researcher  swiper
```

Confirmed against the live agent directory and against the spawnable agent list
Claude Code itself reports. Claude Code's own built-ins (`Explore`, `Plan`,
`general-purpose`) sit alongside them.

## What is documented

`README.md` listed 23. Eighteen have never existed:

```
architect-agent          reviewer-agent           ticket-analyst-agent
debug-agent              test-agent               security-agent
performance-agent        refactor-agent           ui-agent
docs-agent               explore-agent            browser-agent
e2e-agent                workflow-agent           compliance-agent
standards-validator-agent estimator-agent         devops-agent
database-agent           observability-agent      rag-indexing-agent
```

Plus `evaluator-agent`, swept separately on 2026-09-08.

`docs/CLAUDEBOOST-REFERENCE.md` goes further and gives several of them a file
path, `agents/<name>.xml`. There is no `agents/` directory in the tree and
**zero `.xml` files anywhere outside the venv.** Section 3.17 was rewritten to
describe `quick-cop`; 3.18 and its neighbours were not.

## Why this is not just stale prose

Three of these names appear in text that is injected into a live session or
routed on:

- `CLAUDE.md` and `clean-rag/portable/CLAUDE.md`: *"Specialist agents
  (architect, reviewer, debug, security, performance, refactor, ui, docs, test,
  and the rest) are available for focused work."* They are not available. A
  model that believes this will try to spawn one.
- `CLAUDE.md`, Model Routing: *"Opus: architect-agent, reviewer-agent,
  ticket-analyst-agent, good-cop."* Three of four do not exist.
- `.claude/commands/workspace.md` asks the model to pick agents from a roster
  for each work type.

The failure mode is not a broken build. It is a spawn that falls back to a
generic agent, silently, while the session believes it got a specialist.

## The detector already exists and nothing runs it

`scripts/audit-hooks.py` flags any `*-agent` or `*-cop` name in a hook prompt
that is not installed. Run by hand on 2026-09-08 it found the live
`evaluator-agent` site on the first try, and reported clean after the fix.

Nothing invokes it. Not the test suite, not the installer, not a hook. Same
shape as the dead 8612 port: the check was not missing, it was unwired.

## The decision for the human

Three options, and this is the reason it is filed rather than fixed.

1. **Correct the docs to the six that exist.** Cheapest. Loses the roster as a
   statement of intent.
2. **Build the missing agents.** They are plausible and several are genuinely
   useful, but that is a real project, and the current six already cover
   research, swipe, review, fix and claim checking between them.
3. **Correct the docs AND wire the detector**, so the class cannot come back:
   run `audit-hooks.py` from the test suite, and extend it from hook prompts to
   `CLAUDE.md`, `.claude/commands/` and `docs/`.

Option 3 is the recommendation. The first half is an hour of editing; the second
half is what stopped the dead port recurring, and it is the same fix shape.

## Related

- `spec/STATUS.md`, the 8612 sweep, for the identical pattern
- `clean-rag/DEPRECATION_PLAN.md`, for the `evaluator-agent` sweep and the two
  live defects it turned up
- `docs/FIXING-STALE-HOOKS.md`, which already describes this exact failure and
  uses `evaluator-agent` as its worked example
