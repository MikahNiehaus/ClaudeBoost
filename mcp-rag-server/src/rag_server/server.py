"""MCP RAG server entry point. Stdio transport."""

import json
import logging
import time
from pathlib import Path

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from rag_server.config import (
    CHROMA_DIR,
    DEFAULT_MIN_SCORE,
    DEFAULT_SEARCH_LIMIT,
    EMBEDDING_MODEL,
    PROJECT_ROOT,
    RAG_INDEX_DIR,
    SCOPES,
)
from rag_server.core.embedding import SentenceTransformerEmbedding
from rag_server.core.store import ChromaStore
from rag_server.core.watcher import FileWatcher
from rag_server.indexing.engine import IndexingEngine
from rag_server.indexing.markdown_chunker import estimate_tokens
from rag_server.tools.search import rag_search
import rag_server.tools.context as _context_mod

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)

# MCP server (lightweight — no side effects)
app = Server("rag-server")

# Components initialized in main(), accessed via module-level refs
embedder: SentenceTransformerEmbedding | None = None
store: ChromaStore | None = None
engine: IndexingEngine | None = None


@app.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="rag_search",
            description=(
                "Search ClaudeBoost knowledge bases, agent definitions, or project "
                "codebases using semantic similarity. "
                "Returns the most relevant text chunks with source attribution."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Natural language search query.",
                    },
                    "scope": {
                        "type": "string",
                        "enum": ["all", "knowledge", "agents", "codebase", "research"],
                        "description": (
                            "Which collection to search. "
                            "'codebase' requires project_path. "
                            "'research' requires workspace_path."
                        ),
                        "default": "all",
                    },
                    "project_path": {
                        "type": "string",
                        "description": (
                            "Absolute path to the target project. "
                            "Required when scope='codebase'."
                        ),
                    },
                    "workspace_path": {
                        "type": "string",
                        "description": (
                            "Absolute path to the task workspace directory. "
                            "Required when scope='research'."
                        ),
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max results (1-20).",
                        "default": DEFAULT_SEARCH_LIMIT,
                        "minimum": 1,
                        "maximum": 20,
                    },
                    "min_score": {
                        "type": "number",
                        "description": "Minimum similarity threshold (0.0-1.0).",
                        "default": DEFAULT_MIN_SCORE,
                        "minimum": 0.0,
                        "maximum": 1.0,
                    },
                    "mode": {
                        "type": "string",
                        "enum": ["vector", "graph"],
                        "description": (
                            "Search mode. 'vector' = semantic similarity only (default). "
                            "'graph' = vector seed + structural neighbours from graph index. "
                            "Only applies when scope='codebase'. Requires re-indexing with GraphRAG."
                        ),
                        "default": "vector",
                    },
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="rag_index",
            description=(
                "Index or re-index ClaudeBoost files for RAG search. "
                "Re-indexes knowledge bases and agent definitions."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "scope": {
                        "type": "string",
                        "enum": ["knowledge", "agents", "all"],
                        "description": "Which collection to re-index.",
                        "default": "all",
                    },
                    "force": {
                        "type": "boolean",
                        "description": "Force full re-index even if files haven't changed.",
                        "default": False,
                    },
                },
            },
        ),
        Tool(
            name="rag_status",
            description=(
                "Check RAG server status: model info, collection sizes, and all indexed projects. "
                "Each indexed project entry shows graph_active (true = graph-mode search works) "
                "and graph_edges/graph_resolved counts. Graph DBs are per-project — "
                "they are NOT shown as a global component."
            ),
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        Tool(
            name="rag_index_project",
            description=(
                "Index a project's source code for semantic codebase search. "
                "Creates a per-project vector database. Re-runs only re-embed changed files. "
                "Returns: files_indexed, chunks_created, files_unchanged, files_failed, "
                "elapsed_s, graph (edges/resolved), and errors[] if any files failed. "
                "Check files_failed > 0 to detect partial failures — errors[] lists each "
                "file, its error type (read_error or embed_error), and the message."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "project_path": {
                        "type": "string",
                        "description": "Absolute path to the target project root.",
                    },
                    "languages": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "Language filter (e.g., ['python', 'typescript']). "
                            "Omit to index all supported languages."
                        ),
                    },
                    "force": {
                        "type": "boolean",
                        "description": "Force full re-index even if files haven't changed.",
                        "default": False,
                    },
                },
                "required": ["project_path"],
            },
        ),
        Tool(
            name="rag_scan",
            description=(
                "Dry-run scan of a project: returns what would be indexed (by language, "
                "count, estimated size) without writing anything to the vector database. "
                "Run this before rag_index_project to preview scope and catch surprises."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "project_path": {
                        "type": "string",
                        "description": "Absolute path to the project root.",
                    },
                    "languages": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "Language filter (e.g. ['typescript', 'csharp']). "
                            "Omit to scan all supported languages."
                        ),
                    },
                    "max_file_kb": {
                        "type": "integer",
                        "description": "Skip files larger than this size in KB. Default: 200.",
                        "default": 200,
                    },
                },
                "required": ["project_path"],
            },
        ),
        Tool(
            name="rag_index_research",
            description=(
                "Index URLs, PDFs, or local files into a per-task research RAG. "
                "Creates a workspace-scoped vector database that can be queried with "
                "rag_search scope='research'. Supports web pages, PDF URLs, and local "
                ".pdf/.md/.txt files. Incremental: skips sources whose content hasn't changed."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "sources": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "List of URLs (web pages or PDFs) or absolute local file paths "
                            "to index. Supports http/https URLs and local .pdf, .md, .txt files."
                        ),
                    },
                    "workspace_path": {
                        "type": "string",
                        "description": (
                            "Absolute path to the task workspace directory. "
                            "Research index stored at workspace_path/.rag-index/research/."
                        ),
                    },
                    "force": {
                        "type": "boolean",
                        "description": "Re-index even if source content hasn't changed.",
                        "default": False,
                    },
                },
                "required": ["sources", "workspace_path"],
            },
        ),
        Tool(
            name="rag_context",
            description=(
                "Build a curated context package for an agent. Given an agent name and "
                "task description, returns relevant knowledge chunks. "
                "Optionally includes project codebase search (Tier 4). "
                "Use when spawning an agent."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "agent": {
                        "type": "string",
                        "description": "Agent name (e.g., 'debug-agent', 'test-agent').",
                    },
                    "task_description": {
                        "type": "string",
                        "description": "What the agent will work on.",
                    },
                    "project_path": {
                        "type": "string",
                        "description": (
                            "Absolute path to target project. If provided and indexed, "
                            "Tier 4 codebase search is included in context."
                        ),
                    },
                    "max_tokens": {
                        "type": "integer",
                        "description": "Token budget for the context package.",
                        "default": 4000,
                        "minimum": 500,
                        "maximum": 16000,
                    },
                    "weight": {
                        "type": "string",
                        "enum": ["lightweight", "standard", "full"],
                        "description": (
                            "Agent weight class. lightweight: skip guardrails "
                            "(explore, research, docs, estimator, rag-indexing, research-rag). "
                            "standard/full: include all guardrails."
                        ),
                        "default": "standard",
                    },
                },
                "required": ["agent", "task_description"],
            },
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    # All tool handlers call blocking code (ChromaDB, subprocess, embedding inference).
    # On Windows with the MCP subprocess stdout=pipe + anyio I/O, blocking calls inside
    # the asyncio event loop hang indefinitely. Run ALL dispatch in a thread pool.
    #
    # 90-second timeout prevents indefinite hangs when the embedding model is still loading
    # during background startup (model load holds _load_lock, tool calls queue behind it).
    # If startup takes longer than 90s the caller gets a clear retry message instead of silence.
    import asyncio as _asyncio
    _t0 = time.monotonic()
    loop = _asyncio.get_running_loop()
    # Index operations are long-running by nature (10-15 min for large projects).
    # Query tools (search, context, status, scan) get the short 90s guard.
    _LONG_RUNNING = {"rag_index", "rag_index_project", "rag_index_research"}
    _timeout = 900.0 if name in _LONG_RUNNING else 90.0
    try:
        result = await _asyncio.wait_for(
            loop.run_in_executor(None, lambda: _dispatch_tool(name, arguments)),
            timeout=_timeout,
        )
    except _asyncio.TimeoutError:
        logger.error(
            "Tool %s timed out after %.0fs — likely blocked on model load or ChromaDB lock", name, _timeout,
        )
        result = {
            "error": (
                f"Tool '{name}' timed out after {int(_timeout)} seconds. "
                "The RAG server is probably still loading the embedding model or indexing files. "
                "Wait 30-60 seconds and retry — or run /mcp to reconnect if the problem persists."
            )
        }
    except Exception as e:
        logger.error(
            "Tool %s executor failed after %.1fs (threading/process issue): %s",
            name, time.monotonic() - _t0, e, exc_info=True,
        )
        result = {"error": f"Executor error: {e}"}
    else:
        _elapsed = time.monotonic() - _t0
        if "error" not in result:
            logger.info("Tool %s OK (%.1fs)", name, _elapsed)
        else:
            logger.warning("Tool %s returned error (%.1fs): %s", name, _elapsed, result["error"])
    return [TextContent(type="text", text=json.dumps(result, indent=2))]


def _dispatch_tool(name: str, arguments: dict) -> dict:
    """Synchronous tool dispatch — runs in a thread pool via run_in_executor."""
    # Log a brief summary of the call (omit large values like embeddings/content).
    _OMIT_KEYS = {"content", "embeddings"}
    _loggable_args = {
        k: (f"[{len(v)}-item list]" if isinstance(v, list) and len(v) > 10 else v)
        for k, v in arguments.items()
        if k not in _OMIT_KEYS and not isinstance(v, bytes)
    }
    logger.info("Tool call: %s | args=%s", name, _loggable_args)
    _start = time.monotonic()
    try:
        if name == "rag_search":
            return rag_search(
                embedder=embedder,
                store=store,
                query=arguments["query"],
                scope=arguments.get("scope", "all"),
                project_path=arguments.get("project_path"),
                workspace_path=arguments.get("workspace_path"),
                limit=arguments.get("limit", DEFAULT_SEARCH_LIMIT),
                min_score=arguments.get("min_score", DEFAULT_MIN_SCORE),
                mode=arguments.get("mode", "vector"),
            )

        elif name == "rag_scan":
            from rag_server.core.scanner import scan_project
            scan = scan_project(
                project_path=arguments["project_path"],
                languages=arguments.get("languages"),
                max_file_kb=arguments.get("max_file_kb", 200),
            )
            return {
                "files_to_index": len(scan.files),
                "files_by_language": scan.files_by_language,
                "total_discovered": scan.total_discovered,
                "skipped_gitignore": scan.skipped_gitignore,
                "skipped_too_large": scan.skipped_too_large,
                "skipped_generated": scan.skipped_generated,
                "estimated_size_kb": scan.estimated_size_kb,
            }

        elif name == "rag_index_project":
            return engine.index_project(
                project_path=arguments["project_path"],
                languages=arguments.get("languages"),
                force=arguments.get("force", False),
            )

        elif name == "rag_index_research":
            # STOP: fail fast if model isn't loaded — avoids blocking on _load_lock.
            if not embedder.is_loaded:
                return {"error": "Embedding model not ready yet — retry in 30-60 seconds."}
            from rag_server.tools.research import rag_index_research
            return rag_index_research(
                embedder=embedder,
                sources=arguments["sources"],
                workspace_path=arguments["workspace_path"],
                force=arguments.get("force", False),
            )

        elif name == "rag_index":
            # STOP: fail fast if model isn't loaded — avoids blocking on _load_lock.
            if not embedder.is_loaded:
                return {"error": "Embedding model not ready yet — retry in 30-60 seconds."}
            force = arguments.get("force", False)
            scope = arguments.get("scope", "all")
            if scope == "all":
                result = engine.index_all(force=force)
                result["scope"] = "all"
            else:
                result = engine.index_scope(scope, force=force)
                result["scope"] = scope
            return result

        elif name == "rag_status":
            collections_status = {}
            for scope_name, scope_config in SCOPES.items():
                col = scope_config["collection"]
                collections_status[scope_name] = {
                    "chunks": store.count(col),
                    "files": store.count_sources(col) if store.collection_exists(col) else 0,
                }
            # Load per-project graph registry written by rag_index_project
            registry_path = RAG_INDEX_DIR / "projects.json"
            indexed_projects: dict = {}
            if registry_path.exists():
                try:
                    indexed_projects = json.loads(registry_path.read_text(encoding="utf-8"))
                except Exception:
                    pass
            # Health issues are stored in projects.json by rag_index_project at index time.
            # Do NOT run live check_project_health() here — it opens a ChromaDB connection
            # per project, and with 60+ projects this causes rag_status to hang for minutes.
            return {
                "status": "ready",
                "project_root": str(PROJECT_ROOT),
                "collections": collections_status,
                "model": EMBEDDING_MODEL,
                "embedding_dimensions": embedder.dimensions() if embedder.is_loaded else "not loaded yet",
                "indexed_projects": indexed_projects,
            }

        elif name == "rag_context":
            return _build_context(
                agent=arguments["agent"],
                task_description=arguments["task_description"],
                max_tokens=arguments.get("max_tokens", 4000),
                weight=arguments.get("weight", "standard"),
                project_path=arguments.get("project_path"),
            )

        else:
            return {"error": f"Unknown tool: {name}"}

    except Exception as e:
        _elapsed = time.monotonic() - _start
        logger.error(
            "Tool %s failed after %.1fs: %s", name, _elapsed, e, exc_info=True
        )
        return {"error": str(e)}


def _build_context(
    agent: str, task_description: str, max_tokens: int,
    weight: str = "standard", project_path: str | None = None,
) -> dict:
    """Delegate to tools/context.py so changes there hot-reload without a server restart."""
    return _context_mod.build_context(
        agent=agent,
        task_description=task_description,
        max_tokens=max_tokens,
        store=store,
        embedder=embedder,
        project_root=PROJECT_ROOT,
        weight=weight,
        project_path=project_path,
    )


def sync_init() -> FileWatcher:
    """Synchronous startup: initialize components and wire up watchers.

    Kept deliberately fast — no model loading, no indexing. Those run in a
    background thread after the MCP server is ready (see _background_startup).

    ChromaDB 1.5+ uses a Rust/Tokio backend that crashes when called from
    inside an asyncio coroutine. ChromaDB calls in background tasks must use
    run_in_executor (see main()).
    """
    global embedder, store, engine

    logger.info("Starting RAG server. Project root: %s", PROJECT_ROOT)

    # Write heartbeat immediately — guard needs a fresh timestamp before any tool call arrives.
    # The background startup will update it again once model+indexing complete.
    _write_heartbeat()

    embedder = SentenceTransformerEmbedding(model_name=EMBEDDING_MODEL)
    store = ChromaStore(persist_dir=str(CHROMA_DIR))
    engine = IndexingEngine(embedder=embedder, store=store)

    # Start file watcher for auto-indexing on changes
    watcher = FileWatcher()
    watch_paths = []
    for dirname in ["agents", "knowledge"]:
        dirpath = PROJECT_ROOT / dirname
        if dirpath.is_dir():
            watch_paths.append(str(dirpath))
    if watch_paths:
        def _on_file_change(path: str):
            logger.info("File changed, re-indexing: %s", path)
            try:
                engine.index_all()
            except Exception:
                logger.exception("Auto-index failed after file change: %s", path)
        watcher.watch(watch_paths, _on_file_change)
        logger.info("Watcher started for: %s", ", ".join(watch_paths))

    # Hot-reload watcher: reload RAG server source modules when they change so
    # code fixes take effect without needing /mcp. Reloads in dependency order
    # and re-binds the engine global so the updated IndexingEngine class is used.
    src_dir = Path(__file__).parent
    if src_dir.is_dir():
        import importlib
        import rag_server.adapters.sqlite_graph_store as _gstore_mod
        import rag_server.indexing.engine as _engine_mod
        import rag_server.tools.search as _search_mod
        import rag_server.tools.context as _ctx_mod

        def _on_source_change(path: str):
            global engine, rag_search, _context_mod
            logger.info("Source changed, hot-reloading modules: %s", path)
            try:
                importlib.reload(_gstore_mod)
                importlib.reload(_engine_mod)
                importlib.reload(_search_mod)
                importlib.reload(_ctx_mod)
                engine = _engine_mod.IndexingEngine(embedder=embedder, store=store)
                rag_search = _search_mod.rag_search
                _context_mod = _ctx_mod
                logger.info("Hot-reload complete — updated code is now active")
            except Exception:
                logger.exception("Hot-reload failed for %s — still running old code", path)

        watcher.watch([str(src_dir)], _on_source_change)
        logger.info("Source hot-reload watcher active on: %s", src_dir)

    logger.info("Sync init complete — MCP server ready. Background indexing will start shortly.")
    return watcher


def _background_startup() -> None:
    """Slow startup work that runs in a thread pool after MCP server is ready.

    Keeps sync_init() fast so Claude Code can connect before its MCP timeout.
    Must be called via run_in_executor — ChromaDB must not run inside an
    asyncio coroutine.
    """
    try:
        # Check for embedding dimension mismatch (e.g. model swap 384d -> 768d).
        # embedder.dimensions() triggers model load here — intentional, but done in
        # a background thread so it doesn't block MCP startup.
        # STOP: never force re-index on dimension mismatch in background startup.
        # A full force re-index holds ChromaDB locked for minutes, blocking all tool calls
        # (rag_status, rag_search, etc.) and fills the thread pool. Log a warning instead —
        # the user must explicitly trigger a force re-index via rag_index(force=true).
        try:
            for scope_config in SCOPES.values():
                col_name = scope_config["collection"]
                if store.collection_exists(col_name) and store.count(col_name) > 0:
                    sample_dim = store.sample_dimension(col_name)
                    if sample_dim and sample_dim != embedder.dimensions():
                        logger.warning(
                            "DIMENSION MISMATCH in %s: index=%dd, model=%dd. "
                            "Skipping background re-index — run rag_index(force=true) or "
                            "delete .rag-index/chroma to rebuild with the new model.",
                            col_name, sample_dim, embedder.dimensions(),
                        )
                        # Return early — do not index at all. Incremental would add wrong-dimension
                        # chunks; force would block the server. User must act explicitly.
                        return
        except Exception:
            logger.exception("Background: dimension check failed — proceeding with incremental index")

        logger.info("Background: auto-indexing default collections (incremental)...")
        _t0 = time.monotonic()
        result = engine.index_all(force=False)
        logger.info(
            "Background: startup indexing complete in %.1fs: %d files, %d chunks",
            time.monotonic() - _t0, result["files_indexed"], result["chunks_created"],
        )

        # Pre-load the embedding model so the first search call doesn't hang.
        # The dimension-mismatch check above only loads it when chunks exist AND
        # sample_dimension() returns a non-zero value — that path can miss. Always
        # warm up here if the model still hasn't loaded.
        if not embedder.is_loaded:
            logger.info("Background: pre-loading embedding model...")
            try:
                _mt0 = time.monotonic()
                embedder.dimensions()
                logger.info(
                    "Background: model ready in %.1fs (%dd)",
                    time.monotonic() - _mt0, embedder.dimensions(),
                )
            except Exception:
                logger.exception("Background: model pre-load failed — first search will be slow")

    except Exception:
        logger.exception(
            "Background: startup indexing failed — server is up but index may be empty or stale"
        )
    finally:
        # Write heartbeat file so the PreToolUse hook knows the server is alive.
        # Written even on startup failure so rag_status can surface the error.
        _write_heartbeat()
        _start_heartbeat_thread()


def _heartbeat_path() -> Path:
    return RAG_INDEX_DIR / ".heartbeat"


def _write_heartbeat() -> None:
    try:
        _heartbeat_path().parent.mkdir(parents=True, exist_ok=True)
        _heartbeat_path().write_text(str(time.time()), encoding="utf-8")
    except Exception:
        pass


def _start_heartbeat_thread() -> None:
    import threading
    def _beat():
        while True:
            time.sleep(30)
            _write_heartbeat()
    t = threading.Thread(target=_beat, daemon=True, name="rag-heartbeat")
    t.start()


async def main(watcher: FileWatcher) -> None:
    """Run the MCP stdio server. Call sync_init() before this."""
    import asyncio
    logger.info("MCP stdio transport starting")
    try:
        async with stdio_server() as (read_stream, write_stream):
            # Schedule slow startup work (model load + indexing) as a background
            # thread so the MCP handshake completes before it runs.
            loop = asyncio.get_running_loop()
            asyncio.ensure_future(loop.run_in_executor(None, _background_startup))
            logger.info("MCP server ready — accepting tool calls")
            await app.run(read_stream, write_stream, app.create_initialization_options())
        logger.info("MCP stdio connection closed cleanly")
    except Exception:
        logger.exception("MCP server crashed — unhandled exception in main()")
        raise
    finally:
        logger.info("MCP server shutting down, stopping file watchers")
        watcher.stop()


if __name__ == "__main__":
    import asyncio
    _watcher = sync_init()
    try:
        asyncio.run(main(_watcher))
    except KeyboardInterrupt:
        logger.info("RAG server stopped (KeyboardInterrupt)")
    except Exception:
        logger.exception("RAG server exited with unhandled exception")
        raise
