"""MCP RAG server entry point. Stdio transport."""

import json
import logging

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from rag_server.config import (
    CHROMA_DIR,
    DEFAULT_MIN_SCORE,
    DEFAULT_SEARCH_LIMIT,
    EMBEDDING_MODEL,
    PROJECT_ROOT,
    SCOPES,
)
from rag_server.core.embedding import SentenceTransformerEmbedding
from rag_server.core.store import ChromaStore
from rag_server.core.watcher import FileWatcher
from rag_server.indexing.engine import IndexingEngine
from rag_server.indexing.markdown_chunker import estimate_tokens
from rag_server.tools.search import rag_search

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
                        "enum": ["all", "knowledge", "agents", "codebase"],
                        "description": (
                            "Which collection to search. "
                            "'codebase' requires project_path."
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
            description="Check RAG server status: index health, collection sizes, model info.",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        Tool(
            name="rag_index_project",
            description=(
                "Index a project's source code for semantic codebase search. "
                "Creates a per-project vector database. Re-runs only re-embed changed files."
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
                            "(explore, research, docs, estimator, teacher). "
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
    import asyncio as _asyncio
    loop = _asyncio.get_running_loop()
    result = await loop.run_in_executor(None, lambda: _dispatch_tool(name, arguments))
    return [TextContent(type="text", text=json.dumps(result, indent=2))]


def _dispatch_tool(name: str, arguments: dict) -> dict:
    """Synchronous tool dispatch — runs in a thread pool via run_in_executor."""
    try:
        if name == "rag_search":
            return rag_search(
                embedder=embedder,
                store=store,
                query=arguments["query"],
                scope=arguments.get("scope", "all"),
                project_path=arguments.get("project_path"),
                limit=arguments.get("limit", DEFAULT_SEARCH_LIMIT),
                min_score=arguments.get("min_score", DEFAULT_MIN_SCORE),
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

        elif name == "rag_index":
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
                    "files": len(store.list_sources(col)) if store.collection_exists(col) else 0,
                }
            return {
                "status": "ready",
                "project_root": str(PROJECT_ROOT),
                "collections": collections_status,
                "model": EMBEDDING_MODEL,
                "embedding_dimensions": embedder.dimensions() if embedder.is_loaded else "not loaded yet",
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
        logger.error("Tool %s failed: %s", name, e, exc_info=True)
        return {"error": str(e)}


def _build_context(
    agent: str, task_description: str, max_tokens: int,
    weight: str = "standard", project_path: str | None = None,
) -> dict:
    """Build a tiered context package for an agent.

    Tier 0: Agent definition (always included, full text)
    Tier 1: Universal guardrails (skipped for lightweight agents)
    Tier 2: Agent-declared knowledge bases (from <knowledge-base> tags)
    Tier 3: Semantic search fills remaining budget (knowledge only, not agents)
    Tier 4: Codebase search (if project_path provided and index exists)
    """
    import re as _re

    # --- Tier 0: Agent definition ---
    agent_file = f"agents/{agent}.md"
    agent_def = ""
    agent_path = PROJECT_ROOT / agent_file
    if agent_path.exists():
        agent_def = agent_path.read_text(encoding="utf-8")
    else:
        agent_path_xml = PROJECT_ROOT / f"agents/{agent}.xml"
        if agent_path_xml.exists():
            agent_def = agent_path_xml.read_text(encoding="utf-8")
            agent_file = f"agents/{agent}.xml"

    agent_tokens = estimate_tokens(agent_def)
    remaining_budget = max_tokens - agent_tokens

    # --- Parse agent's declared knowledge bases ---
    declared_files = []
    if agent_def:
        # Match <primary file="knowledge/foo.xml"> and <secondary file="knowledge/bar.xml">
        for match in _re.finditer(r'<(?:primary|secondary)\s+file="([^"]+)"', agent_def):
            declared_files.append(match.group(1))

    # --- Tier 1: Universal guardrails (skipped for lightweight agents) ---
    GUARDRAIL_FILES = [
        "knowledge/security.xml",
        "knowledge/observability.xml",
        "knowledge/coding-standards.xml",
        "knowledge/scope-governance.xml",
    ]

    tier1_chunks = []
    tier1_tokens = 0
    tier1_sources_seen = set()

    # Lightweight agents (explore, research, docs, estimator, teacher) skip guardrails —
    # they gather info / produce docs, they don't write code.
    skip_guardrails = weight == "lightweight"

    for guardrail_file in GUARDRAIL_FILES:
        if skip_guardrails:
            break
        if tier1_tokens >= remaining_budget * 0.4:
            break  # Don't let guardrails eat more than 40% of remaining budget
        chunks = store.get_by_source("knowledge", guardrail_file)
        for chunk in chunks:
            chunk_tokens = chunk.metadata.get("token_count", estimate_tokens(chunk.content))
            if tier1_tokens + chunk_tokens > remaining_budget * 0.4:
                break
            tier1_chunks.append({
                "source": chunk.metadata.get("source_file", guardrail_file),
                "section": chunk.metadata.get("section", ""),
                "content": chunk.content,
                "score": 1.0,
                "tier": "guardrail",
            })
            tier1_tokens += chunk_tokens
            tier1_sources_seen.add(guardrail_file)

    remaining_budget -= tier1_tokens

    # --- Tier 2: Agent-declared knowledge bases ---
    tier2_chunks = []
    tier2_tokens = 0
    tier2_sources_seen = set()
    for declared_file in declared_files:
        if declared_file in tier1_sources_seen:
            continue  # Already included as guardrail
        if tier2_tokens >= remaining_budget * 0.5:
            break  # Don't let declared KBs eat more than 50% of what's left
        chunks = store.get_by_source("knowledge", declared_file)
        for chunk in chunks:
            chunk_tokens = chunk.metadata.get("token_count", estimate_tokens(chunk.content))
            if tier2_tokens + chunk_tokens > remaining_budget * 0.5:
                break
            tier2_chunks.append({
                "source": chunk.metadata.get("source_file", declared_file),
                "section": chunk.metadata.get("section", ""),
                "content": chunk.content,
                "score": 1.0,
                "tier": "declared",
            })
            tier2_tokens += chunk_tokens
            tier2_sources_seen.add(declared_file)

    remaining_budget -= tier2_tokens

    # --- Tier 3: Semantic search for task-relevant knowledge ---
    # Only search knowledge collection (not agents — don't leak other agent definitions)
    all_included_sources = tier1_sources_seen | tier2_sources_seen
    tier3_chunks = []
    tier3_tokens = 0

    if remaining_budget > 200 and store.collection_exists("knowledge"):
        query_embedding = embedder.embed_query(task_description)
        search_results = store.search(
            "knowledge", query_embedding, limit=15, min_score=0.4,
        )
        for r in search_results:
            source = r.metadata.get("source_file", "")
            # Skip chunks from files already included in Tier 1/2
            if source in all_included_sources:
                continue
            chunk_tokens = r.metadata.get("token_count", estimate_tokens(r.content))
            if tier3_tokens + chunk_tokens > remaining_budget:
                break
            tier3_chunks.append({
                "source": source,
                "section": r.metadata.get("section", ""),
                "content": r.content,
                "score": r.score,
                "tier": "search",
            })
            tier3_tokens += chunk_tokens

    # --- Tier 4: Codebase search (if project indexed) ---
    tier4_chunks = []
    tier4_tokens = 0

    if project_path and remaining_budget > 200:
        from rag_server.core.project import project_index_dir
        from rag_server.core.store import ChromaStore as _ChromaStore

        idx_dir = project_index_dir(project_path)
        chroma_dir = idx_dir / "chroma"
        if chroma_dir.exists():
            project_store = _ChromaStore(persist_dir=str(chroma_dir))
            if project_store.collection_exists("codebase") and project_store.count("codebase") > 0:
                # Budget: up to 400 tokens or remaining budget, whichever is smaller
                tier4_budget = min(400, remaining_budget)
                query_embedding = embedder.embed_query(task_description)
                codebase_results = project_store.search(
                    "codebase", query_embedding, limit=10, min_score=0.35,
                )
                for r in codebase_results:
                    chunk_tokens = r.metadata.get("token_count", estimate_tokens(r.content))
                    if tier4_tokens + chunk_tokens > tier4_budget:
                        break
                    tier4_chunks.append({
                        "source": r.metadata.get("source_file", ""),
                        "section": r.metadata.get("section", ""),
                        "content": r.content,
                        "score": r.score,
                        "tier": "codebase",
                    })
                    tier4_tokens += chunk_tokens

    all_knowledge = tier1_chunks + tier2_chunks + tier3_chunks + tier4_chunks
    total_tokens = agent_tokens + tier1_tokens + tier2_tokens + tier3_tokens + tier4_tokens

    return {
        "agent_definition": agent_def,
        "agent_file": agent_file,
        "weight": weight,
        "relevant_knowledge": all_knowledge,
        "total_tokens_approx": total_tokens,
        "sources_used": len(all_knowledge) + (1 if agent_def else 0),
        "tier_summary": {
            "guardrails": len(tier1_chunks),
            "declared": len(tier2_chunks),
            "search": len(tier3_chunks),
            "codebase": len(tier4_chunks),
        },
    }


def sync_init() -> FileWatcher:
    """Synchronous startup: initialize components and index files.

    ChromaDB 1.5+ uses a Rust/Tokio backend that crashes when called from
    inside an asyncio coroutine. Run all ChromaDB calls here, before asyncio.run().
    """
    global embedder, store, engine

    logger.info("Starting RAG server. Project root: %s", PROJECT_ROOT)

    embedder = SentenceTransformerEmbedding(model_name=EMBEDDING_MODEL)
    store = ChromaStore(persist_dir=str(CHROMA_DIR))
    engine = IndexingEngine(embedder=embedder, store=store)

    # Check for embedding dimension mismatch (e.g. model swap 384d -> 768d)
    force_reindex = False
    for scope_config in SCOPES.values():
        col_name = scope_config["collection"]
        if store.collection_exists(col_name) and store.count(col_name) > 0:
            sample_dim = store.sample_dimension(col_name)
            if sample_dim and sample_dim != embedder.dimensions():
                logger.warning(
                    "Dimension mismatch in %s: index=%dd, model=%dd. Forcing re-index.",
                    col_name, sample_dim, embedder.dimensions(),
                )
                force_reindex = True
                break

    # Auto-index on startup
    logger.info("Auto-indexing default collections%s...", " (forced)" if force_reindex else "")
    result = engine.index_all(force=force_reindex)
    logger.info(
        "Startup indexing complete: %d files, %d chunks",
        result["files_indexed"], result["chunks_created"],
    )

    # NOTE: Embedding model warmup is intentionally deferred.
    # Pre-warming here blocks the MCP server from starting (5+ second delay),
    # causing Claude Code to time out and drop the MCP connection entirely.
    # All tool handlers run in run_in_executor, so lazy loading is safe.
    if embedder.is_loaded:
        logger.info("Embedding model already loaded from indexing.")
    else:
        logger.info("Embedding model will load on first tool call (deferred for fast MCP startup).")

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

    return watcher


async def main(watcher: FileWatcher) -> None:
    """Run the MCP stdio server. Call sync_init() before this."""
    try:
        async with stdio_server() as (read_stream, write_stream):
            await app.run(read_stream, write_stream, app.create_initialization_options())
    finally:
        watcher.stop()


if __name__ == "__main__":
    import asyncio
    _watcher = sync_init()
    asyncio.run(main(_watcher))
