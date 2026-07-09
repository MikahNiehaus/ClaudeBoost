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
                model_loaded=_embedder is not None and _embedder.is_loaded,
                index_ok=True,
            )

    t = threading.Thread(target=_beat, daemon=True, name="clean-rag-heartbeat")
    t.start()


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

    sources = body.get("sources", ["all_topics"])
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

    graph_meta: dict = {}
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
            meta_out=graph_meta,
            depth=depth,
            direction=direction,
        ),
    )

    search_id = _log_search(query=query, sources=sources, mode=mode, results=results, graph_meta=graph_meta)

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


def _log_search(
    query: str, sources: list[str], mode: str, results: list[dict],
    graph_meta: dict | None = None,
) -> str:
    """Append a real search to the server-side log. Returns the search_id.

    graph_meta (from search()'s meta_out) records whether a mode=graph/both
    search actually found real graph neighbors, not just whether graph mode
    was requested -- see _search_project_graph()'s docstring (search.py) for
    what graph_status "absent"/"empty"/"hit" mean. Observe-only for now
    (Stage 1) -- handle_prove doesn't gate on these fields yet (Stage 4).
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


# Keywords that count as an explicit "no dependents" acknowledgment in a
# quality_aspects assertion, when a codebase angle's graph traversal found
# no callers. Deliberately simple substring matching, not semantic
# understanding -- proof-gate.py has no AI judge, only mechanical checks,
# so this forces an explicit written acknowledgment rather than trying to
# infer intent.
_NO_CALLERS_KEYWORDS = (
    "no caller", "no dependent", "no depend", "leaf file", "leaf node",
    "nothing depends", "not called by", "not imported by", "no one calls",
    "no one imports",
)

# Topics that auto-classify a search's angle as "methodology" instead of
# the generic "technology" default -- kept in sync with proof-gate.py's
# METHODOLOGY_TOPICS values (all of them, not just what any single file's
# _suggest_methodology_topics() would return, since a caller can legitimately
# search any of these for code-quality grounding).
_METHODOLOGY_TOPIC_NAMES = {
    "clean-code-principles", "code-smells", "solid-principles", "design-patterns",
    "api-design", "error-handling", "testing-strategy", "configuration-management",
    "database-design", "performance-optimization", "concurrency",
}

_VALID_PROVE_ANGLES = {"technology", "codebase", "pitfalls", "security", "best_practices", "methodology"}


def _project_has_graph(project_path: str) -> bool:
    import hashlib
    pid = hashlib.sha256(str(Path(project_path).resolve()).encode("utf-8")).hexdigest()[:12]
    return (DATABASES_DIR / "_projects" / pid / "graph.db").exists()


def _has_no_callers_acknowledgment(quality_aspects: list[dict]) -> bool:
    for q in quality_aspects:
        if not isinstance(q, dict):
            continue
        text = str(q.get("assertion", "")).lower()
        if any(kw in text for kw in _NO_CALLERS_KEYWORDS):
            return True
    return False


def _evaluate_codebase_evidence(
    entries: list[dict], quality_aspects: list[dict],
) -> tuple[bool, str | None]:
    """Apply the graph-verified codebase-evidence matrix (plan Stage 4).

    A plain vector hit on a project that actually has a graph isn't enough
    -- the codebase angle must show real graph traversal (real callers, or
    an explicit acknowledgment when there genuinely are none), or a
    verified direct-research receipt (Stage 3) when the project has no
    graph at all. Returns (ok, reason_if_not_ok).
    """
    codebase_entries = [
        e for e in entries
        if any(str(s).startswith("project:") for s in e.get("sources", []))
    ]
    if not codebase_entries:
        return False, "No codebase-sourced entries to evaluate (should be unreachable)."

    reasons = []
    for e in codebase_entries:
        mode = e.get("mode", "vector")
        project_paths = [
            str(s)[8:] for s in e.get("sources", []) if str(s).startswith("project:")
        ]

        if mode == "direct_research":
            # Stage 3's /log-direct-research already independently verified
            # this (file existence, real match count) before issuing the
            # receipt -- sufficient on its own.
            return True, None

        if mode not in ("graph", "both"):
            # mode="vector": never sufficient on its own, whether or not
            # the project has a graph -- either redo with graph/both, or if
            # there's genuinely no graph, use /log-direct-research instead.
            for pp in project_paths:
                if _project_has_graph(pp):
                    reasons.append(
                        f"'{pp}' has a real graph index, but the cited search used mode='vector' "
                        "-- graph traversal was never consulted. Re-run with mode='graph' or 'both'."
                    )
                else:
                    reasons.append(
                        f"'{pp}' has no graph index and the cited search used mode='vector', which "
                        "doesn't verify anything structural. Either index the project first, or use "
                        "POST /log-direct-research to verify Grep/file-read evidence instead."
                    )
            continue

        graph_status = e.get("graph_status")
        caller_count = e.get("caller_count", 0)

        if graph_status == "absent":
            reasons.append(
                f"Graph traversal was attempted but no graph index exists for this project "
                "(graph_status='absent'). Index the project first, or use "
                "POST /log-direct-research to verify Grep/file-read evidence instead."
            )
            continue

        if caller_count and caller_count > 0:
            return True, None

        # graph_status in ("hit", "empty") with zero callers -- a real leaf
        # file is legitimate, but it must be acknowledged explicitly, not
        # silently accepted, so an empty/dependency-only traversal can't
        # become an unnoticed loophole.
        if _has_no_callers_acknowledgment(quality_aspects):
            return True, None

        reasons.append(
            "Graph traversal found no callers for this file (caller_count=0). If this is "
            "genuinely a leaf file with no dependents, add a quality_aspects entry explicitly "
            "saying so (e.g. 'no callers found, this is a leaf file') -- otherwise, check "
            "whether the right seed file was actually searched."
        )

    return False, " ".join(reasons) if reasons else "Codebase evidence did not meet the required bar."


async def handle_prove(request: web.Request) -> web.Response:
    """POST /prove: write a proof-gate proof from independently-logged searches.

    Body fields:
        file_path (str): file the proof is for (required)
        search_ids (list): search_id values returned by prior /search calls
            (required, >=2, at least one must be from a "project:" source --
            the codebase angle proof-gate.py requires). Each entry is either
            a plain search_id string (angle auto-classified: "codebase" for
            project: sources, "security" for topic:owasp, "methodology" for
            a recognized code-quality topic, "technology" otherwise), or
            {"search_id": ..., "angle": ...} to explicitly request one of
            technology/codebase/pitfalls/security/best_practices/methodology
            -- useful for angles auto-classification can't infer (e.g.
            "best_practices" is an intent, not a fixed topic). An explicit
            angle="codebase" claim is still verified against the real
            source (silently corrected to "technology" if the search wasn't
            actually project:-sourced) -- you can request a label, not fake
            what the search actually was.
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

    search_ids_raw = body.get("search_ids", [])
    if not isinstance(search_ids_raw, list) or len(search_ids_raw) < 2:
        return _json_response(
            {"error": "search_ids must be a list of >=2 real /search search_id values"}, 400
        )

    search_ids: list[str] = []
    angle_overrides: dict[str, str] = {}
    for item in search_ids_raw:
        if isinstance(item, str):
            search_ids.append(item)
        elif isinstance(item, dict) and isinstance(item.get("search_id"), str):
            search_ids.append(item["search_id"])
            requested = item.get("angle")
            if requested in _VALID_PROVE_ANGLES:
                angle_overrides[item["search_id"]] = requested
        else:
            return _json_response({
                "error": (
                    "each search_ids entry must be a search_id string, or "
                    '{"search_id": "...", "angle": "..."}'
                ),
            }, 400)

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

        sid = e["search_id"]
        if sid in angle_overrides:
            # Caller-requested angle label (for cases auto-classification
            # can't cover, e.g. "best_practices" -- an intent, not a fixed
            # topic). Still server-verified for "codebase": can't claim it
            # without a real project: source, silently corrected rather
            # than trusted, same principle as everything else in /prove.
            angle = angle_overrides[sid]
            if angle == "codebase" and not is_codebase:
                angle = "technology"
        elif is_codebase:
            angle = "codebase"
        elif any(str(s) == "topic:owasp" for s in sources):
            angle = "security"
        elif any(
            str(s).startswith("topic:") and str(s)[6:] in _METHODOLOGY_TOPIC_NAMES
            for s in sources
        ):
            angle = "methodology"
        else:
            angle = "technology"

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

    codebase_ok, codebase_reason = _evaluate_codebase_evidence(entries, quality_aspects)
    if not codebase_ok:
        return _json_response({"error": codebase_reason}, 400)

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


# Fixed "score" for a verified direct-research receipt. Not a similarity
# estimate (there's nothing to estimate -- the file either exists and the
# pattern either matched or it didn't), so 1.0 reflects certainty from a
# deterministic check, not an inflated confidence claim.
_DIRECT_RESEARCH_SCORE = 1.0


def _grep_files(pattern: str, files: list[str]) -> int:
    """Count real regex matches for `pattern` across `files`.

    Uses Python's re module rather than shelling out to ripgrep -- avoids
    any subprocess/shell-injection surface for a user-supplied pattern and
    file list, and is functionally equivalent for verification purposes
    (a real match count from actually reading the files, not a claim).
    """
    try:
        compiled = re.compile(pattern)
    except re.error:
        return -1  # signals invalid pattern to the caller
    total = 0
    for f in files:
        try:
            text = Path(f).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        total += len(compiled.findall(text))
    return total


async def handle_log_direct_research(request: web.Request) -> web.Response:
    """POST /log-direct-research: issue a search_id-equivalent receipt for
    manual research (Grep/file reads) when a project isn't indexed in
    clean-rag -- the server is up, but there's no graph/vector index for
    this specific project yet. Never blocking, never requires indexing.

    Verifies the claim itself (file existence, a real regex match count)
    instead of trusting a self-reported description -- same principle as
    /prove for real searches: the server checks, the caller doesn't just
    assert. Writes into the same search-log.jsonl /prove already reads,
    tagged with sources=["project:<path>"] so /prove's existing codebase-
    angle detection (app.py's is_codebase check) picks it up with no
    special-casing needed there.

    Body fields:
        project_path (str): the project this research relates to (required)
        files_examined (list[str]): file paths actually grepped/read
            (required, >=1, each must exist on disk)
        method ("grep" | "read"): how the files were examined (required)
        pattern (str): the grep pattern searched for (required if
            method="grep"; must match at least once across files_examined)
        description (str): optional free-text note
    """
    try:
        body = await request.json()
    except Exception:
        return _json_response({"error": "Invalid JSON body"}, 400)

    project_path = body.get("project_path", "").strip()
    if not project_path:
        return _json_response({"error": "Missing 'project_path' field"}, 400)

    files_examined = body.get("files_examined", [])
    if not isinstance(files_examined, list) or not files_examined:
        return _json_response({"error": "files_examined must be a non-empty list"}, 400)

    method = body.get("method", "")
    if method not in ("grep", "read"):
        return _json_response({"error": "method must be 'grep' or 'read'"}, 400)

    pattern = body.get("pattern", "")
    if method == "grep" and not pattern:
        return _json_response({"error": "pattern is required when method='grep'"}, 400)

    missing = [f for f in files_examined if not Path(f).is_file()]
    if missing:
        return _json_response({
            "error": (
                "One or more cited files do not exist -- cannot issue a receipt for "
                "files that were not actually examined."
            ),
            "missing_files": missing,
        }, 400)

    match_count = None
    if method == "grep":
        match_count = _grep_files(pattern, files_examined)
        if match_count < 0:
            return _json_response({"error": f"'{pattern}' is not a valid regex pattern"}, 400)
        if match_count == 0:
            return _json_response({
                "error": (
                    f"Pattern {pattern!r} matched zero times across the cited files -- "
                    "cannot issue a receipt for a grep that found nothing."
                ),
            }, 400)

    search_id = uuid.uuid4().hex[:16]
    entry = {
        "search_id": search_id,
        "ts": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "query": pattern if method == "grep" else body.get("description", "direct file read"),
        "sources": [f"project:{project_path}"],
        "mode": "direct_research",
        "results_count": match_count if method == "grep" else len(files_examined),
        "top_score": _DIRECT_RESEARCH_SCORE,
        "files_examined": files_examined,
        "method": method,
    }
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        with open(_SEARCH_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except OSError:
        logger.exception("Failed to write search-log entry for direct research")

    response = {
        "search_id": search_id,
        "verified": True,
        "files_examined": files_examined,
        "method": method,
    }
    if method == "grep":
        response["match_count"] = match_count

    # Non-blocking, ignorable suggestion -- never a requirement. Only shown
    # when the project genuinely has no graph index, so it's relevant.
    import hashlib
    project_root = Path(project_path).resolve()
    pid = hashlib.sha256(str(project_root).encode("utf-8")).hexdigest()[:12]
    if not (DATABASES_DIR / "_projects" / pid / "graph.db").exists():
        response["suggestion"] = (
            f"'{project_path}' isn't indexed in clean-rag yet. Consider POST /index-project "
            "for richer, graph-verified results next time -- optional, not required."
        )

    return _json_response(response)


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
    try:
        _HEARTBEAT_PATH.unlink(missing_ok=True)
    except Exception:
        pass


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

        _write_heartbeat(model_loaded=True, index_ok=True)
        _start_heartbeat_thread()
        logger.info("Heartbeat thread started (interval=%ds)", _HEARTBEAT_INTERVAL_S)

    app = web.Application()
    app.router.add_get("/status", handle_status)
    app.router.add_post("/search", handle_search)
    app.router.add_post("/prove", handle_prove)
    app.router.add_post("/log-direct-research", handle_log_direct_research)
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
