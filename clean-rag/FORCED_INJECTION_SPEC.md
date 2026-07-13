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

## Verification Method

Every claim in this spec was checked against actual code (`rag-enforce.py`, `code-pattern-inject.py`, `rag-search-on-edit.py`) or actual test runs (`curl`, direct Python `urllib` calls, subprocess hook invocations) in this session — not assumed from documentation or training data. Any future change to these hooks should be verified the same way: run the hook directly with a crafted stdin payload, capture actual stdout/stderr, don't trust that a code change "should" work.
