# Four RAG commands still drive the 8612 server and its scopes

- **Kind:** bloat
- **Area:** cli
- **Found by:** audit of the skill and capability surface, 2026-09-11
- **Why it was not fixed in place:** removing two commands and folding a third
  into a fourth. `/boost` additionally owns a live hard blocking hook, so its
  removal has an order that has to be got right.

## What is there now

Four commands address a server that was deleted. Each was checked against the
live one.

**`/rag`, 128 lines, dead end to end.** It starts a supervisor that does not
exist:

```
rag.md:17  scripts/rag-supervisor.py      does not exist
rag.md:25  scripts/rag-server-start.py    does not exist
```

It describes two servers:

```
rag.md:20   "the supervisor managing both the main RAG server (port 8612)
             and clean-rag server (port 8613) with auto restart on crash"
rag.md:109  "RAG live — main: port 8612 | knowledge: Xc/Yf agents: Xc/Yf
             | clean-rag: port 8613 | supervisor: auto restart active"
```

And it reads response keys the server does not return (`rag.md:64-69`:
`collections.knowledge`, `collections.agents`, `indexed_projects`).

**`/rag-health`, 304 lines, checks a response shape that does not exist.** The
live `GET /status` returns `status, uptime_s, code_embedding_model,
code_embedding_loaded, loaded_models, projects{count,entries}, clean_rag_home,
ram_mb`. The file gates on `code_model_ready` (`:33`), `dimension_mismatch`
(`:34`), `indexed_projects` (`:63, :97`), `collections.knowledge` (`:166`),
`collections.agents` (`:172`), `collections.memories` (`:211`), `dim_ok`
(`:236`). None of those keys are in the response.

**`/index-boost`, 62 lines, indexes a scope that no longer exists.** Its whole
premise is a knowledge and agents index separate from a project.
`clean-rag/CLAUDE.md`'s "Why the KB is gone" section records that deletion on
measured evidence and says not to rebuild it. Its call is also malformed. Run
against the live server:

```
POST /index-project  {"scope":"agents","force":false}
  -> {"error": "Missing 'project_path' field"}
```

**`/boost`, 295 lines, carries the same malformed call.** `boost.md:283` posts
`{"force": true}` with no `project_path`:

```
POST /index-project  {"force":false}
  -> {"error": "Missing 'project_path' field"}
```

`spec/bloat/scripts-boost-command-surface.md` already covers the rest of
`/boost`. One sub-claim in it is now stale: `scripts/boost-run.py` resolves the
port dynamically via `_rag_port()` and no longer targets 8612.

## Why it is a problem

These are the commands a person runs when search is not working. All four
mislead at exactly that moment.

`/rag` is the worst of them, because both CLAUDE.md files send people to it:
"If the server is down, run `/rag` or `clean-rag/cli/server_ctl.py start`." The
first half of that sentence points at a command whose first action is a script
that is not on disk. The second half works.

`/rag-health` reports FAIL on checks that read absent keys, so a healthy server
looks broken. That inverts the tool: it manufactures the alarm it exists to
resolve.

## What to do instead

Delete `/rag` and point its callers at `/clean-rag-server start`, which already
does the job correctly through `cli/server_ctl.py`. Callers to update:
`fix-rag.md`, `index-boost.md:32`, `done.md:23`, and the "If the server is down"
sentence in all four CLAUDE.md files.

Delete `/index-boost`. There is no scope to index. `README.md:428-455` and
`docs/HOW-IT-WORKS.md:104-127` list it and need updating with it.

Rewrite `/rag-health` against the real response, or delete it. `GET /status` is
already legible without a wrapper, and `/index-project.md` is the file in this
repo that documents the real response shapes correctly. Use it as the reference.

Fix `boost.md:283` to pass `project_path`, and take the rest of `/boost` from
the existing spec.

## What it would break

**`/boost` first.** `scripts/workspace-boost-gate.py` is a registered PreToolUse
hook on `Bash(mkdir*workspace*)` that exits 2, gated on a sentinel `/boost`
writes. Remove `/boost` before unwiring that hook and every workspace creation
blocks. `spec/bloat/scripts-boost-command-surface.md` has the order.

`/index-boost` step 5 calls `/rag-health`, so removing one touches the other.

Three documents present `/boost` as the session entry point:
`docs/USING-CLAUDEBOOST.md`, `docs/CLAUDEBOOST-REFERENCE.md`, `README.md`.

`/rag` has no dependents beyond the prose that recommends it, since nothing can
depend on a command whose scripts are absent.

## Open questions

Whether `/rag-health` should exist at all once it is honest. Most of what it
would report is one `GET /status` call, and the failure it was built to catch, a
dimension mismatch between an index and its embedding model, is now reported by
the server itself through `stale_projects` with a reason field. If that covers
it, the command is a wrapper around a curl.
