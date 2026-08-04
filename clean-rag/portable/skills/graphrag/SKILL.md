---
name: graphrag
description: Build or query the semantic code graph (true GraphRAG) for a project. An LLM reads the codebase and extracts entities plus the intent behind calls, imports, and dependencies, then answers cross file "how does X flow to Y" questions the import graph can't. Manual and resumable: a build runs overnight and can be killed and continued. Use to kick off a build, check its percent progress, or ask the built graph a question.
---

# /graphrag

The always on import graph (`POST /search mode=graph`) answers structure: what
imports what, what calls what. It says nothing about *why*. The GraphRAG layer is
the slower semantic one: a local LLM reads each file and extracts entities and the
intent behind the edges, so you can ask "how does a login token reach the database"
and get the path, not just the neighbours.

It is deliberately manual. It never auto indexes, never runs on a hook. You trigger
it, it runs (minutes on a GPU, hours on CPU, both fine), it unloads the model when
done. A killed run resumes from the last finished batch, not from zero.

## Parse the argument

`$ARGUMENTS` is the argument. Read it as one of:

- **A build**: empty, `build`, a path, or "index/graph this project". Default the
  path to the current project root (the git root, or cwd).
- **A status check**: `status`, `progress`, "how far", "is it done".
- **A query**: anything phrased as a question, or `query <question>`. Run it against
  the already built graph for the current project.

If it's ambiguous, prefer status when a build is running, otherwise treat a question
as a query and everything else as a build.

## Build

```
POST http://127.0.0.1:8613/graphrag-build
{"project_path": "<abs path>"}
```

This returns immediately with `{"started": true}` (or an error). The build runs in
the background in the isolated graphrag venv and its own model process. It does NOT
block. First call also lazily starts the graph service, so the first response can
take a few seconds.

Then tell the user it's running and that they can walk away: it checkpoints per
batch and survives a kill. Poll status to report progress; don't sit in a tight
loop, this can run for hours on CPU.

Announce one line, e.g. "GraphRAG build started for `<path>`. It runs in the
background and resumes if interrupted; check back with `/graphrag status`."

## Status

```
GET http://127.0.0.1:8613/graphrag-status?project_path=<abs path>
```

Returns `{building, percent, files_done, files_total, active_version, error}`.
Report it plainly: percent done, files done over total, whether a finished build is
already queryable (`active_version` is set), and any `error`. `active_version` set
with `building: false` means a completed graph is ready to query. If the service
isn't running and nothing was ever built, say so instead of treating it as an error.

## Query

```
POST http://127.0.0.1:8613/graphrag-query
{"project_path": "<abs path>", "query": "how does the auth token reach the db?"}
```

Returns `{answer, version, error}`. A query may reload the model, so it can take a
while on the first hit after an idle period; that's expected. If the answer is
`no built graph for this project yet`, tell the user to run a build first.

Lead with the answer. This is a semantic layer, so treat its output as a lead to
verify against the code, not gospel: the import graph stays the structural
authority, and a GraphRAG claim that contradicts it is the one that's wrong.

## When the service is down

The build and query calls start the graph service on demand. If they keep failing,
the graphrag venv or Ollama isn't set up: `python clean-rag/install.py` sets up the
venv and pulls the models, and Ollama must be running. Status alone never starts the
service; it only reads a running one.

## What this is not

Not the project index. `/index-project` builds the fast vector plus import graph and
runs automatically; this is the separate, manual, heavy semantic graph. Not a
replacement for reading code. It points you at the path; you still open the files.
