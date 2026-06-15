# ClaudeBoost Stack

## Python (3.11+)

All hook scripts and the RAG server require Python 3.11+. Hooks use:
- `from __future__ import annotations` (always — enables deferred type hints)
- `pathlib.Path` for all file operations (no `os.path`)
- `json` for state files and hook payloads
- `subprocess` only in test helpers (`run_hook`) — never in production hooks
- `urllib.request` for HTTP calls to the RAG server (no requests library dependency)

Never add third-party dependencies to hook scripts. They run in whatever Python the
user has configured (`$CLAUDEBOOST_PYTHON`), which may not have pip packages installed.

## RAG Server (mcp-rag-server/)

Python package at `mcp-rag-server/src/rag_server/`. Install with:
```
pip install -e "mcp-rag-server/[dev]"
```

Key dependencies:
- **chromadb** (>=1.5.9) — vector store for embeddings
- **sentence-transformers** (>=3.0) — `BAAI/bge-base-en-v1.5` (768-dim) for knowledge/agents
- **tree-sitter** + language grammars — AST-based code chunking for 14 languages
- **starlette + uvicorn** — HTTP server framework (not FastAPI)
- **networkx** — graph data structure for dependency graph
- **beautifulsoup4 + lxml + html2text** — web page fetching/chunking
- **pymupdf** — PDF text extraction

GPU acceleration: CUDA is used when available (speeds up embedding ~10x).
The server writes a heartbeat to `.rag-index/.heartbeat` every 30 seconds.

## Embedding Models

Two models, both loaded at startup:
- **BAAI/bge-base-en-v1.5** (768 dim) — knowledge/agents/workspace content
- **flax-sentence-embeddings/st-codesearch-distilroberta-base** — codebase search

Don't mix chunks from different models in the same collection — `dim_ok: false` in
`GET /status` indicates a dimension mismatch that requires a force-reindex.

## Testing (pytest)

Test suite is in `scripts/tests/`. Run with:
```
python -m pytest scripts/tests/ -v
```

Dependencies: `pytest>=8.0` (installed via `mcp-rag-server/pyproject.toml [dev]`).

Tests must NOT require a running RAG server. Use the `rag_live`/`rag_dead` fixtures
from conftest.py to simulate RAG state via a fake heartbeat file.

All test scripts use `subprocess.run` to call hook scripts as child processes — this
tests the actual exit codes and stderr output exactly as Claude Code sees them.

## Windows-Specific Considerations

- CLAUDEBOOST_HOME uses forward slashes (`C:/Users/...`) — backslashes cause issues
- `$TEMP` resolves to `C:/Users/.../AppData/Local/Temp` — use full absolute paths, not `$TEMP` in Bash
- Sentinel files: `C:/Users/grayw/AppData/Local/Temp/claudeboost_rag_ok`, `claudeboost_active`
- `$CLAUDEBOOST_PYTHON` must point to the Python that has mcp-rag-server installed
- Line endings: scripts/tests/ must use LF (Unix) endings — CRLF causes pytest issues on Windows

## settings.json Hook Registration

Hooks are registered in `.claude/settings.json` under `"hooks"`. The format:
```json
{
  "matcher": "Agent",
  "hooks": [{
    "type": "command",
    "command": "\"$CLAUDEBOOST_PYTHON\" \"$CLAUDEBOOST_HOME/scripts/hook-name.py\""
  }]
}
```

`$CLAUDEBOOST_PYTHON` and `$CLAUDEBOOST_HOME` are expanded by Claude Code — they work
in settings.json even though they trigger the bash-guard in Bash tool calls.

Matcher values: `Agent`, `Bash(pattern*)`, `Read`, `Grep`, or omit for all tools.

<!-- Source: https://docs.trychroma.com/guides | Tier: A | Date: 2026-06-14 -->
## chromadb (>=1.5.9) — vector store

### What It Does
chromadb is the vector database that stores all embeddings for ClaudeBoost's RAG server.
Every knowledge file, agent definition, and codebase chunk is stored as a vector in chromadb
and retrieved via cosine similarity search. The server uses multiple collections: one for
knowledge/agents content (768-dim BGE embeddings) and one for codebase search.

### Security
An unpatched RCE (CVE-2026-45829) affects all chromadb >= 1.0.0 and is exploitable before
authentication is consulted. The RAG server MUST bind to `127.0.0.1` only (never `0.0.0.0`).
Built-in auth was removed entirely in v1.0.0 — any chromadb port exposed beyond localhost
has zero auth and accepts arbitrary `add()`/`delete()`/`upsert()` from anyone who can reach it.
Verify the bind address in `mcp-rag-server/` startup code before every deployment.

### Performance
HNSW parameters (`M`, `ef_construction`, `ef_search`, `hnsw:space`) cannot be changed after
collection creation — set them at `create_collection` time. Default distance metric is L2,
not cosine. For BGE embeddings, create collections with `metadata={"hnsw:space": "cosine"}`.
Optimal insert batch size is 50–250; do not call `add()` with 10k+ docs at once. RAM formula:
`N = R × 0.245` (millions of embeddings per GB). ClaudeBoost's scale (< 100K chunks) is fine
on typical dev machines.

### Pitfalls
- `get_or_create_collection` silently ignores `metadata` on existing collections (1.x) — if
  you re-pass `hnsw:space` expecting it to update, it won't. Check if collection is new first.
- `list_collections()` returns `Collection` objects — use `.name` attribute, not the object itself.
- Memory is NOT freed after `delete_collection()` without a server restart. Avoid teardown/rebuild
  loops without restarting the process.
- Database migrations are irreversible — back up `.rag-index/` before any chromadb version bump.
- Orphaned HNSW segment directories accumulate after crashes (especially on Windows). Run
  `chops db clean` to remove them if search results look stale.
- Dimensionality is locked once any embedding is added. Switching embedding models requires
  deleting and rebuilding all collections — there is no in-place update path.

### Integration in This Project
ClaudeBoost uses `PersistentClient(path=...)` — never `EphemeralClient()` (loses data on restart).
Do not pass an `embedding_function` to `get_or_create_collection` when storing pre-computed
vectors — if you do, Chroma re-embeds on every `.query()` call, causing silent vector mismatches.
The `SentenceTransformerEmbeddingFunction` built into chromadb defaults `normalize_embeddings=False`;
since ClaudeBoost uses cosine collections, always set `normalize_embeddings=True` or normalize
manually before storing.

<!-- Source: https://www.sbert.net/docs/package_reference/sentence_transformer/SentenceTransformer.html | Tier: A | Date: 2026-06-14 -->
## sentence-transformers (>=3.0) — embedding models

### What It Does
sentence-transformers generates the vector embeddings stored in chromadb. ClaudeBoost loads
two models at startup: `BAAI/bge-base-en-v1.5` (768-dim, for knowledge/agents content) and
`flax-sentence-embeddings/st-codesearch-distilroberta-base` (for codebase search). Never mix
chunks from different models in the same chromadb collection.

### Security
Pin both models with `revision="<commit_sha>"` in `SentenceTransformer(model_name, revision="...")`.
Without a pin, a compromised Hub update can silently change embedding outputs or execute
arbitrary Python via Pickle deserialization in `pytorch_model.bin`. Prefer models that ship
`model.safetensors` (both BGE and the code-search model do) — safetensors performs zero-copy
deserialization with no code execution path.

### Performance
On CPU: ONNX-O4 backend (`pip install sentence-transformers[onnx]`) gives ~3x speedup over
default PyTorch for short texts. Enable via `backend="onnx"`. Flash Attention 2 (requires
`transformers>=5.0`) gives the biggest win for variable-length inputs like ClaudeBoost's
knowledge files. Sort inputs by length before batching — reduces wasted padding computation
by 20-40%. Default batch size is 32; safe to increase to 64-128 on modern CPU.

### Pitfalls
- `BAAI/bge-base-en-v1.5` silently truncates inputs beyond 512 tokens — no warning, tail is
  dropped. Knowledge XML files can exceed this easily. Always chunk before encoding.
- `normalize_embeddings=False` is the default. BGE models require `normalize_embeddings=True`
  for correct cosine similarity. Without it, similarity scores depend on vector magnitude, not
  direction — semantically similar short sentences rank poorly against long ones.
- The v5.4 rename: `encode(sentences=...)` → `encode(inputs=...)`. Old kwarg still works but
  emits deprecation warnings in production logs. Update any call sites using `sentences=`.
- `encode()` is not thread-safe when sharing a model instance across Python threads. Use
  separate instances per thread, or use process-based parallelism.
- Known early-inference memory leak (~first 10K calls). Pre-warm the model with a dummy batch
  at server startup to exhaust the leak window before production traffic hits.

### Integration in This Project
BGE models use cosine similarity — always encode with `normalize_embeddings=True` and create
the chromadb collection with `metadata={"hnsw:space": "cosine"}`. The code-search distilroberta
was trained with dot-product — normalize embeddings to unit length so dot-product equals cosine.
`encode_query()` and `encode_document()` methods (v5.4+) improve BGE retrieval precision for
asymmetric search (short query vs. long document chunk) — worth switching from raw `encode()`.

<!-- Source: https://www.starlette.io/routing/ | Tier: A | Date: 2026-06-14 -->
## starlette (>=0.37) + uvicorn[standard] (>=0.29) — HTTP server

### What It Does
The RAG server is a Starlette ASGI app served by uvicorn on port 8612. Routes are defined
as plain async functions in a `Route` list passed to `Starlette(routes=[...])`. ClaudeBoost
uses this directly — not FastAPI — so there are no decorators or Pydantic schemas. All Claude
Code hooks and the main loop reach the server via `POST /context`, `POST /search`, `POST /index`.

### Security
The RCE risk is at the chromadb layer, not Starlette. For the HTTP server itself: never set
`allow_origins=["*"]` on the CORSMiddleware for authenticated APIs. The RAG server has no
browser clients so CORS is not needed. Input validation is not built-in — validate JSON
bodies manually after `await request.json()` (raises on malformed JSON, but does not type-check).
No CSRF needed for a pure REST API with no cookie-based auth.

### Performance
`pip install uvicorn[standard]` activates `uvloop` (Cython event loop) and `httptools`
(C HTTP parser) — the main performance multipliers. All handlers must be `async def`. Never
call blocking I/O (disk reads, `subprocess`, `requests.get`) directly inside a handler — use
`await asyncio.sleep()`, async libraries, or `loop.run_in_executor()` for blocking work.
Single worker throughput is ~4,900 req/s — more than enough for localhost-only use.

### Pitfalls
- Reading `await request.body()` inside `BaseHTTPMiddleware` consumes the stream. The endpoint
  handler then receives an empty body. Use pure ASGI middleware if you need to inspect the body,
  or avoid `BaseHTTPMiddleware` entirely.
- Starlette 1.0rc1 (Feb 2026) removes `on_startup`/`on_shutdown` parameters, `@app.route()`,
  and all event-handler decorators. If `mcp-rag-server/` uses these, they break on upgrade past
  0.45. Migration target is the `lifespan` context manager.
- Middleware ordering: request phase runs top-to-bottom, response phase bottom-to-top. Auth
  middleware must be added before any middleware that reads auth state.
- No per-request timeout by default. A slow embedding call or a hung chromadb query will hold
  the connection open indefinitely. Wrap slow operations with `asyncio.wait_for(coro, timeout=N)`.
- `BackgroundTask` exceptions are silently discarded after the response is sent — always log
  inside background tasks; don't rely on the exception handler for cleanup.

### Integration in This Project
Always specify `methods=["POST"]` explicitly on routes — function endpoints default to `GET`
only. Access the request body with `await request.json()`. For new endpoints, follow the
existing pattern: validate the JSON shape, call the relevant RAG operation, return a
`JSONResponse`. The server runs in-process via `uvicorn.run()` — no Gunicorn needed for a
single-machine localhost tool.

<!-- Source: https://networkx.org/documentation/stable/reference/classes/digraph.html | Tier: A | Date: 2026-06-14 -->
## networkx (>=3.0) — dependency graph

### What It Does
networkx stores the code dependency graph: directed edges from files to the modules they
import. `DiGraph` is used for directed relationships. The RAG server builds this graph at
index time and uses it for `mode=graph` searches — finding structural neighbours (callers,
callees, imports) that semantic vector search misses.

### Security
The graph is stored in-memory and on disk via pickle. Pickle deserialization executes
arbitrary Python — never load a `graph.db` file from an untrusted source. For ClaudeBoost's
use (locally built from user's own code), this is not a concern in practice.

### Performance
All graph data lives in Python dicts — no C core, no parallel execution. Memory scales at
~100 bytes per edge. At ClaudeBoost's scale (hundreds to low-thousands of files), performance
and memory are non-issues. Rebuilding the graph from scratch on server restart is cheap enough
that on-disk persistence is optional.

### Pitfalls
- **Not thread-safe.** Concurrent reads are fine in practice, but any write must be serialized
  with a lock. Two parallel indexing calls writing to the same graph will corrupt it.
- `G.copy()` is a shallow copy — mutable attribute values (lists, dicts) are still shared
  with the original. Use `copy.deepcopy(G)` for fully independent copies.
- Never add/remove nodes while iterating `G.nodes` or `G.edges` — collect mutations in a list
  first, then apply them after the iteration completes.
- `None` is not a valid node — use an empty string or sentinel value instead.

### Integration in This Project
The RAG server serializes the graph to `graph.db` alongside the vector index. Nodes are
file paths; edges represent import relationships extracted by tree-sitter. `successors()` gives
files that a given file imports; `predecessors()` gives files that import it. Used by
`POST /search mode=graph` to expand a vector query with structural neighbours.

<!-- Source: https://www.python-httpx.org/api/ | Tier: A | Date: 2026-06-14 -->
## httpx (>=0.27) + beautifulsoup4 (>=4.12) + pymupdf (>=1.24) — web fetching stack

### What It Does
When `/research-task` or `/research-project` indexes external URLs, httpx fetches the page,
beautifulsoup4 parses the HTML, html2text converts it to markdown for chunking, and pymupdf
extracts text from PDFs. This stack runs inside the RAG server when `POST /index_research`
or `POST /index` fetches remote sources.

### Security
PyMuPDF is **AGPL v3 licensed**. Open-source use is fine. If ClaudeBoost ever ships as a
hosted SaaS, the AGPL requires either open-sourcing the product or purchasing a commercial
licence from Artifex. Flag this before any hosted deployment.

httpx validates TLS certificates by default. Do not pass `verify=False` to skip cert
validation — this opens man-in-the-middle attacks when fetching external docs.

### Performance
PyMuPDF (MuPDF C engine) is very fast — `page.get_text()` extracts text in milliseconds.
Pass `flags=0` to exclude image decoding for text-only PDFs; cuts runtime roughly in half.
Always use `lxml` as the beautifulsoup4 parser (`BeautifulSoup(html, "lxml")`) — the
auto-detect fallback is slower and produces different parse trees for malformed HTML.

### Pitfalls
- **httpx connection leak on cancellation**: if an async task wrapping an httpx request is
  cancelled, `response.aclose()` may not be called. Always use `async with client.stream(...)`
  or `try/finally: await response.aclose()` to guarantee cleanup.
- **PoolTimeout after long uptime**: a long-lived global `AsyncClient` can exhaust its pool
  if responses are not fully read. Call `await response.aread()` before releasing connections.
- **bs4 encoding**: pass `response.text` (already decoded by httpx) to `BeautifulSoup()`, not
  `response.content` (raw bytes). If you must pass bytes, also pass `from_encoding=response.encoding`
  or non-ASCII content will be silently mangled.
- `follow_redirects=False` is the httpx default — set `follow_redirects=True` explicitly for
  URLs that use 301/302 (most documentation sites do).

### Integration in This Project
The RAG server uses `AsyncClient` with a per-request timeout. All response reads should use
the context-manager form (`async with client.stream(...)`) to avoid connection leaks. The
`POST /index_research` handler fetches each URL, routes to either the PDF or HTML parser
based on Content-Type, then chunks and embeds the result.

<!-- Source: https://tree-sitter.github.io/py-tree-sitter/ | Tier: A | Date: 2026-06-14 -->
## tree-sitter (>=0.23) — AST-based code chunking

### What It Does
tree-sitter parses source files into concrete syntax trees for 14 languages (Python, JS, TS,
C, C++, Go, Rust, Java, Ruby, Bash, Lua, Kotlin, Swift, PHP, C#). The RAG server uses it to
extract meaningful code units (functions, classes, methods) as chunks before embedding — far
more semantically coherent than naive line-based splitting.

### Security
tree-sitter is a pure text parser — it does not execute code, so parsing untrusted source
files carries no code-execution risk. Malformed/adversarial input produces ERROR nodes rather
than crashes. Individual `TSTree` instances are not thread-safe: each worker thread must have
its own `Parser` instance. Do not share trees across threads without copying.

### Performance
Full parse of a 10K-line file takes under 100ms. Incremental re-parse after a single edit
takes under 1ms (reuses unchanged subtrees). Use `TreeCursor` instead of recursive `Node`
property access for tree traversal — avoids per-node Python object allocation and is
significantly faster on large files. Check `Language.version` against `MIN_COMPATIBLE_LANGUAGE_VERSION`
(13) and `LANGUAGE_VERSION` (15) at startup for each of the 14 grammar packages.

### Pitfalls
- **Version cliff at 0.25**: `Query.captures()` and `Query.matches()` moved to `QueryCursor`.
  Any code calling `query.captures(node)` directly breaks on 0.25+. Fix: `QueryCursor(query).captures(node)`.
- **0.23 breaking changes**: `Parser.set_language(lang)` removed — use `parser.language = lang`.
  `keep_text` kwarg removed from `parser.parse()`. `Query.captures()` return type changed from
  `list[tuple[Node, str]]` to `dict[str, list[Node]]`.
- **Grammar/core ABI mismatch**: using a grammar package compiled for a different ABI version
  raises `TypeError: Invalid language object`. Pin grammar packages to ABI-compatible versions
  and check `Language.version` at startup.
- **ERROR node contamination**: a single missing token can collapse an entire subtree into an
  ERROR node. Always check `node.has_error` before embedding a chunk — fall back to line-based
  splitting when the subtree is error-contaminated.
- **Node ID reuse**: after `parser.parse(new_source, old_tree)`, old tree nodes may be reused
  with the same IDs. Don't use node IDs as stable chunk identifiers across incremental parses.

### Integration in This Project
The chunker uses S-expression queries to extract function/class definitions per language:
```scheme
(function_definition name: (identifier) @func.name)
(class_definition name: (identifier) @class.name)
```
The `Tree` object must stay alive while any `Node` from it is referenced — keep a reference
in scope. For the 14-language grammar set, load each `Language` once at startup and cache it.
If a grammar fails its ABI check, log a warning and skip that language's files rather than
crashing the indexer.

<!-- Source: https://python-watchdog.readthedocs.io/en/stable/api.html | Tier: A | Date: 2026-06-14 -->
## watchdog (>=4.0) — file system monitoring

### What It Does
watchdog watches directories for file system events (create, modify, delete, move) and
dispatches them to handler callbacks. ClaudeBoost uses it in `core/watcher.py` to detect
changes to knowledge files and trigger re-indexing. The `Observer` thread manages platform
backends automatically: `ReadDirectoryChangesW` on Windows, `inotify` on Linux, `FSEvents`
on macOS.

### Security
watchdog itself has no network exposure and no known CVEs. The security risk is in handler
callbacks — if the callback triggers a shell command with the changed file path, that path
is attacker-controlled if watching a world-writable directory. ClaudeBoost watches its own
knowledge directory only, so this is not a concern in practice.

### Performance
Keep `on_modified` and `on_created` handlers fast — they run in the observer thread and block
event consumption. Offload slow work (indexing, HTTP calls) to a separate thread or queue.
Event flooding on bulk writes (e.g., a git checkout touching 50 files) will overwhelm a
handler that launches a re-index per event. ClaudeBoost's `DEBOUNCE_SECONDS = 2.0` in
`core/watcher.py` batches all events within a 2-second window into a single callback.

### Pitfalls
- Always call `observer.stop()` then `observer.join()` in a `finally` block. If the process
  exits without `join()`, the background thread may leave inotify file descriptors or Windows
  handles open. A `RuntimeError` from `join()` before `start()` is called is a common mistake.
- On Windows, `ReadDirectoryChangesW` reports delete events without file-vs-directory
  distinction — a `FileDeletedEvent` may actually be a directory. Handle both defensively.
- Directory move/rename events on Windows arrive before the OS finishes moving children —
  child events may be missed or out-of-order.
- `Observer` is a variable holding the best backend for the current platform — not a class.
  For type annotations, use `watchdog.observers.api.BaseObserver`.
- v4.0 breaking change: `FileSystemEvent` and its subclasses are now `dataclass`es — their
  `repr()` changed. Any code that parses `repr()` output breaks.
- v5.0 breaking change: keyword arguments enforced in several internal APIs.
  `BaseObserverSubclassCallable` renamed to `ObserverType`.

### Integration in This Project
`core/watcher.py` wraps watchdog with a `_DebouncedHandler` that batches events into a
single callback after `DEBOUNCE_SECONDS = 2.0`. The Observer is started in `sync_init()`
and stopped in the server shutdown path. The stop sequence is `observer.stop()` followed by
`observer.join()` — never skip `join()` or the thread may linger past process exit on Windows.

<!-- Source: https://python-path-specification.readthedocs.io/en/stable/api.html | Tier: A | Date: 2026-06-14 -->
## pathspec (>=0.12) — gitignore-style path filtering

### What It Does
pathspec compiles gitignore-style patterns and tests file paths against them. ClaudeBoost
uses it in the indexing pipeline to filter which files get included in the codebase RAG
index — applying `.gitignore` and custom exclusion patterns before embedding.

### Security
No known CVEs. The library only compares strings — it does not access the file system, so
it cannot be exploited by path traversal or injection. The risk is indirect: incorrect
pattern semantics silently excluding files from the index (gaps in search) or including
build artifacts (index bloat and retrieval noise).

### Performance
Pattern matching is pure Python regex compilation + string matching. For ClaudeBoost's
scale (hundreds to thousands of files), performance is not a concern. Compile the
`PathSpec` once and reuse across all files in a scan rather than recompiling per file.

### Pitfalls
- **Always normalize to forward slashes before calling `match_file()`** on Windows.
  `os.path.normpath()` converts `/` → `\` which breaks pattern matching. Use
  `path.replace("\\", "/")` or `pathlib.PurePosixPath(path).as_posix()` before passing
  to pathspec.
- **Anchoring confusion**: a pattern without a slash (`*.log`) matches anywhere in the tree.
  A pattern with a slash (`src/foo`, `/foo`, `foo/bar`) anchors to the gitignore file's
  directory. This diverges from how many developers expect patterns to work.
- **Trailing slash** means directory-only match. `node_modules/` matches the directory but
  not a file named `node_modules`.
- **`dir/*`** in 0.12 now matches all descendants (previously only direct children) — same
  as `dir/`. Code relying on the old `dir/*` vs `dir/` distinction will behave differently.
- **Use `GitIgnoreSpec`, not `PathSpec`**, for closest gitignore conformance. The generic
  `PathSpec` does not handle re-including files under excluded directories (the `!` negation
  for files under an excluded parent directory).

### Integration in This Project
The indexing engine uses pathspec to filter files before embedding. Always pass paths with
forward slashes. If adding new exclusion patterns, test with `spec.match_file("path/to/file")`
before deploying — silent non-matches are hard to debug after the fact.

<!-- Source: https://lxml.de/parsing.html | Tier: A | Date: 2026-06-14 -->
## lxml (>=5.0) — XML and HTML parsing

### What It Does
lxml wraps the C libraries `libxml2` and `libxslt`, providing fast XML/HTML parsing with
full XPath 1.0 support. ClaudeBoost uses it in two roles: as the parser backend for
`beautifulsoup4` (`BeautifulSoup(html, "lxml")`), and directly to parse the ClaudeBoost
knowledge files (`knowledge/*.xml`, `agents/*.xml`). The `lxml.etree` module handles strict
XML; `lxml.html` handles real-world web pages with broken markup.

### Security
**lxml 5.0 breaking change**: `resolve_entities` now defaults to `'internal'` (was `True`
in 4.x). External entity expansion (XXE) is disabled by default — this is the right default.
For untrusted XML, also set `no_network=True` and `load_dtd=False`. lxml 5.4.0+ ships
libxml2 2.13.8 which fixes a parameter entity bypass that existed in 5.0–5.3.2. Stay on
5.4.0+. Never set `resolve_entities=True` on user-supplied or externally fetched XML.

### Performance
`etree.parse()` loads the entire tree into memory — fine for ClaudeBoost's KB files (small).
For large files (>10MB), use `iterparse()` with `events=("end",)` and call `elem.clear()`
after processing each element. Also delete processed ancestors with
`while elem.getprevious() is not None: del elem.getparent()[0]`. Compile XPath expressions
once with `etree.XPath(...)` and reuse — recompiling per element is the top lxml performance
mistake. Avoid `//` (descendant axis) in hot XPath paths; prefer specific paths.

### Pitfalls
- Namespace handling: lxml uses Clark notation internally — `{http://ns.uri}tagname`.
  XPath queries must bind namespace prefixes explicitly:
  `etree.XPath("//ns:element", namespaces={"ns": "http://ns.uri"})`.
  Forgetting this produces zero results with no error.
- `lxml.html` silently recovers from malformed HTML — errors in the source are swallowed,
  not raised. Use `etree.XMLParser(recover=False)` when strict XML validation is needed.
- lxml 5.x changed `iterparse` behavior for `resolve_entities` — ensure any code using
  `iterparse` explicitly sets `resolve_entities=False` if it processes untrusted XML.
- The `lxml.objectify` module is a separate API from `lxml.etree` — don't mix them.

### Integration in This Project
Pass `"lxml"` as the parser to `BeautifulSoup()` — never rely on the default auto-detect.
For the ClaudeBoost XML knowledge files, `etree.parse(path)` is appropriate (files are
trusted and small). For any externally fetched XML, use
`etree.XMLParser(resolve_entities=False, no_network=True)` explicitly.

<!-- Source: https://github.com/Alir3z4/html2text/blob/master/docs/usage.md | Tier: A | Date: 2026-06-14 -->
## html2text (>=2024.2) — HTML to Markdown conversion

### What It Does
html2text converts HTML pages to Markdown text. ClaudeBoost uses it in the URL chunker
pipeline: after httpx fetches a page and beautifulsoup4 parses it, html2text converts the
result to Markdown before chunking and embedding. The quality of this conversion directly
affects retrieval quality — noisy output (hard-wrapped lines, link clutter) degrades
embedding fidelity.

### Security
No known CVEs. html2text is a pure text conversion library with no network access and no
code execution. Input sanitization is not its concern — it trusts the HTML it receives.

### Performance
html2text is fast (pure Python string processing). The main cost is in how much noise
it produces — more noise means more chunks and more embedding calls for the same useful
content. Configuration choices below directly affect downstream costs.

### Pitfalls
- **`body_width=78` is the default and hard-wraps text at 78 characters.** This creates
  broken markdown and poor embeddings — every sentence fragment becomes a separate line.
  Always set `body_width=0` for RAG pipelines.
- `ignore_links=False` is the default — inline links like `[text](https://long.url)` pollute
  embedded chunks with URL noise. Set `ignore_links=True` when link content is not meaningful
  for the search use case.
- Tables are converted to ASCII art by default (`bypass_tables=False`) — this is noisy for
  RAG. Set `bypass_tables=True` to output raw HTML tables, or `ignore_tables=True` to skip
  them entirely.
- The library has two distinct table options that do different things: `bypass_tables` outputs
  the original HTML tags; `ignore_tables` drops all table rows. Choosing the wrong one silently
  removes structured content.

### Integration in This Project
The URL chunker (`indexing/url_chunker.py`) should configure html2text with at minimum:
```python
h = html2text.HTML2Text()
h.body_width = 0          # no hard wrapping
h.ignore_links = True     # drop href noise
h.bypass_tables = True    # keep tables as HTML rather than ASCII art
```
This configuration produces clean Markdown suitable for chunking and embedding.

<!-- Source: https://microsoft.github.io/graspologic/latest/ | Tier: A | Date: 2026-06-14 -->
## graspologic (>=3.0) — graph statistics and spectral embedding [optional: pip install ClaudeBoost[graph]]

### What It Does
graspologic is a Microsoft-backed Python library for statistical analysis of graphs. It
provides Adjacency Spectral Embedding (ASE) and Laplacian Spectral Embedding (LSE) for
representing graph structure as vectors, community detection, and automatic dimensionality
selection. ClaudeBoost uses it optionally for advanced GraphRAG — embedding the code
dependency graph to find semantically related files beyond direct imports.

### Security
No known CVEs. graspologic performs in-memory statistical computation on graph data you
supply. No network access, no code execution, no file I/O. The only risk is denial-of-service
from very large graphs (spectral methods require SVD, which is O(n^2) memory).

### Performance
Spectral embedding computes SVD on the adjacency matrix — scales as O(n^2) in memory and
O(n^3) worst-case for dense graphs. At ClaudeBoost's scale (hundreds of files), this runs
in milliseconds. For large projects (10K+ files), limit to the largest connected component
before embedding. `svd_solver_algorithm='randomized'` (the default) is much faster than
exact SVD for large matrices.

### Pitfalls
- **NetworkX DiGraph → numpy bridge**: graspologic's pipeline module accepts NetworkX graphs
  directly via `adjacency_spectral_embedding(graph, ...)` or `laplacian_spectral_embedding(graph, ...)`.
  However, lower-level `AdjacencySpectralEmbed` and `LaplacianSpectralEmbed` work on numpy
  arrays. Use `networkx.to_numpy_array(G)` to convert, not `nx.adjacency_matrix(G)` (which
  returns a sparse matrix requiring `.toarray()`).
- **All edges must have numeric weights.** A graph with `None` edge attributes or missing
  weight keys will raise an error. ClaudeBoost's dependency graph stores edges without weights
  — add a default weight before passing to graspologic:
  `nx.set_edge_attributes(G, 1.0, "weight")`.
- **No multigraph support.** Use `nx.Graph` or `nx.DiGraph`, not `nx.MultiGraph`.
- **Automatic elbow selection** (`elbow_cut=None`) picks the number of embedding dimensions
  automatically but can choose poorly on disconnected or near-disconnected graphs. Inspect the
  returned `n_components` before using embeddings downstream.

### Integration in This Project
Import via `graspologic.pipeline.embed.adjacency_spectral_embedding`. The function returns
an `Embeddings` object with `.latent_left`, `.latent_right` (for directed graphs), and
`.singular_values`. For undirected graphs, `.latent_left` holds the embedding. Pass the
result to downstream similarity search or clustering rather than chromadb (wrong tool for
graph embeddings).

<!-- Source: https://www.morphllm.com/ollama-embedding-models | Tier: B | Date: 2026-06-14 -->
## ollama (>=0.3) — local LLM embeddings [optional: pip install ClaudeBoost[ollama]]

### What It Does
ollama provides a Python client for the Ollama local model server, which runs embedding
models (and generative LLMs) on the user's GPU or CPU without any cloud dependency.
ClaudeBoost uses it as an optional embedding provider — a drop-in for sentence-transformers
when the user has Ollama installed and prefers GPU-offloaded embeddings.

### Security
ollama talks to `http://localhost:11434` by default — local only, no cloud. Model files
are loaded from the user's local Ollama data directory. The security concern is the
Ollama server itself: it has no auth by default, so anyone on the local network who can
reach port 11434 can invoke any installed model. For home dev use this is fine; on a shared
machine or corporate network, bind Ollama to 127.0.0.1.

### Performance
Ollama handles batching internally on the `/api/embed` endpoint (accepts `input` as a list).
The older `/api/embeddings` endpoint takes a single string — use `ollama.embed()` not
`ollama.embeddings()` for batch efficiency. For async workloads, use `AsyncClient` with
`asyncio.gather` over a list of inputs.

### Pitfalls
- **Dimension mismatch with existing chromadb collections**: `nomic-embed-text` → 768 dims,
  `mxbai-embed-large` → 1024 dims, `qwen3-embedding:8b` → 4096 native (can be truncated via
  MRL). Picking a model whose output dimension doesn't match the existing chromadb collection
  raises `InvalidDimensionException`. This is unrecoverable without deleting and rebuilding
  the collection. Check `GET /status dimension_mismatch` before switching models.
- **`nomic-embed-text` silently truncates at 2048 tokens** despite an 8192-token native
  context. The Ollama model card defaults `num_ctx` to 2048. Set `num_ctx=8192` explicitly
  in the `options` field when calling `/api/embed` for long documents.
- **ChromaDB telemetry**: if Ollama is used alongside chromadb and `anonymized_telemetry`
  is not disabled, chromadb connects to PostHog on startup — causing a 21-second hang
  in air-gapped environments. ClaudeBoost's `ChromaStore` already disables this via
  `Settings(anonymized_telemetry=False)`.
- **Ollama daemon must be running**: `ollama.Client()` does not start the daemon. If the
  daemon is down, API calls raise `httpx.ConnectError`. Add a health check before using.

### Integration in This Project
The ollama embedding path must produce vectors of the same dimension as the chromadb
collection it targets. `BAAI/bge-base-en-v1.5` (sentence-transformers default) is 768-dim —
use `nomic-embed-text` as the Ollama equivalent. Never swap to `mxbai-embed-large` (1024)
or `llama3` (4096) without deleting and rebuilding all chromadb collections first.

## Cross-Component Integration — How the Stack Wires Together

This section documents constraints that span multiple libraries. They exist only in code
comments in `mcp-rag-server/src/rag_server/` — not in any library's own docs.

### Startup order: embedding warmup before ChromaDB init (server.py:275–292)

On Windows, BLAS (PyTorch/MKL) and SQLite conflict if SQLite opens first. ChromaDB's
`PersistentClient.__init__()` opens SQLite eagerly. Any subsequent `embed_query()` call
after that will segfault (exit code 139, no Python traceback).

The fix in `sync_init()`:
```python
embedder.embed_query("warmup")          # BLAS initializes here
store = ChromaStore(persist_dir=...)    # SQLite opens here — safe now
```

Never reorder these two lines. Never remove the warmup call as "unused". The failure is a
segfault, not an exception — nothing in the log, the process just dies.

### ChromaDB Rust/Tokio backend must be bypassed (store.py:54–59)

ChromaDB 1.5+ defaults to a Rust/Tokio backend. On Windows, this backend crashes with
`ACCESS_VIOLATION` when the process's stdout is a pipe (which it always is when launched
as an MCP subprocess by Claude Code). All `ChromaStore` instances force the pure-Python
SegmentAPI:

```python
Settings(
    chroma_api_impl="chromadb.api.segment.SegmentAPI",
    anonymized_telemetry=False,
)
```

Never instantiate `chromadb.PersistentClient()` directly — always go through `ChromaStore`
which applies these settings. Any test or script that bypasses `ChromaStore` will get the
wrong backend on Windows.

### ChromaDB process-wide singleton: always use ChromaStore, never PersistentClient directly (store.py:15–21)

ChromaDB's SegmentAPI is a process-wide singleton keyed by persist path. Opening two
`PersistentClient` instances to different directories in the same process causes the
singleton to return wrong segment metadata for the second client — manifests as dimension
mismatch errors that are hard to reproduce and diagnose.

`ChromaStore` maintains `_client_cache` to ensure one client per path:
```python
_client_cache: dict[str, object] = {}   # keyed by canonical resolved path
```

Rules that follow from this:
- Always use `ChromaStore(persist_dir=...)` — never `chromadb.PersistentClient()` directly.
- After `shutil.rmtree(chroma_dir)`: call `ChromaStore.evict_cache(str(chroma_dir))` before
  creating a new store. Without it, the cached client holds SQLite handles to deleted files
  and all writes fail with "attempt to write a readonly database".
- `evict_cache()` calls `client.close()` internally — this releases chromadb's internal
  system cache too, not just the local dict entry.

### All ChromaDB and embedding calls must use run_in_executor (server.py:255–257, :531)

ChromaDB 1.5+'s Rust/Tokio backend crashes when called from inside an asyncio coroutine.
Sentence-transformers' `encode()` blocks the event loop for 100–2000ms per batch.

Every async handler in `main_http()` dispatches through:
```python
result = await asyncio.get_running_loop().run_in_executor(
    None, _dispatch_tool, tool_name, body
)
```

`_dispatch_tool` is synchronous — it calls chromadb and sentence-transformers directly.
Never call `store.search()`, `store.add()`, `embedder.embed_query()` etc. from an
`async def` handler body. Adding a new endpoint: always follow the `run_in_executor` +
`_dispatch_tool` pattern.

### Background startup must never force re-index on dimension mismatch (server.py:385–388)

`_background_startup()` detects embedding dimension mismatches (e.g. after swapping models).
It must NOT trigger a force re-index automatically:

```python
# STOP: never force re-index on dimension mismatch in background startup.
# A full force re-index holds ChromaDB locked for minutes, blocking all requests.
# Log a warning instead — the user must explicitly trigger via POST /index with force=true.
```

If you write code that checks for dimension mismatch, follow this pattern: log the warning
and return. Let the user decide when to re-index. Auto-triggering from the startup path
fills the thread pool and blocks `/search` and `/status` for minutes.

### Watchdog debounce is intentional — don't reduce it (core/watcher.py:15–16)

`DEBOUNCE_SECONDS = 2.0` is set deliberately. A git checkout touching 50 knowledge files
triggers 50 events in rapid succession. Without debouncing, each event would launch a
separate re-index call, corrupting the graph (networkx write-lock violation) and flooding
the thread pool. The `_DebouncedHandler` batches all events within the 2-second window
into a single callback. Don't reduce this value for perceived performance.
