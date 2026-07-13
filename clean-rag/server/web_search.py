"""Web search client for fallback injection. Uses DuckDuckGo (no API key needed)."""

import json
import logging
import re
import time
import unicodedata
from typing import Optional
from urllib.parse import quote, urlparse

import httpx

logger = logging.getLogger(__name__)

# DuckDuckGo instant answer endpoint (no auth required). Only returns results
# for factual/definitional queries ("capital of France") — confirmed by
# direct call to return {"results": [], "error": None} for how-to queries
# like "make flappy bird game html". Kept as the first attempt since it's
# faster when it does have an answer.
DUCKDUCKGO_URL = "https://api.duckduckgo.com"

# DuckDuckGo's HTML results page (html.duckduckgo.com), no API key needed.
# Used as fallback when the Instant Answer API returns nothing, since it
# returns real search results instead of only factual instant-answers.
DUCKDUCKGO_HTML_URL = "https://html.duckduckgo.com/html/"

# User agent to avoid blocks
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

# Source quality ranking. There was no filtering here at all before, results
# came back in DuckDuckGo's raw order, which routinely put SEO content farms
# above primary sources. Primary sources first, content farms last.
PREFERRED_DOMAINS = (
    "github.com",
    "githubusercontent.com",
    "stackoverflow.com",
    "stackexchange.com",
    "developer.mozilla.org",
    "docs.python.org",
    "react.dev",
    "developer.chrome.com",
    "web.dev",
    "arxiv.org",
)

# Not banned, just ranked below anything else. These are scraped, ad heavy, and
# frequently wrong on the details, but they occasionally cover a topic nothing
# else does, so dropping them outright loses real coverage.
DEMOTED_DOMAINS = (
    "w3schools.com",
    "geeksforgeeks.org",
    "tutorialspoint.com",
    "javatpoint.com",
    "codegrepper.com",
)


def _source_rank(url: str) -> int:
    """Lower is better. Used to sort results before truncating to max_results."""
    host = urlparse(url).netloc.lower()
    if any(host == d or host.endswith("." + d) for d in PREFERRED_DOMAINS):
        return 0
    if any(host == d or host.endswith("." + d) for d in DEMOTED_DOMAINS):
        return 2
    return 1


def _rank_by_source(results: list) -> list:
    """Sort by source quality, keeping the engine's own relevance order within a tier."""
    return sorted(results, key=lambda r: _source_rank(r.get("url", "")))


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

        if results:
            return {
                "results": _rank_by_source(results)[:max_results],
                "error": None,
            }

        # Instant Answer API returned nothing (expected for how-to/tutorial
        # queries, confirmed by direct test) — fall through to HTML search,
        # which returns real results for this query class.
        return _web_search_html(query, max_results, timeout)

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


def _web_search_html(query: str, max_results: int, timeout: float) -> dict:
    """Search DuckDuckGo's HTML results page directly, no API key needed.

    The Instant Answer API only returns results for factual/definitional
    queries. This hits the actual search results page and parses out result
    blocks with regex (no HTML parser dependency), which works for the
    tutorial/how-to queries the Instant Answer API leaves empty.
    """
    try:
        headers = {"User-Agent": USER_AGENT}
        client = httpx.Client(timeout=timeout, headers=headers)
        response = client.post(DUCKDUCKGO_HTML_URL, data={"q": query})
        response.raise_for_status()
        html = response.text
        client.close()

        # Each result is a <a class="result__a" href="...">title</a> followed
        # by a <a class="result__snippet">snippet</a>. DuckDuckGo's HTML
        # results wrap the real target URL in a redirect param (uddg=).
        result_blocks = re.findall(
            r'result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>.*?result__snippet[^>]*>(.*?)</a>',
            html,
            re.DOTALL,
        )

        # Take a wider slice than we need. Source ranking below can only promote
        # a primary source into the top N if it actually fetched that far down.
        candidate_limit = max(max_results * 4, 12)

        results = []
        for raw_url, raw_title, raw_snippet in result_blocks[:candidate_limit]:
            url = _extract_redirect_target(raw_url)
            title = _clean_snippet(raw_title)
            snippet = _clean_snippet(raw_snippet)
            if title or snippet:
                results.append({"title": title or "Result", "url": url, "snippet": snippet})

        if not results:
            logger.warning("HTML search returned no parseable results for query: %s", query)

        return {"results": _rank_by_source(results)[:max_results], "error": None}

    except httpx.TimeoutException:
        return {"results": [], "error": f"HTML web search timed out after {timeout}s"}
    except httpx.HTTPError as e:
        logger.warning("HTML web search HTTP error: %s", e)
        return {"results": [], "error": f"HTML web search failed: {e}"}
    except Exception as e:
        logger.error("Unexpected HTML web search error: %s", e, exc_info=True)
        return {"results": [], "error": f"HTML web search error: {e}"}


def _extract_redirect_target(raw_url: str) -> str:
    """DuckDuckGo HTML result links are redirects with the real URL in uddg=."""
    match = re.search(r"uddg=([^&]+)", raw_url)
    if match:
        from urllib.parse import unquote
        return unquote(match.group(1))
    return raw_url


def _clean_snippet(text: str) -> str:
    """Clean HTML entities, strip hidden characters, truncate.

    These snippets get injected straight into a model's context, so they're an
    indirect prompt injection surface. Stripping HTML tags isn't enough on its
    own: the standard trick is to hide instructions in zero width characters or
    homoglyphs, which sail right through tag removal and stay invisible to
    anyone eyeballing the output. NFKC folds homoglyphs to their canonical
    forms, and the explicit strip below kills the zero width and bidi control
    characters NFKC leaves alone.

    This is one layer, not a fix. The injected block is also labelled as
    untrusted reference data (see the hook formatters), because sanitizing
    text you're going to feed to a model is leaky by nature.
    """
    if not text:
        return ""

    # Remove HTML entities
    text = text.replace("&nbsp;", " ")
    text = text.replace("&quot;", '"')
    text = text.replace("&#39;", "'")
    text = text.replace("&amp;", "&")
    text = re.sub(r"<[^>]+>", "", text)

    # Fold homoglyphs and lookalike forms to canonical characters
    text = unicodedata.normalize("NFKC", text)

    # Zero width spaces/joiners, BOM, and the bidi overrides used to visually
    # reorder text so what renders isn't what the model actually reads
    text = re.sub(r"[​-‏‪-‮⁠-⁤﻿]", "", text)

    # Any other invisible control characters, keeping normal whitespace
    text = "".join(c for c in text if unicodedata.category(c) != "Cc" or c in "\t\n\r")

    # Remove extra whitespace
    text = re.sub(r"\s+", " ", text).strip()

    # Truncate to ~200 chars
    if len(text) > 200:
        text = text[:197] + "..."

    return text
