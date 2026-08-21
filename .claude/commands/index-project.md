---
description: Index a project's codebase into clean-rag for vector and import graph search
argument-hint: [path | name] [force]
allowed-tools: Bash, Read, Glob, Grep, AskUserQuestion
---

# Index a project into clean-rag

Builds two things for the target project: a vector index for semantic search, and an import graph for structural search ("what breaks if I change this"). Both live inside clean-rag. Once indexed, the project reindexes itself automatically.

This targets clean-rag on **port 8613**. It used to index into the ClaudeBoost RAG server on 8612 and merely register the path with clean-rag afterwards, which left a registry entry pointing at a project clean-rag had no data for: no vectors, no graph, and an auto reindex sweep with no manifest to diff against. Step 0 below finds those leftovers, because one of them survived and cost an hour.

## Arguments

`$ARGUMENTS` — any of:
- Empty → the current working directory
- A path → `/index-project C:/prj/MyApp`
- A short name → `/index-project LocalAI` (resolve against `clean-rag/state/projects.json` and sibling directories)
- Plus `force` → full rebuild instead of incremental

## Two rules before anything else

**Always pass an absolute path.** `handle_index_project` never calls `.resolve()` and never checks `is_absolute()` (`server/app.py:493-527`). A relative path that happens to exist relative to **the server's** working directory, not yours, is indexed without any error, and `project_id.py:100` then names the index directory after whatever the server resolved. That is a silently wrong project, which is worse than a refusal. There is no response field that reveals it.

**Never index a directory that contains other registered projects.** One index per project. A parent directory means every project inside it gets embedded a second time under a path nothing searches, and it holds the global index lock for hours while doing it. Indexing `C:\Development` meant 10,361 files against `C:\Development\Domain`'s 1,697, and every other index call got a 423 for the duration. If cwd is a subdirectory of a big repo, drop a `.ragroot` file in the folder that is actually the project, or name the path explicitly.

## Where everything goes

Nothing is written into the target project. It all lives under clean-rag, keyed by a slug plus a hash of the project's absolute path (`server/project_id.py:100-101`):

```
clean-rag/databases/_projects/<slug>-<sha256(project_path)[:8]>/
  chroma/         vector index
  graph.db        SQLite import graph (imports, inherits, implements, calls) + PageRank
  manifest.json   per file content hashes, used for incremental reindex
```

Real examples: `domain-8de89d54`, `foodaccessproject-bbf5c772`. Eight hex characters, not twelve.

The registry of indexed projects is `clean-rag/state/projects.json`. The auto reindex loop reads that file, so **a project is only kept fresh once it is in there**. `POST /index-project` adds it for you, at the end of a run.

## Steps

**0. Check for a dead registry row first.**

Read `clean-rag/state/projects.json` and look at the entry for this project, if there is one. A row is dead when **there is no index behind it on disk**:

- `databases/_projects/<slug>-<hash>/` does not exist at all, or
- that directory exists but has no `manifest.json`

Two weaker signals that mean "look closer", not "delete":

- `indexed_at` is `null`, or the `graph` key is missing when every other row has one. `_update_project_registry` (`indexing.py:1154-1161`) always writes a real timestamp, so a null one means the row was not written by an indexing run at all.
- `files_indexed` and `chunks_created` are both `0`. **This does not mean dead.** It is also what a run that stopped early on its very first file reports, and what a run reports when every file was already unchanged. Both of those have a real index and a resumable manifest.

So check the disk before deleting anything. If `manifest.json` exists, the project is resumable and the fix is a retry (step 3), not a deletion. Deleting a row whose manifest and vectors are still on disk drops it from the registry and from the sweep while leaving the data orphaned.

A genuinely dead row is not harmless. It is a claim that the project is indexed, and things that check the registry by path alone believe it. Delete that one, then index normally. This is the exact leftover the header above describes.

**1. Make sure the server is up.**

```bash
curl -s -m 5 http://127.0.0.1:8613/status
```

Interpret the result:

- Connection refused or timeout → the server is down. Start it, below.
- HTTP 200, `"status": "warming_up"` → it is loading the embedding model. Wait 30s and retry. Still warming up after 90s total means restart it.
- HTTP 200, `"status": "ready"` → healthy, go to step 2.
- Anything else → note the body and restart it.

```bash
python "$CLEAN_RAG_HOME/cli/server_ctl.py" start
```

`start` is single instance and checks the port, so running it when a server is already up is safe and does nothing. `restart` and `stop` exist too. Give it about 15 seconds to load the embedding model, then check `/status` again. Do not proceed until it returns `"status": "ready"`.

**2. Resolve the project path.** Must be absolute, and must exist. See the two rules above. If the argument is fuzzy and more than one candidate matches, use AskUserQuestion rather than guessing.

**3. Index it.**

```bash
curl -s -X POST http://127.0.0.1:8613/index-project \
  -H "Content-Type: application/json" \
  -d '{"project_path": "<ABSOLUTE PATH>"}'
```

Add `"force": true` for a full rebuild. Without it, files whose content hash is unchanged are skipped, which is what makes reindexing cheap. A non force retry after an interrupted run resumes it: the manifest checkpoints every 30 seconds (`indexing.py:773-783`) and unchanged hashes are skipped (`indexing.py:658`), so nothing already embedded is redone.

**This is slow, and the old estimate in this file was wrong.** Embedding runs on CPU unless CUDA or MPS is present (`config.py:89-105`). The code's own measured figure is 4.65 seconds for an average file (`resource_guard.py:122-128`), and a real run here did 936 files in 97 minutes, about 6 seconds each. So budget roughly **5 to 6 seconds per file**: a few hundred files is tens of minutes, and two thousand files is a couple of hours. Watch the server's console window for progress.

**4. Read the status code before the body.**

| Code | Body | What it means, what to do |
|---|---|---|
| 200 | the result dict | Nothing was refused. Go to step 5, a 200 is not success. |
| 400 | `Invalid JSON body` | The request body was malformed. Check the quoting, especially on Windows. |
| 400 | `Missing 'project_path' field` | The field is absent or an empty string. |
| 400 | `Project path not found: <path>` | `is_dir()` was false. **The same message covers three different causes**: the path does not exist, it exists but is a file, or it was relative and did not resolve under the server's cwd. Check the filesystem yourself, the body cannot tell you which. |
| 423 | `Index busy, retry in a moment` | The global index lock is held by another run. **Nothing was queued and nothing will retry.** See the lock section below. |
| 503 | `Server not initialized` | Startup has not finished loading the model cache. Wait and retry. |
| 500 | `Internal server error` | An exception inside the indexing run. The real error is only in the server log, never in the body. Read `state/server.log`. |

**5. Read the 200 body honestly.**

The result dict is built at `indexing.py:949-971`:

- `files_indexed` — embedded and stored.
- `files_unchanged` — skipped, hash matched.
- `files_failed` — **above zero means something went wrong.** There is no `errors[]` field in the response, whatever an older version of this file claimed. Per file reasons are logged only (`indexing.py:652`, `indexing.py:748`), so read `state/server.log` to find out which files and why.
- `chunks_created`, `elapsed_s`, `ram_mb` — as named.
- `graph.edges_total` / `graph.edges_resolved` — if `edges_total` is 0, the graph is empty and `mode: "graph"` quietly falls back to plain vector search. Usually the tree-sitter grammar for that language is not installed.
- `graph.error` — a graph build failure lands **inside** the `graph` object, not at the top level. Checking only `edges_total` misses it.
- `stopped_early` — **read this one.** A run that hits the memory floor stops between files and reports the reason here, for example `free RAM 1100 MB (need 4322 MB)`. The status is still 200 and every other number is real, so a 200 alone does not mean the project is fully indexed. The guard is checked before the first file too, so a request that arrives on an already starved machine can stop having indexed nothing.
- `files_pending` — present only alongside `stopped_early`: how many files the run never looked at. Every other count covers only the files it did look at, so this is what tells you the run was cut short rather than finished.
- `index_incomplete` — present only alongside `stopped_early`: whether any of those pending files still need indexing. `false` means the run stopped after confirming every remaining file was already indexed and unchanged, so there is nothing to do and the manifest is left complete. `true` means work is outstanding and the manifest is marked `__incomplete__`.

So a 200 has two outcomes, not one, and there are three in total:

| Outcome | How you tell | What to do |
|---|---|---|
| Done | 200, no `stopped_early` | Go to step 6. |
| Partial | 200, `stopped_early` present, `index_incomplete: true` | The machine ran low on memory and the run gave up on purpose. Nothing is corrupt. Free some memory and **retry without `force`**, which resumes from the checkpointed manifest per step 3. |
| Nothing to do | 200, `stopped_early` present, `index_incomplete: false` | The run stopped early but every file it had left was already indexed and unchanged. The index is complete. Free some memory before the next real reindex, but there is nothing to finish here. |
| Failed | non 200 | See the table in step 4. Nothing was indexed. |

Do not leave a partial index sitting, but finishing one is easy: **run step 3 again without `force`.** That resumes from the checkpointed manifest, skips the hashes that already match, and clears `__incomplete__` when it completes. No sweep involvement, no `force` needed.

What will not reliably happen is anything finishing it *for* you. The manifest stays marked `__incomplete__`, `/search` serves the project with a `stale_projects` warning and `served: true` (`search.py:357`), and the only automatic path that resumes an incomplete index is the sweep's full rebuild branch (`auto_reindex.py:353`), which needs 50 or more changed files in one sweep (`auto_reindex.py:60`). A project whose files rarely change can therefore sit incomplete indefinitely. Noticing is the human's job; fixing it is one retry.

`files_indexed: 0` is not automatically a failure. It is correct when every file's hash already matched (check `files_unchanged`), or when the tree holds no files matching `CODE_EXTENSIONS`. Zero indexed **and** zero unchanged means nothing was found, which is a real problem, unless `stopped_early` is present: then the run never got as far as looking, and `files_pending` plus `index_incomplete` are the two fields that say what state the project is actually in.

**6. Prove search works before declaring success.**

```bash
curl -s -X POST http://127.0.0.1:8613/search \
  -H "Content-Type: application/json" \
  -d '{"query":"<something you know is in this codebase>","sources":["project:<ABSOLUTE PATH>"],"mode":"both","limit":3}'
```

Check both of these, not just the first:

- **`results` is non-empty**, with `relation` and `seed_file` on the graph hits. If it comes back empty, the index did not work, whatever the index response claimed.
- **`stale_projects` is absent.** This is the check the older version of this file missed. `search.py:203-232` compares the model recorded in the project's manifest against the model search actually resolves, and refuses the project when they differ, because two models of the same width produce compatible vectors with unrelated meanings. That refusal can happen immediately after a clean index. If `stale_projects` names this project:
  - `"served": false` → the index was refused outright. Print its `reason` and rebuild with `force`.
  - `"served": true` → partial index, results are real but incomplete. Print its `reason` and finish it with `force`.

Empty results plus a `stale_projects` entry is a broken index, not an empty codebase. Read the `reason` before concluding the code is not there.

## The index lock, and why 423 matters

There is **one global index lock** for the whole server (`indexing.py:68`, `state/index-lock.json`). It is not per project. Every `/index-project` and `/reindex-file` call takes it, whatever they target.

That means a slow index of an unrelated project locks you out completely. `app.py:515` hard rejects with 423 and there is no queue, no position, no retry. A caller that ignores the status code sees no fields it recognises and can read the refusal as an ambiguous result.

The lock records the holding PID. If that process is dead, the next acquire clears the lock automatically (`indexing.py:76-97`). If it is alive, your options are to wait or to restart the server, since there is no cancel endpoint. Read `state/index-lock.json` to see who holds it and since when, and `state/index-runner.log` for what the background hook's own index attempts actually returned.

## What gets skipped

Defined once in `clean-rag/server/file_scan.py` and applied everywhere, including the auto reindex sweep: `SKIP_DIRS`, `SKIP_FILES`, `SKIP_SUFFIXES`, `SKIP_NAME_GLOBS`, an allowlist of `CODE_EXTENSIONS`, and a 500KB per file cap. Files inside a virtualenv are treated as dependencies and skipped. Everything goes through `scan_project()`. If a file type should or shouldn't be indexed, change it there, not here.

## Reindexing happens on its own

Once the project is in `state/projects.json` **with a real index behind it**, three things keep it fresh:

1. **After every edit Claude makes.** `hooks/reindex-after-edit.py` reindexes just that file.
2. **Every 10 minutes.** `server/auto_reindex.py` sweeps every registered project, diffs file hashes against the manifest, and reindexes only what changed. This catches edits from another editor, a `git pull`, or a branch switch. If files were deleted, or 50-plus changed, it rebuilds fully instead, because stale chunks can't be cleared file by file.
3. **On demand.** Re-run this command with `force`.

All three take the same global lock, so they cannot race each other, and they cannot run at the same time as each other either.

The sweep will **not** rescue a project that was never indexed. `auto_reindex.py:182-184` returns early when there is no manifest: "Never indexed. Not this loop's job to decide it should be." A registry row with no index behind it stays broken until someone runs this command.

So index a project **once**. Don't re-run this on a schedule or "just to be safe" — that's what the loop is for, and a forced rebuild is expensive.

## After indexing

Search with `mode: "both"`. Vector and graph surface different files; running only one leaves a gap.
