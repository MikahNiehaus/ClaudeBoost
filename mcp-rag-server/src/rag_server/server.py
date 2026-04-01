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
                "Search the ClaudeMemory knowledge base, agent definitions, workspace "
                "history, and optionally a target codebase using semantic similarity. "
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
                        "enum": ["all", "knowledge", "agents", "workspaces", "codebase"],
                        "description": "Which collection to search.",
                        "default": "all",
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
                "Index or re-index files for RAG search. Use 'path' to index a "
                "codebase directory. Omit to re-index default collections."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Absolute path to a directory to index as codebase.",
                    },
                    "scope": {
                        "type": "string",
                        "enum": ["knowledge", "agents", "workspaces", "codebase", "all"],
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
            name="rag_context",
            description=(
                "Build a curated context package for an agent. Given an agent name and "
                "task description, returns relevant knowledge chunks and past workspace "
                "decisions. Use when spawning an agent."
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
                    "max_tokens": {
                        "type": "integer",
                        "description": "Token budget for the context package.",
                        "default": 4000,
                        "minimum": 500,
                        "maximum": 16000,
                    },
                },
                "required": ["agent", "task_description"],
            },
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    try:
        if name == "rag_search":
            result = rag_search(
                embedder=embedder,
                store=store,
                query=arguments["query"],
                scope=arguments.get("scope", "all"),
                limit=arguments.get("limit", DEFAULT_SEARCH_LIMIT),
                min_score=arguments.get("min_score", DEFAULT_MIN_SCORE),
            )

        elif name == "rag_index":
            path = arguments.get("path")
            force = arguments.get("force", False)
            scope = arguments.get("scope", "all")

            if path:
                result = engine.index_codebase(path, force=force)
                result["scope"] = "codebase"
                result["path"] = path
            elif scope == "all":
                result = engine.index_all(force=force)
                result["scope"] = "all"
            else:
                result = engine.index_scope(scope, force=force)
                result["scope"] = scope

        elif name == "rag_status":
            collections_status = {}
            for scope_name, scope_config in SCOPES.items():
                col = scope_config["collection"]
                collections_status[scope_name] = {
                    "chunks": store.count(col),
                    "files": len(store.list_sources(col)) if store.collection_exists(col) else 0,
                }
            # Codebase collection
            collections_status["codebase"] = {
                "chunks": store.count("codebase"),
                "files": len(store.list_sources("codebase")) if store.collection_exists("codebase") else 0,
            }

            result = {
                "status": "ready",
                "project_root": str(PROJECT_ROOT),
                "collections": collections_status,
                "model": EMBEDDING_MODEL,
                "embedding_dimensions": embedder.dimensions() if embedder.is_loaded else "not loaded yet",
            }

        elif name == "rag_context":
            result = _build_context(
                agent=arguments["agent"],
                task_description=arguments["task_description"],
                max_tokens=arguments.get("max_tokens", 4000),
            )

        else:
            result = {"error": f"Unknown tool: {name}"}

    except Exception as e:
        logger.error("Tool %s failed: %s", name, e, exc_info=True)
        result = {"error": str(e)}

    return [TextContent(type="text", text=json.dumps(result, indent=2))]


def _build_context(agent: str, task_description: str, max_tokens: int) -> dict:
    """Build a curated context package for an agent."""
    # Always include the agent's own definition
    agent_file = f"agents/{agent}.md"
    agent_def = ""
    agent_path = PROJECT_ROOT / agent_file
    if agent_path.exists():
        agent_def = agent_path.read_text(encoding="utf-8")
    else:
        # Try .xml
        agent_path_xml = PROJECT_ROOT / f"agents/{agent}.xml"
        if agent_path_xml.exists():
            agent_def = agent_path_xml.read_text(encoding="utf-8")
            agent_file = f"agents/{agent}.xml"

    # Budget: reserve ~30% for agent def, rest for knowledge + history
    agent_tokens = estimate_tokens(agent_def)
    remaining_budget = max_tokens - agent_tokens
    knowledge_budget = int(remaining_budget * 0.7)
    history_budget = remaining_budget - knowledge_budget

    # Search knowledge for relevant chunks
    query_embedding = embedder.embed_query(task_description)
    knowledge_results = []
    for scope_name in ["knowledge", "agents"]:
        col = SCOPES[scope_name]["collection"]
        if store.collection_exists(col):
            results = store.search(col, query_embedding, limit=10, min_score=0.3)
            knowledge_results.extend(results)

    knowledge_results.sort(key=lambda r: r.score, reverse=True)

    # Fill knowledge budget
    relevant_knowledge = []
    tokens_used = 0
    for r in knowledge_results:
        chunk_tokens = r.metadata.get("token_count", estimate_tokens(r.content))
        if tokens_used + chunk_tokens > knowledge_budget:
            break
        relevant_knowledge.append({
            "source": r.metadata.get("source_file", "unknown"),
            "section": r.metadata.get("section", ""),
            "content": r.content,
            "score": r.score,
        })
        tokens_used += chunk_tokens

    # Search workspace history
    history_results = []
    if store.collection_exists("workspaces"):
        ws_results = store.search("workspaces", query_embedding, limit=5, min_score=0.3)
        ws_tokens = 0
        for r in ws_results:
            chunk_tokens = r.metadata.get("token_count", estimate_tokens(r.content))
            if ws_tokens + chunk_tokens > history_budget:
                break
            history_results.append({
                "source": r.metadata.get("source_file", "unknown"),
                "section": r.metadata.get("section", ""),
                "content": r.content,
                "score": r.score,
            })
            ws_tokens += chunk_tokens

    total_tokens = agent_tokens + tokens_used + sum(
        estimate_tokens(h["content"]) for h in history_results
    )

    return {
        "agent_definition": agent_def,
        "agent_file": agent_file,
        "relevant_knowledge": relevant_knowledge,
        "relevant_history": history_results,
        "total_tokens_approx": total_tokens,
        "sources_used": len(relevant_knowledge) + len(history_results) + (1 if agent_def else 0),
    }


async def main():
    """Run the MCP server."""
    global embedder, store, engine

    logger.info("Starting RAG server. Project root: %s", PROJECT_ROOT)

    # Initialize components (deferred from import time to avoid blocking MCP startup)
    embedder = SentenceTransformerEmbedding(model_name=EMBEDDING_MODEL)
    store = ChromaStore(persist_dir=str(CHROMA_DIR))
    engine = IndexingEngine(embedder=embedder, store=store)

    # Auto-index on startup
    logger.info("Auto-indexing default collections...")
    result = engine.index_all()
    logger.info(
        "Startup indexing complete: %d files, %d chunks",
        result["files_indexed"], result["chunks_created"],
    )

    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
