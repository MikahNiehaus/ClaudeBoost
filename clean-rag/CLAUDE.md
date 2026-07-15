# clean-rag

Forced research before code edits, plus semantic and structural search over your indexed projects.

Two things live here:

1. **The research gate.** Every code edit is blocked until swiper has actually run this turn. Not asked for. Required.
2. **The project index.** Each project you index gets a vector database and an import graph, both stored inside clean-rag.

There is no topic knowledge base. There used to be, and it was removed. See "Why the KB is gone" below, because the reasoning matters and will otherwise get rebuilt by someone with good intentions.

## The research gate

`hooks/research-gate.py` (PreToolUse on Edit, Write, MultiEdit) blocks any edit to a code file unless `swiper` completed during the current turn.

The gate keys off a real agent run, not a claim of one. That distinction is the whole design:

- `hooks/rag-enforce.py` (UserPromptSubmit) opens a fresh turn record on every message.
- `hooks/research-record.py` (PostToolUse on Task and Agent) stamps that record when `swiper` finishes.
- `hooks/research-gate.py` reads the record and refuses the edit if nothing stamped it.

Only Claude Code can start an agent, and the stamp only lands after one completes. There is no path from "say you researched" to a stamped record. This replaced an earlier proof file design where the model wrote a JSON blob attesting it had researched, which proves nothing: the model writes the file, so the file says whatever the model wants it to say.

**Exempt:** anything that isn't source code (`.md`, `.json`, `.yaml`, configs), plus `workspace/`, `state/`, `plans/`, `docs/`, `.claude/`, `node_modules/`, and temp directories. A markdown edit has nothing to research.

**Escape hatch:** `CLEAN_RAG_RESEARCH_GATE=off`. Use it when the gate itself is broken, not when it's inconvenient.

## swiper

**`swiper`** (Sonnet) is the gatekeeper. When the gate blocks an edit you spawn it; it picks its own queries, covers depth and breadth, checks whether the thing already exists, reads the import graph, and reports with sources and a `COVERS:` line. It hates writing code from scratch: its whole job is to find real working code (in the project, the stdlib, an installed dependency, GitHub, or StackOverflow) and copy-paste it directly into the target file, not just describe it. Writing original logic is its last resort, said plainly when reached. It runs real research every time it fires (roughly 44 to 52k tokens and 2 to 8 minutes for a full pass) and does NOT guess whether a change is trivial. Spawn it in the foreground (`run_in_background: false`), never backgrounded — a backgrounded completion arrives later as a `TaskNotificationMessage`, not a tool result, so `research-record.py`'s `PostToolUse` hook never fires for it and the gate stays blocked for the rest of the turn no matter how long you wait. It's defined in `~/.claude/agents/` and preloads the `research-routing` skill (depth vs breadth routing, the does-this-exist check).

Its report also names a `MATCH_STRATEGY:`, one of two values: `clone-and-patch` or `pattern-only`. There is no `adapt` tier: that word let a builder rewrite a shipping ready reference from scratch instead of using it, a real observed failure, so it's gone, not softened. `clone-and-patch` means copy the verbatim quoted block as the literal starting point and make only the smallest set of changes actually required, whatever the fetched reference's original framework or scale, no rewrite, no restyle, no swapped libraries, no added structure the reference didn't have. That's a hard ceiling on the diff, not a suggestion. `pattern-only` means nothing was worth stealing; only then does a real diff from correctness properties apply.

There used to be a cheap `triage-agent` (Haiku) in front of it that answered NONE-versus-RESEARCH in seconds. It was removed: it decided whether a change needed research *without reading the code*, and that blind guess was wrong often enough to be worse than useless. The call about what deserves a full research pass is now the human's, exposed as the `/ps` skill (a quick turn that skips both the gate and the verifier), not a model's to guess. After a full pass, swiper may itself recommend `/ps` for that kind of change next time if the research turned out functionally unneeded, but it never skips on its own.

### swiper writes, but its shell is caged

It reads untrusted web content, which makes it the obvious target for an indirect prompt injection. Sanitizing that text is leaky by nature, so the defense isn't filtering, it's capability removal from the one channel that could act on an injected instruction:

- `Write` and `Edit` are allowed, deliberately: swiper's whole point is to place stolen code directly into the project, not just report it. What's capped instead is Bash: `hooks/research-agent-bash-guard.py` (a PreToolUse hook in its own frontmatter, name not yet renamed to match) restricts Bash to `curl` against `127.0.0.1` clean-rag only. Verified against 15 cases: `rm -rf`, remote exfil, `;` and `&&` chaining, piping into `sh`, `>` redirects, `python -c`, command substitution, cloud metadata endpoints, and lookalike hosts such as `127.0.0.1.evil.com`. `git clone https://` is allowed as a special case: `_check_git_clone()` in `research-agent-bash-guard.py` permits it when the URL starts with `https://` and no dangerous flags are present. The dangerous flag set (`--upload-pack`, `ext::` transport, `--template`, `-c`/`--config`) are the documented arbitrary-command vectors (CVE-2022-25900, GHSA-jcxm-m3jx-f287) and are still refused. All other `git` subcommands are blocked.

A fully compromised swiper can search and write files, but only files it already has real fetched content for, and it still cannot run an arbitrary shell command to do anything else.

## Search

```
POST http://127.0.0.1:8613/search
{
  "query": "how does the research gate decide to block",
  "sources": ["project:C:/prj/ClaudeBoost"],
  "mode": "both",
  "limit": 5,
  "min_score": 0.3
}
```

`sources` takes `project:<absolute path>`. There is no `all_topics` and no `topic:<name>`; they were removed and now fall through to an unknown-specifier branch that returns nothing.

`mode`:
- `vector` (default) is embedding similarity.
- `graph` walks the import graph from the vector matches: what imports this, what does this import, what inherits from it.
- `both` runs the two together, dedupes, and merges by score. **Use this.** They surface different files, and one without the other leaves a gap.

`depth` (1 to 5, default 2) and `direction` (`callers`, `dependencies`, `both`) tune the graph walk.

Graph results carry `relation` (`imports`, `inherits`, `implements`, `calls`), `seed_file` (the vector match that led there), and `is_caller`.

## Web search

```
POST http://127.0.0.1:8613/web-search
{"query": "fixed timestep accumulator game loop", "max_results": 5}
```

DuckDuckGo, no API key. Results are ranked so GitHub, StackOverflow, and official docs come first and content farms come last, and snippets are sanitized (NFKC normalized, zero-width and bidi and control characters stripped, since those survive HTML tag removal and are how payloads get smuggled into a model's context).

Snippets run about 200 characters. Survey with this, then `WebFetch` only the page that actually matters. That ordering is what took research runs from ~50k tokens down to ~5-10k.

## Project indexing

```
POST http://127.0.0.1:8613/index-project
{"project_path": "C:/path/to/project"}
```

Everything for a project lives inside clean-rag, keyed by a hash of its absolute path:

```
clean-rag/databases/_projects/<sha256(path)[:12]>/
  chroma/         vector index
  graph.db        SQLite import graph, plus PageRank scores
  manifest.json   per file content hashes, for incremental reindex
```

The registry of what's indexed is `state/projects.json`.

**What gets skipped** (`server/indexing.py`): `SKIP_DIRS`, `SKIP_FILES`, `SKIP_SUFFIXES`, an allowlist of `CODE_EXTENSIONS`, and a 500KB per file cap. Every path into the index goes through `scan_project()`, so the skip rules are defined once and apply everywhere, including the auto reindex sweep.

**The graph is built automatically at index time.** Tree-sitter parses each file's AST and extracts `imports`, `inherits`, `implements`, and `calls` edges across 15 languages, then PageRank ranks the nodes. No LLM is involved. This is the cheap kind of code graph, the same approach as Aider's repo map, not the expensive GraphRAG kind where a model reads your whole codebase to extract entities.

### Reindexing keeps itself honest

Three layers, so the index never silently drifts:

1. **After every edit.** `hooks/reindex-after-edit.py` (PostToolUse) reindexes just the changed file.
2. **Every 10 minutes.** `server/auto_reindex.py` walks every project in the registry, diffs file hashes against the manifest, and reindexes only what changed. This is what catches edits from another editor, a `git pull`, or a branch switch. A deletion, or 50-plus changed files, triggers a full rebuild instead, because stale chunks can't be cleared file by file and a branch switch is cheaper to rebuild wholesale.
3. **On demand.** `POST /index-project` with `"force": true`.

All three take `acquire_index_lock()` so they can't race each other.

## Server

```bash
python clean-rag/cli/server_ctl.py start     # headed, own console window
python clean-rag/cli/server_ctl.py stop
python clean-rag/cli/server_ctl.py restart
python clean-rag/cli/server_ctl.py status
```

Or double click `clean-rag/runragserver.bat`.

It runs **headed**, in its own console window, so you can watch indexing and search happen instead of reconstructing it from a log afterwards. Set `CLEAN_RAG_HEADLESS=1` for the old detached behaviour.

`start` is single instance and checks the **port**, not the PID file. The PID file lies: it goes stale when a server dies badly and knows nothing about one started by hand. Running `start` twice is safe and does nothing the second time.

Logs stream to the console and to `state/server.log`.

## Endpoints

| Route | What it does |
|---|---|
| `GET /status` | Health, model state, every indexed project with its graph stats |
| `POST /search` | Vector, graph, or both, over `project:` sources |
| `POST /web-search` | DuckDuckGo, source ranked, sanitized |
| `POST /index-project` | Index a project, build its graph |
| `POST /reindex-file` | Reindex one file |
| `GET /projects` | The project registry |
| `POST /register-project` | Register a project indexed by another RAG server |

## Why the KB is gone

clean-rag used to carry a topic knowledge base: dozens of scraped documentation sets, searchable by `all_topics`. It was deleted, along with `research/`, `cli/topic.py`, `server/index_queue.py`, and six endpoints.

It was removed because **it confidently returned wrong answers, and no threshold could catch them.** Measured, not guessed:

| Query | What came back | Score |
|---|---|---|
| "is it done" | Azure Functions `context.done()` docs | 0.82 |
| "duck duck go" | react-query docs, then PCMag browser reviews | 0.80 |
| a function containing a SQL injection | Go stack trace docs | 0.86 |
| `MAX_RETRIES = 5` | PowerShell retry docs | 0.86 |

`min_score: 0.5` caught none of it. Cosine similarity always hands back a confident nearest neighbour; there is no "I don't know". A wrong query gets a wrong answer that *looks* right.

Two things follow, and both were believed false until they were measured:

**Vector search does not degrade gracefully.** A keyword soup query embeds into *something*, and something is always nearby.

**Embedding search retrieves text resembling your query, never a critique of it.** Feed it SQL-injecting code and you get more SQL code, not the vulnerability warning. Getting the warning would mean searching "SQL string concatenation vulnerability", which means having already read the code and spotted the bug. That is reasoning, and a hook does not have any.

So retrieval moved to the only thing that can write a decent query: a reasoning agent. The project index stayed, because a hit there is a real file you can open and check, and because the import graph answers a question no web search can ("what breaks if I change this").

**Do not rebuild the topic KB.** If local docs seem necessary, the failure above will reproduce, because the problem was never corpus quality. It was that a mechanical query has no judgment behind it.
