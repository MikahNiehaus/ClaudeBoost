# OpenCode RAG + Metrics Integration

Wire OpenCode (any model: DeepSeek, Claude, LocalAI) to clean-rag for RAG injection + code metrics.

## Prerequisites

- clean-rag server running on port 8613: `python clean-rag/server/app.py`
- OpenCode installed (https://github.com/anthropics/opencode, or using Docker/local build)
- Python 3.10+

## Installation

### 1. Start the MCP Server

```bash
cd /c/prj/ClaudeBoost/clean-rag/mcp
python opencode_mcp_server.py
```

Server listens on stdin/stdout (MCP protocol) and connects to clean-rag on port 8613. Log file: `/tmp/opencode_mcp_server.log`

### 2. Configure OpenCode

Edit your OpenCode settings (usually `~/.opencode/settings.json` or project-level `.opencode.json`):

```json
{
  "mcpServers": {
    "clean-rag": {
      "command": "python",
      "args": ["/c/prj/ClaudeBoost/clean-rag/mcp/opencode_mcp_server.py"],
      "env": {
        "CLEAN_RAG_HOME": "/c/prj/ClaudeBoost/clean-rag",
        "CLEAN_RAG_PORT": "8613"
      }
    }
  },
  "tools": {
    "rag_search": { "enabled": true },
    "code_metrics": { "enabled": true },
    "web_search_fallback": { "enabled": true },
    "inject_full_context": { "enabled": true }
  }
}
```

### 3. Restart OpenCode

The MCP server auto-connects. You should see 4 tools available:
- `rag_search` — semantic search on RAG knowledge base
- `code_metrics` — code quality analysis
- `web_search_fallback` — web search when RAG is weak
- `inject_full_context` — complete context injection in one call

## Usage

### Automatic Context Injection (Recommended)

Ask OpenCode to analyze a file with code metrics + RAG context:

```
What collision detection bugs might this have? Inject full context first: /flappy_bird_claude_test.py
```

OpenCode will:
1. Call `inject_full_context` with your prompt + filepath
2. Receive metrics (LOC, complexity, maintainability, call graph)
3. Search RAG for "collision detection" + "game physics"
4. Fall back to web search if RAG scores < 0.4
5. Inject all context into its response before generating code

### Manual Tool Calls

**Search RAG:**
```
Search RAG for "error handling patterns in Python"
```

**Get Code Metrics:**
```
Analyze the metrics for /c/prj/LocalAI/tests/flappy_bird_claude_test.py
```

**Web Search Fallback:**
```
Web search for "flappy bird collision algorithm"
```

## How It Works

### Injection Pipeline

```
User Query
  ↓
OpenCode calls inject_full_context with (prompt, filepath)
  ↓
MCP server:
  1. Search RAG for prompt
  2. Get code metrics for filepath
  3. Check if RAG score < 0.4 → trigger web search
  ↓
Format results as markdown section:
  - Research Context (RAG scores, content snippets)
  - Code Quality Metrics (LOC, complexity, maintainability, call graph)
  - Web Search Results (if fallback triggered)
  ↓
Inject formatted context into prompt
  ↓
Model (DeepSeek, Claude, etc.) sees injection + original prompt
  ↓
Model generates response with injected proof visible
```

### Metrics Injection

When a filepath is provided, the server computes:
- **Lines of Code** — total lines in the file
- **Cyclomatic Complexity** — nesting/branching complexity score
- **Maintainability Index** — code quality score (0-100)
- **Call Graph** — extracted functions, classes, imports in the file

### Web Search Fallback

When RAG search returns no results or scores < 0.4:
1. Server triggers DuckDuckGo web search (async, non-blocking)
2. Extracts top 3 results with title, snippet, URL
3. Returns as fallback context
4. Background indexer crawls and indexes results for future searches

## Troubleshooting

### MCP Server Not Connecting

1. Check log: `tail -f /tmp/opencode_mcp_server.log`
2. Verify clean-rag server is running: `curl http://127.0.0.1:8613/health`
3. Restart OpenCode: close and re-open the editor

### RAG Returning No Results

Check if project is indexed:
```bash
curl http://127.0.0.1:8613/projects
```

If your project is missing, index it:
```bash
curl -X POST http://127.0.0.1:8613/index-project \
  -H "Content-Type: application/json" \
  -d '{"project_path": "/c/prj/LocalAI"}'
```

### Metrics Not Showing

1. Ensure filepath is absolute and correct
2. Verify file is Python, JavaScript, TypeScript, or Go
3. Check server log for parse errors

## Examples

### Example 1: Analyze Collision Detection

**Query:**
```
Can you find and fix the collision detection bug in flappy_bird_claude_test.py? 
Use inject_full_context to see the code metrics and any collision algorithms from research.
```

**Result:**
- OpenCode receives metrics: LOC=169, Complexity=12, Maintainability=65
- RAG search finds "collision detection algorithms" with score 0.78
- Call graph shows: `check_collision()`, `Bird.get_rect()`, `Pipe.get_top_rect()`, etc.
- Injection output shows what the model sees

### Example 2: Improve Code Quality

**Query:**
```
This function is getting too complex. What patterns does our codebase use for this?
Tool: inject_full_context filepath=/c/prj/LocalAI/tests/flappy_bird_claude_test.py
```

**Result:**
- Metrics show complexity score + maintainability index
- RAG search finds project patterns for similar functions
- Model suggests refactoring based on project conventions

### Example 3: Security Review

**Query:**
```
Review this for security issues. Check against OWASP patterns.
Tool: rag_search with query "OWASP security patterns python"
```

**Result:**
- RAG returns OWASP guidelines
- Model reviews code against standards
- Web search fallback if OWASP coverage is weak

## Architecture

```
OpenCode Editor
  ↓ (MCP protocol)
  ↓
opencode_mcp_server.py
  ├─ rag_search()           → POST /search to clean-rag:8613
  ├─ code_metrics()         → POST /metrics to clean-rag:8613
  ├─ web_search_fallback()  → POST /web-search to clean-rag:8613
  └─ inject_full_context()  → coordinates all three + formats results
  ↓
clean-rag server (port 8613)
  ├─ /search                → ChromaDB semantic search
  ├─ /metrics               → AST parsing for code quality
  ├─ /web-search            → DuckDuckGo API
  └─ /index-project         → background indexing
```

## Metrics Computation (AST-based)

The server parses code via AST (no LLM):
- **Python**: `ast.parse()` + traversal
- **JavaScript/TypeScript**: RegEx + token analysis (no external parsers)
- **Go**: RegEx parsing

Extracted data:
```json
{
  "lines_of_code": 169,
  "cyclomatic_complexity": 12,
  "maintainability_index": 65,
  "call_graph": {
    "functions": ["check_collision", "update_bird", "update_pipes"],
    "classes": ["Bird", "Pipe", "GameState", "FlappyBirdGame"],
    "imports": ["pygame", "random", "enum"]
  }
}
```

## Disabling Features

To disable specific tools in OpenCode:

```json
{
  "tools": {
    "rag_search": { "enabled": false },
    "web_search_fallback": { "enabled": false }
  }
}
```

## Performance

- **RAG search** — typically < 1 second (local ChromaDB)
- **Code metrics** — typically < 0.5 seconds (AST parsing, cached)
- **Web search** — typically 2-4 seconds (async, non-blocking)
- **Injection formatting** — < 100ms

Total injection overhead: usually under 2 seconds for all three.

## Logging

All tool calls are logged to `/tmp/opencode_mcp_server.log`:

```
2026-07-11 10:15:23 - opencode_mcp_server - INFO - Tool call: inject_full_context with ['prompt', 'filepath', 'model']
2026-07-11 10:15:23 - opencode_mcp_server - INFO - Injecting context for deepseek: What collision detection bugs...
2026-07-11 10:15:23 - opencode_mcp_server - INFO - RAG search 'collision detection' returned 3 results
2026-07-11 10:15:25 - opencode_mcp_server - INFO - Web search 'collision detection' returned 2 results
```

## Next Steps

1. **Start the MCP server** (if not already running)
2. **Update OpenCode settings** with the MCP config
3. **Restart OpenCode**
4. **Test with flappy_bird_claude_test.py** — ask OpenCode to find collision detection bugs
5. **Verify injection in logs** — check `/tmp/opencode_mcp_server.log`

## Support

- For RAG issues: `/rag` in Claude Code
- For OpenCode issues: see OpenCode documentation
- For metrics computation bugs: file an issue with the file path + language
