"""Wikipedia search for clean-rag, the human curated general knowledge tier.

For a fact or a concept, a Wikipedia article is human edited and reviewed, which is
a different quality tier than a DuckDuckGo web scrape. Free, no key. One call to the
MediaWiki action API searches and returns each hit's plain text intro extract.

Set a real, descriptive User-Agent or Wikimedia returns 403. On any rate limit or
error this returns a clean string, not a raise, so the caller's fallback ladder
(another source, or the model's own reasoning) just proceeds. If the tier is used
up, the AI can always fall back to itself.
"""

import logging

import httpx

from .web_search import _clean_code

logger = logging.getLogger(__name__)

WIKI_API = "https://en.wikipedia.org/w/api.php"

# Wikimedia policy requires a descriptive User-Agent (tool, version, contact). A
# missing or browser mimicking one gets a hard 403 and the harshest throttle tier.
USER_AGENT = "clean-rag/1.0 (grounded research tool; https://github.com/) httpx"


def wikipedia_search(query, max_results=3, timeout=6.0, max_chars=1500):
    """Search Wikipedia, return each hit's plain text intro extract.

    Returns {"results": [{title, url, extract}], "error": None or str}, ranked by
    the search relevance order.
    """
    if not query or not isinstance(query, str) or not query.strip():
        return {"results": [], "error": "Invalid query"}

    n = max(1, min(int(max_results), 10))
    params = {
        "action": "query",
        "format": "json",
        "generator": "search",
        "gsrsearch": query.strip(),
        "gsrlimit": n,
        "prop": "extracts|info",
        "exintro": 1,
        "explaintext": 1,
        "exlimit": "max",
        "inprop": "url",
        "redirects": 1,
    }

    try:
        with httpx.Client(timeout=timeout, headers={"User-Agent": USER_AGENT}) as client:
            resp = client.get(WIKI_API, params=params)
        resp.raise_for_status()
        data = resp.json()

        if data.get("error"):
            info = data["error"].get("info", "unknown")
            return {"results": [], "error": f"Wikipedia API error: {info}"}

        pages = (data.get("query") or {}).get("pages") or {}
        # pages is a dict keyed by pageid; sort by the search rank index, since dict
        # order is not the relevance order.
        ordered = sorted(pages.values(), key=lambda p: p.get("index", 1_000_000))

        results = []
        for p in ordered:
            extract = p.get("extract")
            if not extract:
                continue  # a page with no intro extract, skip rather than KeyError
            results.append({
                "title": p.get("title", ""),
                "url": p.get("fullurl", ""),
                "extract": _clean_code(extract, is_html=False, max_chars=max_chars),
            })
        return {"results": results[:n], "error": None}

    except httpx.TimeoutException:
        return {"results": [], "error": f"Wikipedia search timed out after {timeout}s"}
    except httpx.HTTPStatusError as e:
        code = e.response.status_code
        hint = " (rate limited)" if code in (429, 503) else ""
        return {"results": [], "error": f"Wikipedia search unavailable: HTTP {code}{hint}"}
    except httpx.HTTPError as e:
        logger.warning("Wikipedia search HTTP error: %s", e)
        return {"results": [], "error": f"Wikipedia search failed: {e}"}
    except Exception as e:  # noqa: BLE001
        logger.error("Unexpected Wikipedia search error: %s", e, exc_info=True)
        return {"results": [], "error": f"Wikipedia search error: {e}"}
