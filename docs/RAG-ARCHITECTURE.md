# RAG Architecture

How the ClaudeBoost RAG server works — from file discovery through semantic search and graph traversal.

---

## Overview

The RAG server is a Python HTTP service on port 8612 that starts as a subprocess when Claude Code opens. It exposes a REST API (`POST /search`, `POST /context`, `POST /index`, `GET /status`) that Claude, hooks, and agents call during sessions. Two separate indexes exist and serve different purposes:

| Index | What it holds | Location |
|-------|--------------|----------|
| **ClaudeBoost RAG** | `agents/*.xml` + `knowledge/*.xml` — agent definitions and knowledge bases | `mcp-rag-server/.rag-index/chroma/` |
| **Project RAG** | A specific project's source code | `<project>/workspace/.rag-index/chroma/` |
| **Graph DB** | Code structure graph (imports, inheritance, calls) for a project | `<project>/workspace/.rag-index/graph.db` |

These are built and queried independently. `POST /context` combines both — ClaudeBoost RAG for knowledge, Project RAG for codebase context.

---

## Module Map

```
mcp-rag-server/src/rag_server/
├── config.py                      — paths, embedding model, scope definitions
├── server.py                      — MCP server, tool dispatch, async→thread bridge
│
├── ports/                         — abstract interfaces (ports/adapters pattern)
│   ├── embedding_port.py          — EmbeddingPort ABC
│   ├── store_port.py              — StorePort ABC, Chunk, SearchResult dataclasses
│   └── graph_port.py              — GraphStorePort ABC, GraphEdge dataclass
│
├── core/
│   ├── embedding.py               — SentenceTransformerEmbedding (lazy-loaded, thread-safe)
│   ├── store.py                   — ChromaStore (ChromaDB embedded/SQLite, cosine HNSW)
│   ├── project.py                 — language→extension map, file discovery, project IDs
│   ├── scanner.py                 — smart scanner: pathspec/.gitignore + size/generated filters
│   ├── locking.py                 — file-based write lock (cross-process safe)
│   ├── metadata.py                — chunk ID generation, content hashing
│   ├── community.py               — Leiden community detection (optional graspologic dep)
│   └── summarizer.py              — LLM summaries for communities
│
├── indexing/
│   ├── engine.py                  — IndexingEngine: orchestrates all indexing paths
│   ├── code_chunker.py            — tree-sitter AST chunking + graph edge extraction
│   ├── markdown_chunker.py        — section-header chunking for .md files
│   ├── xml_chunker.py             — section-based chunking for .xml files
│   ├── url_chunker.py             — HTML page → markdown chunks
│   └── pdf_chunker.py             — PDF → text chunks
│
├── adapters/
│   └── sqlite_graph_store.py      — SQLiteGraphStore: edges + communities in SQLite
│
└── tools/
    ├── search.py                  — rag_search implementation
    ├── context.py                 — rag_context (tiered context assembly)
    └── research.py                — rag_index_research (per-task URL/PDF indexing)
```

---

## Storage Layout

```
$LOCALAPPDATA/rag-server-index/       ← ClaudeBoost RAG (knowledge + agents)
├── chroma/                           ← ChromaDB collections: "knowledge", "agents"
├── manifest.json                     ← file hash manifest for incremental indexing
├── index.lock                        ← write lock
└── projects.json                     ← global project registry (graph counts, timestamps)

<project>/workspace/.rag-index/       ← Project RAG (per project)
├── chroma/                           ← ChromaDB collection: "codebase"
├── graph.db                          ← SQLite: edges, communities, community_summaries
├── manifest.json                     ← project file hash manifest (+ __schema_version__)
└── index.lock                        ← write lock
```

The ClaudeBoost index defaults to `$LOCALAPPDATA` on Windows to stay off OneDrive — HNSW binary files corrupt when synced across machines. Override with `RAG_INDEX_DIR` env var. (`config.py:24–33`)

---

## Key Data Structures

### Chunk (`ports/store_port.py:8`)
The unit stored in ChromaDB. Built during indexing, never read back directly by callers — only search results come back.

```python
@dataclass
class Chunk:
    id: str               # sha256(source_file + chunk_index)
    content: str          # raw text of the chunk
    embedding: list[float] # float[384] from sentence-transformers
    metadata: dict         # source_file, scope, section, line_start, line_end,
                           # content_hash, chunk_index, token_count
```

### SearchResult (`ports/store_port.py:17`)
Returned by `rag_search` and used internally by `rag_context`.

```python
@dataclass
class SearchResult:
    content: str
    metadata: dict   # same fields as Chunk.metadata
    score: float     # cosine similarity 0.0–1.0
```

### GraphEdge (`ports/graph_port.py:9`)
One directed relationship extracted from AST. Stored in SQLite, not ChromaDB (ChromaDB metadata is scalar-only).

```python
@dataclass
class GraphEdge:
    source_file: str     # project-relative path of the file containing the reference
    source_symbol: str   # class/function name, or "<module>" for import statements
    target_file: str     # resolved project-relative path (or "" if unresolved, "_external_" if stdlib/npm)
    target_symbol: str   # what was imported or inherited
    edge_type: str       # "imports" | "inherits" | "calls"
    confidence: str      # "EXTRACTED" (direct AST) | "INFERRED" (name-match heuristic)
```

---

## Embedding Model

**File:** `core/embedding.py`

Default model: `sentence-transformers/all-MiniLM-L6-v2` — 384 dimensions, ~22MB, ~2s load time.
Alternative: `all-mpnet-base-v2` — 768 dimensions, ~420MB, 60–120s load. Override via `RAG_EMBEDDING_MODEL` env var.

The model loads lazily on first use. `SentenceTransformerEmbedding` uses a double-checked lock (`_load_lock`) so concurrent calls from the thread pool don't trigger parallel loads. (`embedding.py:27–44`)

Two embed methods:
- `embed(texts)` — batch, used during indexing (documents)
- `embed_query(text)` — single text, used during search (with `search_query:` prefix for nomic models)

If the model isn't loaded yet, any tool that needs it returns an error immediately rather than blocking the event loop. A background warmup thread is kicked off so the model is ready for the next call. (`search.py:20–35`)

---

## Vector Indexing Pipeline

Both ClaudeBoost RAG and Project RAG follow the same core loop. The difference is what gets scanned, where it's stored, and whether graph extraction runs.

### 1. File Discovery

**ClaudeBoost RAG** (`engine.py:226–250`): globs `knowledge/*.xml`, `agents/*.xml` from `PROJECT_ROOT`.

**Project RAG** (`engine.py:466–476`): uses `scan_project()` in `core/scanner.py`.

The scanner works in two tiers:

1. **pathspec** (`scanner.py:84–88`): reads `.gitignore` via the `pathspec` library. Walks with `os.walk`, then filters out any path that matches the gitignore spec. Falls back to tier 2 if pathspec isn't installed or there's no `.gitignore`.
2. **os.walk** (`scanner.py:174–185`): plain directory walk with `DEFAULT_EXCLUDES` (node_modules, .git, dist, build, __pycache__, .venv, obj, bin, .rag-index, etc.).

After discovery, three post-filters run:
- **Generated files**: exact names (`package-lock.json`, `yarn.lock`) and suffixes (`.min.js`, `.d.ts`, `.generated.cs`) are skipped. (`scanner.py:13–31`)
- **Size limit**: files over 200KB are skipped. (`scanner.py:113–120`)
- **`.ragignore`**: project-level exclude list; directory names matched during `os.walk`. (`project.py:67–86`)

Language support covers 20 languages: Python, JavaScript, TypeScript, C#, Go, Rust, Java, C, C++, Ruby, Bash, Lua, Kotlin, Swift, PHP, CSS, HTML, JSON, TOML, YAML. (`project.py:21–43`)

### 2. Incremental Check

For each file, `file_hash(content)` (SHA-256) is compared against `manifest.json`. If the hash matches, the file is skipped — no re-embedding. This is what makes incremental runs complete in under a second when nothing changed. (`engine.py:540`)

Force re-index deletes the collection first (`delete_collection`) to handle model dimension changes (e.g., swapping from 384d to 768d). (`engine.py:458–463`)

### 3. Chunking

The chunker is chosen by file extension (`engine.py:818–842`):

**Code files** → `code_chunker.chunk_code()` (`code_chunker.py:223`):

1. A tree-sitter parser is lazy-loaded for the language (`_get_parser`, `code_chunker.py:171`). Supported: Python, JS, TS, Go, Rust, Java, C, C++, Ruby, Bash, Lua, Kotlin, Swift, PHP, C#.
2. The AST is walked for top-level definition nodes (`_DEFINITION_TYPES` map, `code_chunker.py:23–112`). For Python these are `function_definition`, `class_definition`, `decorated_definition`. For TypeScript they include `interface_declaration`, `type_alias_declaration`, `enum_declaration` as well.
3. Each top-level definition becomes one `RawChunk` with `section` = the function/class name and `line_start`/`line_end` from the AST node.
4. Everything before the first definition (imports, module-level code) becomes a `[imports]` chunk. Small import blocks (<150 tokens) get merged into the first definition chunk to avoid import stubs outranking implementation in search.
5. Large definitions (>500 tokens) get split at method boundaries, then at blank-line boundaries. (`code_chunker.py:390–462`)
6. If tree-sitter is unavailable or parsing fails: falls back to blank-line splitting.

**Markdown files** → `markdown_chunker.chunk_markdown()`: splits on `##` and `###` headers, targeting 200–500 tokens per chunk, merging tiny sections.

**XML files** → `xml_chunker.chunk_xml()`: section-based.

**Data files** (JSON, YAML, TOML, HTML, CSS): fallback blank-line splitting — no AST available for these.

`RawChunk` carries `content`, `section`, `line_start`, `line_end`, `token_count_approx`. Token count uses a fast approximation (characters / 4). Chunks under `MIN_CHUNK_TOKENS` (50) are discarded.

### 4. Embedding

All chunks from one file are embedded in a single batch call: `embedder.embed(texts)` → `list[list[float]]`. Each returns a `float[384]` vector. (`engine.py:570–571`)

### 5. Storage

`ChromaStore.add_chunks()` calls ChromaDB's `upsert()` with IDs, documents, embeddings, and metadata. (`store.py:60–70`)

ChromaDB uses cosine HNSW internally (`metadata={"hnsw:space": "cosine"}`). On Windows, it's forced into pure-Python `SegmentAPI` mode to avoid an ACCESS_VIOLATION crash when stdout is piped (the MCP subprocess context). (`store.py:23–30`)

### 6. Manifest Update

After a successful embed+store, `manifest[rel_path] = current_hash` is written. On failure the file is recorded in `errors[]` with a `read_error` or `embed_error` type. (`engine.py:596`, `engine.py:598–600`)

---

## Graph Indexing Pipeline

Graph indexing runs inside the same `_do_index_project` loop, immediately after chunking and before embedding. It builds a structural map of how files relate to each other.

### 1. Edge Extraction

For each file, `extract_edges(content, language, filepath)` is called. (`engine.py:562`, `code_chunker.py:571`)

The function parses the file with the same tree-sitter parser used for chunking, then walks the AST with `_walk_for_edges()`. Three types of edges are extracted:

**imports** (EXTRACTED): direct AST reads of import statements.
- Python: `import foo.bar` → `source_symbol="<module>", target_symbol="foo.bar"`
- Python: `from foo import bar` → `target_symbol="foo"`
- TypeScript/JavaScript: `import X from "path"` → `target_symbol="path"`
- Go: `import "github.com/x/y"` → `target_symbol="github.com/x/y"`
- C#: `using System.Linq` → `target_symbol="System.Linq"`
- Ruby, Rust, Java: similar patterns

**inherits** (EXTRACTED): class inheritance.
- Python: `class A(B, C):` → two edges, `target_symbol="B"` and `target_symbol="C"`
- TypeScript: `class A extends B` → `edge_type="inherits"`
- Java: `class A extends B` → `edge_type="inherits"`

**calls** (INFERRED): function call references — approximate, name-match only. Less reliable than imports/inherits.

All edges are stored immediately with `target_file=""` — the target file path is unknown at this point because we're processing one file at a time. (`engine.py:563–567`)

### 2. Post-loop Resolution

After all files are processed, `_build_file_map()` creates a lookup table from module-name variants to project-relative file paths. (`engine.py:60–202`)

For a file like `mcp-rag-server/src/rag_server/ports/graph_port.py`, the file map contains entries for:
- `"mcp-rag-server/src/rag_server/ports/graph_port"` (no extension)
- `"mcp-rag-server.src.rag_server.ports.graph_port"` (dotted)
- `"rag_server.ports.graph_port"` (suffix form — handles src-layout projects)
- `"rag_server/ports/graph_port"` (slash form)
- and shorter suffix variants

This is how `from rag_server.ports.graph_port import GraphEdge` resolves to the correct file even though the import doesn't include the `mcp-rag-server/src/` prefix.

`graph_store.resolve_target_files(file_map)` then does a bulk UPDATE on all edges where `target_file=""`. For each, `_resolve_symbol()` tries: exact match, dotted↔slash conversion, relative import resolution, extension-less JS/TS resolution, `@/` path alias resolution. (`sqlite_graph_store.py:472–539`)

Edges that can't be resolved get classified:
- **External imports** → marked `_external_`: Python stdlib (os, re, json, ...), npm packages (any non-relative JS/TS import), C# BCL/NuGet namespaces (System, Microsoft, Azure, ...), Go stdlib (no dot in first path segment), Go external deps (domain-style import not matching project modules). (`sqlite_graph_store.py:107–159`)
- **Unresolved**: truly unknown — could be a monorepo package not yet indexed, or an import pattern the resolver doesn't understand.

`_external_` edges don't count as unresolved in health checks. External deps can never resolve to project files, so leaving them as `""` would create misleading health check warnings.

### 3. Ghost Pruning

After resolution, `delete_ghost_edges(current_files)` removes edges pointing to files that were deleted since the last index run. This keeps the graph consistent with the current checkout. (`engine.py:643–646`, `sqlite_graph_store.py:412–434`)

### 4. Community Detection (optional)

If `graspologic` and `networkx` are installed, Leiden community detection runs on the resolved graph. (`engine.py:648–673`, `community.py`)

1. All edges are loaded from SQLite with `get_all_edges()`.
2. A NetworkX undirected graph is built. Unresolved edges (`target_file=""`) are skipped for the edge but the source node is still added, so isolated files get their own community.
3. `leiden(G)` partitions the graph. Each file gets a `community_id`.
4. Community assignments are saved to the `communities` table.
5. `summarize_community()` optionally generates LLM summaries for each community and stores them in `community_summaries`.

Communities are informational for now — they're not used in search ranking, but they could be used to suggest related files or scope searches.

### 5. SQLite Schema

**`graph.db`** contains three tables (`sqlite_graph_store.py:17–47`):

```sql
CREATE TABLE edges (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    source_file   TEXT NOT NULL,
    source_symbol TEXT NOT NULL,
    target_file   TEXT NOT NULL,   -- "" = unresolved, "_external_" = stdlib/npm/NuGet
    target_symbol TEXT NOT NULL,
    edge_type     TEXT NOT NULL,   -- "imports" | "inherits" | "calls"
    confidence    TEXT NOT NULL,   -- "EXTRACTED" | "INFERRED"
    UNIQUE(source_file, source_symbol, target_file, target_symbol, edge_type)
);

CREATE TABLE communities (
    file          TEXT PRIMARY KEY,
    community_id  INTEGER NOT NULL
);

CREATE TABLE community_summaries (
    community_id  INTEGER PRIMARY KEY,
    summary       TEXT NOT NULL,
    member_hash   TEXT NOT NULL,
    model         TEXT NOT NULL
);
```

Indexes on `source_file` and `target_file` make neighbour lookups fast.

### 6. Project Registry

After indexing, `projects.json` is updated with edge counts and `graph_active = (edges > 0 AND resolved > 0)`. This is what `rag_status` reads — it doesn't open each project's `graph.db`, just reads the cached counts. (`engine.py:700–722`)

---

## Vector Search Pipeline

**File:** `tools/search.py`

```
query string
    → embedder.embed_query(query)         # float[384]
    → ChromaStore.search(collection, ...)  # ChromaDB HNSW cosine ANN
    → filter by min_score (default 0.5)
    → sort descending by score
    → top N results
```

Score conversion: ChromaDB returns cosine *distance* (0 = identical, 2 = opposite). The server converts to similarity: `score = 1.0 - (distance / 2.0)`. (`store.py:97–99`)

Scope routing (`search.py:86–220`):
- `scope="knowledge"` or `scope="agents"` → main ClaudeBoost ChromaDB
- `scope="all"` → both knowledge and agents, merged and re-ranked
- `scope="codebase"` → per-project ChromaDB at `project_index_dir(project_path)`
- `scope="research"` → per-task workspace ChromaDB at `workspace_path/.rag-index/research/`

If a reindex is in progress (write lock held), search waits up to 30 seconds before returning empty results, so searches issued just after `/index-project` don't silently fail. (`search.py:144–151`)

---

## Graph Search Pipeline (mode=graph)

**File:** `tools/search.py:250–326`

Graph mode augments the vector results with structurally related files. It does not replace vector search — it adds to it.

```
1. Run vector search (same as above) → seed_results[]
2. Take top 3 seeds
3. For each seed:
   a. seed_file = seed.metadata["source_file"]
   b. graph_store.get_neighbours(seed_file)
      → SQL: SELECT * FROM edges WHERE source_file = ? OR target_file = ?
      → returns all edges incident on the seed file (imports, imported-by, inherits, inherited-by)
   c. For each neighbour edge:
      - Skip if target_file is "" or "_external_"
      - Skip if already in seen_sources
      - Fetch up to 2 chunks from that file: project_store.get_by_source("codebase", neighbour_file)
      - Score = max(0.1, seed.score - 0.15)   ← penalized relative to seed
4. Merge: sorted(seed_results + graph_chunks, key=score, reverse=True)[:limit]
5. Return combined results, graph_augmented=True if any neighbours were added
```

The score penalty (`seed.score - 0.15`) is intentional — structural neighbours compete naturally with vector results. A neighbour file that also happens to be semantically relevant to the query will score well. One that's structurally linked but unrelated to the query will score low and get pushed out by better semantic matches. This avoids the "forced slot" problem where graph results displace stronger semantic matches.

`graph_augmented=true` in the response means neighbours were found and added to the candidate pool. It doesn't guarantee any survived into the final top-N.

---

## `rag_context` Pipeline (Tiered Assembly)

**File:** `tools/context.py`

`rag_context` assembles a complete knowledge package for a spawned agent. It combines ClaudeBoost knowledge with project codebase context in a fixed priority order, respecting a token budget.

```
max_tokens budget
├── Tier 0: Agent definition (always — no budget limit)
│   → reads agents/<agent>.xml (or .md)
│   → consumed first; remaining_budget = max_tokens - agent_tokens
│
├── Budget pre-reservation for Tier 4
│   → if project_path provided: reserve min(600, remaining//4) tokens for codebase
│   → prevents Tiers 1-3 from starving Tier 4 at tight budgets
│
├── Tier 1: Universal guardrails (skipped for weight="lightweight")
│   → security.xml, observability.xml, coding-standards.xml, scope-governance.xml
│   → up to 40% of remaining budget
│   → fetched with get_by_source() — no embedding needed, direct lookup
│
├── Tier 2: Agent-declared knowledge bases
│   → parsed from <primary file="..."> and <secondary file="..."> in the agent definition
│   → up to 50% of remaining budget after Tier 1
│   → skips files already loaded in Tier 1
│
├── Tier 3: Semantic search
│   → embedder.embed_query(task_description) → search "knowledge" collection, limit=15, min_score=0.4
│   → fills remaining budget with the highest-scoring knowledge chunks
│   → skips files already loaded in Tiers 1-2
│
├── Tier 4: Codebase search (only if project_path provided and project is indexed)
│   → embedder.embed_query(task_description) → search "codebase" collection, limit=10, min_score=0.35
│   → uses the pre-reserved budget from top
│   → first chunk always included even if it exceeds budget (prevents 0-result edge case)
│
└── Tier 4b: Graph structural neighbours
    → same graph expansion as mode=graph search, but using Tier 4 chunks as seeds
    → budget = (remaining - tier4_tokens) // 2
    → up to 2 chunks per neighbour file, top 3 seeds
    → scored at seed.score - 0.15, stored with tier="codebase_graph"
```

Response includes `tier_summary: {guardrails, declared, search, codebase}` — chunk counts per tier. `tier_errors` lists any failures (model not loaded, file missing, dimension mismatch).

Weight classes control which tiers run:
- `lightweight`: skips Tier 1 guardrails entirely (explore-agent, research-agent, docs-agent, rag-indexing-agent)
- `standard` / `full`: all tiers

---

## Threading Model

**File:** `server.py`

The MCP server runs on Python's asyncio event loop. ChromaDB and sentence-transformers both do blocking I/O and CPU work that would deadlock the loop if called directly.

Every tool call goes through `run_in_executor(None, lambda: _dispatch_tool(name, arguments))` — offloaded to Python's default thread pool. (`server.py:299–345`)

Timeouts:
- Short tools (search, context, status, scan): 90 seconds
- Long tools (index, index_project, index_research): 900 seconds

The write lock (`core/locking.py`) is a file-based lock (`fcntl.flock` on Unix, `msvcrt.locking` on Windows). It serializes concurrent index writes across both threads and processes. Readers don't acquire the lock — reads and writes can overlap, with readers potentially seeing a partially-updated collection during a slow reindex.

Model loading uses a threading.Lock (`_load_lock`) with double-checked locking to prevent parallel loads from multiple thread pool workers. (`embedding.py:28–43`)

---

## Health Checks and Recovery

`_check_project_health()` (`engine.py:741–784`) runs at the start of every incremental index and flags:
- Manifest schema version older than current (`MANIFEST_VERSION = 2`)
- ChromaDB collection empty while manifest has entries (corrupt index)
- ChromaDB chunk count < 50% of manifest file count (partial index)
- >10 ghost edges pointing to deleted files
- >50% of edges unresolved (import resolution failure)

If issues are found, `rag_index_project` returns `needs_reindex: true` with a `health_issues` list instead of proceeding. The caller (Claude) must confirm before running with `force=True`.

Dimension mismatch (model swap from 384d to 768d) is detected by peeking at a stored vector and comparing its dimension against `embedder.dimensions()`. If they differ, `force=True` is set automatically. (`engine.py:449–456`)

---

## Incremental Indexing on Branch Switch

When you switch branches, files change. The incremental indexer handles this correctly:

1. **Changed files**: `file_hash` differs from manifest → re-embed and store
2. **New files**: not in manifest → index fresh
3. **Deleted files**: manifest has them but `scan_project` doesn't → stale eviction loop removes their chunks from ChromaDB and their edges from `graph.db` (`engine.py:484–511`)
4. **Unchanged files**: hash matches → skipped

After the main loop, edge resolution and ghost pruning run again to keep the graph consistent with the new file set.

---

## Supported Languages Summary

| Language | Extensions | AST chunking | Graph edges |
|----------|-----------|-------------|-------------|
| Python | .py | ✓ | imports, inherits |
| TypeScript | .ts, .tsx | ✓ | imports, inherits |
| JavaScript | .js, .jsx, .mjs | ✓ | imports |
| C# | .cs | ✓ | imports (using directives), inherits |
| Go | .go | ✓ | imports |
| Rust | .rs | ✓ | imports (use declarations) |
| Java | .java | ✓ | imports, inherits |
| C / C++ | .c .h .cpp .hpp | ✓ | — |
| Ruby | .rb | ✓ | imports (require) |
| Bash | .sh .bash | ✓ | — |
| Kotlin | .kt .kts | ✓ | — |
| Swift | .swift | ✓ | — |
| PHP | .php | ✓ | — |
| Lua | .lua | ✓ | — |
| CSS / HTML | .css .html | fallback | — |
| JSON / TOML / YAML | .json .toml .yaml | fallback | — |

"fallback" = blank-line splitting, no AST. These file types are indexed for their content but don't get semantic function/class boundaries in chunks.
