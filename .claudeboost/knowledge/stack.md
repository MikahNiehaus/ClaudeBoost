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
