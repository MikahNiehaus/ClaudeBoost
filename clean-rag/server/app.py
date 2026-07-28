"""HTTP server for clean-rag. Handles project indexing and search.

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
    DEFAULT_MIN_SCORE,
    DEFAULT_SEARCH_LIMIT,
    STANDALONE_PORT,
    STATE_DIR,
    CODE_EMBEDDING_MODEL,
    WEB_SEARCH_ENABLED,
    WEB_SEARCH_TIMEOUT,
    WEB_SEARCH_MAX_RESULTS,
    WEB_SEARCH_SCORE_THRESHOLD,
)
from .embedding import SentenceTransformerEmbedding
from .lang_router import ModelCache
from .github_search import github_fetch_file, github_search
from .graphrag_client import build as graphrag_build, query as graphrag_query, status as graphrag_status
from .indexing import acquire_index_lock, index_project, reindex_file, release_index_lock
from .mutation import run_mutation
from .security import run_security_scan
from .search import search
from .stackexchange import stackoverflow_search
from .wikipedia import wikipedia_search

logger = logging.getLogger(__name__)

# Server-wide singletons (initialized in create_app)
_model_cache: ModelCache | None = None
_doc_embedder: SentenceTransformerEmbedding | None = None
_start_time: float = 0.0

# Heartbeat: writes a JSON file every 30s so the supervisor (and health checks)
# can detect a stuck process without HTTP calls.
_HEARTBEAT_PATH = STATE_DIR / ".heartbeat"
_HEARTBEAT_INTERVAL_S = 30


def _write_heartbeat(model_loaded: bool = False, index_ok: bool = False) -> None:
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        _HEARTBEAT_PATH.write_text(
            json.dumps({"ts": time.time(), "model_loaded": model_loaded, "index_ok": index_ok}),
            encoding="utf-8",
        )
    except Exception:
        logger.debug("Heartbeat write failed (not fatal)", exc_info=True)


def _start_heartbeat_thread() -> None:
    import threading

    def _beat():
        while True:
            time.sleep(_HEARTBEAT_INTERVAL_S)
            _write_heartbeat(
                model_loaded=_model_cache is not None and len(_model_cache) > 0,
                index_ok=True,
            )

    t = threading.Thread(target=_beat, daemon=True, name="clean-rag-heartbeat")
    t.start()


def _get_ram_mb() -> float:
    """Get current process RAM usage in MB."""
    try:
        import psutil
        import os
        return round(psutil.Process(os.getpid()).memory_info().rss / 1024**2, 1)
    except (ImportError, Exception):
        return 0.0


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
    """GET /status: server health, model status, indexed projects."""
    projects = _list_projects()

    return _json_response({
        "status": "ready" if _model_cache and len(_model_cache) > 0 else "warming_up",
        "uptime_s": round(time.time() - _start_time, 1),
        "code_embedding_model": CODE_EMBEDDING_MODEL,
        "code_embedding_loaded": len(_model_cache) > 0 if _model_cache else False,
        "loaded_models": _model_cache.loaded_models() if _model_cache else [],
        "projects": {
            "count": len(projects),
            "entries": projects,
        },
        "clean_rag_home": str(CLEAN_RAG_HOME),
        "ram_mb": _get_ram_mb(),
    })


async def handle_search(request: web.Request) -> web.Response:
    """POST /search: search across indexed projects.

    Body fields:
        query (str): search query text (required)
        sources (list[str]): source specifiers, e.g. ["project:<path>"] (required)
        limit (int): max results (default: 5)
        min_score (float): minimum similarity score (default: 0.3)
        mode (str): "vector" (default), "graph", or "both"
            Graph mode finds structural neighbors (imports, callers,
            inheritance) of vector-matched files.
        depth (int): graph traversal depth, 1-5 (default 2). Only applies
            to mode="graph"/"both".
        direction (str): "both" (default), "callers" (blast-radius
            direction -- files that depend on/call/import the seed), or
            "dependencies" (files the seed depends on). Only applies to
            mode="graph"/"both".
    """
    try:
        body = await request.json()
    except Exception:
        return _json_response({"error": "Invalid JSON body"}, 400)

    query = body.get("query", "").strip()
    if not query:
        return _json_response({"error": "Missing 'query' field"}, 400)

    sources = body.get("sources", [])
    limit = body.get("limit", DEFAULT_SEARCH_LIMIT)
    min_score = body.get("min_score", DEFAULT_MIN_SCORE)
    mode = body.get("mode", "vector")
    depth = body.get("depth", 2)
    direction = body.get("direction", "both")

    if mode not in ("vector", "graph", "both"):
        return _json_response({"error": "mode must be 'vector', 'graph', or 'both'"}, 400)

    if not isinstance(depth, int) or not (1 <= depth <= 5):
        return _json_response({"error": "depth must be an integer 1-5"}, 400)

    if direction not in ("both", "callers", "dependencies"):
        return _json_response(
            {"error": "direction must be 'both', 'callers', or 'dependencies'"}, 400,
        )

    if not _model_cache:
        return _json_response({"error": "Server not initialized"}, 503)

    # Get the default code embedder for query embedding
    loop = asyncio.get_running_loop()
    try:
        _code_embedder = _model_cache.get(CODE_EMBEDDING_MODEL)
    except Exception as e:
        logger.exception("Code embedding model failed to load")
        return _json_response({"error": f"Code embedding model failed to load: {e}"}, 503)

    # docs: sources need the separate prose embedder, warmed up the same way,
    # only when one is actually present so a pure project: search never pays
    # for a model it doesn't use.
    if any(s.startswith("docs:") for s in sources) and _doc_embedder and not _doc_embedder.is_loaded:
        try:
            await loop.run_in_executor(None, _doc_embedder.embed_query, "warmup")
        except Exception as e:
            logger.exception("Docs embedding model failed to load")
            return _json_response({"error": f"Docs embedding model failed to load: {e}"}, 503)

    graph_meta: dict = {}
    results = await loop.run_in_executor(
        None,
        partial(
            search,
            query=query,
            sources=sources,
            code_embedder=_code_embedder,
            limit=limit,
            min_score=min_score,
            mode=mode,
            meta_out=graph_meta,
            depth=depth,
            direction=direction,
            doc_embedder=_doc_embedder,
        ),
    )

    search_id = _log_search(query=query, sources=sources, mode=mode, results=results, graph_meta=graph_meta)

    # Check if fallback web search is needed (low scores or no results)
    top_score = max((r.get("score", 0.0) for r in results), default=0.0)
    fallback_triggered = False
    web_search_results = []

    if WEB_SEARCH_ENABLED and (len(results) == 0 or top_score < WEB_SEARCH_SCORE_THRESHOLD):
        # Trigger web search as fallback
        from .web_search import web_search
        web_result = web_search(query, max_results=WEB_SEARCH_MAX_RESULTS, timeout=WEB_SEARCH_TIMEOUT)
        if web_result.get("results"):
            web_search_results = web_result["results"]
            fallback_triggered = True
            logger.info("Web search fallback triggered for query: %s (score=%.2f)", query, top_score)
            # Background indexing on fallback deprecated: casual conversational
            # queries were triggering this fallback and getting permanently
            # written into the KB (confirmed real pollution — medical
            # content indexed from a message using "injection" in the RAG
            # sense, among others). Web results still returned for this
            # call, just no longer auto-indexed.

    response = {
        "results": results,
        "search_id": search_id,
        "fallback_triggered": fallback_triggered,
    }

    if web_search_results:
        response["web_search_results"] = web_search_results

    return _json_response(response)


# ---------------------------------------------------------------------------
# Search log: append-only record of every real /search call.
#
# Read by scripts/verify-session-proof.py as the session-activity signal, and
# written to directly by hooks/graph-context-inject.py.
# ---------------------------------------------------------------------------

_SEARCH_LOG_PATH = STATE_DIR / "search-log.jsonl"


def _log_search(
    query: str, sources: list[str], mode: str, results: list[dict],
    graph_meta: dict | None = None,
) -> str:
    """Append a real search to the server-side log. Returns the search_id.

    The log is the session-activity signal scripts/verify-session-proof.py
    reads, and hooks/graph-context-inject.py appends entries in this same
    shape. graph_meta (from search()'s meta_out) records whether a
    mode=graph/both search actually found real graph neighbors, not just
    whether graph mode was requested -- see _search_project_graph()'s
    docstring (search.py) for what graph_status "absent"/"empty"/"hit" mean.
    """
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
    if graph_meta:
        entry["graph_status"] = graph_meta.get("graph_status")
        entry["graph_hit_count"] = graph_meta.get("graph_hit_count", 0)
        entry["caller_count"] = graph_meta.get("caller_count", 0)
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        with open(_SEARCH_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except OSError:
        logger.exception("Failed to write search-log entry")
    return search_id


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

    if not _model_cache:
        return _json_response({"error": "Server not initialized"}, 503)

    if not acquire_index_lock("index-project"):
        return _json_response({"error": "Index busy, retry in a moment"}, 423)

    loop = asyncio.get_running_loop()
    try:
        result = await loop.run_in_executor(
            None, partial(index_project, project_path, _model_cache, force=force)
        )
    finally:
        release_index_lock()

    status = 200 if "error" not in result else 400
    return _json_response(result, status)


async def handle_docs_ingest(request: web.Request) -> web.Response:
    """POST /docs-ingest: fetch, chunk, citation tag, and store official
    document sources under a persistent topic, searchable afterward via
    POST /search with sources: ["docs:<topic>"].

    Body fields:
        topic (str): topic name, e.g. "medical-debt-law" (required)
        sources (list[dict]): each entry:
            source_id (str): stable id for this source, e.g. a URL (required)
            type (str): "ecfr" or "html" (required)
            heading_pattern (str): regex identifying a citation heading line
                (required)
            citation_prefix (str): jurisdiction/code prefix, e.g.
                "Tex. Fin. Code" or "45 CFR" (required)
            jurisdiction (str): e.g. "Texas" or "Federal" (required)
            url (str): source URL, required for type "html"
            title (int), date (str), section (str, optional): required for
                type "ecfr"
        force (bool): re ingest even if content hash is unchanged
    """
    try:
        body = await request.json()
    except Exception:
        return _json_response({"error": "Invalid JSON body"}, 400)

    topic = body.get("topic", "").strip()
    if not topic:
        return _json_response({"error": "Missing 'topic' field"}, 400)

    source_entries = body.get("sources", [])
    if not source_entries or not isinstance(source_entries, list):
        return _json_response({"error": "'sources' must be a non empty list"}, 400)

    force = body.get("force", False)

    if not _doc_embedder:
        return _json_response({"error": "Server not initialized"}, 503)

    loop = asyncio.get_running_loop()
    if not _doc_embedder.is_loaded:
        try:
            await loop.run_in_executor(None, _doc_embedder.embed_query, "warmup")
        except Exception as e:
            return _json_response({"error": f"Docs embedding model failed to load: {e}"}, 503)

    from .docs_chunker import heading_pattern_matches
    from .docs_fetch import fetch_ecfr_section, fetch_html_as_text
    from .docs_store import ingest_source

    results = []
    for entry in source_entries:
        source_id = entry.get("source_id", "").strip()
        source_type = entry.get("type", "").strip()
        heading_pattern = entry.get("heading_pattern", "")
        citation_prefix = entry.get("citation_prefix", "")
        jurisdiction = entry.get("jurisdiction", "")

        if not all([source_id, source_type, heading_pattern, citation_prefix, jurisdiction]):
            results.append({"source_id": source_id or "?", "error": "missing required field(s)"})
            continue

        # Validate the caller-supplied heading regex once, up front. A malformed
        # pattern otherwise raises an uncaught re.error later (in
        # heading_pattern_matches for html, or in chunk_by_heading for any
        # source type), which propagates as a request-wide 500 and aborts every
        # other well-formed source in the batch. Surface it as a scoped
        # per-source error instead, same shape as the other validation failures.
        try:
            re.compile(heading_pattern)
        except re.error as e:
            results.append({
                "source_id": source_id,
                "error": f"invalid heading_pattern regex ({heading_pattern!r}): {e}",
            })
            continue

        if source_type == "ecfr":
            title = entry.get("title")
            date = entry.get("date", "")
            section = entry.get("section")
            if not title or not date:
                results.append({"source_id": source_id, "error": "ecfr source needs title and date"})
                continue
            text = await loop.run_in_executor(
                None, partial(fetch_ecfr_section, title, date, section)
            )
            source_url = f"https://www.ecfr.gov/current/title-{title}"
        elif source_type == "html":
            url = entry.get("url", "")
            if not url:
                results.append({"source_id": source_id, "error": "html source needs url"})
                continue
            text = await loop.run_in_executor(None, partial(fetch_html_as_text, url))
            source_url = url
        else:
            results.append({"source_id": source_id, "error": f"unknown type {source_type!r}"})
            continue

        if not text:
            results.append({"source_id": source_id, "error": "fetch returned no content"})
            continue

        # Content-sanity check for html sources: a non-empty fetch can still be
        # junk (a JS-rendered shell returns its nav chrome, not the statute), and
        # that junk would otherwise be chunked and stamped with a clean-looking
        # but false citation. Require the source's own heading_pattern to match
        # at least once. The never-match sentinel "(?!)" marks an intentionally
        # single-section fetch (no heading line by design), so it's exempt.
        if (
            source_type == "html"
            and heading_pattern.strip() != "(?!)"
            and not heading_pattern_matches(text, heading_pattern)
        ):
            results.append({
                "source_id": source_id,
                "error": (
                    f"fetched content has no heading_pattern match ({heading_pattern!r}); "
                    "the page is likely a client-rendered shell or the wrong URL, "
                    "not the expected multi-section document"
                ),
            })
            continue

        stats = await loop.run_in_executor(
            None,
            partial(
                ingest_source,
                topic, source_id, text, heading_pattern, citation_prefix,
                source_url, jurisdiction, _doc_embedder, force=force,
            ),
        )
        results.append(stats)

    return _json_response({"topic": topic, "results": results})


async def handle_docs_status(request: web.Request) -> web.Response:
    """GET/POST /docs-status: what's been ingested for a docs topic."""
    if request.method == "GET":
        topic = request.query.get("topic", "").strip()
    else:
        try:
            body = await request.json()
        except Exception:
            return _json_response({"error": "Invalid JSON body"}, 400)
        topic = body.get("topic", "").strip()

    if not topic:
        return _json_response({"error": "Missing 'topic' field"}, 400)

    from .docs_store import topic_status
    return _json_response(topic_status(topic))


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

    if not _model_cache:
        return _json_response({"error": "Server not initialized"}, 503)

    loop = asyncio.get_running_loop()

    if not acquire_index_lock("reindex-file"):
        return _json_response({"error": "Index busy, retry in a moment"}, 423)

    try:
        result = await loop.run_in_executor(
            None, partial(reindex_file, project_path, file_path, _model_cache)
        )
    finally:
        release_index_lock()

    status = 200 if "error" not in result else 400
    return _json_response(result, status)


def _has_pytest_tests(root: Path) -> bool:
    """True if this looks like a pytest project worth running.

    pyproject/pytest.ini or any test_*.py / *_test.py at the root or under
    tests/. Kept cheap on purpose so it never walks a huge tree.
    """
    if (root / "pyproject.toml").is_file() or (root / "pytest.ini").is_file():
        return True
    for pat in ("test_*.py", "*_test.py"):
        for _ in root.glob(pat):
            return True
    tests_dir = root / "tests"
    if tests_dir.is_dir():
        for _ in tests_dir.rglob("test_*.py"):
            return True
    return False


def _run_project_tests(project_path: str) -> dict:
    """Detect the project's test command, run it, report the real result.

    Blocking (subprocess), so callers run it in an executor. Returns
    has_tests False when there's nothing to run, which is the signal the Stop
    hook needs to tell "tests passed" apart from "no tests here" and never
    block on the latter.

    Command strings are fixed literals run with shell=True so npm/npx/python
    resolve the same way on Windows and posix. project_path is never spliced
    into the command, it's only the cwd, so there's no shell injection surface.
    """
    root = Path(project_path)
    cmd = None
    label = ""

    pkg = root / "package.json"
    if pkg.is_file():
        try:
            data = json.loads(pkg.read_text(encoding="utf-8"))
        except Exception:
            data = {}
        scripts = data.get("scripts") or {}
        test_script = scripts.get("test") or ""
        # The npm init default is a placeholder that always exits 1. Running it
        # would report a fake failure, so skip it and fall through to a real runner.
        if test_script and "no test specified" not in test_script:
            cmd, label = "npm test", "npm test"
        else:
            deps = {**(data.get("dependencies") or {}), **(data.get("devDependencies") or {})}
            if "vitest" in deps:
                cmd, label = "npx vitest run", "vitest"
            elif "jest" in deps:
                cmd, label = "npx jest", "jest"

    if cmd is None and _has_pytest_tests(root):
        cmd, label = "python -m pytest -q", "pytest"

    if cmd is None:
        return {"has_tests": False, "passed": None, "summary": "no test command found"}

    import os
    import subprocess
    # CI=true stops watch mode runners (create-react-app, vitest) from hanging.
    env = {**os.environ, "CI": "true"}
    try:
        proc = subprocess.run(
            cmd, cwd=str(root), shell=True, capture_output=True, text=True,
            timeout=120, env=env, errors="replace",
        )
    except subprocess.TimeoutExpired as e:
        out = (e.stdout or "") + (e.stderr or "") if isinstance(e.stdout, str) else ""
        return {
            "has_tests": True, "passed": False, "exit_code": None,
            "summary": f"{label} timed out after 120s",
            "failures": out[-2000:],
        }
    except Exception as e:
        return {
            "has_tests": True, "passed": None, "exit_code": None,
            "summary": f"could not run {label}: {e}",
            "failures": str(e)[-2000:],
        }

    combined = (proc.stdout or "") + (proc.stderr or "")
    passed = proc.returncode == 0
    summary = f"{label}: {'passed' if passed else f'failed (exit {proc.returncode})'}"
    return {
        "has_tests": True,
        "passed": passed,
        "exit_code": proc.returncode,
        "summary": summary,
        # Tail only. The full log is noise, the tail is where the assertion diff
        # and stack trace live, which is the feedback a weak model actually needs.
        "failures": "" if passed else combined[-2000:],
    }


async def handle_run_tests(request: web.Request) -> web.Response:
    """POST /run-tests: detect and run a project's tests, return the real result.

    Body: {"project_path": "<abs>"}. Runs the detected command in an executor so
    the event loop stays free. See _run_project_tests for detection order.
    """
    try:
        body = await request.json()
    except Exception:
        return _json_response({"error": "Invalid JSON body"}, 400)

    project_path = body.get("project_path", "").strip()
    if not project_path:
        return _json_response({"error": "Missing 'project_path' field"}, 400)

    if not Path(project_path).is_dir():
        return _json_response({"error": f"Project path not found: {project_path}"}, 400)

    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(None, partial(_run_project_tests, project_path))
    return _json_response(result)


async def handle_mutation_test(request: web.Request) -> web.Response:
    """POST /mutation-test: prove the tests bite, by running the mutation tool.

    Body: {"project_path": "<abs>", "changed_files": ["src/a.py", ...]}. Runs the
    detected tool (mutmut, StrykerJS, cargo mutants) scoped to changed_files in an
    executor. A surviving mutant means a test that should have caught a broken
    version did not. No tool for the language reports has_tool false, which is a
    real answer rather than a silent skip. See server/mutation.py.
    """
    try:
        body = await request.json()
    except Exception:
        return _json_response({"error": "Invalid JSON body"}, 400)

    project_path = body.get("project_path", "").strip()
    if not project_path:
        return _json_response({"error": "Missing 'project_path' field"}, 400)
    if not Path(project_path).is_dir():
        return _json_response({"error": f"Project path not found: {project_path}"}, 400)

    changed_files = body.get("changed_files") or []
    if not isinstance(changed_files, list):
        return _json_response({"error": "'changed_files' must be a list"}, 400)

    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(
        None, partial(run_mutation, project_path, changed_files)
    )
    return _json_response(result)


async def handle_security_scan(request: web.Request) -> web.Response:
    """POST /security-scan: run security tools on changed files.

    Body: {"project_path": "<abs>", "changed_files": ["src/a.py", ...]}. Runs
    available scanners (bandit, pip-audit, semgrep) scoped to changed_files in
    an executor. A missing tool reports has_tool false with install instructions.
    """
    try:
        body = await request.json()
    except Exception:
        return _json_response({"error": "Invalid JSON body"}, 400)

    project_path = body.get("project_path", "").strip()
    if not project_path:
        return _json_response({"error": "Missing 'project_path' field"}, 400)
    if not Path(project_path).is_dir():
        return _json_response({"error": f"Project path not found: {project_path}"}, 400)

    changed_files = body.get("changed_files") or []
    if not isinstance(changed_files, list):
        return _json_response({"error": "'changed_files' must be a list"}, 400)

    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(
        None, partial(run_security_scan, project_path, changed_files)
    )
    return _json_response(result)


async def handle_web_search(request: web.Request) -> web.Response:
    """POST /web-search: DuckDuckGo search, source ranked and sanitized.

    Exists so a reasoning agent can run its own web searches. The agent picks
    the query, and that's the whole point. The hook's keyword extraction has no
    judgment and produced junk like PCMag browser reviews for a message that
    merely mentioned duckduckgo. An agent choosing its own query doesn't have
    that failure mode.

    web_search is blocking, so it runs in an executor to keep the loop free.
    """
    try:
        body = await request.json()
    except Exception:
        return _json_response({"error": "Invalid JSON body"}, 400)

    query = (body.get("query") or "").strip()
    if not query:
        return _json_response({"error": "query is required"}, 400)

    max_results = min(int(body.get("max_results", 5)), 10)
    timeout = min(float(body.get("timeout", 8.0)), 20.0)

    from server.web_search import web_search

    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(
        None, lambda: web_search(query, max_results=max_results, timeout=timeout)
    )

    if result.get("error"):
        logger.error("Web search failed for %r: %s", query, result["error"])

    return _json_response({"query": query, **result})


async def handle_github_search(request: web.Request) -> web.Response:
    """POST /github-search: search GitHub repositories, best maintained first.

    For finding a real repo to adopt, ranked by stars and recency that GitHub
    knows and DuckDuckGo does not. Token optional via GITHUB_TOKEN in .env (10 per
    minute unauthenticated, 30 with a token). Blocking, so run in an executor.
    """
    try:
        body = await request.json()
    except Exception:
        return _json_response({"error": "Invalid JSON body"}, 400)

    query = (body.get("query") or "").strip()
    if not query:
        return _json_response({"error": "query is required"}, 400)

    max_results = min(int(body.get("max_results", 5)), 50)
    sort = body.get("sort", "stars")
    timeout = min(float(body.get("timeout", 6.0)), 20.0)

    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(
        None, lambda: github_search(query, max_results=max_results, sort=sort, timeout=timeout)
    )

    if result.get("error"):
        logger.error("GitHub search failed for %r: %s", query, result["error"])

    return _json_response({"query": query, **result})


async def handle_github_file(request: web.Request) -> web.Response:
    """POST /github-file: fetch one file's text from a public GitHub repo.

    Body: {"owner", "repo", "path", "ref"?}. For pulling a real reference file to
    study once the repo search finds the repo. Code is returned intact (only the
    invisible injection characters stripped) and is untrusted reference data.
    Blocking, run in an executor.
    """
    try:
        body = await request.json()
    except Exception:
        return _json_response({"error": "Invalid JSON body"}, 400)

    owner = (body.get("owner") or "").strip()
    repo = (body.get("repo") or "").strip()
    path = (body.get("path") or "").strip()
    if not (owner and repo and path):
        return _json_response({"error": "owner, repo, and path are required"}, 400)
    ref = body.get("ref") or None

    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(
        None, lambda: github_fetch_file(owner, repo, path, ref=ref)
    )
    if result.get("error"):
        logger.error("GitHub file fetch failed for %s/%s %s: %s", owner, repo, path, result["error"])
    return _json_response(result)


async def handle_stackoverflow_search(request: web.Request) -> web.Response:
    """POST /stackoverflow-search: top accepted StackOverflow answers, with code.

    Body: {"query", "max_results"?}. For the few lines that do X, human voted. Key
    optional via STACKEXCHANGE_KEY in .env. Blocking, run in an executor.
    """
    try:
        body = await request.json()
    except Exception:
        return _json_response({"error": "Invalid JSON body"}, 400)

    query = (body.get("query") or "").strip()
    if not query:
        return _json_response({"error": "query is required"}, 400)
    max_results = min(int(body.get("max_results", 3)), 10)
    timeout = min(float(body.get("timeout", 8.0)), 20.0)

    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(
        None, lambda: stackoverflow_search(query, max_results=max_results, timeout=timeout)
    )
    if result.get("error"):
        logger.error("StackOverflow search failed for %r: %s", query, result["error"])
    return _json_response({"query": query, **result})


async def handle_wikipedia_search(request: web.Request) -> web.Response:
    """POST /wikipedia-search: human curated general knowledge, free and keyless.

    Body: {"query", "max_results"?}. The high quality general info tier, a fact or
    concept from a human edited encyclopedia. Blocking, run in an executor.
    """
    try:
        body = await request.json()
    except Exception:
        return _json_response({"error": "Invalid JSON body"}, 400)

    query = (body.get("query") or "").strip()
    if not query:
        return _json_response({"error": "query is required"}, 400)
    max_results = min(int(body.get("max_results", 3)), 10)

    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(
        None, lambda: wikipedia_search(query, max_results=max_results)
    )
    if result.get("error"):
        logger.error("Wikipedia search failed for %r: %s", query, result["error"])
    return _json_response({"query": query, **result})


async def handle_graphrag_build(request: web.Request) -> web.Response:
    """POST /graphrag-build: start the GraphRAG build for a project (manual, overnight).

    Body: {"project_path": "<abs>"}. Returns immediately; poll /graphrag-status for
    percent. Proxies to the isolated graph service (auto started) in an executor.
    """
    try:
        body = await request.json()
    except Exception:
        return _json_response({"error": "Invalid JSON body"}, 400)
    project_path = (body.get("project_path") or "").strip()
    if not project_path:
        return _json_response({"error": "project_path is required"}, 400)
    if not Path(project_path).is_dir():
        return _json_response({"error": f"Project path not found: {project_path}"}, 400)
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(None, partial(graphrag_build, project_path))
    return _json_response(result)


async def handle_graphrag_query(request: web.Request) -> web.Response:
    """POST /graphrag-query: ask the built semantic graph a cross file question.

    Body: {"project_path": "<abs>", "query": "..."}. The semantic layer, for the
    why and intent a query the import graph cannot answer. Proxied in an executor.
    """
    try:
        body = await request.json()
    except Exception:
        return _json_response({"error": "Invalid JSON body"}, 400)
    project_path = (body.get("project_path") or "").strip()
    q = (body.get("query") or "").strip()
    if not project_path or not q:
        return _json_response({"error": "project_path and query are required"}, 400)
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(None, partial(graphrag_query, project_path, q))
    return _json_response(result)


async def handle_graphrag_status(request: web.Request) -> web.Response:
    """GET /graphrag-status?project_path=<abs> (or POST body): build progress."""
    project_path = (request.query.get("project_path") or "").strip()
    if not project_path and request.method == "POST":
        try:
            body = await request.json()
            project_path = (body.get("project_path") or "").strip()
        except Exception:
            pass
    if not project_path:
        return _json_response({"error": "project_path is required"}, 400)
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(None, partial(graphrag_status, project_path))
    return _json_response(result)


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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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
    task = app.get("auto_reindex_task")
    if task:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        logger.info("Auto reindex loop stopped")

    from .store import ChromaStore
    ChromaStore.clear_cache()
    logger.info("ChromaDB client cache cleared")
    try:
        _HEARTBEAT_PATH.unlink(missing_ok=True)
    except Exception:
        pass


@web.middleware
async def error_middleware(request: web.Request, handler) -> web.Response:
    try:
        return await handler(request)
    except web.HTTPException:
        raise  # preserve 4xx/5xx raised intentionally by handlers
    except Exception as exc:
        logger.exception(
            "Unhandled error in %s %s: %s: %s",
            request.method, request.path, type(exc).__name__, exc,
        )
        return _json_response({"error": "Internal server error"}, 500)


def create_app() -> web.Application:
    """Create and configure the aiohttp application."""
    global _model_cache, _doc_embedder, _start_time

    _start_time = time.time()

    # Model cache with language-based routing (loads models lazily on first use)
    _model_cache = ModelCache()
    # General prose embedder for docs: sources (statutes, regulations, etc),
    # a separate model from the code search tuned one above. Also loaded
    # lazily, on first docs: search or ingest, not at startup: the code
    # embedder's startup warmup already imports sentence_transformers once,
    # single threaded, so the thread safety concern that warmup exists for
    # does not apply a second time here.
    _doc_embedder = SentenceTransformerEmbedding()

    # Ensure state directory exists
    STATE_DIR.mkdir(parents=True, exist_ok=True)

    async def _on_startup(app: web.Application) -> None:
        """Warm up the code embedder before the server accepts connections.

        sentence-transformers' first import is not thread-safe
        (github.com/huggingface/sentence-transformers/issues/2313); loading it
        lazily from a request-handling executor thread races with that first
        import and intermittently raises "attempted relative import with no
        known parent package". aiohttp awaits on_startup handlers to completion
        before opening the listening socket, so doing it here is guaranteed
        single-threaded and race-free.
        """
        loop = asyncio.get_running_loop()
        try:
            # Warm up the default code model before accepting connections.
            # sentence-transformers' first import is not thread safe, so this
            # must complete single-threaded before request handlers fire.
            await loop.run_in_executor(None, _model_cache.get, CODE_EMBEDDING_MODEL)
            logger.info("Code embedder warmed up at startup (model=%s)", CODE_EMBEDDING_MODEL)
        except Exception:
            logger.exception("Embedder warmup failed at startup")

        _write_heartbeat(model_loaded=len(_model_cache) > 0, index_ok=True)
        _start_heartbeat_thread()
        logger.info("Heartbeat thread started (interval=%ds)", _HEARTBEAT_INTERVAL_S)

        # Catches changes the per edit hook never sees: another editor, a git
        # pull, a branch switch. Without it the index drifts and search starts
        # confidently returning code that no longer exists.
        from .auto_reindex import auto_reindex_loop
        app["auto_reindex_task"] = asyncio.create_task(
            auto_reindex_loop(lambda: _model_cache)
        )
        logger.info("Auto reindex loop started")

    app = web.Application(middlewares=[error_middleware])
    app.router.add_get("/status", handle_status)
    app.router.add_post("/search", handle_search)
    app.router.add_post("/web-search", handle_web_search)
    app.router.add_post("/github-search", handle_github_search)
    app.router.add_post("/github-file", handle_github_file)
    app.router.add_post("/stackoverflow-search", handle_stackoverflow_search)
    app.router.add_post("/wikipedia-search", handle_wikipedia_search)
    app.router.add_post("/graphrag-build", handle_graphrag_build)
    app.router.add_post("/graphrag-query", handle_graphrag_query)
    app.router.add_get("/graphrag-status", handle_graphrag_status)
    app.router.add_post("/graphrag-status", handle_graphrag_status)
    app.router.add_post("/index-project", handle_index_project)
    app.router.add_post("/reindex-file", handle_reindex_file)
    app.router.add_post("/docs-ingest", handle_docs_ingest)
    app.router.add_get("/docs-status", handle_docs_status)
    app.router.add_post("/docs-status", handle_docs_status)
    app.router.add_post("/run-tests", handle_run_tests)
    app.router.add_post("/mutation-test", handle_mutation_test)
    app.router.add_post("/security-scan", handle_security_scan)
    app.router.add_get("/projects", handle_projects)
    app.router.add_post("/register-project", handle_register_project)

    from .kanban import setup_kanban
    setup_kanban(app)

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
