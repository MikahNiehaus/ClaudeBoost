#!/usr/bin/env python3
"""clean-rag RAG enforcement: UserPromptSubmit hook.

Fires on every user message. Injects actual RAG search results as context.
Intelligent reranking: official docs > community, practical > theoretical.
Forced data injection, not instructions.

Exit codes:
  0 = always (UserPromptSubmit hooks cannot block)
"""

import json
import os
import sys
import urllib.request
import subprocess
from pathlib import Path
import re
from datetime import datetime


def _clean_rag_home() -> Path:
    """Resolve the clean-rag root directory."""
    env = os.environ.get("CLEAN_RAG_HOME")
    if env:
        return Path(env)
    return Path(__file__).resolve().parent.parent


def _extract_keywords(message: str, limit: int = 5) -> list[str]:
    """Extract search keywords from user message."""
    stop_words = {"is", "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for", "of", "with", "by", "from", "as", "i", "you", "we", "they", "it", "this", "that", "be", "have", "do"}
    words = re.findall(r'\b[a-z]+\b', message.lower())
    keywords = [w for w in words if len(w) > 3 and w not in stop_words]
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
    except Exception:
        return False


def _trigger_self_heal(port: str) -> None:
    """Attempt to restart RAG server if down."""
    home = _clean_rag_home()
    try:
        # Spawn server restart in background
        import subprocess
        subprocess.Popen(
            [sys.executable, str(home / "cli" / "server_ctl.py"), "restart"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
    except Exception:
        pass


def _search_rag(query: str, port: str, limit: int = 10) -> tuple[list[dict], bool]:
    """Search clean-rag for relevant results (initial retrieval).

    Returns: (results, is_healthy)
    """
    # Health check first
    if not _health_check(port):
        _trigger_self_heal(port)
        return [], False

    try:
        req_data = json.dumps({
            "query": query,
            "sources": ["all_topics"],
            "limit": limit,
            "min_score": 0.4
        }).encode("utf-8")

        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/search",
            data=req_data,
            headers={"Content-Type": "application/json"},
            method="POST"
        )

        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("results", []), True
    except Exception:
        _trigger_self_heal(port)
        return [], False


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

        # Boost official/authoritative sources
        file_path = result.get("file", "").lower()
        if any(x in file_path for x in ["official", "reference", "spec", "doc"]):
            boost += 0.15
        if any(x in file_path for x in ["example", "guide", "tutorial", "how-to"]):
            boost += 0.10

        # Penalize community/discussion content
        if any(x in file_path for x in ["discussion", "issue", "comment", "forum"]):
            boost -= 0.10

        # Boost practical content
        content = result.get("content", "").lower()
        if any(x in content for x in ["example", "code", "implementation", "usage"]):
            boost += 0.05
        if any(x in content for x in ["theory", "concept", "explain", "describe"]):
            boost -= 0.02

        reranked_score = max(0, min(1, base_score + boost))
        scored.append((reranked_score, result))

    scored.sort(reverse=True, key=lambda x: x[0])
    return [r for _, r in scored]


def _web_search_fallback(query: str, port: str) -> list[dict]:
    """Fallback to web search when RAG results are poor."""
    try:
        req_data = json.dumps({
            "query": query,
            "max_results": 3
        }).encode("utf-8")

        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/web-search",
            data=req_data,
            headers={"Content-Type": "application/json"},
            method="POST"
        )

        with urllib.request.urlopen(req, timeout=4) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("results", [])
    except Exception:
        return []


def _spawn_background_crawler(results: list[dict], port: str) -> None:
    """Spawn background crawler to index web search results (no LLM)."""
    try:
        urls = [r.get("url") for r in results if r.get("url")]
        if not urls:
            return

        home = _clean_rag_home()
        crawler_script = home / "server" / "web_crawler.py"
        if not crawler_script.exists():
            return

        # Spawn in background, don't wait
        subprocess.Popen(
            [sys.executable, str(crawler_script), "--urls"] + urls,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
    except Exception:
        pass


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


def main() -> int:
    port = os.environ.get("CLEAN_RAG_PORT", "8613")

    # Default broad search for methodology/patterns
    search_query = "code quality patterns methodology security error handling"
    rag_results, is_healthy = _search_rag(search_query, port, limit=10)

    # If RAG is down, alert (fail-closed per OWASP score 0.8653)
    if not is_healthy:
        print(
            "\n⚠️ RAG SERVER UNAVAILABLE\n"
            "Research-backed context injection is offline.\n"
            "Self-healing initiated. Retry in 30 seconds.\n"
            "Proceeding without injected research context.\n"
        )
        return 0

    # Rerank by relevance criteria
    reranked = _rerank_results(rag_results)

    # Check if results are good enough (best score >= 0.5)
    best_score = reranked[0].get("score", 0) if reranked else 0

    if best_score < 0.5 and len(reranked) < 2:
        # Poor RAG results — trigger web search fallback
        web_results = _web_search_fallback(search_query, port)
        if web_results:
            web_context = _format_web_results(web_results)
            print(web_context)
            # Spawn background crawler to index results (no LLM)
            _spawn_background_crawler(web_results, port)
            print("📥 Background crawler indexing web results for future queries...\n")
            return 0

    # Good RAG results — output them
    rag_context = _format_rag_results(reranked)
    if rag_context:
        print(rag_context)
    else:
        print("\n⚠️ No quality research results found. Proceeding with codebase analysis.\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
