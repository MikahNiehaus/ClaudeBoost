# Nine commands open with an index preflight that is broken in both halves

- **Kind:** bloat
- **Area:** cli
- **Found by:** audit of the skill and capability surface, 2026-09-11
- **Why it was not fixed in place:** it spans ten files and the right fix is to
  stop copying the block, which is a change to how commands are written rather
  than a repair to any one of them.

## What is there now

Nine command files open with the same pasted preflight. It checks whether the
project is indexed, then acts on the answer. Both steps are dead.

**The check reads a field the server does not return.** Four command files look
for `indexed_projects` in the `GET /status` response, across five lines:

```
.claude/commands/estimate.md:40    check `indexed_projects` for `PROJECT_PATH`
.claude/commands/estimate.md:44    Find `PROJECT_PATH` in `indexed_projects`
.claude/commands/qa.md:49          check `indexed_projects` for the detected path
.claude/commands/rag-health.md:63  Find the project in `indexed_projects`
.claude/commands/rag.md:68         `indexed_projects` — any project codebases indexed
```

The live server returns no such key. Called directly:

```json
{"status": "ready", "uptime_s": 108873.4,
 "code_embedding_model": "nomic-ai/CodeRankEmbed",
 "projects": {"count": 13, "entries": {"ascendmobile-79699337": {"project_path": "..."}}}}
```

The real path is `projects.entries.<key>.project_path`. Grepping the response
body for `indexed_projects` returns 0.

**The remedy calls a skill that does not exist.** Nine files then run:

```
Skill(skill="index-project", args="<project_path>")
```

```
.claude/commands/audit.md:37             .claude/commands/qa.md:52
.claude/commands/create-prd.md:27        .claude/commands/security-review.md:53
.claude/commands/estimate.md:47          .claude/commands/visualize.md:23
.claude/commands/explore.md:176          .claude/commands/xray.md:69
.claude/commands/graph.md:93
```

There is no `index-project` skill. No directory by that name exists under
`~/.claude/skills/`, `clean-rag/portable/skills/`, or `.claude/skills/`.
`index-project` is a slash command, `.claude/commands/index-project.md`.

A tenth copy sits in `.claude/commands/qa.md.bak-prevideo`, a tracked 2962 line
backup file that nothing loads.

## Why it is a problem

The two halves fail in a way that compounds. The check looks for a missing key,
so it concludes "not indexed" for every project including the thirteen that are
indexed. It then reaches for the remedy, which is a tool call that does not
resolve. Whatever happens next is improvised, on every invocation of nine
commands, before the command's actual work starts.

This is the failure mode a preflight exists to prevent, arriving through the
preflight itself.

It also hides a working path. `POST /index-project` is a real route and
`.claude/commands/index-project.md:84` already calls it correctly with curl. The
nine copies do not use it.

## What to do instead

Delete the pasted block from all nine files. Replace it with one line naming the
real check and the real remedy:

```
If `GET http://127.0.0.1:8613/status` has no entry under `projects.entries`
whose `project_path` matches, run `POST http://127.0.0.1:8613/index-project`
with `{"project_path": "<abs>"}`.
```

Better, put the sentence in one place and have the commands point at it.
`clean-rag/CLAUDE.md` already carries the endpoint table and is already loaded.
A preflight copied into nine files drifts in nine directions, which is how this
one reached two dead references without anyone noticing.

Files: the nine listed above, plus a decision about
`.claude/commands/qa.md.bak-prevideo`.

## What it would break

Nothing depends on the current text, because the current text does not work. The
`Skill` call does not resolve and the field lookup never matches.

The commands that wrap this block in a larger flow need their surrounding step
numbering checked: `qa.md:49-52`, `estimate.md:40-47` and `graph.md:93` embed
the preflight inside a numbered phase rather than in a preamble.

`rag.md:68` and `rag-health.md:63` are describing the status response to a human
rather than gating on it, so those two want the field name corrected rather than
the block removed.

## A second block with the same problem

The same copy-paste pattern put a workspace detection block in the wrong place
in three files. It is headed `Phase 0`, and in three of four files it sits after
the command's own final step:

| File | Lines | `Phase 0` at |
|---|---|---|
| `.claude/commands/handoff.md` | 79 | 57, after the "Next step" conclusion at 52 |
| `.claude/commands/ticket-handoff.md` | 244 | 222, after "Report to user" at 212 |
| `.claude/commands/test-hooks.md` | 54 | 32, after "When to run" at 22 |
| `.claude/commands/pr-description.md` | 209 | 13, correctly before Phase 1 |

A model reads the whole file before acting, so this is not a hard break. It is
the same defect as above in a milder form: a block pasted into four files landed
correctly in one of them, and nothing checks.

`security-review.md:17-36` and `:40-54` are a third instance, two workspace
detection blocks stacked back to back using different methods. The first calls
`scripts/get-active-workspace.py`, which every other command uses. The second
reads `state/project-workspaces.json` directly, an older method whose result the
first block has already produced.

## Open questions

Whether the preflight should exist at all in most of these commands. Indexing
happens on its own: `POST /index-project` registers a project and the server
reindexes after every edit plus a full sweep every ten minutes. A command that
searches an unindexed project gets zero results and a `stale_projects` entry
saying why, which is a clearer signal than a preflight that has been silently
wrong for as long as this one has.
