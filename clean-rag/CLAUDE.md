# clean-rag

Research-verified editing enforcement for Claude Code. Every source code edit requires verified proof from indexed research or codebase patterns.

## How It Works

clean-rag maintains separate ChromaDB databases organized by topic. Each topic (e.g., `fastapi`, `react-hooks`, `jwt-tokens`) has its own database at `databases/<topic>/chroma/`. Project source code is indexed separately at `databases/_projects/<hash>/chroma/`.

When you try to edit a source file, the `proof-gate.py` hook blocks the edit unless you've searched RAG and written a proof file with mechanical verification checks (score >= 0.5, content hash, freshness).

## The Proof Cycle

Every Edit, Write, or MultiEdit on source code follows this cycle:

1. **Search for proof**: `POST http://127.0.0.1:8613/search` with a query about what you're changing and why. You need at least one result with score >= 0.5.
2. **Auto-research if needed**: If search returns nothing or scores below 0.5, call `POST http://127.0.0.1:8613/acquire-topic {"topic": "<slug>"}` to acquire docs automatically, then re-search. You can also do targeted research directly (reading the specific doc you need) while a parallel agent handles broader category indexing.
3. **Write the proof file**: Use `write_pending_proof()` from `verifier/log.py`. Each file gets its own keyed proof file (not a single shared file). Include `content_hash` (SHA-256 of the edit content) and `min_score` (best RAG result score, must be >= 0.5). Set verdict to "VERIFIED" and include a summary of the RAG results that justify the edit.
4. **Retry the edit**: The hook atomically consumes the keyed proof file and passes if:
   - verdict == VERIFIED
   - content_hash matches the proposed edit (prevents reuse for different edits)
   - min_score >= 0.5 (mechanical quality threshold)
   - timestamp is timezone-aware and within 120 seconds (naive timestamps rejected)

No independent verifier agent is needed. The mechanical checks (score threshold, content hash binding, freshness) catch the same issues faster and cheaper.

## Research-First Mandate

Everything Claude says or does must be grounded in indexed research. RAG is not optional. Before responding to any question, making any decision, or editing any file:

1. **Check the topic tree**: Look at indexed topics to find relevant databases.
2. **Search RAG**: `POST http://127.0.0.1:8613/search` with your specific question.
3. **If nothing found**: Do direct research (see Fast Path below), then write proof.
4. **Base your response on RAG results**, not training data. Cite which topic and score backed each claim.

For edits, the proof-gate hook mechanically blocks until you've done this. For responses, the research-stop-gate (a `type: "prompt"` Stop hook evaluated by Haiku) mechanically blocks Claude from finishing a response that makes unsourced technical claims. The rag-enforce hook also reminds you every turn.

## Smart Topic Routing

Before searching all topics, check the topic tree (injected by rag-enforce.py every turn) to find the right database. Search the specific topic first (`topic:<name>`), then fall back to `all_topics` only if the specific topic misses.

When a topic is missing or the existing results don't answer your specific question, use the **Fast Path** (seconds, not minutes):

1. **Research the specific question directly** (Grep codebase, read a doc file, WebSearch). This gets you the answer NOW.
2. **Save what you found** to `clean-rag/knowledge/<category>/<topic>/` (even one file is enough).
3. **Quick-index**: `POST http://127.0.0.1:8613/index-topic {"topic": "<name>", "category": "<category>"}` (indexes a few files in under 2 seconds).
4. **Search the new topic** (will return high scores now). Write proof and continue.

**Background enrichment** (parallel, non-blocking): Spawn an Agent to run `POST http://127.0.0.1:8613/acquire-topic {"topic": "<slug>"}` for full topic coverage. Do NOT wait for it. Do NOT spawn a second agent for a topic already being researched. The agent fills the database for future queries while you continue working now.

## Search API

```
POST http://127.0.0.1:8613/search
Content-Type: application/json

{
    "query": "FastAPI dependency injection with Depends()",
    "sources": ["topic:fastapi", "all_topics", "project:/path/to/project"],
    "limit": 5,
    "min_score": 0.5,
    "mode": "vector"
}
```

Source specifiers:
- `topic:<name>` searches one topic database
- `all_topics` searches every topic database and ranks by cosine similarity
- `project:<path>` searches the project's codebase index

Mode (applies to project sources only, topics always use vector):
- `vector` (default) searches by embedding similarity
- `graph` finds structural neighbors (imports, callers, inheritance) of vector-matched seed files
- `both` runs vector and graph, deduplicates, returns merged results sorted by score

Results include `score`, `file`, `tree_path`, `section`, and `content`. Higher score = better match. Graph results also include `relation` (edge type) and `seed_file` (the vector match that led to this neighbor).

## Writing Proof

After searching RAG and getting results with score >= 0.5, use `write_pending_proof()` from `clean-rag/verifier/log.py`:

```python
from clean_rag.verifier.log import write_pending_proof

write_pending_proof(
    state_dir="clean-rag/state",
    file_path="path/to/file.py",
    verdict="VERIFIED",
    verifier_response="RAG results: FastAPI Depends() pattern documented in dependencies-tutorial.md (score 0.87), project uses same pattern in auth.py:23 (score 0.72)",
    rag_results_count=3,
    topics_cited=["fastapi"],
    project_cited=True,
    content_hash="<sha256 of edit content>",
    min_score=0.87,
    research_angles=[
        {"angle": "technology", "query": "FastAPI dependency injection Depends()", "score": 0.87},
        {"angle": "codebase", "query": "existing DI patterns in project", "score": 0.72},
    ],
    quality_aspects=[
        {"aspect": "architecture", "assertion": "New endpoint goes in routes/auth.py alongside existing auth routes. Controller layer only."},
        {"aspect": "patterns", "assertion": "Project uses Depends() for DI everywhere (auth.py:23, users.py:15). Following same pattern."},
    ],
)
```

The proof file is keyed per target file (uses a hash of the canonical path), so concurrent edits to different files each get their own proof. The gate atomically renames the proof file during consumption to prevent TOCTOU races.

**Required fields the gate checks:**
- `file` must be present and match the file being edited (normalized to lowercase POSIX path)
- `verdict` must be `"VERIFIED"`
- `ts` must be timezone-aware ISO format (Z suffix or +00:00) and within 120 seconds
- `content_hash` must match the SHA-256 of the actual edit being applied
- `min_score` must be >= 0.5 (best RAG result score from the search)
- `research_angles` must have >= 2 entries (multiple search perspectives required)
- `research_angles` must include at least one entry with `angle: "codebase"` (callers, imports, dependents of the target file must be researched)
- `quality_aspects` must have >= 2 entries (multiple quality perspectives required)
- `quality_aspects` must include at least one entry with `aspect: "architecture"` or `aspect: "patterns"` (macro quality proving the code fits the project)

### Research Angles

Every proof must include at least 2 research angles, and one of them **must** be a `codebase` angle. The codebase angle proves you searched the surrounding codebase (callers, imports, files that depend on the target) before editing, not just the target file itself.

| Angle | What to search | Required? |
|-------|---------------|-----------|
| `codebase` | Callers, imports, dependents of the target file | **Yes, always** |
| `technology` | How does this tech work? Search the topic docs | No |
| `pitfalls` | What commonly goes wrong with this approach? | No |
| `security` | Any security implications? (when applicable) | No |
| `best_practices` | What is the recommended pattern? | No |

Each angle entry is `{"angle": "<name>", "query": "<what you searched>", "score": <best_score>}`. The gate rejects proofs with fewer than 2 angles or missing a codebase angle.

### Quality Aspects

Every proof must include at least 2 quality aspects, and at least one must be `architecture` or `patterns` (macro quality). Quality aspects prove you considered code quality at multiple levels, not just whether the code runs correctly. There is a difference between writing a good for loop and understanding the architecture around that for loop.

| Aspect | What to verify | Required? |
|--------|---------------|-----------|
| `architecture` | Does the change fit the project structure? Right file, right layer, right separation of concerns. | **At least one of architecture or patterns is required** |
| `patterns` | Does the code follow existing project patterns, not invent new ones? | **At least one of architecture or patterns is required** |
| `maintainability` | Will the code be easy to change later? Clear naming, low coupling, reasonable complexity. | No |
| `security` | Does this introduce any vulnerabilities? (when applicable) | No |
| `performance` | Any unnecessary performance costs? (when applicable) | No |
| `testing` | Is this testable? How will it be tested? | No |

Each aspect entry is `{"aspect": "<name>", "assertion": "<what you verified>"}`. The assertion is freeform text describing what you checked and found. You can verify quality aspects by reading the codebase (Grep, Read) without needing RAG. The gate rejects proofs with fewer than 2 aspects or missing a macro quality aspect (architecture or patterns).

## Auto-Research (builds knowledge permanently)

When your search returns no results, scores below 0.5, or results that don't cover your specific question, use the Fast Path first, then enrich in the background.

### Fast Path (use THIS, not acquire-topic)

1. **Research the specific question directly**: Grep the codebase, read a doc file, or WebSearch. Just enough to answer what you need. This takes seconds.
2. **Save what you found** to `clean-rag/knowledge/<category>/<topic>/` (even one file works).
3. **Quick-index**: `POST http://127.0.0.1:8613/index-topic {"topic": "<name>", "category": "<category>"}` (under 2 seconds for a few files).
4. **Search the new topic** (will return high scores). Write proof and continue.

### Background Enrichment (parallel, non-blocking)

After using the Fast Path, spawn a background Agent to acquire full topic coverage for future queries:

```
Agent(model="haiku", run_in_background=true, prompt="
  POST http://127.0.0.1:8613/acquire-topic {\"topic\": \"<slug>\"}
  This runs the 4-layer waterfall: GitHub sparse checkout, llms.txt,
  BFS doc crawl. Report what was indexed when done.
")
```

Do NOT wait for this agent. Do NOT spawn a second agent for a topic already being researched. The main agent continues working immediately.

The 4-layer waterfall (run by acquire-topic):
- Layer 1: GitHub sparse checkout (if source_map has the repo)
- Layer 2: llms.txt / llms-full.txt check (if doc_root known)
- Layer 3: BFS crawl of documentation site
- Layer 4: (you handle this) WebSearch fallback

### Why this saves tokens

First edit touching FastAPI? Fast Path costs ~5 seconds. Background agent enriches the full topic for future queries. Every subsequent FastAPI edit hits the local vector index in milliseconds. No re-research, no re-downloading. Proof comes from local search, not training data.

### Categorization Rules

When saving docs from WebSearch or creating a new topic, place it in the correct category directory. These categories are based on the established taxonomy:

| Category | What goes here | Examples |
|----------|---------------|---------|
| `ai` | ML frameworks, LLM tools, model serving | huggingface, langchain, ollama |
| `api` | API protocols and specifications | graphql, grpc, openapi, rest |
| `cloud` | Cloud provider services | azure-functions, aws-lambda, gcp |
| `databases` | Database engines and ORMs (non-dotnet) | postgresql, redis, chromadb, mongodb |
| `dotnet` | All .NET ecosystem | aspnet, blazor, efcore, signalr, maui, nunit |
| `frontend` | Browser frameworks and client libraries | react, vue, angular, svelte, nextjs, astro |
| `infrastructure` | DevOps, containers, CI/CD | docker, kubernetes, github-actions, terraform |
| `languages` | Programming language docs | python, typescript, rust, go, csharp, swift |
| `node-frameworks` | Server-side Node.js frameworks | express, nestjs, fastify |
| `php-frameworks` | PHP frameworks | laravel, symfony |
| `python-frameworks` | Python web/data frameworks | fastapi, django, flask, pydantic |
| `ruby-frameworks` | Ruby frameworks | rails, sinatra |
| `security` | Security standards and checklists | owasp, cve-databases |
| `testing` | Testing frameworks | playwright, pytest, cypress, vitest, jest |
| `tools` | Build tools, linters, dev tools | vite, eslint, webpack, prettier |
| `ui` | CSS frameworks and design systems | sass, tailwind, bootstrap |

If a technology doesn't fit any category, create a new category with a clear name. Don't use `other/`.

## Exempt Files

The proof gate does NOT apply to:
- Files under directories named: workspace/, knowledge/, plans/, docs/, state/, .claudeboost/, .claude/ (checked at directory boundaries, not substrings)
- Files in the system temp directory ($TEMP, %TMP%, /tmp) including subdirectories
- Files outside any git repository (not project code, just scratch/output files)
- When ClaudeBoost AUTO mode is active (logged to proof-log.jsonl for audit trail)

**No file extension exemptions.** Every file type requires research proof, including .md, .json, .yaml, .toml, .xml, and all source code. The only exemptions are directory based (workspace, state, etc.) and temp paths.

Files under `clean-rag/` also require proof (the enforcement system does not exempt itself).

## Database Organization

Each topic is a separate ChromaDB database. The tree looks like:

```
databases/
  fastapi/
    chroma/         # ChromaDB for FastAPI docs
    manifest.json   # File hash manifest for incremental indexing
  react-hooks/
    chroma/
    manifest.json
  jwt-tokens/
    chroma/
    manifest.json
  _projects/
    a1b2c3d4e5f6/   # Project hash
      chroma/       # ChromaDB for project source code
      manifest.json
```

Knowledge files mirror this structure with subdirectories preserved:

```
knowledge/
  fastapi/
    tutorial/
      dependencies.md
      security.md
    advanced/
      events.md
    reference/
      parameters.md
  react-hooks/
    guides/
      useState.md
      useEffect.md
    patterns/
      custom-hooks.md
```

The search module queries each database independently, collects results from all matching databases, then sorts by cosine similarity score to return the best matches.

## Server Management

```bash
python clean-rag/cli/server_ctl.py start    # Start on port 8613
python clean-rag/cli/server_ctl.py stop     # Stop
python clean-rag/cli/server_ctl.py status   # Health check
```

## Topic Management

```bash
python clean-rag/cli/topic.py list                      # List all topics
python clean-rag/cli/topic.py create <name>             # Create topic dir
python clean-rag/cli/topic.py index <name>              # Index a topic
python clean-rag/cli/topic.py search <name> "query"     # Search a topic
python clean-rag/cli/topic.py delete <name>             # Delete a topic
python clean-rag/cli/topic.py acquire <name>            # Auto-research + index
```

## Project Registry (System Wide)

clean-rag maintains a central registry of ALL indexed projects across all RAG servers at `state/projects.json`. Each entry tracks the project path, which RAG system indexed it, and stats.

**Automatic registration:** When clean-rag indexes a project (`POST /index-project`), it auto-registers with `source: "clean-rag"`. When the ClaudeBoost RAG server (port 8612) indexes a project via the `/index-project` skill, it calls `POST /register-project` to register with `source: "claudeboost-rag"`.

**API:**
- `GET /projects` returns the full registry
- `POST /register-project` registers an externally indexed project:
  ```json
  {"project_path": "/path", "source": "claudeboost-rag", "server": "http://127.0.0.1:8612", "files_indexed": 200, "chunks_created": 1000}
  ```

## Project Indexing

```bash
python clean-rag/cli/index.py /path/to/project          # Index project code
python clean-rag/cli/index.py /path/to/project --force   # Full reindex
```

Or via the server API:
```
POST http://127.0.0.1:8613/index-project
{"project_path": "/path/to/project"}
```

### Auto-Index Detection

When the proof gate blocks an edit, it detects the project root (by walking up to find `.git`) and checks whether the project is indexed. The block message includes one of three guidance sections:

- **NOT INDEXED**: tells you to either index the project first (`POST /index-project`) or use Grep as a fallback for the codebase research angle
- **INDEXED**: reminds you to include `project:<path>` in your search sources
- **UNKNOWN**: could not detect the project root; use Grep as the codebase angle

This means Claude always knows whether codebase search is available and what to do about it.

## Auto-Reindex After Edits

A PostToolUse hook (`reindex-after-edit.py`) fires after every successful Edit, Write, or MultiEdit. It sends the changed file to the server for incremental reindexing via `POST /reindex-file`. This keeps the project index fresh without full rescans.

The hook runs in a background thread so it never blocks the editing flow. If the server is down or the file isn't in an indexed project, it silently does nothing.

Files that are skipped:
- Files inside the clean-rag directory (internal, not project code)

The single file reindex only re-embeds the changed file (checks content hash against the manifest to skip unchanged files), making it fast enough to run after every edit.
