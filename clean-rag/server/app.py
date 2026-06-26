"""HTTP server for clean-rag. Handles topic/project indexing and search.

Standalone mode: runs on port 8613.
Bundled with ClaudeBoost: routes registered under /clean-rag/* on port 8612.
"""

import asyncio
import json
import logging
import re
import time
from functools import partial
from pathlib import Path

from aiohttp import web

from .config import (
    CLEAN_RAG_HOME,
    DATABASES_DIR,
    DEFAULT_MIN_SCORE,
    DEFAULT_SEARCH_LIMIT,
    KNOWLEDGE_DIR,
    STANDALONE_PORT,
    STATE_DIR,
    CODE_EMBEDDING_MODEL,
    EMBEDDING_MODEL,
)
from .embedding import SentenceTransformerEmbedding
from .indexing import index_project, index_topic
from .search import search

# acquire_topic is imported lazily to avoid pulling in research deps at startup

logger = logging.getLogger(__name__)

# Server-wide singletons (initialized in create_app)
_embedder: SentenceTransformerEmbedding | None = None
_code_embedder: SentenceTransformerEmbedding | None = None
_start_time: float = 0.0


_TOPIC_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


def _validate_topic_name(name: str) -> str | None:
    """Return an error message if topic name is invalid, None if OK."""
    if not name:
        return "Missing topic name"
    if len(name) > 64:
        return "Topic name too long (max 64 chars)"
    if not _TOPIC_NAME_RE.match(name):
        return "Topic name must be lowercase alphanumeric, hyphens, or underscores"
    return None


def _json_response(data: dict, status: int = 200) -> web.Response:
    return web.Response(
        text=json.dumps(data, indent=2),
        content_type="application/json",
        status=status,
    )


# ---------------------------------------------------------------------------
# Route handlers
# ---------------------------------------------------------------------------

async def handle_status(request: web.Request) -> web.Response:
    """GET /status: server health, model status, topic count."""
    topics = _list_topics()
    projects = _list_projects()

    return _json_response({
        "status": "ready" if _embedder and _embedder.is_loaded else "warming_up",
        "uptime_s": round(time.time() - _start_time, 1),
        "embedding_model": EMBEDDING_MODEL,
        "code_embedding_model": CODE_EMBEDDING_MODEL,
        "embedding_loaded": _embedder.is_loaded if _embedder else False,
        "code_embedding_loaded": _code_embedder.is_loaded if _code_embedder else False,
        "topics": {
            "count": len(topics),
            "names": list(topics.keys()),
        },
        "projects": {
            "count": len(projects),
            "entries": projects,
        },
        "clean_rag_home": str(CLEAN_RAG_HOME),
    })


async def handle_search(request: web.Request) -> web.Response:
    """POST /search: search across topics and/or projects."""
    try:
        body = await request.json()
    except Exception:
        return _json_response({"error": "Invalid JSON body"}, 400)

    query = body.get("query", "").strip()
    if not query:
        return _json_response({"error": "Missing 'query' field"}, 400)

    sources = body.get("sources", ["all_topics"])
    limit = body.get("limit", DEFAULT_SEARCH_LIMIT)
    min_score = body.get("min_score", DEFAULT_MIN_SCORE)

    if not _embedder or not _code_embedder:
        return _json_response({"error": "Server not initialized"}, 503)

    # Warm up embedders on first search (lazy load)
    loop = asyncio.get_running_loop()
    if not _embedder.is_loaded:
        try:
            await loop.run_in_executor(None, _embedder.embed_query, "warmup")
        except Exception as e:
            return _json_response({"error": f"Embedding model failed to load: {e}"}, 503)

    # Only load code embedder if a project source is requested
    has_project_source = any(s.startswith("project:") for s in sources)
    if has_project_source and not _code_embedder.is_loaded:
        try:
            await loop.run_in_executor(None, _code_embedder.embed_query, "warmup")
        except Exception as e:
            return _json_response({"error": f"Code embedding model failed to load: {e}"}, 503)

    results = await loop.run_in_executor(
        None,
        partial(
            search,
            query=query,
            sources=sources,
            embedder=_embedder,
            code_embedder=_code_embedder,
            limit=limit,
            min_score=min_score,
        ),
    )

    return _json_response({"results": results})


async def handle_index_topic(request: web.Request) -> web.Response:
    """POST /index-topic: index a topic's knowledge files."""
    try:
        body = await request.json()
    except Exception:
        return _json_response({"error": "Invalid JSON body"}, 400)

    topic = body.get("topic", "").strip()
    err = _validate_topic_name(topic)
    if err:
        return _json_response({"error": err}, 400)

    force = body.get("force", False)

    if not _embedder:
        return _json_response({"error": "Server not initialized"}, 503)

    # Warm up embedder
    loop = asyncio.get_running_loop()
    if not _embedder.is_loaded:
        try:
            await loop.run_in_executor(None, _embedder.embed_query, "warmup")
        except Exception as e:
            return _json_response({"error": f"Embedding model failed to load: {e}"}, 503)

    result = await loop.run_in_executor(
        None, partial(index_topic, topic, _embedder, force=force)
    )

    status = 200 if "error" not in result else 400
    return _json_response(result, status)


async def handle_index_project(request: web.Request) -> web.Response:
    """POST /index-project: index a project's source code."""
    try:
        body = await request.json()
    except Exception:
        return _json_response({"error": "Invalid JSON body"}, 400)

    project_path = body.get("project_path", "").strip()
    if not project_path:
        return _json_response({"error": "Missing 'project_path' field"}, 400)

    if not Path(project_path).is_dir():
        return _json_response({"error": f"Project path not found: {project_path}"}, 400)

    force = body.get("force", False)

    if not _code_embedder:
        return _json_response({"error": "Server not initialized"}, 503)

    loop = asyncio.get_running_loop()
    if not _code_embedder.is_loaded:
        try:
            await loop.run_in_executor(None, _code_embedder.embed_query, "warmup")
        except Exception as e:
            return _json_response({"error": f"Code embedding model failed to load: {e}"}, 503)

    result = await loop.run_in_executor(
        None, partial(index_project, project_path, _code_embedder, force=force)
    )

    status = 200 if "error" not in result else 400
    return _json_response(result, status)


async def handle_topics(request: web.Request) -> web.Response:
    """GET /topics: list all topic databases with stats."""
    topics = _list_topics()
    return _json_response({"topics": topics})


async def handle_delete_topic(request: web.Request) -> web.Response:
    """DELETE /topics/{name}: delete a topic database."""
    import gc
    import shutil

    topic = request.match_info["name"]
    err = _validate_topic_name(topic)
    if err:
        return _json_response({"error": err}, 400)

    topic_db_dir = DATABASES_DIR / topic
    topic_kb_dir = KNOWLEDGE_DIR / topic

    deleted = []

    if topic_db_dir.exists():
        # Evict ChromaDB cache before deleting
        chroma_dir = topic_db_dir / "chroma"
        if chroma_dir.exists():
            from .store import ChromaStore
            ChromaStore.evict_cache(str(chroma_dir))
            gc.collect()

        shutil.rmtree(topic_db_dir, ignore_errors=True)
        deleted.append("database")

    if topic_kb_dir.exists():
        shutil.rmtree(topic_kb_dir, ignore_errors=True)
        deleted.append("knowledge")

    # Remove from registry
    registry_path = STATE_DIR / "topics.json"
    if registry_path.exists():
        try:
            registry = json.loads(registry_path.read_text(encoding="utf-8"))
            if topic in registry:
                del registry[topic]
                registry_path.write_text(json.dumps(registry, indent=2), encoding="utf-8")
        except Exception as e:
            logger.warning("Failed to update topic registry after delete: %s", e)

    if not deleted:
        return _json_response({"error": f"Topic '{topic}' not found"}, 404)

    return _json_response({"deleted": topic, "removed": deleted})


async def handle_projects(request: web.Request) -> web.Response:
    """GET /projects: list indexed projects."""
    projects = _list_projects()
    return _json_response({"projects": projects})


async def handle_acquire_topic(request: web.Request) -> web.Response:
    """POST /acquire-topic: run auto-research to acquire docs for a topic."""
    try:
        body = await request.json()
    except Exception:
        return _json_response({"error": "Invalid JSON body"}, 400)

    topic = body.get("topic", "").strip()
    err = _validate_topic_name(topic)
    if err:
        return _json_response({"error": err}, 400)

    try:
        from research.acquire import acquire_topic
    except ImportError:
        return _json_response(
            {"error": "Research module not available. Install clean-rag dependencies."},
            503,
        )

    loop = asyncio.get_running_loop()
    try:
        result = await loop.run_in_executor(None, partial(acquire_topic, topic))
    except Exception as e:
        logger.error("acquire_topic(%s) failed: %s", topic, e)
        return _json_response({"error": f"Acquisition failed: {e}"}, 500)

    # Auto-index if files were acquired
    if result.get("files_acquired", 0) > 0 and _embedder:
        if not _embedder.is_loaded:
            try:
                await loop.run_in_executor(None, _embedder.embed_query, "warmup")
            except Exception as e:
                logger.warning("Embedder warmup failed after acquisition: %s", e)
        if _embedder.is_loaded:
            idx_result = await loop.run_in_executor(
                None, partial(index_topic, topic, _embedder, force=True)
            )
            result["index"] = idx_result

    return _json_response(result)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _list_topics() -> dict:
    """Read topic registry from state/topics.json."""
    registry_path = STATE_DIR / "topics.json"
    if not registry_path.exists():
        return {}
    try:
        return json.loads(registry_path.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning("Failed to read topic registry: %s", e)
        return {}


def _list_projects() -> dict:
    """Read project registry from state/projects.json."""
    registry_path = STATE_DIR / "projects.json"
    if not registry_path.exists():
        return {}
    try:
        return json.loads(registry_path.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning("Failed to read project registry: %s", e)
        return {}


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

async def _on_shutdown(app: web.Application) -> None:
    """Clean up ChromaDB clients on shutdown."""
    from .store import ChromaStore
    ChromaStore.clear_cache()
    logger.info("ChromaDB client cache cleared")


def create_app() -> web.Application:
    """Create and configure the aiohttp application."""
    global _embedder, _code_embedder, _start_time

    _start_time = time.time()

    # Create embedders (lazy-loaded, actual model download happens on first use)
    _embedder = SentenceTransformerEmbedding(model_name=EMBEDDING_MODEL)
    _code_embedder = SentenceTransformerEmbedding(model_name=CODE_EMBEDDING_MODEL)

    # Ensure state directory exists
    STATE_DIR.mkdir(parents=True, exist_ok=True)

    app = web.Application()
    app.router.add_get("/status", handle_status)
    app.router.add_post("/search", handle_search)
    app.router.add_post("/index-topic", handle_index_topic)
    app.router.add_post("/index-project", handle_index_project)
    app.router.add_get("/topics", handle_topics)
    app.router.add_delete("/topics/{name}", handle_delete_topic)
    app.router.add_get("/projects", handle_projects)
    app.router.add_post("/acquire-topic", handle_acquire_topic)
    app.on_shutdown.append(_on_shutdown)

    logger.info("clean-rag server configured (port %d)", STANDALONE_PORT)
    return app


def run_server() -> None:
    """Start the standalone HTTP server."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )
    app = create_app()
    logger.info("Starting clean-rag server on http://127.0.0.1:%d", STANDALONE_PORT)
    web.run_app(app, host="127.0.0.1", port=STANDALONE_PORT, print=None)
