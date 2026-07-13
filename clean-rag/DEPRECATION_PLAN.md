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
- Remove `scripts/research-task-nudge.py` (a whole UserPromptSubmit hook that
  nags you to run a command that will no longer exist), its install block in
  `setup.py:820-823`, and its test.
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
