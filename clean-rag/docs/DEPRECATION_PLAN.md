# Deprecation Plan: retire port 8612, knowledge/, agents/, and the three research commands

Mapped by two exploration passes over the whole repo. This is the plan for
approval before any execution.

## What you asked for

1. Remove `/research-rag`, `/research-task`, `/research-project`.
2. Stop using the ClaudeBoost RAG server (port 8612); use only clean-rag (8613).
3. `knowledge/` (109 files) and `agents/` (25 XMLs) are dead weight now; research
   setup primes better.
4. Anything that used the KB should spawn research-agent instead.

## The blast radius (why this is not a delete)

Port 8612 is referenced in ~90 files, ~380 lines. `knowledge/` and `agents/` are
RAG collections read through that server. Three findings are load bearing:

- **`mcp-rag-server/config.py:9-18` defines the repo root as "the dir containing
  both agents/ and knowledge/".** Delete both and the server can't find
  PROJECT_ROOT at all. Hard break, must be fixed first or the server won't boot.
- **`/context` has no clean-rag equivalent.** clean-rag does project search, web
  search, indexing. There is no knowledge/agents context endpoint on 8613.
- **The 24 specialist agents exist ONLY as `agents/*.xml`.** `/context` Tier 0
  reads `agents/<name>.xml` off disk and injects it as that agent's brain. This
  is the thing worth pausing on, see the decision below.

Good news that shrinks the work:
- The agent-spawn gate is **already a no-op stub** on this branch. Nothing live
  enforces "call /context first". Only stale prose and one registry entry remain.
- `/research-rag` is **already gone**. Only its name lingers in docs.
- Slash command sync is glob based, so deleting a command file just stops it
  syncing, no code edit needed.

## DECISION MADE: Plan B

Keep the 24 specialist agents. Kill knowledge/ and the 8612 server. Prime the
specialists from research-agent instead of the dead KB.

Consequence for Phase 3: keeping the specialists while removing /context means
each agent needs its definition delivered without /context Tier 0. The clean way
is to convert `agents/*.xml` into native Claude Code subagents at
`~/.claude/agents/*.md` (same format as research-agent and triage-agent), bundled
into `clean-rag/portable/` so they travel to a new machine. That replaces the
/context Tier 0 mechanism entirely.

Executing in staged phases, verified between each, NOT as one big bang. A change
this wide bricks the toolkit if rushed.

## The one decision only you can make

You said the agents are "useless now because research primes them better." That's
true for the *research/priming* function. But `agents/*.xml` isn't priming, it's
the actual definition of 24 specialists: reviewer-agent's 15 pass logic,
architect-agent's SOLID review, debug-agent's root cause workflow, and so on.
research-agent does not contain any of that. It researches; it doesn't review or
architect.

So deleting `agents/` means those 24 specialists lose their instructions. The
commands that spawn them (`/workspace`, `/audit`, `/xray`, `/debug`, `/qa`,
`/security-review`, `/create-prd`, and more) would spawn a generic agent with no
specialist behavior.

**Two readings of your intent, and they lead to very different plans:**

- **A. Kill the whole old agent system.** You're moving to a research-first flow
  where the main model does the specialist work directly, informed by research,
  and you don't want 24 separate agent personas anymore. Then deleting `agents/`
  is correct and the commands that spawn them get rewritten or removed too.
- **B. Kill only the KB and the 8612 server, keep the specialist agents.** The
  agents stay as spawnable specialists; they just stop being primed by the dead
  KB and get primed by research-agent instead. Then `agents/` stays, and only
  `knowledge/` + the 8612 server + `/context`'s knowledge tiers go.

I need you to pick A or B before I touch agents/. Everything else is the same
either way.

## Phase 1: safe now, clearly redundant (low risk, no decision needed)

- Delete `.claude/commands/research-task.md` and `research-project.md`.
- ~~Remove `scripts/research-task-nudge.py` (a whole UserPromptSubmit hook that
  nags you to run a command that will no longer exist), its install block in
  `setup.py:820-823`, and its test.~~ **Done 2026-09-16.** The install block and
  the test were already gone when this was picked up; only a comment at
  `setup.py:953` records the removal. The file itself had been emptied to 0
  bytes rather than deleted, and was registered in neither settings file. Now
  deleted.
- Clean dangling references to the already-dead `research-rag-agent`,
  `research-task`, `research-project` in: `knowledge/skill-routing.xml`,
  `scripts/skill-verify-gate.py`, `agents/_orchestrator.xml`,
  `scripts/session-primer.py`, `scripts/workspace-primer.py`,
  `scripts/action-gate.py`, `scripts/prompt-rules-injector.py`, and the doc
  cross links (`CLAUDE.md`, `README.md`, `docs/`).
- Fix the last stale proof reference at `docs/CLAUDEBOOST-REFERENCE.md:1093`.

## Phase 2: retire the 8612 server (both A and B)

- `config.py:9-18`: change root detection so it does NOT require `knowledge/` (and
  `agents/` too if plan A). Key it on `.git` or `CLAUDEBOOST_HOME` instead. This
  is the must-fix-first item.
- Stop launching 8612: `scripts/rag-server-start.py`, `rag-supervisor.py`
  (drop the 8612 child, keep the 8613 child), `restart-rag.py`, `boost-run.py`,
  `session-primer.py` auto-start, `setup.py:install_rag_server` and
  `_seed_rag_index`, `rag-statusline.py`.
- `context-nudge.py:52,252,255`: the `_is_http_rag` check keys on the literal
  `8612` string; repoint to 8613 or drop.
- Repoint `/context` consumers. Since clean-rag has no `/context`, every command
  and hook that calls `/context` for priming either drops the call or switches to
  a clean-rag project search. This is the biggest mechanical chunk (20+ commands,
  several hooks, the orchestrator template).

## Phase 3: delete knowledge/ (both A and B) and agents/ (plan A only)

- Delete `knowledge/`. Remove the `knowledge` collection from `config.py`, the
  Tier 1 guardrail hardcodes in `tools/context.py:133-136`, `/index-boost`'s
  knowledge step, and every `knowledge/*.xml` pointer in `CLAUDE.md` and commands.
- (Plan A only) Delete `agents/`. Remove the `agents` collection, `/context`
  Tier 0, and rewrite or remove every command that spawns an XML agent.
- (Plan B) Keep `agents/`. Repoint each agent's "FIRST ACTION call /context" rule
  to either nothing or a clean-rag project search, since 8612 is gone.

## Phase 4: rewrite the story

`CLAUDE.md` (the "25 agents / 109 knowledge / 8612" sections), `README.md`, and
`docs/` all describe the old system. Rewrite to the clean-rag research flow.

## Verification

- The clean-rag server (8613) still starts and serves search after config.py
  changes.
- No command references a dead endpoint (grep for `8612`, `/context`,
  `all_topics`, `/index-topic`, comes back clean or intentional only).
- Spawn one agent that a command uses, confirm it still works under whichever
  plan (A: gone/rewritten, B: still has its definition).
- Fresh install dry run: `setup.py` runs without launching 8612 and without
  indexing a now deleted knowledge/.


---

# Status, 2026-09-08: the `scripts/` sweep is done

The plan above was written and then not finished. That gap is not a tidiness
problem, it is where four live defects came from: `session-primer.py` (a
UserPromptSubmit hook) spent months injecting "call `POST
http://127.0.0.1:8612/search`", "`GET :8612/status`" and "call `POST
:8612/context` as first step in every agent spawn prompt" into the model's
context on **every prompt**. Nothing failed loudly. The calls returned
connection refused and the session carried on with no context.

Verified before touching anything: `curl http://127.0.0.1:8612/status` is
connection refused (exit 7); 8613 answers.

## Done

Live code that called the dead port:

- `scripts/session-primer.py` `_get_rag_status()` now GETs 8613. The address is a
  single `RAG_BASE_URL` constant, because the port was named at five separate
  sites in that file and each went stale on its own.
- `scripts/rag-statusline.py` `RAG_HTTP_PORT = 8612` deleted. It was read
  nowhere in the repo.
- `scripts/rag-index-safe.py` deleted. Nothing referenced it, it POSTed to
  `/index` which no longer exists, and its payload carried an unconditional
  `force: true`. Repointing it would have created a live 30-plus minute reindex
  entry point that nothing calls.

Instruction text injected into sessions:

- `session-primer.py` rule (E) and standing orders (1), (2), (6), (7): repointed
  to 8613 and rewritten to the real contract, `sources: ["project:<abs path>"]`
  with `mode: "both"`. The old text told the model to send `scope=codebase` and
  to run `mode=vector` and `mode=graph` as two separate calls; `scope` is not a
  parameter of any clean-rag route, and `mode: "both"` is the documented way to
  get both walks in one call.
- `session-primer.py` rule (G) "Dynamic RAG tiers" deleted outright. It described
  Tier 3/3c/4 loading through `POST /context`. There is no replacement.
- `session-primer.py` workspace dashboard: the `POST /context` params block and
  the "RAG TIER STATUS" rows for Tier 5 research and Project KB are gone. Both
  read directories belonging to the deleted knowledge base.
- `workspace-primer.py`: the whole tier briefing removed, including the `POST
  :8612/context` call and the Tier 0-4 token budget. What survives is the part
  that never depended on that server: which workspace is active and where.
- `compaction-primer.py`: the `/context` line dropped; the surviving RAG order
  now names `8613/search` with its real body.
- `rag-read-guard.py`: repointed, and `rag_search(scope='codebase', ...)`
  replaced. That named both a tool and a parameter that no longer exist.
- `reindex-check.py`: `/index` to `/index-project`, which takes the same body.

Stale prose in otherwise-correct modules: `clean-rag/server/app.py` docstring
(the "/clean-rag/* on port 8612" bundled-mode line) and
`clean-rag/server/config.py`'s port comment.

## A second defect, found by the same sweep

`session-primer.py`'s dashboard read `rag_status['indexed_projects']`. That key
belonged to the retired server. clean-rag returns `projects.entries`, keyed by
project id, with `files_indexed` and `chunks_created`. The lookup therefore
missed every time, and the hook emitted "REQUIRED BEFORE RESPONDING: CODEBASE
NOT INDEXED, run index-project as your FIRST action" for projects that were
fully indexed. Reproduced against the live server with a real 299-file project,
fixed, and re-run.

Its two tests did not catch it because they asserted `"READY" in result or
"task-codebase" in result`, and the workspace id is in the dashboard
unconditionally. They now assert the rendered line.

## Deliberately NOT done, and why

- **`scripts/boost-run.py`** still has `PORT = 8612` (line 38) and prints
  `--- RAG (port 8612) ---` (line 380). Real debt, left alone on purpose: the
  file is the subject of a pending human decision in
  `spec/bloat/scripts-boost-command-surface.md`, and one of its siblings is a
  live hard-blocking hook.
- **`scripts/uninstall.py:472`** `stop_rag_server()` silently does nothing. It
  shells `restart-rag.py`, whose process pattern is `*rag_server*`, but the
  server runs `clean-rag/server/__main__.py`. Outstanding; owned elsewhere at
  the time of this sweep.
- **`scripts/action-gate.py:138`** still describes a "ClaudeBoost KB" tier in its
  template. The KB was deleted; that prose is stale. Not in this sweep's scope.
- **Comments and docstrings naming 8612** in `context-nudge.py`,
  `prompt-rules-injector.py`, `setup.py` and `boost-run.py` are untouched by
  design. They explain what was removed and why, which is what stops the next
  reader rebuilding it.
- **`evaluator-agent`** was named across 25 tracked files including live hook
  text, and no such agent has ever existed (`bad-cop`, `good-cop`, `quick-cop`,
  `researcher`, `swiper` do). Same class of defect as this one, larger blast
  radius. **Swept 2026-09-08.** Every site now names the agent that does that
  job: `quick-cop` for checking whether a finding or a completion claim is
  true, `bad-cop` with `MODE: evidence-judge` for judging QA artifacts.

  Two live defects came out of it, neither of which was the name itself:

  - `scripts/skill-verify-gate.py` refused action skills (`exit 2`) and told
    the operator to spawn the phantom. The flag it waited on cleared only when
    a Task description happened to contain the literal word "evaluator" or
    "verdict", so following the instruction verbatim could not clear it. It now
    nudges rather than refuses, and `verify-gate-cmd.py` recognises real agents
    by `subagent_type` using the same resolution order as `research-record.py`.
  - The same hook crashed (`exit 1`, `AttributeError`) on a payload of `null`,
    `[]`, a bare string or a number, because `json.loads` accepts any JSON
    value. It had no test file at all; it has one now.

  The detector for this already existed. `scripts/audit-hooks.py` flags any
  `*-agent` or `*-cop` name in a hook prompt that is not installed, and it
  found the live site immediately. Nothing had ever run it. That is the real
  lesson here, and it is the same one as the dead port: the check was not
  missing, it was unwired.

## What stops this drifting again

`clean-rag/tests/test_skill_rag_routes.py` already failed on any `.claude/commands/`
file naming a retired port or an unserved route. It now applies the same contract
to the **runtime string literals** of `scripts/`, `clean-rag/hooks/` and
`clean-rag/server/`, checked against the live aiohttp router.

Docstrings and comments are exempt by construction: comments never reach the AST,
and docstrings are skipped by position. So the historical record survives while
the injected instruction text is held to the real route table. The hostless form
(`POST /context` with no host on the line, which is how these survived the port
migration) is checked too.
