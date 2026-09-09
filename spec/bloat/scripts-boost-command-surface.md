# /boost and its supporting scripts

- **Kind:** bloat
- **Area:** scripts
- **Found by:** the human, confirmed by the orchestrator, 2026-09-07
- **Why it was not fixed in place:** removing a feature entirely, and one of the
  files is a live hard-blocking hook wired into the user's `settings.json`.
  Deleting in the wrong order leaves workspace creation permanently blocked.

## What is there now

`/boost` is the documented entry point for a session.
`docs/USING-CLAUDEBOOST.md` opens with "Open any project in Claude Code and run
`/boost`. That starts the RAG server, primes the session, and shows recent
workspaces."

It takes three forms, per `.claude/commands/boost.md:2`:

| Argument | What it does |
|---|---|
| `true` | turn on the always-on rules |
| `false` | turn them off |
| `verify` or empty | health check, then optional auto-repair |

The `verify` path is the substantial one. `.claude/commands/boost.md:33-60` runs
`scripts/boost-run.py verify`, reads a `=== BOOST_SUMMARY ===` JSON line, and
acts on seven fields: `rag_ready`, `healed_scopes`, `missing_hooks`, `rules_ok`,
`mode`, `active_workspaces`, `project_cwd`. It then checks the state files and
whether `edge_tts` imports.

The surface is nine files:

```
.claude/commands/boost.md              the command, 10.5KB
scripts/boost-run.py                   414 lines, the health check and repair
scripts/boost-inline.py                47 lines
scripts/matrix-boost.py
scripts/boost-banner.sh
scripts/workspace-boost-gate.py        40 lines, LIVE HOOK, hard block
scripts/tests/test_boost_run.py
scripts/tests/test_boost_inline.py
scripts/tests/test_matrix_boost.py
scripts/tests/test_workspace_boost_gate.py
```

## Why it is a problem

**Its health check points at a server that was deleted.** `scripts/boost-run.py`
sets `PORT = 8612`. That server was removed; `clean-rag/CLAUDE.md` records the
removal and says any remaining text naming 8612 is stale. Verified live:
`curl http://127.0.0.1:8612/status` is connection refused, `8613` answers.

So `step_rag()` always fails, `rag_ready` is always `false`, and
`boost-run.py:374` prints a banner headed `--- RAG (port 8612) ---`. The command
whose job is to tell you the system is healthy cannot report a healthy system.

Five comments in that same file (`boost-run.py:91,114,164,180,205`) already
describe 8612 as "the retired server". The constant contradicts the file's own
comments.

**`clean-rag/DEPRECATION_PLAN.md:98` already lists `boost-run.py` for cleanup**
as part of the 8612 removal. The plan was written and the item was never done.

**One of the files is a live hard block, and its stated reason is also stale.**
`scripts/workspace-boost-gate.py` is registered in `~/.claude/settings.json` as a
PreToolUse hook on `Bash(mkdir*workspace*)`, installed by
`scripts/setup.py:727-731`. It exits 2, a hard refusal, unless `/boost` has left
a sentinel at `$TEMP/claudeboost_rag_ok`. It is one of the few genuine blocks in
the whole system.

Its docstring gives the reason: "the RAG index is unverified and POST /context
won't load correctly into the workspace". `/context` was a route on the deleted
8612 server. So the gate blocks workspace creation to protect a call that no
longer exists, and the only way to satisfy it is a command whose health check
cannot pass.

**This is the fourth live defect traced to one removal.** The 8612 server was
deleted and its dependents were never swept:

1. `/register-project` remained, writing the registry any request could poison,
   which became the precondition for a remote code execution. Removed 2026-09-07.
2. `boost-run.py`'s health check, above.
3. `scripts/uninstall.py:472` `stop_rag_server()`, which shells `restart-rag.py`,
   whose process pattern matches nothing, so it silently does nothing.
4. This gate's rationale.

The pattern is the finding, not any one item. A subsystem was deleted without a
sweep of what named it.

## What to do instead

Remove the surface. Order matters, because of the gate.

1. **Unwire the hook first**, from `~/.claude/settings.json` and from
   `scripts/setup.py:727-731`, so a fresh install stops adding it. Deleting
   `workspace-boost-gate.py` while the hook entry survives leaves every workspace
   creation blocked by a missing script.
2. Delete the nine files listed above.
3. Remove `/boost` from the docs that present it as the entry point:
   `docs/USING-CLAUDEBOOST.md`, `docs/CLAUDEBOOST-REFERENCE.md`, and
   `.claudeboost/knowledge/architecture.md`. Those tell a new user to start with
   a command that will not exist.
4. Tick off the `boost-run.py` line in `clean-rag/DEPRECATION_PLAN.md:98`.

The alternative, if the workspace gate is wanted on its own merits, is to keep it
and repoint it at a real `8613` `/status` check rather than a sentinel that only
`/boost` writes. That is a different feature with the same name, and it should be
decided on whether anyone wants the block, not on whether the file already
exists.

## What it would break

- **Workspace creation, if step 1 is skipped or done last.** This is the only
  ordering that actually matters.
- **`scripts/setup.py`** installs the hook at `:727-731` and seeds the sentinel
  logic at `:1302`. Both need removing or the installer re-adds what was deleted.
- **The documented onboarding path.** Three docs open with `/boost`. A new user
  following them hits a missing command. Whatever replaces the first step needs
  writing, even if that is just "run `/rag`".
- **Four test files** covering the deleted scripts. They go with the code.
- **`tests/test_badcop_adversarial_mcp.py` and `scripts/tests/test_fix_hooks.py`**
  both reference boost. Check whether they assert on it or merely mention it
  before deleting anything.
- **Nothing else.** `/boost` is not called by any hook, agent, or skill other
  than the workspace gate. `scripts/setup.py` is the only non-test caller.

## Open questions

- Does anyone actually want a hard block on workspace creation? The gate exists,
  but its reason is gone. If the answer is no, this is a clean delete. If yes, it
  needs a real health check behind it and that is a small build, not a removal.
- Is `/boost true` / `/boost false` used? The always-on rules toggle is a
  separate concern from the health check that shares the command name, and it may
  deserve to survive as something else.
- `scripts/matrix-boost.py` and `scripts/boost-banner.sh` were not investigated
  beyond their names. Confirm what they do before deleting them, rather than
  assuming the prefix means they belong to this feature.
