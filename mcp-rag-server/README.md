# MCP RAG Server for ClaudeMemory

Semantic search over knowledge bases, agent definitions, workspace history, and codebases.

## Setup

```bash
cd mcp-rag-server
pip install -e .
# or with uv:
uv pip install -e .
```

First run downloads the embedding model (~90MB, requires internet once).

## Claude Code Integration

Add to your Claude Code MCP config (`.claude/mcp.json` or `~/.claude/mcp.json`):

```json
{
  "mcpServers": {
    "rag": {
      "command": "python",
      "args": ["-m", "rag_server"],
      "cwd": "C:/Users/grayw/gt/claudememory/crew/mikah/mcp-rag-server/src",
      "env": {
        "RAG_PROJECT_ROOT": "C:/Users/grayw/gt/claudememory/crew/mikah"
      }
    }
  }
}
```

## Tools

| Tool | Purpose |
|------|---------|
| `rag_search` | Semantic search with scope filtering |
| `rag_index` | Trigger indexing of files or codebase |
| `rag_status` | Server health and collection sizes |
| `rag_context` | Build curated context for agent spawning |

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `RAG_PROJECT_ROOT` | Auto-detected | Path to ClaudeMemory project root |
| `RAG_INDEX_DIR` | `{root}/mcp-rag-server/.rag-index` | Where ChromaDB stores data |
| `RAG_EMBEDDING_MODEL` | `all-MiniLM-L6-v2` | Sentence-transformers model name |

## How It Works

1. On startup, indexes `knowledge/`, `agents/`, and `workspace/` directories
2. Files are chunked by section (markdown headers or XML elements)
3. Chunks are embedded using sentence-transformers and stored in ChromaDB
4. Agents query semantically: "error handling for API calls" finds relevant chunks
5. Incremental indexing: only re-embeds files that changed (SHA-256 hash comparison)
6. File watcher auto-reindexes when source files change

## Standalone vs Gas Town

Works independently in any ClaudeMemory project. With Gas Town, polecats and crew
use `rag_context` for automatic knowledge routing when slung work.
