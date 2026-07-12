"""Web search client for fallback injection. Uses DuckDuckGo (no API key needed)."""

import json
import logging
import re
import time
from typing import Optional
from urllib.parse import quote

import httpx

logger = logging.getLogger(__name__)

# DuckDuckGo instant answer endpoint (no auth required)
DUCKDUCKGO_URL = "https://api.duckduckgo.com"

# User agent to avoid blocks
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"


def web_search(
    query: str,
    max_results: int = 3,
    timeout: float = 4.0,
) -> dict:
    """Search the web via DuckDuckGo instant answer API.

    Args:
        query: search query text
        max_results: max results to return (default 3)
        timeout: request timeout in seconds (default 4.0)

    Returns:
        {
            "results": [
                {
                    "title": "...",
                    "url": "...",
                    "snippet": "..."
                },
                ...
            ],
            "error": None  # or error message if search failed
        }
    """
    if not query or not isinstance(query, str):
        return {"results": [], "error": "Invalid query"}

    query = query.strip()
    if not query:
        return {"results": [], "error": "Empty query"}

    try:
        # DuckDuckGo instant answer API, returns JSON with search results
        params = {
            "q": query,
            "format": "json",
            "no_redirect": "1",
            "kl": "us-en",
        }

        headers = {"User-Agent": USER_AGENT}

        client = httpx.Client(timeout=timeout, headers=headers)
        response = client.get(DUCKDUCKGO_URL, params=params)
        response.raise_for_status()

        data = response.json()
        client.close()

        results = []

        # Parse AbstractText if available (instant answer)
        if data.get("AbstractText"):
            results.append({
                "title": data.get("Heading", "Answer"),
                "url": data.get("AbstractURL", ""),
                "snippet": data.get("AbstractText", ""),
            })

        # Parse Related Topics (second-best source)
        for topic in data.get("RelatedTopics", [])[:max_results - len(results)]:
            if isinstance(topic, dict) and topic.get("Text"):
                results.append({
                    "title": topic.get("FirstURL", "").split("/")[-1] or "Result",
                    "url": topic.get("FirstURL", ""),
                    "snippet": topic.get("Text", ""),
                })

        # Fallback: parse Results array if above failed
        if not results:
            for result in data.get("Results", [])[:max_results]:
                if isinstance(result, dict):
                    results.append({
                        "title": result.get("Title", ""),
                        "url": result.get("FirstURL", ""),
                        "snippet": result.get("Text", ""),
                    })

        # Clean up snippets (remove HTML entities, truncate)
        for r in results:
            r["snippet"] = _clean_snippet(r["snippet"])

        return {
            "results": results[:max_results],
            "error": None,
        }

    except httpx.TimeoutException:
        return {
            "results": [],
            "error": f"Web search timed out after {timeout}s",
        }
    except httpx.HTTPError as e:
        logger.warning("Web search HTTP error: %s", e)
        return {
            "results": [],
            "error": f"Web search failed: {e}",
        }
    except (json.JSONDecodeError, KeyError) as e:
        logger.warning("Web search parse error: %s", e)
        return {
            "results": [],
            "error": f"Web search parse failed: {e}",
        }
    except Exception as e:
        logger.error("Unexpected web search error: %s", e, exc_info=True)
        return {
            "results": [],
            "error": f"Web search error: {e}",
        }


def _clean_snippet(text: str) -> str:
    """Clean HTML entities and truncate snippet."""
    if not text:
        return ""

    # Remove HTML entities
    text = text.replace("&nbsp;", " ")
    text = text.replace("&quot;", '"')
    text = text.replace("&#39;", "'")
    text = text.replace("&amp;", "&")
    text = re.sub(r"<[^>]+>", "", text)

    # Remove extra whitespace
    text = re.sub(r"\s+", " ", text).strip()

    # Truncate to ~200 chars
    if len(text) > 200:
        text = text[:197] + "..."

    return text
