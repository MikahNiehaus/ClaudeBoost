"""RAG server — HTTP only.

Run modes:
  python -m rag_server --http              HTTP on default port 8612
  python -m rag_server --http --port N     HTTP on custom port
"""

import json
import logging
import os
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

from rag_server.config import (
    CHROMA_DIR,
    CODE_EMBEDDING_MODEL,
    DEFAULT_MIN_SCORE,
    DEFAULT_SEARCH_LIMIT,
    EMBEDDING_MODEL,
    PROJECT_ROOT,
    RAG_INDEX_DIR,
    SCOPES,
)
from rag_server.core.embedding import OnnxDirectMLEmbedding, SentenceTransformerEmbedding
from rag_server.core.store import ChromaStore
from rag_server.core.watcher import FileWatcher
from rag_server.indexing.engine import IndexingEngine
from rag_server.tools.search import rag_search
import rag_server.tools.context as _context_mod

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)

# Components initialized in main(), accessed via module-level refs
from rag_server.ports.embedding_port import EmbeddingPort
embedder: EmbeddingPort | None = None
code_embedder: EmbeddingPort | None = None  # separate model for codebase scope (optional)
store: ChromaStore | None = None
engine: IndexingEngine | None = None   # codebase project indexing (code_embedder)
kb_engine: IndexingEngine | None = None  # knowledge/agents/memories indexing (embedder)


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
            _scope = arguments.get("scope", "all")
            _active_embedder = code_embedder if _scope == "codebase" else embedder
            return rag_search(
                embedder=_active_embedder,
                store=store,
                query=arguments["query"],
                scope=_scope,
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

        elif name == "rag_reset_research":
            from rag_server.tools.research import rag_reset_research
            return rag_reset_research(workspace_path=arguments["workspace_path"])

        elif name == "rag_index_docs":
            if not embedder.is_loaded:
                return {"error": "Embedding model not ready yet. Retry in 30-60 seconds."}
            from rag_server.tools.docs import rag_index_docs
            return rag_index_docs(
                embedder=embedder,
                project_path=arguments["project_path"],
                paths=arguments.get("paths"),
                force=arguments.get("force", False),
            )

        elif name == "rag_index_memories":
            from rag_server.config import MEMORY_DIR
            from rag_server.tools.memory import rag_index_memories
            return rag_index_memories(
                embedder=embedder,
                store=store,
                memory_dir=MEMORY_DIR,
                force=arguments.get("force", False),
            )

        elif name == "rag_index":
            # STOP: fail fast if model isn't loaded — avoids blocking on _load_lock.
            if not embedder.is_loaded:
                return {"error": "Embedding model not ready yet — retry in 30-60 seconds."}
            force = arguments.get("force", False)
            scope = arguments.get("scope", "all")
            if scope == "memories":
                from rag_server.config import MEMORY_DIR
                from rag_server.tools.memory import rag_index_memories
                mem = rag_index_memories(embedder=embedder, store=store, memory_dir=MEMORY_DIR, force=force)
                if "error" in mem:
                    return mem
                result = {
                    "files_indexed": mem.get("indexed", 0),
                    "chunks_created": mem.get("indexed", 0),
                    "files_unchanged": mem.get("skipped", 0),
                    "files_failed": mem.get("failed", 0),
                    "scope": "memories",
                }
            elif scope == "all":
                result = kb_engine.index_all(force=force)
                # memories scope has no file patterns and is skipped by index_all — run separately
                from rag_server.config import MEMORY_DIR
                from rag_server.tools.memory import rag_index_memories
                if MEMORY_DIR:
                    mem = rag_index_memories(embedder=embedder, store=store, memory_dir=MEMORY_DIR, force=force)
                    result["files_indexed"] += mem.get("indexed", 0)
                    result["files_unchanged"] = result.get("files_unchanged", 0) + mem.get("skipped", 0)
                    result["files_failed"] += mem.get("failed", 0)
                result["scope"] = "all"
            else:
                result = kb_engine.index_scope(scope, force=force)
                result["scope"] = scope
            return result

        elif name == "rag_warmup":
            if embedder.is_loaded:
                return {"ready": True, "elapsed_s": 0.0, "model": EMBEDDING_MODEL}
            # Kick off model load immediately (idempotent if already loading).
            from rag_server.tools.search import _ensure_warmup
            _ensure_warmup(embedder)
            _warmup_start = time.monotonic()
            _deadline = _warmup_start + 120.0
            while not embedder.is_loaded and time.monotonic() < _deadline:
                time.sleep(0.5)
            _elapsed = round(time.monotonic() - _warmup_start, 1)
            if embedder.is_loaded:
                return {"ready": True, "elapsed_s": _elapsed, "model": EMBEDDING_MODEL}
            return {
                "ready": False,
                "elapsed_s": _elapsed,
                "error": "Model did not load within 120s — restart the server and retry.",
            }

        elif name == "rag_status":
            # Live model dimension — only if already loaded; never trigger a load here
            # (status must stay sub-second).
            model_dim = embedder.dimensions() if embedder.is_loaded else None
            dimension_mismatch: list[str] = []
            collections_status = {}
            for scope_name, scope_config in SCOPES.items():
                col = scope_config["collection"]
                entry = {
                    "chunks": store.count(col),
                    "files": store.count_sources(col) if store.collection_exists(col) else 0,
                }
                # Flag collections whose stored vectors don't match the active model's
                # dimension. A model swap leaves these unqueryable — searches silently
                # return 0. Only check populated collections, and only once the model is up.
                if model_dim and entry["chunks"] > 0:
                    stored_dim = store.sample_dimension(col)
                    if stored_dim:
                        entry["stored_dim"] = stored_dim
                        entry["dim_ok"] = stored_dim == model_dim
                        if stored_dim != model_dim:
                            dimension_mismatch.append(scope_name)
                collections_status[scope_name] = entry
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
            from rag_server.config import DEVICE
            _main_ready = embedder.is_loaded
            _code_ready = (
                code_embedder is None
                or code_embedder is embedder
                or code_embedder.is_loaded
            )
            status: dict = {
                "status": "ready" if (_main_ready and _code_ready) else "warming_up",
                "project_root": str(PROJECT_ROOT),
                "collections": collections_status,
                "model": EMBEDDING_MODEL,
                "device": DEVICE,
                "embedding_dimensions": model_dim if model_dim else "not loaded yet",
                "dimension_mismatch": dimension_mismatch,
                "indexed_projects": indexed_projects,
            }
            if code_embedder is not None and code_embedder is not embedder:
                status["code_model"] = CODE_EMBEDDING_MODEL
                status["code_model_ready"] = code_embedder.is_loaded
            return status

        elif name == "rag_context":
            return _build_context(
                agent=arguments["agent"],
                task_description=arguments["task_description"],
                max_tokens=arguments.get("max_tokens", 6000),
                weight=arguments.get("weight", "standard"),
                project_path=arguments.get("project_path"),
                workspace_path=arguments.get("workspace_path"),
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
    workspace_path: str | None = None,
) -> dict:
    """Delegate to tools/context.py so changes there hot-reload without a server restart."""
    return _context_mod.build_context(
        agent=agent,
        task_description=task_description,
        max_tokens=max_tokens,
        store=store,
        embedder=embedder,
        code_embedder=code_embedder,
        project_root=PROJECT_ROOT,
        weight=weight,
        project_path=project_path,
        workspace_path=workspace_path,
    )


def sync_init() -> FileWatcher:
    """Synchronous startup: initialize components and wire up watchers.

    Kept deliberately fast — no model loading, no indexing. Those run in a
    background thread after the server is ready (see _background_startup).

    ChromaDB 1.5+ uses a Rust/Tokio backend that crashes when called from
    inside an asyncio coroutine. ChromaDB calls in background tasks must use
    run_in_executor (see main_http()).
    """
    global embedder, code_embedder, store, engine, kb_engine

    logger.info("Starting RAG server. Project root: %s", PROJECT_ROOT)

    # Write heartbeat immediately — guard needs a fresh timestamp before any tool call arrives.
    _write_heartbeat(model_loaded=False, index_ok=False)

    from rag_server.config import DEVICE
    _EmbedCls = OnnxDirectMLEmbedding if DEVICE == "onnx-dml" else SentenceTransformerEmbedding
    embedder = _EmbedCls(model_name=EMBEDDING_MODEL)
    if CODE_EMBEDDING_MODEL and CODE_EMBEDDING_MODEL != EMBEDDING_MODEL:
        logger.info("Code embedding model: %s", CODE_EMBEDDING_MODEL)
        code_embedder = _EmbedCls(model_name=CODE_EMBEDDING_MODEL)
    else:
        code_embedder = embedder  # same model for all scopes

    # Windows fix: force BLAS (PyTorch/MKL) initialization before SQLite opens.
    # ChromaDB's PersistentClient eagerly opens SQLite in __init__. On Windows,
    # BLAS and SQLite conflict if SQLite initializes first — any subsequent
    # embed_query() call causes a segfault (exit code 139). Running a warmup
    # inference here ensures BLAS memory regions are established before SQLite.
    logger.info("Pre-warming embedding model before ChromaDB init...")
    try:
        embedder.embed_query("warmup")
        if code_embedder is not embedder:
            code_embedder.embed_query("warmup")
        logger.info("Embedding model pre-warmed (%dd)", embedder.dimensions())
    except Exception:
        logger.warning(
            "Pre-warm failed — PyTorch/SQLite conflict may still occur on /context calls",
            exc_info=True,
        )

    store = ChromaStore(persist_dir=str(CHROMA_DIR))

    # Language routing: wrap the project indexing engine with a ModelCache so
    # each project gets the best embedding model for its dominant language.
    from rag_server.config import LANG_ROUTING_ENABLED
    _lang_router = None
    if LANG_ROUTING_ENABLED:
        from rag_server.indexing.lang_router import ModelCache
        _lang_router = ModelCache()
        # Seed the cache with the default code embedder so it's reused for
        # CSN-family projects without an extra model load.
        _lang_router._cache[CODE_EMBEDDING_MODEL] = code_embedder
        logger.info("Language routing enabled (RAG_LANG_ROUTING=1)")
    else:
        logger.info("Language routing disabled (RAG_LANG_ROUTING=0)")

    engine = IndexingEngine(embedder=code_embedder, store=store, lang_router=_lang_router)
    kb_engine = IndexingEngine(embedder=embedder, store=store)

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
                kb_engine.index_all()
            except Exception:
                logger.exception("Auto-index failed after file change: %s", path)
        watcher.watch(watch_paths, _on_file_change)
        logger.info("Watcher started for: %s", ", ".join(watch_paths))

    # Hot-reload watcher: reload RAG server source modules when they change so
    # code fixes take effect without restarting the server. Reloads in dependency
    # order and re-binds the engine global so the updated IndexingEngine class is used.
    src_dir = Path(__file__).parent
    if src_dir.is_dir():
        import importlib
        import rag_server.adapters.sqlite_graph_store as _gstore_mod
        import rag_server.adapters.fts_store as _fts_mod
        import rag_server.core.community as _community_mod
        import rag_server.core.summarizer as _summarizer_mod
        import rag_server.indexing.engine as _engine_mod
        import rag_server.tools.search as _search_mod
        import rag_server.tools.context as _ctx_mod

        def _on_source_change(path: str):
            global engine, kb_engine, rag_search, _context_mod
            logger.info("Source changed, hot-reloading modules: %s", path)
            try:
                importlib.reload(_gstore_mod)
                importlib.reload(_fts_mod)
                importlib.reload(_community_mod)
                importlib.reload(_summarizer_mod)
                importlib.reload(_engine_mod)
                importlib.reload(_search_mod)
                importlib.reload(_ctx_mod)
                engine = _engine_mod.IndexingEngine(embedder=code_embedder, store=store, lang_router=_lang_router)
                kb_engine = _engine_mod.IndexingEngine(embedder=embedder, store=store)
                rag_search = _search_mod.rag_search
                _context_mod = _ctx_mod
                logger.info("Hot-reload complete — updated code is now active")
            except Exception:
                logger.exception("Hot-reload failed for %s — still running old code", path)

        watcher.watch([str(src_dir)], _on_source_change)
        logger.info("Source hot-reload watcher active on: %s", src_dir)

    logger.info("Sync init complete — HTTP RAG server ready. Background indexing will start shortly.")
    return watcher


def _background_startup() -> None:
    """Slow startup work that runs in a thread pool after the HTTP server is ready.

    Keeps sync_init() fast so the server can accept requests quickly.
    Must be called via run_in_executor — ChromaDB must not run inside an
    asyncio coroutine.
    """
    # Start heartbeat thread immediately — ticks independently of model load time.
    # Reflect actual model load state here: sync_init() runs warmup before this
    # background thread starts, so the model may already be loaded.
    _write_heartbeat(model_loaded=embedder.is_loaded if embedder else False, index_ok=False)
    _start_heartbeat_thread()

    try:
        # Check for embedding dimension mismatch (e.g. model swap 384d -> 768d).
        # embedder.dimensions() triggers model load here — intentional, but done in
        # a background thread so it doesn't block startup.
        # STOP: never force re-index on dimension mismatch in background startup.
        # A full force re-index holds ChromaDB locked for minutes, blocking all requests
        # (status, search, etc.) and fills the thread pool. Log a warning instead —
        # the user must explicitly trigger a force re-index via POST /index with force=true.
        try:
            for scope_config in SCOPES.values():
                col_name = scope_config["collection"]
                if store.collection_exists(col_name) and store.count(col_name) > 0:
                    sample_dim = store.sample_dimension(col_name)
                    if sample_dim and sample_dim != embedder.dimensions():
                        logger.warning(
                            "DIMENSION MISMATCH in %s: index=%dd, model=%dd. "
                            "Skipping background re-index — run POST /index with force=true or "
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
        result = kb_engine.index_all(force=False)
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
        _write_heartbeat(
            model_loaded=embedder.is_loaded if embedder else False,
            index_ok=True,
        )


RAG_HTTP_PORT = 8612  # SHA256("ClaudeBoost-rag-server") % 900 + 8100


def _heartbeat_path() -> Path:
    return RAG_INDEX_DIR / ".heartbeat"


def _server_info_path() -> Path:
    return RAG_INDEX_DIR / ".server.json"


def _write_heartbeat(model_loaded: bool = False, index_ok: bool = False) -> None:
    try:
        _heartbeat_path().parent.mkdir(parents=True, exist_ok=True)
        _heartbeat_path().write_text(
            json.dumps({"ts": time.time(), "model_loaded": model_loaded, "index_ok": index_ok}),
            encoding="utf-8",
        )
    except Exception as e:
        logger.debug("Heartbeat write failed (non-fatal): %s", e)


def _start_heartbeat_thread() -> None:
    import threading
    def _beat():
        while True:
            time.sleep(30)
            _write_heartbeat(
                model_loaded=embedder.is_loaded if embedder else False,
                index_ok=True,
            )
    t = threading.Thread(target=_beat, daemon=True, name="rag-heartbeat")
    t.start()


def _write_server_info(port: int) -> None:
    import os
    try:
        _server_info_path().parent.mkdir(parents=True, exist_ok=True)
        _server_info_path().write_text(
            json.dumps({"pid": os.getpid(), "port": port, "started_at": time.time()}),
            encoding="utf-8",
        )
    except Exception:
        pass


def _update_project_rag_flag(result: dict) -> None:
    """Update the stale-index head file after a successful /index run."""
    if "files_indexed" in result and "error" not in result:
        try:
            head = subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=str(PROJECT_ROOT), stderr=subprocess.DEVNULL
            ).decode().strip()
            branch = subprocess.check_output(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=str(PROJECT_ROOT), stderr=subprocess.DEVNULL
            ).decode().strip()
            head_file = PROJECT_ROOT / "state" / "last-indexed-head.json"
            head_file.write_text(json.dumps({
                "head": head,
                "branch": branch,
                "indexed_at": datetime.now(timezone.utc).isoformat(),
            }), encoding="utf-8")
        except Exception:
            pass


class _TelemetryMiddleware:
    """ASGI middleware that records every RAG HTTP request to rag-usage.jsonl.

    Catches all callers (hook scripts, agents, external curl) at one point.
    Writes happen in a daemon thread — the response path is never blocked.
    Skipped entirely when DISABLE_TELEMETRY=1.

    db_used is derived from the 'mode' parameter:
      vector  -> ["chroma_vector"]
      graph   -> ["sqlite_graph"]
      both    -> ["chroma_vector", "sqlite_graph"]
      (none)  -> ["chroma_vector"]  (default for /context and unspecified /search)
    """

    # Endpoints worth logging — skip health-check noise like /index/progress
    _LOGGED_PATHS = frozenset([
        "/search", "/context", "/status", "/index",
        "/scan", "/index_research", "/reset_research", "/warmup",
    ])

    def __init__(self, app) -> None:
        self.app = app
        self._disabled = os.environ.get("DISABLE_TELEMETRY", "") == "1"

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http" or self._disabled:
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        if path not in self._LOGGED_PATHS:
            await self.app(scope, receive, send)
            return

        import time
        t0 = time.monotonic()
        method = scope.get("method", "GET")

        # Buffer request body so the route handler can still read it.
        body_parts: list[bytes] = []

        async def buffered_receive():
            msg = await receive()
            if msg.get("type") == "http.request":
                body_parts.append(msg.get("body", b""))
            return msg

        status_holder: list[int] = [200]
        resp_parts: list[bytes] = []

        async def capture_send(msg) -> None:
            if msg["type"] == "http.response.start":
                status_holder[0] = msg.get("status", 200)
            elif msg["type"] == "http.response.body":
                resp_parts.append(msg.get("body", b""))
            await send(msg)

        try:
            await self.app(scope, buffered_receive, capture_send)
        finally:
            try:
                latency_ms = int((time.monotonic() - t0) * 1000)
                import threading
                raw_req = b"".join(body_parts)
                raw_resp = b"".join(resp_parts)
                threading.Thread(
                    target=self._write,
                    args=(path, method, status_holder[0], raw_req, raw_resp, latency_ms),
                    daemon=True,
                ).start()
            except Exception:
                pass  # Telemetry must never interfere with the response path

    @staticmethod
    def _write(path: str, method: str, status: int,
               raw_req: bytes, raw_resp: bytes, latency_ms: int) -> None:
        """Parse and write one rag-usage.jsonl record. Called in background thread."""
        try:
            import hashlib
            import json
            import os
            from datetime import datetime, timezone
            from pathlib import Path

            req = json.loads(raw_req) if raw_req.strip() else {}
            resp = json.loads(raw_resp) if raw_resp.strip() else {}

            scope_val = req.get("scope")
            mode = req.get("mode")
            query = req.get("query") or req.get("task_description")
            project_path = req.get("project_path")

            # Determine which DB backends were hit.
            # /context always uses both — it runs vector search (Tier 4) and graph
            # neighbour expansion (Tier 4b) internally regardless of the 'mode' param.
            if path in ("/status", "/index", "/scan", "/warmup"):
                db_used: list[str] = []
            elif path == "/context":
                db_used = ["chroma_vector", "sqlite_graph"]
            elif mode == "graph":
                db_used = ["sqlite_graph"]
            elif mode == "both":
                db_used = ["chroma_vector", "sqlite_graph"]
            else:
                db_used = ["chroma_vector"]

            # Count chunks returned
            chunks = 0
            if "results" in resp:
                r = resp["results"]
                if isinstance(r, list):
                    chunks = len(r)
                elif isinstance(r, dict):
                    # mode=both: {"vector": {"results": [...]}, "graph": {"results": [...]}}
                    for v in r.values():
                        if isinstance(v, dict):
                            chunks += len(v.get("results", []))

            def _h(text) -> str | None:
                if not text:
                    return None
                return "sha256:" + hashlib.sha256(str(text).encode()).hexdigest()

            def _read_session_id(home: Path) -> str:
                try:
                    return (home / "state" / "session-id.txt").read_text(encoding="utf-8").strip()
                except Exception:
                    return os.environ.get("CLAUDE_SESSION_ID", "unknown")

            # Resolve boost_home here so _read_session_id and the workspace lookup
            # both use the same Path object.
            _env_home = os.environ.get("CLAUDEBOOST_HOME")
            boost_home = Path(_env_home) if _env_home else Path(__file__).resolve().parent.parent.parent.parent

            record = {
                "ts": datetime.now(timezone.utc).isoformat(),
                "session_id": _read_session_id(boost_home),
                "agent_name": req.get("agent"),
                "endpoint": path,
                "method": method,
                "scope": scope_val,
                "mode": mode,
                "query_hash": _h(query),
                "project_path_hash": _h(project_path),
                "db_used": db_used,
                "chunks_returned": chunks,
                "latency_ms": latency_ms,
                "status_code": status,
                "error": resp.get("error") if status >= 400 else None,
            }

            # Fall back to the repo root derived from this file's location when the
            # env var is unset or empty (mirrors the pattern in telemetry-writer.py).
            # (boost_home already set above)
            active_file = boost_home / "state" / "active-workspace.json"
            wp: str | None = None
            try:
                ws_data = json.loads(active_file.read_text(encoding="utf-8"))
                wp = ws_data.get("workspace_path")
            except Exception:
                pass

            if wp:
                tel_dir = Path(wp) / "Telemetry"
                tel_dir.mkdir(parents=True, exist_ok=True)
                target = tel_dir / "rag-usage.jsonl"
            else:
                fallback = boost_home / "state" / "telemetry-unrouted.jsonl"
                fallback.parent.mkdir(parents=True, exist_ok=True)
                target = fallback

            with target.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(record) + "\n")

            # Increment rag_count in session.json via the shared writer so the
            # file lock is respected (prevents races with the PostToolUse hook).
            if wp:
                try:
                    import sys as _sys
                    scripts_dir = boost_home / "scripts"
                    if str(scripts_dir) not in _sys.path:
                        _sys.path.insert(0, str(scripts_dir))
                    from telemetry_writer import update_session_json
                    update_session_json("rag_count")
                except Exception:
                    pass

        except Exception:
            pass  # Never let telemetry crash the server


async def main_http(watcher: FileWatcher, host: str, port: int) -> None:
    """Run the HTTP REST server. Call sync_init() before this."""
    import asyncio
    try:
        from starlette.applications import Starlette
        from starlette.routing import Route
        import uvicorn
    except ImportError as e:
        logger.error(
            "HTTP mode requires starlette and uvicorn. Run: "
            "pip install starlette 'uvicorn[standard]'. Error: %s", e
        )
        raise SystemExit(1)

    async def handle_rest_search(request):
        from starlette.responses import JSONResponse
        if embedder is None or store is None:
            return JSONResponse({"error": "Server is still initializing, retry in a moment."}, status_code=503)
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"error": "Request body must be valid JSON."}, status_code=400)
        result = await asyncio.get_running_loop().run_in_executor(
            None, _dispatch_tool, "rag_search", body
        )
        return JSONResponse(result, status_code=500 if "error" in result else 200)

    async def handle_rest_context(request):
        from starlette.responses import JSONResponse
        if embedder is None or store is None:
            return JSONResponse({"error": "Server is still initializing, retry in a moment."}, status_code=503)
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"error": "Request body must be valid JSON."}, status_code=400)
        if "agent" not in body or "task_description" not in body:
            return JSONResponse({"error": "Required fields: agent, task_description"}, status_code=400)
        result = await asyncio.get_running_loop().run_in_executor(
            None, _dispatch_tool, "rag_context", body
        )
        return JSONResponse(result, status_code=500 if "error" in result else 200)

    async def handle_rest_status(request):
        from starlette.responses import JSONResponse
        if embedder is None or store is None:
            return JSONResponse({"status": "initializing"}, status_code=503)
        result = await asyncio.get_running_loop().run_in_executor(
            None, _dispatch_tool, "rag_status", {}
        )
        return JSONResponse(result)

    async def handle_rest_index(request):
        from starlette.responses import JSONResponse
        if embedder is None or store is None:
            return JSONResponse({"error": "Server is still initializing, retry in a moment."}, status_code=503)
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"error": "Request body must be valid JSON."}, status_code=400)
        if body.get("project_path"):
            # Project codebase index
            result = await asyncio.get_running_loop().run_in_executor(
                None, _dispatch_tool, "rag_index_project", body
            )
            _update_project_rag_flag(result)
        else:
            # Knowledge/agents index (no project_path = index_all)
            result = await asyncio.get_running_loop().run_in_executor(
                None, _dispatch_tool, "rag_index", body
            )
        return JSONResponse(result, status_code=500 if "error" in result else 200)


    async def handle_rest_scan(request):
        from starlette.responses import JSONResponse
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"error": "Request body must be valid JSON."}, status_code=400)
        if not body.get("project_path"):
            return JSONResponse({"error": "project_path is required."}, status_code=400)
        result = await asyncio.get_running_loop().run_in_executor(
            None, _dispatch_tool, "rag_scan", body
        )
        return JSONResponse(result, status_code=500 if "error" in result else 200)

    async def handle_rest_index_research(request):
        from starlette.responses import JSONResponse
        if embedder is None or store is None:
            return JSONResponse({"error": "Server is still initializing, retry in a moment."}, status_code=503)
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"error": "Request body must be valid JSON."}, status_code=400)
        if not body.get("workspace_path"):
            return JSONResponse({"error": "workspace_path is required."}, status_code=400)
        if not body.get("sources") or not isinstance(body.get("sources"), list):
            return JSONResponse({"error": "sources must be a non-empty list."}, status_code=400)
        bad = [s for s in body["sources"] if not isinstance(s, str)]
        if bad:
            return JSONResponse(
                {"error": f"sources must be a list of strings (URLs or file paths). Got non-string items: {bad[:3]}"},
                status_code=400,
            )
        result = await asyncio.get_running_loop().run_in_executor(
            None, _dispatch_tool, "rag_index_research", body
        )
        return JSONResponse(result, status_code=500 if "error" in result else 200)

    async def handle_rest_index_docs(request):
        from starlette.responses import JSONResponse
        if embedder is None or store is None:
            return JSONResponse({"error": "Server is still initializing, retry in a moment."}, status_code=503)
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"error": "Request body must be valid JSON."}, status_code=400)
        if not body.get("project_path"):
            return JSONResponse({"error": "project_path is required."}, status_code=400)
        result = await asyncio.get_running_loop().run_in_executor(
            None, _dispatch_tool, "rag_index_docs", body
        )
        return JSONResponse(result, status_code=500 if "error" in result else 200)

    async def handle_rest_reset_research(request):
        from starlette.responses import JSONResponse
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"error": "Request body must be valid JSON."}, status_code=400)
        if not body.get("workspace_path"):
            return JSONResponse({"error": "workspace_path is required."}, status_code=400)
        result = await asyncio.get_running_loop().run_in_executor(
            None, _dispatch_tool, "rag_reset_research", body
        )
        return JSONResponse(result, status_code=500 if "error" in result else 200)

    async def handle_rest_warmup(request):
        from starlette.responses import JSONResponse
        if embedder is None:
            return JSONResponse({"error": "Server is still initializing, retry in a moment."}, status_code=503)
        result = await asyncio.get_running_loop().run_in_executor(
            None, _dispatch_tool, "rag_warmup", {}
        )
        return JSONResponse(result, status_code=500 if "error" in result else 200)

    async def handle_rest_index_progress(request):
        from starlette.responses import JSONResponse
        import rag_server.indexing.engine as _eng_mod
        return JSONResponse(_eng_mod._progress)

    starlette_app = Starlette(
        routes=[
            Route("/search", endpoint=handle_rest_search, methods=["POST"]),
            Route("/context", endpoint=handle_rest_context, methods=["POST"]),
            Route("/status", endpoint=handle_rest_status, methods=["GET"]),
            Route("/index", endpoint=handle_rest_index, methods=["POST"]),
            Route("/index/progress", endpoint=handle_rest_index_progress, methods=["GET"]),
            Route("/scan", endpoint=handle_rest_scan, methods=["POST"]),
            Route("/index_research", endpoint=handle_rest_index_research, methods=["POST"]),
            Route("/index_docs", endpoint=handle_rest_index_docs, methods=["POST"]),
            Route("/reset_research", endpoint=handle_rest_reset_research, methods=["POST"]),
            Route("/warmup", endpoint=handle_rest_warmup, methods=["POST"]),
        ]
    )

    # Wrap with telemetry middleware — writes rag-usage.jsonl per active workspace.
    # Implemented as ASGI middleware so it catches all callers (hooks, agents, curl)
    # at a single point. Writes happen in a background thread; overhead <1ms on the
    # response path. Skipped entirely when DISABLE_TELEMETRY=1.
    starlette_app = _TelemetryMiddleware(starlette_app)

    # Write server info so rag-server-start.py knows we're up
    _write_server_info(port)

    # Schedule background startup (model load + indexing) once at server start
    loop = asyncio.get_running_loop()
    asyncio.ensure_future(loop.run_in_executor(None, _background_startup))

    logger.info("HTTP RAG server on http://%s:%d", host, port)

    config = uvicorn.Config(
        starlette_app,
        host=host,
        port=port,
        log_level="warning",
        access_log=False,
    )
    server = uvicorn.Server(config)
    try:
        await server.serve()
    finally:
        logger.info("HTTP server stopped")
        watcher.stop()


if __name__ == "__main__":
    import argparse
    import asyncio

    parser = argparse.ArgumentParser(description="ClaudeBoost RAG server")
    parser.add_argument("--host", default="127.0.0.1", help="HTTP bind address (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=RAG_HTTP_PORT, help=f"HTTP port (default: {RAG_HTTP_PORT})")
    args = parser.parse_args()

    _watcher = sync_init()
    try:
        asyncio.run(main_http(_watcher, args.host, args.port))
    except KeyboardInterrupt:
        logger.info("RAG server stopped (KeyboardInterrupt)")
    except Exception:
        logger.exception("RAG server exited with unhandled exception")
        raise
