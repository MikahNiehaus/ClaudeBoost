# MCP RAG Server for ClaudeBoost

Semantic search over knowledge bases, agent definitions, and project codebases.

## Setup

```bash
cd mcp-rag-server
pip install -e .
# or with uv:
uv pip install -e .
```

First run downloads the embedding model (~90MB, requires internet once).

## Claude Code Integration

Run `install.bat` from the ClaudeBoost root — it registers the MCP server globally
with the correct `RAG_PROJECT_ROOT` for your machine. Manual registration example:

```json
{
  "mcpServers": {
    "rag-server": {
      "command": "python",
      "args": ["-m", "rag_server"],
      "env": {
        "RAG_PROJECT_ROOT": "<path-to-ClaudeBoost>"
      }
    }
  }
}
```

## Tools

| Tool | Purpose |
|------|---------|
| `rag_search` | Semantic search with scope filtering |
| `rag_index` | Re-index ClaudeBoost knowledge bases and agent definitions |
| `rag_status` | Server health and collection sizes |
| `rag_context` | Build curated context for agent spawning |
| `rag_index_project` | Index a project's source code for codebase search |
| `rag_scan` | Dry-run scan — preview what would be indexed without writing |

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `RAG_PROJECT_ROOT` | Auto-detected | Path to ClaudeBoost project root |
| `RAG_INDEX_DIR` | `{root}/mcp-rag-server/.rag-index` | Where ChromaDB stores data |
| `RAG_EMBEDDING_MODEL` | `all-MiniLM-L6-v2` | Sentence-transformers model name |

## How It Works

1. On startup, indexes `knowledge/` and `agents/` directories
2. Files are chunked by section (markdown headers or XML elements)
3. Chunks are embedded using sentence-transformers and stored in ChromaDB
4. Agents query semantically: "error handling for API calls" finds relevant chunks
5. Incremental indexing: only re-embeds files that changed (SHA-256 hash comparison)
6. File watcher auto-reindexes when source files change

## Standalone vs Gas Town

Works independently in any ClaudeBoost project. With Gas Town, polecats and crew
use `rag_context` for automatic knowledge routing when slung work.
