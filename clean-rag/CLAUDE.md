# clean-rag

Research-verified editing enforcement for Claude Code. Every source code edit requires verified proof from indexed research or codebase patterns.

## How It Works

clean-rag maintains separate ChromaDB databases organized by topic. Each topic (e.g., `fastapi`, `react-hooks`, `jwt-tokens`) has its own database at `databases/<topic>/chroma/`. Project source code is indexed separately at `databases/_projects/<hash>/chroma/`.

When you try to edit a source file, the `proof-gate.py` hook blocks the edit unless you've already verified your proof through a Haiku verification agent.

## The Proof Cycle

Every Edit, Write, or MultiEdit on source code follows this cycle:

1. **Search for proof**: `POST http://127.0.0.1:8613/search` with a query about what you're changing and why
2. **Spawn a Haiku verifier**: Use the Agent tool with `model: "haiku"` to independently verify your proof
3. **Write the verification**: Use `write_pending_proof()` from `verifier/log.py`. Each file gets its own keyed proof file (not a single shared file). Include `content_hash` (SHA-256 of the edit content) and `min_score` (best RAG result score, must be >= 0.5).
4. **Retry the edit**: The hook atomically consumes the keyed proof file and passes if:
   - verdict == VERIFIED
   - content_hash matches the proposed edit (prevents reuse for different edits)
   - min_score >= 0.5 (mechanical quality threshold)
   - timestamp is timezone-aware and within 120 seconds (naive timestamps rejected)

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

## Verification Agent

Spawn a Haiku agent with the verification prompt. The prompt must include:
- The file being edited and the proposed change
- Architecture context (what the file does, what the project uses)
- RAG search results (content, score, source)
- Your justification for the change

The agent responds with one of:
- `VERIFIED: [reason]` (proof is sufficient, proceed)
- `RESEARCH_MORE: [what topic needs more research]`
- `INSUFFICIENT: [what is missing]`

## Writing Verified Proof

After receiving VERIFIED, use `write_pending_proof()` from `clean-rag/verifier/log.py`:

```python
from clean_rag.verifier.log import write_pending_proof

write_pending_proof(
    state_dir="clean-rag/state",
    file_path="path/to/file.py",
    verdict="VERIFIED",
    verifier_response="The response from the Haiku agent",
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

## Auto-Research

If the Haiku agent says RESEARCH_MORE, you need to acquire documentation for the missing topic before retrying:

1. Call `POST http://127.0.0.1:8613/acquire-topic {"topic": "<name>"}` to auto-acquire and index
2. Re-search with the newly indexed topic
3. Re-verify with the Haiku agent

The `/acquire-topic` endpoint runs the four-layer waterfall automatically: GitHub sparse checkout, llms.txt check, BFS crawl, then indexes the results. If it reports `needs_websearch: true`, layers 1-3 produced fewer than 5 files and you should supplement with WebSearch.

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
