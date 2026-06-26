# clean-rag

Research-verified editing enforcement for Claude Code. Every source code edit requires verified proof from indexed research or codebase patterns.

## How It Works

clean-rag maintains separate ChromaDB databases organized by topic. Each topic (e.g., `fastapi`, `react-hooks`, `jwt-tokens`) has its own database at `databases/<topic>/chroma/`. Project source code is indexed separately at `databases/_projects/<hash>/chroma/`.

When you try to edit a source file, the `proof-gate.py` hook blocks the edit unless you've already verified your proof through a Haiku verification agent.

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
3. **If nothing found**: Auto-acquire the topic, then search again.
4. **Base your response on RAG results**, not training data. Cite which topic and score backed each claim.

For edits, the proof-gate hook mechanically blocks until you've done this. For responses, the rag-enforce hook reminds you every turn.

## Smart Topic Routing

Before searching all topics, check the topic tree (injected by rag-enforce.py every turn) to find the right database. Search the specific topic first (`topic:<name>`), then fall back to `all_topics` only if the specific topic misses.

When a topic is missing entirely:
- **You need the answer now**: Research the specific question directly (read the doc, fetch the URL) and use that as your proof. This keeps you unblocked.
- **Broader coverage needed**: Spawn a parallel research agent to acquire and index the full topic. Do NOT spawn a second agent for a topic already being researched. Do NOT wait for the agent to finish. The agent only acquires and indexes. It does not read or summarize the research (saves tokens). The indexed docs are available for all future queries.

## Search API

```
POST http://127.0.0.1:8613/search
Content-Type: application/json

{
    "query": "FastAPI dependency injection with Depends()",
    "sources": ["topic:fastapi", "all_topics", "project:/path/to/project"],
    "limit": 5,
    "min_score": 0.5
}
```

Source specifiers:
- `topic:<name>` searches one topic database
- `all_topics` searches every topic database and ranks by cosine similarity
- `project:<path>` searches the project's codebase index

Results include `score`, `file`, `tree_path`, `section`, and `content`. Higher score = better match.

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
)
```

The proof file is keyed per target file (uses a hash of the canonical path), so concurrent edits to different files each get their own proof. The gate atomically renames the proof file during consumption to prevent TOCTOU races.

**Required fields the gate checks:**
- `verdict` must be `"VERIFIED"`
- `ts` must be timezone-aware ISO format (Z suffix or +00:00) and within 120 seconds
- `content_hash` must match the SHA-256 of the actual edit being applied
- `min_score` must be >= 0.5 (best RAG result score from the search)

## Auto-Research (builds knowledge permanently)

When your search in step 1 returns no results or scores below 0.5, OR the Haiku verifier says RESEARCH_MORE, you must acquire docs before retrying. This is not a one-time cost. Every topic you research gets permanently indexed and reused across all future sessions.

### Flow

1. Call `POST http://127.0.0.1:8613/acquire-topic {"topic": "<technology-slug>"}`
   This runs the 4-layer waterfall:
   - Layer 1: GitHub sparse checkout (if source_map has the repo)
   - Layer 2: llms.txt / llms-full.txt check (if doc_root known)
   - Layer 3: BFS crawl of documentation site
   - Layer 4: (you handle this) WebSearch fallback

2. Check the response:
   - `covered: true` means layers 1-3 got enough docs. The topic is indexed. Go back to search.
   - `needs_websearch: true` means layers 1-3 found fewer than 5 files. Use WebSearch to find authoritative docs (official docs, GitHub repos, MDN, OWASP). Save them to `clean-rag/knowledge/<category>/<topic>/` then index:
     `POST http://127.0.0.1:8613/index-topic {"topic": "<name>", "category": "<category>"}`

3. Re-search with the newly indexed topic
4. Re-verify with the Haiku agent
5. Loop until VERIFIED

### Why this saves tokens

First edit touching FastAPI? Research costs ~30 seconds. Every subsequent FastAPI edit hits the local vector index in milliseconds. No re-research, no re-downloading, no re-reading docs. The proof comes from local search, not from Claude reasoning from training data.

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
- Files with extensions: .md, .mdx, .rst, .txt, .gitignore, .env.example, .csv, .svg
- When ClaudeBoost AUTO mode is active (logged to proof-log.jsonl for audit trail)

**Deliberately NOT exempt:**
- `.json`, `.yaml`, `.yml`, `.toml`, `.xml` files require proof (prevents proof file fabrication)
- Files under `clean-rag/` require proof (the enforcement system does not exempt itself)

Only documentation files and internal workspace artifacts skip the gate.

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

## Project Indexing

```bash
python clean-rag/cli/index.py /path/to/project          # Index project code
python clean-rag/cli/index.py /path/to/project --force   # Full reindex
```
