#!/usr/bin/env python3
"""clean-rag RAG enforcement: UserPromptSubmit hook.

Fires on every user message. Injects actual RAG search results as context.
Intelligent reranking: official docs > community, practical > theoretical.
Forced data injection, not instructions.

Exit codes:
  0 = always (UserPromptSubmit hooks cannot block)
"""

import json
import logging
import os
import sys
import time
import urllib.request
import subprocess
from pathlib import Path
import re

# Windows consoles default to cp1252, which cannot encode emoji. Reconfigure
# stdout to UTF-8 with a safe fallback so print() never crashes the hook.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def _clean_rag_home() -> Path:
    """Resolve the clean-rag root directory."""
    env = os.environ.get("CLEAN_RAG_HOME")
    if env:
        return Path(env)
    return Path(__file__).resolve().parent.parent


def _log_path() -> Path:
    return _clean_rag_home() / "state" / "rag-enforce.log"


try:
    _log_file = _log_path()
    _log_file.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        filename=str(_log_file),
        filemode="a",
        format="%(asctime)s %(levelname)s %(message)s",
    )
except Exception:
    logging.basicConfig(level=logging.INFO, stream=sys.stderr)
logger = logging.getLogger(__name__)


def _extract_keywords(message: str, limit: int = 5) -> list[str]:
    """Extract search keywords from user message.

    len >= 3, not > 3: confirmed the stricter cutoff drops meaningful short
    words ("fix", "bug", "add", "run", "log"), which silently forced every
    short message ("did u fix it") into the generic fallback query, the
    same misleading-generic-content problem from the start of this session,
    just from a different cause.
    """
    stop_words = {"is", "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for", "of", "with", "by", "from", "as", "i", "you", "we", "they", "it", "this", "that", "be", "have", "do", "did", "was", "are", "can"}
    words = re.findall(r'\b[a-z]+\b', message.lower())
    keywords = [w for w in words if len(w) >= 3 and w not in stop_words]
    return keywords[:limit]


def _health_check(port: str) -> bool:
    """Quick health check of RAG server."""
    try:
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/status",
            method="GET"
        )
        with urllib.request.urlopen(req, timeout=1) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("status") in ("ready", "warming_up")
    except Exception as e:
        logger.error(f"Health check failed: {type(e).__name__}: {e}")
        return False


def _trigger_self_heal(port: str) -> None:
    """Attempt to restart RAG server if down."""
    home = _clean_rag_home()
    try:
        subprocess.Popen(
            [sys.executable, str(home / "cli" / "server_ctl.py"), "restart"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        logger.info("Self-heal restart triggered")
    except Exception as e:
        logger.error(f"Self-heal trigger failed: {type(e).__name__}: {e}")


def _search_rag(query: str, port: str, limit: int = 10, retries: int = 2) -> tuple[list[dict], bool, list[dict]]:
    """Search clean-rag for relevant results, with retries on transient failure.

    The server's own /search endpoint (app.py:230-253) already runs score-based
    web search fallback internally and returns it as "web_search_results" in
    the same response, plus spawns its own background KB indexer. There is no
    separate /web-search route — calling one 404s.

    Returns: (results, is_healthy, web_search_results)
    """
    if not _health_check(port):
        logger.error(f"RAG unhealthy before search. query={query!r}")
        _trigger_self_heal(port)
        return [], False, []

    req_data = json.dumps({
        "query": query,
        "sources": ["all_topics"],
        "limit": limit,
        "min_score": 0.4
    }).encode("utf-8")

    backoffs = [0.2, 0.5][:retries]
    last_error = None
    # Measured: a real all_topics search across 61 topic databases with
    # limit=10 took 7.8s under load (curl, this session). 3s was too short
    # and made every search look like a failure when it was just slow.
    search_timeout = 12

    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(
                f"http://127.0.0.1:{port}/search",
                data=req_data,
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            start = time.monotonic()
            with urllib.request.urlopen(req, timeout=search_timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                elapsed = time.monotonic() - start
                logger.info(f"Search took {elapsed:.2f}s. query={query!r}")
                if attempt > 0:
                    logger.info(f"Search succeeded on retry {attempt}. query={query!r}")
                return data.get("results", []), True, data.get("web_search_results", [])
        except Exception as e:
            last_error = e
            logger.error(
                f"Search attempt {attempt + 1}/{retries + 1} failed: "
                f"{type(e).__name__}: {e}. query={query!r} endpoint=/search"
            )
            if attempt < retries:
                time.sleep(backoffs[attempt])

    logger.error(f"Search exhausted all retries. query={query!r} last_error={last_error}")
    _trigger_self_heal(port)
    return [], False, []


def _rerank_results(results: list[dict]) -> list[dict]:
    """Rerank results by: score, official docs preference, practical examples.

    Based on research (docker/manuals/ai/docker-agent/rag.md score 0.818):
    Prioritize official documentation over community, practical examples over
    theoretical, recent over outdated.
    """
    scored = []
    for result in results:
        base_score = result.get("score", 0)
        boost = 0

        file_path = result.get("file", "").lower()
        if any(x in file_path for x in ["official", "reference", "spec", "doc"]):
            boost += 0.15
        if any(x in file_path for x in ["example", "guide", "tutorial", "how-to"]):
            boost += 0.10

        if any(x in file_path for x in ["discussion", "issue", "comment", "forum"]):
            boost -= 0.10

        content = result.get("content", "").lower()
        if any(x in content for x in ["example", "code", "implementation", "usage"]):
            boost += 0.05
        if any(x in content for x in ["theory", "concept", "explain", "describe"]):
            boost -= 0.02

        reranked_score = max(0, min(1, base_score + boost))
        scored.append((reranked_score, result))

    scored.sort(reverse=True, key=lambda x: x[0])
    return [r for _, r in scored]


def _keyword_overlap_ratio(query: str, results: list[dict], top_n: int = 3) -> float:
    """Fraction of query keywords that actually appear in the top results' content.

    Mechanical relevance check, not a score threshold. A result can score 0.8
    on embedding similarity while sharing zero literal keywords with the query
    (e.g. "canvas" in a testing doc vs "canvas" in a game dev query). This
    catches that case without an LLM judgment call.
    """
    query_words = set(re.findall(r'\b[a-z]+\b', query.lower()))
    query_words = {w for w in query_words if len(w) > 3}
    if not query_words:
        return 1.0  # nothing to check against, don't force a fallback

    combined_content = " ".join(
        r.get("content", "").lower() for r in results[:top_n]
    )
    hits = sum(1 for w in query_words if w in combined_content)
    return hits / len(query_words)


def _web_search_fallback(query: str, port: str) -> list[dict]:
    """Fallback to web search when RAG results are poor or off-topic.

    There is no HTTP /web-search route on the server (confirmed by scanning
    every registered handler in app.py) — the server only runs web search
    internally inside /search, keyed off its own score threshold. That
    threshold is score-only and misses topically-wrong-but-high-scoring
    results (this session: "BigBird" model docs scored 0.78 against a
    "flappy bird" query on the shared literal word "bird"). This function
    is the client-side escape hatch for that gap: it imports and calls the
    same web_search() function the server uses, directly, in-process.
    """
    try:
        home = _clean_rag_home()
        server_dir = home / "server"
        if str(server_dir) not in sys.path:
            sys.path.insert(0, str(server_dir))
        from web_search import web_search as _do_web_search

        result = _do_web_search(query, max_results=3, timeout=4.0)
        if result.get("error"):
            logger.error(f"Web search returned error: {result['error']}. query={query!r}")
        return result.get("results", [])
    except Exception as e:
        logger.error(f"Web search fallback failed: {type(e).__name__}: {e}. query={query!r}")
        return []


def _slugify(text: str, max_len: int = 40) -> str:
    """Turn a query into a filesystem-safe topic slug."""
    slug = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    return slug[:max_len] or "fallback"


def _spawn_background_crawler(results: list[dict], port: str, source_query: str) -> None:
    """Spawn background crawler to index web search results (no LLM).

    web_crawler.py uses relative imports (server package) and has no CLI
    entry point, so it cannot run as `python web_crawler.py`. Runs through
    _crawl_runner.py instead, which imports it correctly. A real subprocess
    (not a thread) so it survives after this short-lived hook process exits
    — daemon threads die the instant the process exits, before doing
    anything, confirmed by testing.
    """
    try:
        urls = [r.get("url") for r in results if r.get("url")]
        if not urls:
            return

        home = _clean_rag_home()
        runner_script = home / "hooks" / "_crawl_runner.py"
        if not runner_script.exists():
            logger.error(f"Crawl runner not found: {runner_script}")
            return

        topic_slug = _slugify(source_query)

        subprocess.Popen(
            [sys.executable, str(runner_script), topic_slug, source_query] + urls,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        logger.info(f"Background crawler spawned for {len(urls)} URL(s), topic={topic_slug!r}")
    except Exception as e:
        logger.error(f"Crawler spawn failed: {type(e).__name__}: {e}")


def _format_rag_results(results: list[dict]) -> str:
    """Format search results as markdown context."""
    if not results:
        return ""

    lines = ["## Research Context\n"]
    for i, result in enumerate(results[:3], 1):
        topic = result.get("topic", "unknown")
        content = result.get("content", "")[:250]
        score = result.get("score", 0)
        lines.append(f"**{i}. [{topic}]** (relevance: {score:.2f})")
        lines.append(f"{content}...\n")

    return "\n".join(lines)


def _format_web_results(results: list[dict]) -> str:
    """Format web search results as markdown context."""
    if not results:
        return ""

    lines = ["## Web Search Fallback\n"]
    for i, result in enumerate(results[:3], 1):
        title = result.get("title", "Unknown")
        snippet = result.get("snippet", "")[:250]
        url = result.get("url", "")
        lines.append(f"**{i}. {title}**")
        lines.append(f"{snippet}...")
        lines.append(f"*Source: {url}*\n")

    return "\n".join(lines)


def _read_user_prompt() -> str:
    """Read the user's actual prompt from stdin (UserPromptSubmit payload)."""
    try:
        payload = json.loads(sys.stdin.read())
        return payload.get("prompt", "")
    except Exception as e:
        logger.error(f"Failed to read prompt from stdin: {type(e).__name__}: {e}")
        return ""


def main() -> int:
    port = os.environ.get("CLEAN_RAG_PORT", "8613")

    user_prompt = _read_user_prompt()
    keywords = _extract_keywords(user_prompt) if user_prompt else []

    if not keywords:
        # No usable keywords (empty prompt, or a short conversational
        # message like "did u fix it" / "thanks" / "ok"). Confirmed this
        # used to silently fall back to a generic OWASP/dotnet/go query,
        # injecting content with no real relevance to what was typed — the
        # same misleading-injection problem this whole session started
        # from. Skip injection entirely instead of guessing.
        logger.info(f"No usable keywords, skipping injection. prompt={user_prompt!r}")
        return 0

    search_query = " ".join(keywords)

    rag_results, is_healthy, server_web_results = _search_rag(search_query, port, limit=10)

    if not is_healthy:
        print(
            "\n[WARN] RAG SERVER UNAVAILABLE\n"
            "Research-backed context injection is offline.\n"
            "Self-healing initiated. Retry in 30 seconds.\n"
            "Proceeding without injected research context.\n"
        )
        return 0

    reranked = _rerank_results(rag_results)

    best_score = reranked[0].get("score", 0) if reranked else 0
    overlap = _keyword_overlap_ratio(search_query, reranked) if reranked else 0.0

    # The server already ran its own score-based web fallback inside /search
    # (app.py:235) and, if triggered, spawned its own background indexer.
    # Use that first — don't duplicate the web call or the indexing.
    if server_web_results:
        logger.info(f"Server-side fallback already ran. query={search_query!r}")
        print(_format_web_results(server_web_results))
        return 0

    # Server's score threshold missed it, but our overlap check catches
    # results that score high while being topically wrong (shared literal
    # word, wrong domain). Run the client-side fallback for that case only.
    needs_fallback = overlap < 0.5

    if needs_fallback:
        logger.info(
            f"Client-side fallback triggered. best_score={best_score:.2f} overlap={overlap:.2f} query={search_query!r}"
        )
        web_results = _web_search_fallback(search_query, port)
        if web_results:
            web_context = _format_web_results(web_results)
            print(web_context)
            _spawn_background_crawler(web_results, port, search_query)
            print("[INFO] Background crawler indexing web results for future queries...\n")
            return 0

    rag_context = _format_rag_results(reranked)
    if rag_context:
        print(rag_context)
    else:
        print("\n[WARN] No quality research results found. Proceeding with codebase analysis.\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
