---
description: Index a project's codebase into clean-rag for vector and import graph search
allowed-tools: Bash, Read, Glob, Grep, AskUserQuestion
---

# Index a project into clean-rag

Builds two things for the target project: a vector index for semantic search, and an import graph for structural search ("what breaks if I change this"). Both live inside clean-rag. Once indexed, the project reindexes itself automatically.

This targets clean-rag on **port 8613**. It used to index into the ClaudeBoost RAG server on 8612 and merely register the path with clean-rag afterwards, which left a registry entry pointing at a project clean-rag had no data for: no vectors, no graph, and an auto reindex sweep with no manifest to diff against.

## Arguments

`$ARGUMENTS` — any of:
- Empty → the current working directory
- A path → `/index-project C:/prj/MyApp`
- A short name → `/index-project LocalAI` (resolve against `clean-rag/state/projects.json` and sibling directories)
- Plus `force` → full rebuild instead of incremental

## Where everything goes

Nothing is written into the target project. It all lives under clean-rag, keyed by a hash of the project's absolute path:

```
clean-rag/databases/_projects/<sha256(project_path)[:12]>/
  chroma/         vector index
  graph.db        SQLite import graph (imports, inherits, implements, calls) + PageRank
  manifest.json   per file content hashes, used for incremental reindex
```

The registry of indexed projects is `clean-rag/state/projects.json`. The auto reindex loop reads that file, so **a project is only kept fresh once it is in there**. `POST /index-project` adds it for you.

## Steps

**1. Make sure the server is up.**

```bash
curl -s -m 5 http://127.0.0.1:8613/status
```

If it does not answer, start it. It runs headed, in its own window, so the user can watch it work:

```bash
python "$CLEAN_RAG_HOME/cli/server_ctl.py" start
```

`start` is single instance and checks the port, so running it when a server is already up is safe and does nothing. Give it about 15 seconds to load the embedding model, then check `/status` again. Do not proceed until it returns `"status": "ready"`.

**2. Resolve the project path.** Must be absolute, and must exist. If the argument is fuzzy and more than one candidate matches, use AskUserQuestion rather than guessing.

**3. Index it.**

```bash
curl -s -X POST http://127.0.0.1:8613/index-project \
  -H "Content-Type: application/json" \
  -d '{"project_path": "<ABSOLUTE PATH>"}'
```

Add `"force": true` for a full rebuild. Without it, files whose content hash is unchanged are skipped, which is what makes reindexing cheap.

This is not instant. A few hundred files takes a minute or two: every chunk is embedded, and every file is parsed with tree-sitter to extract graph edges. Watch the server's console window for progress.

**4. Read the result honestly.**

- `files_indexed` — embedded and stored
- `files_unchanged` — skipped, hash matched
- `files_failed` — **above zero means something went wrong.** Read `errors[]` and report it. A 200 response does not mean a healthy index.
- `graph.edges_total` / `graph.edges_resolved` — if `edges_total` is 0, the graph is empty and `mode: "graph"` will quietly fall back to plain vector search. Usually the tree-sitter grammar for that language isn't installed.

**5. Prove search works before declaring success.**

```bash
curl -s -X POST http://127.0.0.1:8613/search \
  -H "Content-Type: application/json" \
  -d '{"query":"<something you know is in this codebase>","sources":["project:<ABSOLUTE PATH>"],"mode":"both","limit":3}'
```

You want real results, with `relation` and `seed_file` on the graph hits. If it comes back empty, the index did not work, whatever the index response claimed.

## What gets skipped

Defined once in `clean-rag/server/indexing.py` and applied everywhere, including the auto reindex sweep: `SKIP_DIRS`, `SKIP_FILES`, `SKIP_SUFFIXES`, an allowlist of `CODE_EXTENSIONS`, and a 500KB per file cap. Everything goes through `scan_project()`. If a file type should or shouldn't be indexed, change it there, not here.

## Reindexing happens on its own

Once the project is in `state/projects.json`, three things keep it fresh and you do not have to do anything:

1. **After every edit Claude makes.** `hooks/reindex-after-edit.py` reindexes just that file.
2. **Every 10 minutes.** `server/auto_reindex.py` sweeps every registered project, diffs file hashes against the manifest, and reindexes only what changed. This catches edits from another editor, a `git pull`, or a branch switch. If files were deleted, or 50-plus changed, it rebuilds fully instead, because stale chunks can't be cleared file by file.
3. **On demand.** Re-run this command with `force`.

All three take the index lock, so they can't race each other. You will see every sweep in the server's console window.

So index a project **once**. Don't re-run this on a schedule or "just to be safe" — that's what the loop is for, and a forced rebuild is expensive.

## After indexing

Search with `mode: "both"`. Vector and graph surface different files; running only one leaves a gap.
