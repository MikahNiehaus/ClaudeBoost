# Forced Injection Spec

Defines how clean-rag must inject research into every prompt and every code edit, with no exceptions and no judgment calls left to the model.

## Core Principle

Injection is not a suggestion the model can accept or ignore. It is infrastructure. The model never decides whether research was needed — the hook decides, mechanically, before the model sees the prompt or performs the edit.

Everything below is confirmed against actual code and actual test runs in this session, not assumed.

## Bugs Found This Session (root causes, not symptoms)

### Bug 1: Static query, never real user input
`rag-enforce.py` (before fix) hardcoded `search_query = "code quality patterns methodology security error handling"` on every single call. `_extract_keywords()` existed but was never invoked. Every prompt, regardless of content, searched the same static string. This is why "make a flappy bird game" returned OWASP/.NET/Go results — the actual words "flappy," "bird," "game," "canvas," "html" were never searched.

**Fix applied:** `main()` now reads `payload.get("prompt", "")` from stdin (confirmed correct field name by cross-checking `session-primer.py:574`, which reads the same key), extracts keywords, and only falls back to the static string when there's no usable prompt text.

### Bug 2: Emoji crash on Windows console
`rag-enforce.py` printed `⚠️` and `📥` directly to stdout. Windows consoles default to cp1252 encoding, which cannot represent these characters, throwing `UnicodeEncodeError` and crashing the hook with exit code 1. This produced every "UserPromptSubmit hook error / Failed with non-blocking status code: Traceback" the user saw throughout this session — not a RAG connectivity problem, a print encoding crash.

**Fix applied:** `sys.stdout.reconfigure(encoding="utf-8", errors="replace")` at module load, plus emoji replaced with plain ASCII tags (`[WARN]`, `[INFO]`).

### Bug 3: code-pattern-inject.py never reached the model
The hook ran pattern detection and RAG search in a background daemon thread, then only wrote results to a log file. Background threads that outlive the hook process's stdout flush never make it into Claude Code's injected context — only what's printed to stdout before the hook process exits gets injected. The hook always exited 0 immediately, orphaning the search.

**Fix applied:** rewritten to search synchronously and `print()` the formatted results before returning, matching the pattern in `rag-search-on-edit.py` (which worked correctly the whole time because it always searched synchronously).

### Bug 4: Timeout shorter than real search latency
`_search_rag()` used a 3-second timeout with no logging on failure, so every slow response looked identical to a dead server. Measured directly with `curl`: an `all_topics` search across 61 topic databases with `limit=10` took **7.8 seconds** under load. The 3s timeout was simply too short for real server behavior, not a sign of instability.

**Fix applied:** timeout raised to 12s (rag-enforce.py) / 10s (code-pattern-inject.py, lighter `limit=2` queries), retry logic added (2 retries, 200ms/500ms backoff), and every attempt now logs its exception type, message, query, and elapsed time to `state/rag-enforce.log` / `state/code-pattern-inject.log`.

### Bug 5: `/web-search` endpoint does not exist
`_web_search_fallback()` called `POST /web-search`, which 404s — confirmed by scanning every registered route in `app.py` (`handle_status`, `handle_search`, `handle_prove`, etc. — no `handle_web_search`). The server's actual web fallback lives **inside** `handle_search` (app.py:230-253): it checks `top_score < WEB_SEARCH_SCORE_THRESHOLD` itself, calls `web_search()` internally, spawns its own background indexer, and returns the results as `web_search_results` in the same `/search` response. The hook's fallback call was silently 404ing on every single invocation, the entire time.

**Fix applied:** `_search_rag()` now also returns `web_search_results` straight from the server's own `/search` response. `_web_search_fallback()` was rewritten to import and call `server/web_search.py`'s `web_search()` function directly, in-process, for the one case the server's score-only threshold misses (see Bug 6).

### Bug 6: Score-only fallback trigger misses topical mismatches
Server-side and original hook-side triggers were both score-only (`best_score < 0.5`). Confirmed failure case: query "make flappy bird game html" scored 0.78 against HuggingFace's "BigBird" model docs (shared literal word "bird") and React's tic-tac-toe tutorial (shared word "game") — high embedding similarity, zero topical relevance. Score alone cannot catch this.

**Fix applied:** `_keyword_overlap_ratio()` — a mechanical check, not an LLM judgment call. Extracts keywords (len > 3, stopwords removed) from the query, checks what fraction literally appear in the top 3 results' content. Threshold set to 0.5 (majority overlap required) after testing 0.34 let false matches through. Confirmed working: the BigBird/react case now measures overlap=0.40, correctly triggers client-side fallback.

### Bug 7 (open, not a hook bug): DuckDuckGo Instant Answer API returns empty for how-to queries
Verified directly: `web_search("make flappy bird game html", max_results=3, timeout=4.0)` returns `{'results': [], 'error': None}` — HTTP 200, no error, just nothing. DuckDuckGo's Instant Answer API (`api.duckduckgo.com`, used by `server/web_search.py`) is built for factual/definitional lookups ("capital of France"), not tutorial or how-to queries. This is an external API limitation, confirmed by direct call, not a hook-level bug.

**Not fixed — needs a decision, not more debugging.** Every layer above this (query construction, timeout, retry, logging, overlap-based trigger, in-process fallback call) is confirmed working end to end. The one remaining gap is the search backend itself. Fixing this requires swapping to an API that actually returns general web results (a real search API, not an instant-answer API) — see Open Decision below.

## Required Behavior (spec, not yet fully implemented)

### 1. Query construction — always real, never static
Every hook that searches RAG must build its query from actual input:
- `UserPromptSubmit` hooks: from `payload["prompt"]`
- `PreToolUse` hooks on Edit/Write/MultiEdit: from `tool_input["new_string"]` / `tool_input["content"]`
- Never a hardcoded string as the primary query. A hardcoded string is only acceptable as a last-resort fallback when the real input is empty.

### 2. Injection must reach stdout, synchronously, before hook exit
Background threads are banned for anything meant to reach the model. If a hook wants to inject context, it must:
1. Run the search inline (blocking the hook's own process, not the user's edit — PreToolUse hooks already run in a subprocess Claude Code waits on briefly)
2. `print()` the formatted result before `return`
3. Exit only after the print has happened

Background threads are still allowed for **non-injection** side effects (e.g. spawning the web crawler to fill the KB for next time), because those don't need to reach the current turn.

### 3. Retry before declaring failure
A single failed request must not be treated as "server down." Required:
- Up to 2 retries with a short backoff (e.g. 200ms, 500ms) before falling back to the unavailable/self-heal path
- Every retry attempt and its outcome logged (exception type + message, not swallowed)
- Only after all retries fail does the hook print the `[WARN] RAG SERVER UNAVAILABLE` message and trigger self-heal

### 4. All failures logged with real detail
No bare `except Exception: return [], False`. Every except block must log:
- The exception type and message
- The query that was being searched
- The endpoint that was called
- A timestamp

Logs go to a file under `clean-rag/state/`, one log file per hook, so failures can be read directly instead of relying on the user to paste terminal output.

### 5. Web search fallback trigger must be mechanical, not score-only
**Fixed.** `_keyword_overlap_ratio()` catches the case a score threshold alone misses — high embedding similarity from a shared literal word, wrong domain. Threshold: fallback fires when fewer than half the query's keywords literally appear in the top results' content. Confirmed against a real failure case (BigBird/react matching "flappy bird" at score 0.78, overlap 0.40, correctly triggered).

### 6. No LLM judgment on whether to inject
The model must never decide "I don't need RAG for this, I know it cold." That decision belongs to the hook, before the model sees the prompt. If the hook decides to search, it searches. If the hook decides to fall back to web search, it falls back automatically. The model's only job is to use whatever was injected, or note explicitly when nothing relevant came back.

### 7. Background crawler still applies
When web search fallback fires, the existing `_spawn_background_crawler()` behavior stays: index crawled results without LLM summarization, so future queries on the same topic hit local RAG instead of re-searching the web every time.

### 8. Agent correction when injected results are clearly wrong (user approved, not yet actually practiced)

The hook's mechanical search has a real, confirmed failure mode: casual or vague messages get searched literally and can return nonsense (this session alone: "really sure" returned grammar advice, "wired up" returned electrical wiring instructions, "would it be better" returned a Dickens quote and a Bible verse, then wrote that content into the permanent KB via the background crawler). The hook cannot fix this on its own — it has no real conversation understanding, only a transcript file it can parse for keywords.

The agreed fix: the hook still fires first, every time, as the fast mechanical default. But when the injected results are obviously wrong given the actual conversation, the model itself must spawn an Agent with real context (not a re-parsed transcript, the actual conversation state) to run a corrected search before treating the bad injection as final. The hook cannot do this itself since it has no access to the Agent or Task tool, that only exists in the model's own turn.

This was approved but not implemented. A user check on 2026-07-12 confirmed it had not actually been practiced even once, despite several visibly bad injections occurring in the same session after approval. The gap: noticing an injection is bad is not the same as acting on it. This section exists specifically so that gap does not repeat silently again.

## Open Decision: Search Backend

Every layer of the injection pipeline is confirmed working end to end (real query, correct timeout, retries with logging, mechanical topical relevance check, in-process fallback call). The one remaining gap is `server/web_search.py`'s use of DuckDuckGo's Instant Answer API, which returns empty results for tutorial/how-to queries by design, not by failure. This was verified with a direct call, not assumed.

Options, none implemented yet:
- **Swap to a real search API** (Bing, Brave, SerpAPI, etc.) — most already requires an API key and has usage limits or cost, unlike the current free, keyless DuckDuckGo endpoint
- **Use DuckDuckGo's HTML scrape endpoint** instead of the Instant Answer API — returns real search results, no key needed, but scraping HTML is more fragile than a JSON API and can break on layout changes
- **Accept the gap for how-to queries** and rely on the model's own training knowledge for that category, while keeping forced injection for factual/API/library questions where DuckDuckGo's Instant Answers actually work

This choice affects cost, reliability, and setup complexity — it needs a decision, not a silent pick.

## Tried and Reverted: Zero Shot Query Classifier

Built, tested, and removed in the same session. Worth recording so it isn't
tried again the same way without knowing why it didn't hold up.

**What it was:** a persistent HTTP server (`server/classifier_server.py`)
running `MoritzLaurer/deberta-v3-large-zeroshot-v2.0` in an isolated venv
(`.venv-router`, CPU-only torch, needed to avoid a real confirmed conflict
with `open-webui`'s pinned `pyarrow==20.0.0` in the shared Python
environment). It classified each prompt into "programming or coding",
"small talk", or "explaining how a tool works", and `rag-enforce.py` used
that to skip injection on small talk and add project-scoped search sources
for tool questions.

**What worked:** clear cases were genuinely well handled. "thanks" correctly
classified as small talk and skipped injection. "how do I handle async
errors in javascript" classified as programming at 1.00 confidence. Self
healing was confirmed working (killed the server mid session, it
auto-restarted, the request still completed via graceful fallback).

**Why it was removed:** confirmed weak on borderline/ambiguous real
messages, the exact category causing the original problem this session
started from. One concrete example, reproduced in testing: a message
about the injection system's own architecture scored 0.52 "programming or
coding" vs 0.46 "explaining how a tool works", different runs of the same
kind of message could tip either way. The model was not unreliable due to
a bug, it was genuinely uncertain, and that uncertainty landed exactly on
the hardest cases this system needed to get right.

**Replacement direction:** since a background hook subprocess cannot spawn
a Claude agent (confirmed architectural limit, not a config gap, see
`Sub-Agents Do Not Inherit Hooks` below), the judgment call moves to the
orchestrating model itself: spawn a parallel research agent alongside any
real work agent to determine what is actually worth researching, using
real conversation understanding instead of a three-label classifier.

## Sub-Agents Do Not Inherit Hooks

Confirmed via direct research against Claude Code's own documentation and
a tracked GitHub issue (`anthropics/claude-code#27661`), not guessed: Task
tool spawned sub-agents do not inherit `UserPromptSubmit` or `PreToolUse`
hooks from the parent session's `settings.json`. This was independently
confirmed empirically in this session too — two real Task agent spawns
produced zero corresponding entries in `rag-enforce.log`, the hook simply
never fired for them.

This means `rag-enforce.py` and `code-pattern-inject.py` only ever run in
the main conversation, never inside a spawned agent. If a sub-agent needs
injected research, the orchestrating model has to build and pass it in the
agent's own prompt explicitly — there is no hook-level mechanism that
reaches into Task-spawned agents, and none is exposed to configure.

## Root Cause: Research Agents Skip Requested Aspects Under an Open Quota

Found by direct investigation, not assumption, after a research agent's
output was missing coverage of one of five aspects it was explicitly asked
to research (code organization and testability for a Flappy Bird build).
Confirmed this was not a retrieval gap: a direct search against clean-rag
for "separate game logic from rendering, testable, pure functions"
returned real, relevant results at 0.83 to 0.87 score, sourced from
`react` and `testing-library`. The content existed and was reachable. The
research agent simply never searched for it, and never reported its
absence either.

**Root cause:** the research agent's prompt listed 5 aspects to cover but
asked for "the 3-5 best, most specific, most actionable findings." An open
quota like that rewards depth on whichever aspect surfaces the richest
vein first (here, React `requestAnimationFrame` pitfalls), and gives no
structural reason to come back and search the remaining aspects once the
quota is filled. This is a prompt design flaw in how research agents get
instructed, not something specific to Flappy Bird or to this one research
agent's judgment.

**Fix, not a band aid:** research agent prompts must require one finding
(or an explicit "searched X, found nothing relevant" note) per listed
aspect, not an open ended top N across all aspects combined. Coverage is
enforced by structure, not left to the agent's own prioritization.
Retested on a deliberately unrelated task (a Python CSV watcher CLI, not
Flappy Bird, so the fix is verified general rather than tuned to one
example) with the same 5-aspects-explicit-per-item structure.

## Research Agent Template: Explicit Depth Versus Breadth Routing

Extends the per-aspect coverage fix above. That fix made research agents
cover every requested aspect instead of over-digging one rich vein. This
adds a second, previously unenforced rule on top: which source to search
for each aspect.

The design principle (agreed on, but not written into any actual prompt
until now): clean-rag's vector DB should serve as **depth**, general
software engineering principles and patterns that generalize across many
unrelated projects (test organization, separation of concerns, standard
algorithmic approaches). Web search should serve as **breadth**,
practical, task-specific guidance (how people actually build this exact
kind of thing, common mistakes in this specific genre, what the best way
to structure this particular tool looks like).

This split was never actually enforced before this section existed. It
emerged by coincidence in the Flappy Bird and CSV watcher test runs
(clean-rag happened to surface general principles, WebSearch happened to
surface task-specific tips) because that is roughly what each source
naturally contains, not because any research agent was told to route that
way.

**The rule, to include verbatim in every research agent spawn prompt:**

For each listed aspect, first decide: would the same answer apply across
many unrelated projects (depth), or is the answer specific to this one
kind of task (breadth)? Breadth includes not just pitfalls but also "what
is the best/recommended way to build this specific kind of thing" —
generality is what separates the two, not phrasing. Depth aspects search
clean-rag first (`POST http://127.0.0.1:8613/search`, `all_topics`), only
falling through to WebSearch if clean-rag genuinely returns nothing
relevant (confirmed this happens routinely: 3 of 5 CSV-watcher aspects had
zero useful clean-rag hits). Breadth aspects go straight to WebSearch — a
docs-and-patterns focused KB is unlikely to hold task-specific practical
tips, and forcing a clean-rag search first just wastes a round trip
(confirmed: clean-rag returned off-topic noise for "common Flappy Bird
implementation mistakes," an explicitly breadth aspect). The existing
per-aspect coverage requirement still applies on top of this — one finding
or an explicit "nothing found" note per aspect, never silently dropped.

## Root Cause: Retrieval Is Only As Good As The Query

The single finding this session keeps re-deriving, now measured rather than
argued. Every bad injection traces back to one thing: the query was built
mechanically, with no reasoning behind it. Not "web search is bad," not "the
KB is bad." The query.

Scores measured on garbage, all with mechanically built queries:

| Query source | What it retrieved | Score |
|---|---|---|
| "is it done" (keywords) | Azure Functions `context.done()` docs | 0.82 |
| "duck duck go" (keywords) | react-query docs, then PCMag browser reviews | 0.80 |
| a function with a SQL injection in it (canned pattern) | Go stack trace docs | 0.86 |
| `MAX_RETRIES = 5` (raw code) | PowerShell retry docs | 0.86 |
| that same SQL injection (raw code) | Flask query docs, no mention of the vuln | 0.87 |

**`min_score` does not save you.** Every one of those cleared 0.5 comfortably.
Cosine similarity always returns a nearest neighbour, and it's always confident.
A wrong query gets a confident wrong answer, not an empty result.

Two things follow, and both were assumed wrong earlier in this session:

**"Vector search degrades gracefully" is false.** It was stated in this doc and
in the code, and the table above falsifies it. A keyword soup query embeds into
*something*, and something is always nearby.

**Embedding search retrieves text that looks like the query, not a critique of
it.** Feeding it SQL injecting code returns more SQL code. Getting the warning
would require searching "SQL string concatenation vulnerability", which requires
having already read the code and noticed the bug. That's reasoning, and a hook
does not have it.

### The architecture that follows

Hooks cannot reason, and they cannot spawn something that can
(claude-code#64898 is open, not shipped). So:

- **Hooks enforce, they do not retrieve.** They print the reuse check and the
  research mandate (depth and breadth), and name the tools. They do not guess a
  query.
- **One exception, the project index.** `project:<git_root>` is still searched,
  because a hit there is a real file in the repo that can be opened and checked.
  It's checkable noise rather than confident fiction. The topic KB
  (`all_topics`) is off in both hooks.
- **Reasoning models retrieve**, because only they can write a query worth
  running. research-agent picks its own queries and has been reliably good all
  session, precisely for that reason: rate limiter query returned real ASP.NET
  rate limiting docs at 0.85, Flappy Bird research covered all five aspects with
  real sources.

## Test Variant: Web Covers Both Depth and Breadth (One Off Test)

User asked to try a simpler variant before committing to the split above:
since `web_search.py` already filters to good sources, let WebSearch alone
cover both depth and breadth aspects for one retest, skip clean-rag
routing entirely for this run, and see how the output compares. This is a
one time comparison, not a replacement for the routing rule above.

Concrete Flappy Bird framing the user gave for the split itself (kept for
future use once routing is turned back on): depth is code structure, things
like separation of responsibility and TDD, and the specific choice to
implement the bird as a React-based animation. Breadth is what a Flappy
Bird game should look like and feel like: which parts should be animated,
general visual and design choices, not the code shape underneath them.

## Deprecated: Web Crawler Automatic Indexing

Removed entirely, both call sites (`rag-enforce.py`'s
`_spawn_background_crawler`, `app.py`'s `_spawn_web_indexer`), plus the now
orphaned `server/web_crawler.py` and `hooks/_crawl_runner.py` files
themselves. Confirmed no remaining callers anywhere in the codebase before
deleting either file.

**Why:** casual conversational messages were triggering the web search
fallback and getting permanently written into the knowledge base under
auto generated topic names. Confirmed real, not hypothetical: a message
using the word "injection" in the RAG sense got real medical cortisone
shot content crawled and indexed under a topic slugged from that message.
Twenty two such fallback topics had accumulated in a single session before
this was caught and removed.

**Cleanup performed:** stopped the running server (a stale PID file meant
`server_ctl.py stop` did not actually kill the live process, found and
killed the real one directly via the port), deleted `knowledge/fallback/`
and `databases/fallback/` entirely, then found the topic list is cached in
`state/topics.json` independent of the database files on disk (a restart
alone did not clear it), removed all 22 entries tagged
`"category": "fallback"` from that file directly, confirmed via a fresh
server restart that the topic count dropped from 83 to the real 61
curated topics.

**What still works:** the client side fallback (`_web_search_fallback` in
`rag-enforce.py`) still runs and still displays real web results for the
current turn when local RAG is weak. It just no longer writes anything to
the permanent knowledge base afterward. Verified live: a repeat of the
Flappy Bird fallback query after this change still returned three real
web results, and `knowledge/fallback/` stayed empty afterward.

## Verification Method

Every claim in this spec was checked against actual code (`rag-enforce.py`, `code-pattern-inject.py`, `rag-search-on-edit.py`) or actual test runs (`curl`, direct Python `urllib` calls, subprocess hook invocations) in this session — not assumed from documentation or training data. Any future change to these hooks should be verified the same way: run the hook directly with a crafted stdin payload, capture actual stdout/stderr, don't trust that a code change "should" work.
