# ClaudeBoost

Research gated development for Claude Code. Every code edit is researched before
it happens, and search runs over your own indexed projects, not a scraped
knowledge base.

## Where the rules actually live

The full rule set is one file, installed globally at `~/.claude/CLAUDE.md`. The
portable copy for a standalone install is `clean-rag/portable/CLAUDE.md`. Both
hold the same text.

This file used to hold a third copy, and that is why it is now a pointer.
Claude Code loads the user file and the project file together and concatenates
them with no deduplication, so every line written in both places was paid for
twice on every session and again after every compaction. Measured before the
split: the two files were 789 and 790 lines and shared 630 identical lines, and
the instructions attachment carrying them cost about 45,000 tokens each time it
was re-injected.

Neither file was a superset when they were compared, which is the part worth
remembering. Each carried roughly 160 lines the other did not, and on both sides
that content was live rules rather than local detail: the global file alone had
the clean-rag calling contract, the scratchpad and `rm` rules, the plain writing
section and the real browser scope, while this file alone had good-cop's
obligations, the lesson about execution proving only the environment it ran in,
the debugging and QA section and the plugins table. They had drifted apart in
both directions. A straight delete of the duplicate lines would have thrown away
whichever side lost, so the two were merged into the single canonical file
instead.

Keep it that way. Anything that belongs to the pipeline goes in the canonical
file, not here, or the duplication comes back one section at a time.

## Editing the rules

Change `~/.claude/CLAUDE.md`, then copy it to `clean-rag/portable/CLAUDE.md` so
a standalone install gets the same text. Nothing enforces that copy today, so it
is on you to do it in the same change.

Anthropic's own guidance is to target under 200 lines per `CLAUDE.md`, because a
longer file costs context and reduces adherence. The canonical file is well over
that and wants trimming, not extending. Two built in tools help and neither
needs anything installed: `/context` breaks down what is consuming the window by
source, and `/doctor` proposes trims for a checked in `CLAUDE.md`, cutting what
Claude can derive from the codebase and keeping pitfalls and rationale.

For anything procedure shaped or path specific, prefer a lazily loaded home over
this always loaded one. `.claude/rules/*.md` with `paths:` frontmatter loads only
when Claude touches a matching file, and a skill loads only when it is invoked or
judged relevant.
