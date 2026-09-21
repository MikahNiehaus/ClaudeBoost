# clean-rag

Forced research before code edits, plus semantic and structural search over your indexed projects.

Two things live here:

1. **The research gate.** Every code edit is nudged toward research from swiper, and the audit trail records whether that research actually happened this turn, but the edit itself is never refused.
2. **The project index.** Each project you index gets a vector database and an import graph, both stored inside clean-rag.

There is no topic knowledge base. There used to be, and it was removed. See "Why the KB is gone" below, because the reasoning matters and will otherwise get rebuilt by someone with good intentions.

## The research gate

`hooks/research-gate.py` (PreToolUse on Edit, Write, MultiEdit) checks whether
`swiper` completed during the current turn before an edit to a code file, and
either way, allows the edit. It used to block (exit 2) until `swiper` had
actually run. That per turn scoping turned out to be too disruptive in
practice: a file swiper had just covered needed covering again the instant
another message came in, before anything had even been edited. Rather than
fix the scoping and keep a hard block, the block itself is gone. The hook
still checks and still records; it just never refuses.

- `hooks/rag-enforce.py` (UserPromptSubmit) opens a fresh turn record on every message.
- `hooks/research-record.py` (PostToolUse on Task and Agent) stamps that record when `swiper` finishes.
- `hooks/research-gate.py` reads the record, prints a nudge to stderr when nothing covers the file, and logs the real coverage status (covered or not, and by what) to the audit trail either way.

Only Claude Code can start an agent, and the stamp only lands after one completes. There is no path from "say you researched" to a stamped record, so the audit trail is honest even though the gate no longer blocks on it. This replaced an earlier proof file design where the model wrote a JSON blob attesting it had researched, which proves nothing: the model writes the file, so the file says whatever the model wants it to say.

**Exempt:** anything that isn't source code (`.md`, `.json`, `.yaml`, configs), plus `workspace/`, `state/`, `plans/`, `docs/`, `.claude/`, `node_modules/`, and temp directories. A markdown edit has nothing to research.

**`CLEAN_RAG_RESEARCH_GATE=off`** silences the nudge and the audit entry entirely. Since the gate no longer blocks anything, this only matters if you want the hook to do nothing at all rather than nudge and log.

## What the hooks inject, and why it is said once

Every fixed block these hooks emit is now sent **once per session**, then as a short pointer or not at all. Changed 2026-09-21 on measured evidence, and it is the opposite of what the design assumed.

The assumption was that repeating a rule on every message is what makes it followed. Counted from one real session's transcript, that cost **339,523 tokens**, which is 1.7 full 200k context windows spent on hook output:

| block | firings | tokens | state |
|---|---|---|---|
| RAG contract plus rules | 325 | 164,012 | byte identical every time |
| "does it already exist?" | 183 | 98,978 | byte identical every time |
| Project and Research Context | 140 | 54,639 | header fixed, snippets retrieved |
| decision nudge | 47 | 28,344 | byte identical every time |
| "verify by running" | 98 | 19,502 | byte identical every time |

Three things make repetition the wrong tool, not merely an expensive one:

- **A `UserPromptSubmit` injection is a new permanent message, not one block re sent.** 325 firings leave 325 copies in the transcript, every one of them re sent on every later API call. A system prompt is one copy.
- **Position beats count.** Liu et al., "Lost in the Middle", measured a U shaped recall curve: best at the very start or the very end, worst in the middle. Every copy but the newest sits in the middle. No study isolates repeat count as a lever that improves compliance.
- **Restating a rule does not close the compliance gap.** Mechanical enforcement does, which is what the gates already are. A hook that checks beats a hook that reminds.

So each block moved to the layer that fits it. Anything invariant belongs in the Plain output style, which rewrites the system prompt and is cached. Anything session stable is said once. Anything genuinely conditional still fires at its moment, in a short form after the first time, which is ESLint's convention of a short message plus a rule id with the reasoning one lookup away.

`hooks/research_state.py` owns the mechanism: `claim_session_once(session_id, key, fingerprint)` returns True the first time and again whenever the fingerprint changes, so switching workspace or indexing the project re emits rather than going stale. It carries **no TTL on purpose**. The event that should restore a block is a context wipe, not the clock, so `scripts/compaction-restore.py` calls `clear_session_once` on `source == "compact"` and `source == "clear"`. That holds whether or not Claude Code issues a fresh session id for a compaction.

Measured after: **328,853 tokens down to 45,411, an 86% cut**, with the per message floor at zero for the fixed blocks.

**`CLEAN_RAG_PROMPT_SEARCH=1`** brings back the automatic search on every message. It is off by default. The comment in `rag-enforce.py` already refused to *web* search there, because "a keyword-extracted query has no judgment behind it", and defended the vector search on the grounds that "a bad match scores low and gets dropped". This project measured that defence and it is false: see "Why the KB is gone" below, where four wrong hits scored 0.80 to 0.86 and `min_score: 0.5` caught none. Observed again on 2026-09-21, a message about context budgets returned three unrelated test helper functions.

Turning it off also fixed something unrelated looking. Pausing indexing evicts the embedding models to give the RAM back, and the per message search pulled them straight back in 11 seconds later, so the pause never worked. The hook still probes `/status`, which loads nothing, so an outage is still reported.

## swiper

**`swiper`** (Sonnet) is the researcher. When the gate nudges toward research on an edit, spawn it; it picks its own queries, covers depth and breadth, checks whether the thing already exists, reads the import graph, and reports with sources, a `COVERS:` line, and a `MATCH_STRATEGY:`. It hates writing code from scratch: its whole job is to find real working code (in the project, the stdlib, an installed dependency, GitHub, or StackOverflow) and hand it back exactly as found so the builder can place it, not just describe it. It does not write or edit project files itself. Writing original logic is the builder's last resort, said plainly when reached. It runs real research every time it fires (roughly 44 to 52k tokens and 2 to 8 minutes for a full pass) and does NOT guess whether a change is trivial. It's defined in `~/.claude/agents/` and preloads the `research-routing` skill (depth vs breadth routing, the does-this-exist check).

**Every agent spawn runs in the background. You cannot choose otherwise.** The line above used to end with "spawn it in the foreground (`run_in_background: false`), never backgrounded". That instruction asked for something the agent tool does not offer. Its inputs are `description`, `isolation`, `model`, `prompt` and `subagent_type`, and nothing else; `run_in_background` is a `Bash` input, not an agent one. Verified 2026-09-18 by reading the live tool schema.

The consequence is structural, not a mistake anyone made. A completion arrives as a `TaskNotificationMessage` rather than a tool result, so `research-record.py` on `PostToolUse` never fires for a subagent and can never stamp coverage. `SubagentStop` is the only event that can. Do not try to work around this by spawning differently; there is no other way to spawn.

Its report also names a `MATCH_STRATEGY:`, one of two values: `clone-and-patch` or `pattern-only`. There is no `adapt` tier: that word let a builder rewrite a shipping ready reference from scratch instead of using it, a real observed failure, so it's gone, not softened. `clone-and-patch` means copy the verbatim quoted block as the literal starting point and make only the smallest set of changes actually required, whatever the fetched reference's original framework or scale, no rewrite, no restyle, no swapped libraries, no added structure the reference didn't have. That's a hard ceiling on the diff, not a suggestion. `pattern-only` means nothing was worth swiping; only then does a real diff from correctness properties apply.

There used to be a cheap `triage-agent` (Haiku) in front of it that answered NONE-versus-RESEARCH in seconds. It was removed: it decided whether a change needed research *without reading the code*, and that blind guess was wrong often enough to be worse than useless. The call about what deserves a full research pass is now the human's, exposed as the `/ps` skill (a quick turn that skips both the gate and the verifier), not a model's to guess. After a full pass, swiper may itself recommend `/ps` for that kind of change next time if the research turned out functionally unneeded, but it never skips on its own.

### swiper reports, it never writes, and its shell is caged

It reads untrusted web content, which makes it the obvious target for an indirect prompt injection. Sanitizing that text is leaky by nature, so the defense isn't filtering, it's capability removal from the one channel that could act on an injected instruction:

- **No `Write` or `Edit`, on purpose.** swiper quotes what it found in its report; the builder places it. This used to be the other way around (swiper wrote the code straight into the target file itself), until a real observed failure: giving it that access is exactly the channel an injected instruction could act through, on top of being the wrong division of labor once a real consult step sits between "here's what's out there" and "here's what we're doing about it."
- **Bash is capped regardless.** `hooks/research-agent-bash-guard.py` (a PreToolUse hook in its own frontmatter, name not yet renamed to match) restricts Bash to `curl` against `127.0.0.1` clean-rag only. Verified against 15 cases: `rm -rf`, remote exfil, `;` and `&&` chaining, piping into `sh`, `>` redirects, `python -c`, command substitution, cloud metadata endpoints, and lookalike hosts such as `127.0.0.1.evil.com`. `git clone https://` is allowed as a special case: `_check_git_clone()` in `research-agent-bash-guard.py` permits it when the URL starts with `https://` and no dangerous flags are present. The dangerous flag set (`--upload-pack`, `ext::` transport, `--template`, `-c`/`--config`) are the documented arbitrary-command vectors (CVE-2022-25900, GHSA-jcxm-m3jx-f287) and are still refused. All other `git` subcommands are blocked.

A fully compromised swiper can search and quote whatever it already has real fetched content for in its report, but it cannot write anything to disk and cannot run an arbitrary shell command to do anything else. `researcher` (see below) is defined the same way, for the same reason.

## researcher, and the /start pipeline

**`researcher`** (Sonnet) runs before swiper on `/start`. It indexes and searches the project itself (`/index-project`, then `/search` with `mode: "both"`), reaches for the `graphrag` skill on a genuinely cross file behavior question, and checks the general engineering standard for the change against a real source. No `Write`/`Edit`, same posture as swiper, same Bash cage. It replaces an ad hoc codebase exploring subagent for understanding a project, since it has clean-rag's real indexed databases behind it.

`/start` is the deliberate entry point for a new build or feature: researcher first, then swiper informed by researcher's findings, then a real consult with the user (`AskUserQuestion`) before anything is written, then the main AI writes the code.

## bad-cop and good-cop

Post write verification is two agents, but good-cop is conditional, not
always spawned. **`bad-cop`** (Sonnet) runs first: writes adversarial tests,
runs the code, adds logging, and reports the real, provable failures it
finds, with actual execution output attached. It never fixes anything. If it
finds nothing, it emits the `VERIFIED:` line itself and the pass is done, no
`good-cop` run needed to re-confirm a clean adversarial pass. If every
finding it has is Nit severity, it emits `NITS:` and good-cop still does not
run: nits are non blocking, so the orchestrator applies them directly and
re-runs bad-cop for the re-check that earns the stamp. Only when bad-cop
emits `HANDOFF:`, meaning at least one Critical or High finding, does
**`good-cop`** (Opus) run: takes bad-cop's
findings, researches the correct fix, applies it, and reruns bad-cop's new
tests plus the existing suite until everything is actually green, and stamps
`VERIFIED:`. After good-cop stamps, bad-cop re-runs for a final adversarial
re-check. If bad-cop finds nothing on that re-check, it stamps `VERIFIED:`
itself and the loop ends. If it finds more issues, good-cop runs again. The
loop (bad-cop → good-cop → bad-cop) continues until bad-cop stamps
`VERIFIED:` on a clean pass — that is the only terminal condition.
`hooks/verifier-gate.py` enforces this: bad-cop's final clean stamp is what
clears the gate. Both are defined in `~/.claude/agents/` the same way swiper
and researcher are.

**Both cops review the diff by default, and whatever you name instead.** With
no review scope given, bad-cop resolves the diff itself: the uncommitted working
tree, or the branch against its merge base when the tree is clean. Anything the
human names on a `REVIEW SCOPE:` line replaces that, in their own words, with no
fixed vocabulary. `entire project`, `anything that touches security`, `anything
that touches OrderService`, `anything around this bug fix`, a bare path, all
valid. Pass their sentence through verbatim; do not paraphrase it and do not
resolve it to files yourself. bad-cop resolves it with search and the import
graph, then prints the resolved file list at the top of its report, which is the
only place a misread scope gets caught, so read that block first. Copy the same
`REVIEW SCOPE:` and `RESOLVED:` lines into good-cop's prompt. Both work the same
surface. That list bounds where a root cause is allowed to live; it does not
widen what good-cop may change, which stays at what the findings require.


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

**The graph is built automatically at index time.** Tree-sitter parses each file's AST and extracts `imports`, `inherits`, `implements`, and `calls` edges across 14 languages, then PageRank ranks the nodes. No LLM is involved. This is the cheap kind of code graph, the same approach as Aider's repo map, not the expensive GraphRAG kind where a model reads your whole codebase to extract entities.

### Reindexing keeps itself honest

Three layers, so the index never silently drifts:

1. **After every edit.** `hooks/reindex-after-edit.py` (PostToolUse) reindexes just the changed file.
2. **Every 10 minutes.** `server/auto_reindex.py` walks every project in the registry, diffs file hashes against the manifest, and reindexes only what changed. This is what catches edits from another editor, a `git pull`, or a branch switch. A deletion, or 50-plus changed files, triggers a full rebuild instead, because stale chunks can't be cleared file by file and a branch switch is cheaper to rebuild wholesale.
3. **On demand.** `POST /index-project` with `"force": true`.

All three take `acquire_index_lock()` so they can't race each other.

## Server

```bash
python clean-rag/cli/server_ctl.py start     # windowless; CLEAN_RAG_HEADED=1 for a console
python clean-rag/cli/server_ctl.py stop
python clean-rag/cli/server_ctl.py restart
python clean-rag/cli/server_ctl.py status
```

Or double click `clean-rag/runragserver.bat`.

The server runs **windowless** and `start` now opens `cli/console.py` in its own window beside it, so indexing is visible without a second command. It never was before: `server_ctl.py` had no reference to the console at all, and `runragserver.bat` printed the console command as a suggestion rather than running it.

`CLEAN_RAG_CONSOLE=0` turns the UI off. Automation should set it, and `scripts/boost-run.py` does, because that path captures stdout and a terminal appearing in it is noise. Windows only: `CREATE_NEW_CONSOLE` has no POSIX equivalent that works without knowing the terminal emulator, so the POSIX branch skips it rather than guessing. A console that cannot start never stops the server, which is the one guarantee `test_a_console_that_cannot_start_does_not_stop_the_server` pins by making the spawn raise for real.

`CLEAN_RAG_HEADED=1` still gives the **server** its own raw terminal. `runragserver.bat` no longer sets it, because with the console launching too it produced two windows showing one log, and the console is the better of the two: it renders indexing state, it can pause sweeps, and closing it cannot kill the server the way closing a headed server's window could and did on 2026-09-18.

This reverses an earlier "headed by default" decision. That decision existed so logs were visible as they happened rather than reconstructed afterwards, and the console now does exactly that. A headed server also died whenever its window was closed, which is how it died on 2026-09-18.

`start` is single instance and checks the **port**, not the PID file. The PID file lies: it goes stale when a server dies badly and knows nothing about one started by hand. Running `start` twice is safe and does nothing the second time.

Logs stream to the console and to `state/server.log`.

## Endpoints

All 22 of them, generated from the router rather than kept by hand. `clean-rag/tests/test_skill_rag_routes.py` fails when a skill names a route the server does not serve; it does not notice a route nothing documents, which is how 16 of these went unlisted.

### Your indexed projects

| Route | What it does | Body keys |
|---|---|---|
| `POST /search` | Search across indexed projects. | `depth`, `direction`, `limit`, `min_score`, `mode`, `query`, `sources` |
| `POST /index-project` | Index a project's source code. | `force`, `project_path` |
| `POST /reindex-file` | Reindex a single changed file within a project. | `file_path`, `project_path` |
| `GET /projects` | List indexed projects. |  |
| `GET /status` | Server health, model status, indexed projects. |  |

### Outside sources

| Route | What it does | Body keys |
|---|---|---|
| `POST /web-search` | DuckDuckGo search, source ranked and sanitized. | `max_results`, `query`, `timeout` |
| `POST /github-search` | Search GitHub repositories, best maintained first. | `max_results`, `query`, `sort`, `timeout` |
| `POST /github-code-search` | Search FILE CONTENTS across public GitHub. | `language`, `max_results`, `query`, `timeout` |
| `POST /github-file` | Fetch one file's text from a public GitHub repo. | `owner`, `path`, `ref`, `repo` |
| `POST /stackoverflow-search` | Top accepted StackOverflow answers, with code. | `max_results`, `query`, `timeout` |
| `POST /wikipedia-search` | Human curated general knowledge, free and keyless. | `max_results`, `query` |

### Running things against a project

| Route | What it does | Body keys |
|---|---|---|
| `POST /run-tests` | Detect and run a project's tests, return the real result. | `project_path` |
| `POST /mutation-test` | Prove the tests bite, by running the mutation tool. | `changed_files`, `project_path` |
| `POST /security-scan` | Run security tools on changed files. | `changed_files`, `project_path` |

### GraphRAG, the manual deep layer

| Route | What it does | Body keys |
|---|---|---|
| `POST /graphrag-build` | Start the GraphRAG build for a project (manual, overnight). | `project_path` |
| `POST /graphrag-query` | Ask the built semantic graph a cross file question. | `project_path`, `query` |
| `GET/POST /graphrag-status` | Build progress. Takes `project_path` as a query string on GET or in the body on POST. | `project_path` |

### Docs ingest

A persistent topic scoped document pipeline, backed by `server/docs_store.py`. That is the same shape as the topic knowledge base described in the next section, which was deleted on measured evidence. Whether it should exist is an open decision, recorded at `spec/architecture-changes/server-docs-ingest-topic-kb-reincarnation.md`.

| Route | What it does | Body keys |
|---|---|---|
| `POST /docs-ingest` | Fetch, chunk, citation tag, and store official document sources under a persistent topic. Searchable afterward through `POST /search` with `sources: ["docs:<topic>"]`. | `force`, `sources`, `topic` |
| `GET/POST /docs-status` | What's been ingested for a docs topic. | `topic` |

### Kanban board

A browser view, not a search route. `/kanban/events` is Server Sent Events.

| Route | What it does | Body keys |
|---|---|---|
| `GET /kanban` | Serve the kanban board HTML. |  |
| `GET /kanban/tasks` | Return JSON snapshot of all current tasks. |  |
| `GET /kanban/events` | SSE endpoint for real time task updates. |  |

Every body key above is read by that route's own handler.

`POST /search` is the one to reach for on a code question: pass `sources` as a list of `project:<absolute path>` and `mode` as `"both"`, because vector and graph surface different files.

`sources` takes two prefixes, not one. `project:<absolute path>` is the code index. `docs:<topic>` reads what `/docs-ingest` stored, and goes through a separate prose embedder (`app.py:369`) rather than the code one. Read the note above that section before reaching for it.

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
