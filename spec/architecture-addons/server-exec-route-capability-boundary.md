# The routes that execute project code have no capability the caller must hold

- **Kind:** architecture-addon
- **Area:** server
- **Found by:** adversarial review on 2026-09-07, against `/register-project`
- **Why it was not fixed in place:** adds a new architectural layer (a
  capability the operator issues and every existing caller must present), and
  changes a contract three shipped hooks depend on.

## What is there now

`/run-tests`, `/mutation-test` and `/security-scan` execute whatever the target
directory supplies. `clean-rag/server/app.py:885` says so plainly:

```
    That last sentence is true and is not a safety claim, so do not read it as
    one. Every command here hands control to the project anyway: ``npm test``
    runs whatever ``scripts.test`` says, ``npx`` runs whatever is in the
    project's node_modules, and ``pytest`` imports the project's conftest.py.
```

The control on that is `_registered_project_or_error`
(`clean-rag/server/app.py:777`): the `project_path` in the request body must
already appear in `state/projects.json`.

Two things write that file. `indexing._update_project_registry`
(`clean-rag/server/indexing.py:1448`) writes an entry after actually walking
and embedding the directory. `/register-project` used to write one straight
from the request body with no directory check and no index behind it; that
route is gone as of this change (`clean-rag/server/app.py`, route table at
`:1505`), which is what closed the immediate hole.

What remains is that `/index-project` (`clean-rag/server/app.py:501`) is itself
an unauthenticated route taking `project_path` from a request body. It requires
the directory to exist (`app.py:512`) and it does real work, but the caller
still chooses the path. So the sequence "POST /index-project on a directory I
control, then POST /run-tests on it" is still available to anything that can
reach the port.

`local_origin_middleware` (exercised by
`clean-rag/tests/test_exec_routes_require_registered_project.py:462`) refuses a
cross origin browser request and a rebound `Host`, so the caller has to be a
local non browser process. That is not hypothetical here:
`clean-rag/hooks/research-agent-bash-guard.py:28` cages that agent's Bash to
`curl` against this server and nothing else, and that agent reads untrusted web
pages by design.

## Why it is a problem

The gate's own docstring is careful to claim only that it "narrows a request
body value". That is accurate, and it is less than what an allowlist sounds
like. An agent whose entire sanctioned capability is "curl 127.0.0.1:8613" can
still reach arbitrary code execution outside its cage in two calls, because
registering a directory and executing from a directory are guarded by the same
thing: nothing the caller has to hold.

This has already produced one real defect at this exact seam. A reproduction
registered an attacker directory and ran its `package.json` test script through
the real handlers, producing the side effect file, with the first version of
the gate in place.

Removing `/register-project` raised the cost of that chain from one free POST
to one POST plus an index. **Measured, that is not a meaningful cost.**
`clean-rag/tests/test_index_then_run_tests_registry_escalation.py` drives the
whole chain and prints what it took:

```
[measured] index-project(1 code file) -> run-tests round trip: 1.817s to
become a registered, runnable project. files_indexed=0
run_summary='npm test: passed'

[measured] files_indexed=0 was enough to register and then run tests: True
```

Timed twice on the same machine, at 0.605s and at 1.817s. The spread is
scheduling noise and neither number is the interesting one; both are inside a
single interactive request.

Two things in that output matter more than the seconds. `files_indexed=0`
means the directory does not have to contain anything the indexer recognises
as code: `package.json` is not in `CODE_EXTENSIONS`
(`clean-rag/server/file_scan.py:32`), so a single JSON file naming a command
registers and runs. And the resulting entry in `state/projects.json` is shaped
exactly like a legitimate one, so nothing downstream can tell them apart.

Read the earlier sentence about raising the cost as "one extra round trip of
under two seconds", not as "an attacker now needs a codebase".

## What to do instead

Give the executing routes a capability the operator issues and a request cannot
mint. The smallest shape that fits how this server is already deployed:

- A token generated at first start into `clean-rag/state/`, readable only by
  the user the server runs as, alongside the existing files there
  (`clean-rag/server/config.py:57`).
- `_registered_project_or_error` (or a sibling) additionally requires the token
  on `/run-tests`, `/mutation-test`, `/security-scan`. Nothing else changes:
  search and indexing stay open, because neither executes project code.
- The callers that legitimately need it read it from the same path they already
  resolve `CLEAN_RAG_HOME` from.

Files: `clean-rag/server/app.py`, `clean-rag/server/config.py`,
`clean-rag/hooks/auto-test-gate.py`, and whichever agent definitions document
the `/run-tests` call.

## What it would break

- `clean-rag/hooks/auto-test-gate.py` posts the session's git root to
  `/run-tests` on every Stop. It is the one Stop hook in this family that
  genuinely blocks, so a token it cannot read turns into a hook that either
  fails open silently or blocks every turn. Named at
  `clean-rag/tests/test_exec_routes_require_registered_project.py:311`.
- `clean-rag/hooks/research-agent-bash-guard.py:202` allows `curl` to the local
  server by host only. A token in a header is fine there; a token in the URL
  would land in `clean-rag/state/search-log.jsonl`, which is exactly the
  "secrets in URLs" rule this project bans.
- Any agent or skill markdown that hands a bare `curl .../run-tests` line to a
  model. `clean-rag/tests/test_skill_rag_routes.py` checks that those URLs
  resolve against the real router, so it will not catch a missing header.
- Every existing install: a server that starts requiring a token that no
  installed hook sends breaks testing on upgrade unless the token is generated
  and the hooks are updated in the same change.

## Open questions

- Whether the residual is worth a token at all. The gate's own docstring notes
  that "any process already running as this user can do anything this server
  can", which is true and makes a filesystem readable token a boundary only
  against callers that are deliberately caged, not against arbitrary local
  code. The caged research agent is precisely such a caller, so the answer is
  probably yes, but it should be decided on that basis and not on a general
  appeal to defence in depth.
- Whether `/index-project` should require it too. It executes nothing, but it
  is what puts a path in the registry, so leaving it open leaves the two step
  chain intact for anything that can pay the indexing cost.
- Whether the token belongs in `state/` at all, given `state/` is where the
  search log and the registry live and is not otherwise treated as secret.
