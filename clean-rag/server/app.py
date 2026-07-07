"""HTTP server for clean-rag. Handles topic/project indexing and search.

Standalone mode: runs on port 8613.
Bundled with ClaudeBoost: routes registered under /clean-rag/* on port 8612.
"""

import asyncio
import json
import logging
import re
import time
import uuid
from datetime import datetime, timezone
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
from .indexing import acquire_index_lock, index_project, index_topic, reindex_file, release_index_lock
from .index_queue import IndexQueue
from .search import search
from verifier.log import write_pending_proof

# acquire_topic is imported lazily to avoid pulling in research deps at startup

logger = logging.getLogger(__name__)

# Server-wide singletons (initialized in create_app)
_embedder: SentenceTransformerEmbedding | None = None
_code_embedder: SentenceTransformerEmbedding | None = None
_start_time: float = 0.0
_index_queue: IndexQueue | None = None


_TOPIC_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


def _get_ram_mb() -> float:
    """Get current process RAM usage in MB."""
    try:
        import psutil
        import os
        return round(psutil.Process(os.getpid()).memory_info().rss / 1024**2, 1)
    except (ImportError, Exception):
        return 0.0


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
        "ram_mb": _get_ram_mb(),
    })


async def handle_search(request: web.Request) -> web.Response:
    """POST /search: search across topics and/or projects.

    Body fields:
        query (str): search query text (required)
        sources (list[str]): source specifiers (default: ["all_topics"])
        limit (int): max results (default: 5)
        min_score (float): minimum similarity score (default: 0.3)
        mode (str): "vector" (default), "graph", or "both"
            Graph mode finds structural neighbors (imports, callers,
            inheritance) of vector-matched files. Only applies to
            project sources; topic sources always use vector.
    """
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
    mode = body.get("mode", "vector")

    if mode not in ("vector", "graph", "both"):
        return _json_response({"error": "mode must be 'vector', 'graph', or 'both'"}, 400)

    if not _embedder or not _code_embedder:
        return _json_response({"error": "Server not initialized"}, 503)

    # Warm up embedders on first search (lazy load)
    loop = asyncio.get_running_loop()
    if not _embedder.is_loaded:
        try:
            await loop.run_in_executor(None, _embedder.embed_query, "warmup")
        except Exception as e:
            logger.exception("Embedding model failed to load")
            return _json_response({"error": f"Embedding model failed to load: {e}"}, 503)

    # Only load code embedder if a project source is requested
    has_project_source = any(s.startswith("project:") for s in sources)
    if has_project_source and not _code_embedder.is_loaded:
        try:
            await loop.run_in_executor(None, _code_embedder.embed_query, "warmup")
        except Exception as e:
            logger.exception("Code embedding model failed to load")
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
            mode=mode,
        ),
    )

    search_id = _log_search(query=query, sources=sources, mode=mode, results=results)

    return _json_response({"results": results, "search_id": search_id})


# ---------------------------------------------------------------------------
# Search log + /prove: independent, server-side proof verification.
#
# write_pending_proof() (verifier/log.py) accepts whatever score/count/angle
# values the caller passes -- verifier/prompts.py:6 documents this as
# intentional ("No separate agent is needed; the mechanical checks... handle
# verification"), but that means a proof's content is entirely self-reported
# by whoever calls it, with no independent check that a claimed score came
# from a real search. _log_search()/handle_prove() close that gap: every real
# /search call is appended to an append-only server-side log the caller can't
# edit, and /prove only accepts search_id references into that log -- it
# looks up the real score/sources itself rather than trusting a client-typed
# number, then calls write_pending_proof() with server-verified values.
# ---------------------------------------------------------------------------

_SEARCH_LOG_PATH = STATE_DIR / "search-log.jsonl"
_SEARCH_LOG_WINDOW_S = 1800  # how long a search_id remains citable in /prove


def _log_search(query: str, sources: list[str], mode: str, results: list[dict]) -> str:
    """Append a real search to the server-side log. Returns the search_id."""
    search_id = uuid.uuid4().hex[:16]
    top_score = max((r.get("score", 0.0) for r in results), default=0.0)
    entry = {
        "search_id": search_id,
        "ts": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "query": query,
        "sources": sources,
        "mode": mode,
        "results_count": len(results),
        "top_score": top_score,
    }
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        with open(_SEARCH_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except OSError:
        logger.exception("Failed to write search-log entry")
    return search_id


def _read_search_log_entries(search_ids: set[str]) -> list[dict]:
    """Read matching, still-fresh entries for the given search_ids."""
    if not _SEARCH_LOG_PATH.exists():
        return []
    now = datetime.now(timezone.utc)
    matched: dict[str, dict] = {}
    with open(_SEARCH_LOG_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            sid = entry.get("search_id")
            if sid not in search_ids:
                continue
            try:
                ts = datetime.fromisoformat(entry["ts"].replace("Z", "+00:00"))
            except (KeyError, ValueError):
                continue
            if (now - ts).total_seconds() > _SEARCH_LOG_WINDOW_S:
                continue
            matched[sid] = entry  # last write for a given id wins
    return list(matched.values())


async def handle_prove(request: web.Request) -> web.Response:
    """POST /prove: write a proof-gate proof from independently-logged searches.

    Body fields:
        file_path (str): file the proof is for (required)
        search_ids (list[str]): search_id values returned by prior /search
            calls (required, >=2, at least one must be from a "project:"
            source -- the codebase angle proof-gate.py requires)
        quality_aspects (list[dict]): [{"aspect":..., "assertion":...}, ...]
            (required, >=2, at least one aspect must be "architecture" or
            "patterns") -- these remain caller-written since they're
            judgment calls about code fit, not measurable search facts.
        note (str): optional extra context appended to verifier_response
    """
    try:
        body = await request.json()
    except Exception:
        return _json_response({"error": "Invalid JSON body"}, 400)

    file_path = body.get("file_path", "").strip()
    if not file_path:
        return _json_response({"error": "Missing 'file_path' field"}, 400)

    search_ids = body.get("search_ids", [])
    if not isinstance(search_ids, list) or len(search_ids) < 2:
        return _json_response(
            {"error": "search_ids must be a list of >=2 real /search search_id values"}, 400
        )

    quality_aspects = body.get("quality_aspects", [])
    if not isinstance(quality_aspects, list) or len(quality_aspects) < 2:
        return _json_response(
            {"error": "quality_aspects must be a list of >=2 {aspect, assertion} entries"}, 400
        )
    macro_aspects = {"architecture", "patterns"}
    if not any(isinstance(q, dict) and q.get("aspect") in macro_aspects for q in quality_aspects):
        return _json_response(
            {"error": "quality_aspects must include at least one aspect='architecture' or 'patterns'"},
            400,
        )

    entries = _read_search_log_entries(set(search_ids))
    if len(entries) < len(set(search_ids)):
        found = {e["search_id"] for e in entries}
        missing = sorted(set(search_ids) - found)
        return _json_response({
            "error": (
                "One or more search_ids were not found in the server's search log, or expired "
                f"(entries older than {_SEARCH_LOG_WINDOW_S}s are no longer citable). "
                "Only search_id values returned by a real POST /search call in the last "
                f"{_SEARCH_LOG_WINDOW_S}s can be cited -- scores/counts are looked up from that "
                "log, not from anything in this request body."
            ),
            "missing_search_ids": missing,
        }, 400)

    research_angles = []
    topics_cited: list[str] = []
    project_cited = False
    for e in entries:
        sources = e.get("sources", [])
        is_codebase = any(str(s).startswith("project:") for s in sources)
        if is_codebase:
            project_cited = True
        angle = "codebase" if is_codebase else "technology"
        research_angles.append({
            "angle": angle,
            "query": e["query"],
            "score": e["top_score"],
        })
        for s in sources:
            s = str(s)
            if s.startswith("topic:"):
                topics_cited.append(s.split(":", 1)[1])

    if not any(a["angle"] == "codebase" for a in research_angles):
        return _json_response({
            "error": (
                "None of the cited search_ids used a 'project:<path>' source. "
                "proof-gate.py requires a codebase angle -- re-run one search with "
                "sources including 'project:<path>' (or Grep the codebase and use the "
                "existing Fast Path if the project isn't indexed), then cite that search_id."
            ),
        }, 400)

    min_score = max((a["score"] for a in research_angles), default=0.0)
    rag_results_count = sum(e.get("results_count", 0) for e in entries)

    note = body.get("note", "")
    verifier_response = (
        f"Server-verified via /prove: {len(entries)} real /search call(s) looked up in "
        f"{_SEARCH_LOG_PATH.name} (not client-supplied). Queries: "
        + "; ".join(f'"{a["query"]}" (angle={a["angle"]}, score={a["score"]:.4f})' for a in research_angles)
        + (f". {note}" if note else "")
    )

    proof_path = write_pending_proof(
        state_dir=str(STATE_DIR),
        file_path=file_path,
        verdict="VERIFIED" if min_score >= DEFAULT_MIN_SCORE else "INSUFFICIENT",
        verifier_response=verifier_response,
        rag_results_count=rag_results_count,
        topics_cited=sorted(set(topics_cited)),
        project_cited=project_cited,
        content_hash="",
        min_score=min_score,
        research_angles=research_angles,
        quality_aspects=quality_aspects,
    )

    if min_score < DEFAULT_MIN_SCORE:
        return _json_response({
            "error": f"Best logged score {min_score:.4f} is below the required {DEFAULT_MIN_SCORE}. "
                     "Proof was written with verdict=INSUFFICIENT and will not pass proof-gate.py.",
            "min_score": min_score,
        }, 400)

    return _json_response({
        "verdict": "VERIFIED",
        "proof_path": str(proof_path),
        "min_score": min_score,
        "rag_results_count": rag_results_count,
        "research_angles": research_angles,
    })


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
    category = body.get("category", None)

    if not _embedder:
        return _json_response({"error": "Server not initialized"}, 503)

    # Prevent concurrent indexing (each index op loads embeddings into RAM)
    if not acquire_index_lock(f"index-topic:{topic}"):
        return _json_response({
            "error": "Another indexing operation is already running. Wait or use /batch-index for sequential queuing.",
        }, 409)

    try:
        # Warm up embedder
        loop = asyncio.get_running_loop()
        if not _embedder.is_loaded:
            try:
                await loop.run_in_executor(None, _embedder.embed_query, "warmup")
            except Exception as e:
                logger.exception("Embedding model failed to load")
                return _json_response({"error": f"Embedding model failed to load: {e}"}, 503)

        result = await loop.run_in_executor(
            None, partial(index_topic, topic, _embedder, force=force, category=category)
        )

        status = 200 if "error" not in result else 400
        return _json_response(result, status)
    finally:
        release_index_lock()


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


async def handle_reindex_file(request: web.Request) -> web.Response:
    """POST /reindex-file: reindex a single changed file within a project.

    Much faster than POST /index-project since it only re-embeds one file.
    Used by the PostToolUse reindex hook to keep the index fresh after edits.
    """
    try:
        body = await request.json()
    except Exception:
        return _json_response({"error": "Invalid JSON body"}, 400)

    project_path = body.get("project_path", "").strip()
    file_path = body.get("file_path", "").strip()

    if not project_path:
        return _json_response({"error": "Missing 'project_path' field"}, 400)
    if not file_path:
        return _json_response({"error": "Missing 'file_path' field"}, 400)

    if not Path(project_path).is_dir():
        return _json_response({"error": f"Project path not found: {project_path}"}, 400)

    if not _code_embedder:
        return _json_response({"error": "Server not initialized"}, 503)

    loop = asyncio.get_running_loop()
    if not _code_embedder.is_loaded:
        try:
            await loop.run_in_executor(None, _code_embedder.embed_query, "warmup")
        except Exception as e:
            return _json_response({"error": f"Code embedding model failed to load: {e}"}, 503)

    result = await loop.run_in_executor(
        None, partial(reindex_file, project_path, file_path, _code_embedder)
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


async def handle_register_project(request: web.Request) -> web.Response:
    """POST /register-project: register an externally indexed project.

    Called by /index-project skill after indexing on ClaudeBoost RAG (port 8612)
    so clean-rag tracks all RAG databases system wide.

    Body fields:
        project_path (str): absolute path to the project (required)
        source (str): which RAG system indexed it, e.g. "claudeboost-rag" (required)
        server (str): base URL of the RAG server, e.g. "http://127.0.0.1:8612"
        files_indexed (int): number of files indexed
        chunks_created (int): number of chunks created
        graph (dict): optional graph stats
    """
    try:
        body = await request.json()
    except Exception:
        return _json_response({"error": "Invalid JSON body"}, 400)

    project_path = body.get("project_path", "").strip()
    if not project_path:
        return _json_response({"error": "Missing 'project_path' field"}, 400)

    source = body.get("source", "").strip()
    if not source:
        return _json_response({"error": "Missing 'source' field"}, 400)

    import hashlib
    from datetime import datetime, timezone
    norm_path = project_path.replace("\\", "/").rstrip("/").lower()
    pid = f"ext_{hashlib.md5(norm_path.encode()).hexdigest()[:12]}"

    registry = _list_projects()
    entry = {
        "project_path": project_path.replace("\\", "/").rstrip("/"),
        "source": source,
        "registered_at": datetime.now(timezone.utc).isoformat(),
    }
    if body.get("server"):
        entry["server"] = body["server"]
    if body.get("files_indexed") is not None:
        entry["files_indexed"] = body["files_indexed"]
    if body.get("chunks_created") is not None:
        entry["chunks_created"] = body["chunks_created"]
    if body.get("graph"):
        entry["graph"] = body["graph"]

    registry[pid] = entry

    registry_path = STATE_DIR / "projects.json"
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text(json.dumps(registry, indent=2), encoding="utf-8")

    logger.info("Registered external project: %s (source=%s, id=%s)", project_path, source, pid)
    return _json_response({"registered": pid, "project_path": entry["project_path"], "source": source})


async def handle_queue_status(request: web.Request) -> web.Response:
    """GET /queue: show the acquire-topic index queue state."""
    if not _index_queue:
        return _json_response({"error": "Queue not initialized"}, 503)
    return _json_response(_index_queue.status())


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

    category = body.get("category", None)

    try:
        from research.acquire import acquire_topic
    except ImportError:
        return _json_response(
            {"error": "Research module not available. Install clean-rag dependencies."},
            503,
        )

    loop = asyncio.get_running_loop()
    try:
        result = await loop.run_in_executor(
            None, partial(acquire_topic, topic, category=category)
        )
    except Exception as e:
        logger.error("acquire_topic(%s) failed: %s", topic, e)
        return _json_response({"error": f"Acquisition failed: {e}"}, 500)

    # Queue indexing so parallel acquire calls process one at a time
    if result.get("files_acquired", 0) > 0 and _index_queue:
        idx_status = _index_queue.submit(topic, category=category, force=True)
        result["index"] = idx_status

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


async def handle_batch_index(request: web.Request) -> web.Response:
    """POST /batch-index: index multiple topics sequentially with memory management.

    Body fields:
        topics (list[str]): topic names to index (required)
        force (bool): force reindex (default: false)
        category (str|null): optional category for all topics

    Uses process lock to prevent concurrent bulk indexing (the 8 GB RAM issue).
    Runs GC between each topic to keep memory bounded.
    """
    try:
        body = await request.json()
    except Exception:
        return _json_response({"error": "Invalid JSON body"}, 400)

    topics = body.get("topics", [])
    if not topics:
        return _json_response({"error": "Missing 'topics' list"}, 400)

    force = body.get("force", False)
    category = body.get("category", None)

    if not _embedder:
        return _json_response({"error": "Server not initialized"}, 503)

    # Acquire process lock
    if not acquire_index_lock("batch-index"):
        return _json_response({
            "error": "Another indexing operation is already running. Wait or kill the other process.",
        }, 409)

    loop = asyncio.get_running_loop()

    # Warm up embedder
    if not _embedder.is_loaded:
        try:
            await loop.run_in_executor(None, _embedder.embed_query, "warmup")
        except Exception as e:
            logger.exception("Embedding model failed to load")
            release_index_lock()
            return _json_response({"error": f"Embedding model failed to load: {e}"}, 503)

    results = []
    try:
        for topic in topics:
            err = _validate_topic_name(topic)
            if err:
                results.append({"topic": topic, "error": err})
                continue

            try:
                result = await loop.run_in_executor(
                    None, partial(index_topic, topic, _embedder, force=force, category=category)
                )
                results.append(result)
            except Exception as e:
                results.append({"topic": topic, "error": str(e)})
    finally:
        release_index_lock()

    succeeded = sum(1 for r in results if "error" not in r)
    failed = sum(1 for r in results if "error" in r)
    total_chunks = sum(r.get("chunks_created", 0) for r in results)
    return _json_response({
        "topics_indexed": succeeded,
        "topics_failed": failed,
        "total_chunks": total_chunks,
        "results": results,
    })


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

async def _on_shutdown(app: web.Application) -> None:
    """Clean up queue worker and ChromaDB clients on shutdown."""
    if _index_queue:
        await _index_queue.stop()
    from .store import ChromaStore
    ChromaStore.clear_cache()
    logger.info("ChromaDB client cache cleared")


def create_app() -> web.Application:
    """Create and configure the aiohttp application."""
    global _embedder, _code_embedder, _start_time, _index_queue

    _start_time = time.time()

    # Create embedders (lazy-loaded, actual model download happens on first use)
    _embedder = SentenceTransformerEmbedding(model_name=EMBEDDING_MODEL)
    _code_embedder = SentenceTransformerEmbedding(model_name=CODE_EMBEDDING_MODEL)

    # Create index queue (worker starts after the event loop is running)
    _index_queue = IndexQueue()

    # Ensure state directory exists
    STATE_DIR.mkdir(parents=True, exist_ok=True)

    async def _on_startup(app: web.Application) -> None:
        """Start the index queue worker once the event loop is running.

        Also warms up both embedders here, synchronously, before the server
        starts accepting connections. sentence-transformers' first import is
        not thread-safe (github.com/huggingface/sentence-transformers/issues/2313);
        loading it lazily from a request-handling executor thread races with
        that first import and intermittently raises "attempted relative import
        with no known parent package". aiohttp awaits on_startup handlers to
        completion before opening the listening socket, so doing it here is
        guaranteed single-threaded and race-free.
        """
        _index_queue.start(_embedder)
        loop = asyncio.get_running_loop()
        try:
            await loop.run_in_executor(None, _embedder.embed_query, "warmup")
            await loop.run_in_executor(None, _code_embedder.embed_query, "warmup")
            logger.info("Embedders warmed up at startup")
        except Exception:
            logger.exception("Embedder warmup failed at startup")

    app = web.Application()
    app.router.add_get("/status", handle_status)
    app.router.add_post("/search", handle_search)
    app.router.add_post("/prove", handle_prove)
    app.router.add_post("/index-topic", handle_index_topic)
    app.router.add_post("/index-project", handle_index_project)
    app.router.add_post("/reindex-file", handle_reindex_file)
    app.router.add_get("/topics", handle_topics)
    app.router.add_delete("/topics/{name}", handle_delete_topic)
    app.router.add_get("/projects", handle_projects)
    app.router.add_post("/register-project", handle_register_project)
    app.router.add_post("/acquire-topic", handle_acquire_topic)
    app.router.add_post("/batch-index", handle_batch_index)
    app.router.add_get("/queue", handle_queue_status)
    app.on_startup.append(_on_startup)
    app.on_shutdown.append(_on_shutdown)

    logger.info("clean-rag server configured (port %d)", STANDALONE_PORT)
    return app


def run_server() -> None:
    """Start the standalone HTTP server."""
    from logging.handlers import RotatingFileHandler

    log_format = "%(asctime)s [%(name)s] %(levelname)s: %(message)s"
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    file_handler = RotatingFileHandler(
        STATE_DIR / "server.log", maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(logging.Formatter(log_format))
    logging.basicConfig(
        level=logging.INFO,
        format=log_format,
        handlers=[logging.StreamHandler(), file_handler],
    )
    app = create_app()
    logger.info("Starting clean-rag server on http://127.0.0.1:%d", STANDALONE_PORT)
    web.run_app(app, host="127.0.0.1", port=STANDALONE_PORT, print=None)
