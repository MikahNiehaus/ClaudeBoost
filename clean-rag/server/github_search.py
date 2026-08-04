"""GitHub repository search for clean-rag.

DuckDuckGo (web_search.py) surfaces github.com PAGES it happened to index, ranked
first, which is fine for "does a README exist" but weak for "find the best
maintained repo to adopt": no stars, no recency, no code, and the HTML scrape gets
rate limited. This hits GitHub's own search API instead, so the research agent can
find and rank real repos, which is what makes the "lean toward GitHub" rule real.

No key required: unauthenticated search works at 10 requests per minute. Set
GITHUB_TOKEN in .env to raise that to 30 per minute. The token is optional and read
from the environment (config.py already loads .env).

A repo description is attacker controllable free text going into a model's context,
so it is a prompt injection surface, the same class as a web snippet. It runs
through _clean_snippet (NFKC fold, zero width and bidi stripping, control char
removal), and whatever injects it should label it untrusted, same as web results.
"""

import base64
import logging
import os
from datetime import datetime, timezone
from urllib.parse import quote

import httpx

from .web_search import _clean_code, _clean_snippet

logger = logging.getLogger(__name__)

GITHUB_SEARCH_URL = "https://api.github.com/search/repositories"
GITHUB_CONTENTS_URL = "https://api.github.com/repos/{owner}/{repo}/contents/{path}"

# GitHub rejects any request with no User-Agent (a flat 403 that looks like a rate
# limit but is not). Send an identifying one, not a browser string.
_USER_AGENT = "clean-rag-github-search"
_API_VERSION = "2022-11-28"

# The only sort values the API accepts; anything else means best match relevance,
# which we get by omitting the param.
_SORTS = {"stars", "forks", "updated", "help-wanted-issues"}


def _headers(token):
    h = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": _API_VERSION,
        "User-Agent": _USER_AGENT,
    }
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


def _rate_limit_error(resp):
    """A user facing message when GitHub rate limited us, else None.

    Do not branch on the status code alone: primary and secondary limits both come
    back as 403 or 429. Branch on which headers are present. retry-after means the
    secondary (abuse) limit; remaining 0 means the primary limit.
    """
    retry_after = resp.headers.get("retry-after")
    if retry_after:
        return (f"GitHub secondary rate limit hit; wait {retry_after}s. Set "
                "GITHUB_TOKEN in .env and avoid rapid repeated searches.")
    if resp.headers.get("x-ratelimit-remaining") == "0":
        reset = resp.headers.get("x-ratelimit-reset", "")
        wait = ""
        if reset.isdigit():
            secs = int(reset) - int(datetime.now(timezone.utc).timestamp())
            if secs > 0:
                wait = f", resets in {secs}s"
        return (f"GitHub API rate limited (remaining 0{wait}). Set GITHUB_TOKEN in "
                ".env for 30 per minute instead of 10 for search.")
    return None


def github_search(query, max_results=5, sort="stars", timeout=6.0):
    """Search GitHub repositories, best maintained first.

    Returns {"results": [{full_name, url, stars, forks, language, updated,
    archived, description}], "error": None or str}. sort="stars" ranks by
    popularity; pass sort="" for GitHub's own relevance ordering.
    """
    if not query or not isinstance(query, str) or not query.strip():
        return {"results": [], "error": "Invalid query"}

    per_page = max(1, min(int(max_results), 100))
    params = {"q": query.strip(), "order": "desc", "per_page": per_page}
    if sort in _SORTS:
        params["sort"] = sort

    token = os.environ.get("GITHUB_TOKEN")

    try:
        with httpx.Client(timeout=timeout, headers=_headers(token)) as client:
            resp = client.get(GITHUB_SEARCH_URL, params=params)

        # Check rate limiting before raise_for_status so we can give the useful
        # "add a token" message instead of a bare HTTP error.
        if resp.status_code in (403, 429):
            msg = _rate_limit_error(resp)
            if msg:
                return {"results": [], "error": msg}
        resp.raise_for_status()

        data = resp.json()
        results = []
        for item in data.get("items", [])[:per_page]:
            results.append({
                "full_name": item.get("full_name", ""),
                "url": item.get("html_url", ""),
                "stars": item.get("stargazers_count", 0),
                "forks": item.get("forks_count", 0),
                "language": item.get("language") or "",
                "updated": item.get("updated_at", ""),
                "archived": bool(item.get("archived")),
                "description": _clean_snippet(item.get("description") or ""),
            })
        return {"results": results, "error": None}

    except httpx.TimeoutException:
        return {"results": [], "error": f"GitHub search timed out after {timeout}s"}
    except httpx.HTTPStatusError as e:
        msg = _rate_limit_error(e.response) or f"GitHub search failed: HTTP {e.response.status_code}"
        return {"results": [], "error": msg}
    except httpx.HTTPError as e:
        logger.warning("GitHub search HTTP error: %s", e)
        return {"results": [], "error": f"GitHub search failed: {e}"}
    except Exception as e:  # noqa: BLE001
        logger.error("Unexpected GitHub search error: %s", e, exc_info=True)
        return {"results": [], "error": f"GitHub search error: {e}"}


def github_fetch_file(owner, repo, path, ref=None, timeout=8.0, max_chars=40000):
    """Fetch one file's text from a public GitHub repo, via the Contents API.

    Uses the Contents API rather than raw.githubusercontent so it works without
    knowing the default branch (omit ref and GitHub uses it). Returns
    {"content": str, "url": str, "size": int, "truncated": bool, "error": None or str}.
    The content is untrusted reference data: it runs through _clean_code (which keeps
    the code intact and strips only the invisible injection characters), and whatever
    injects it should label it untrusted, same as web results. Public repos need no
    token; a private repo needs GITHUB_TOKEN.
    """
    for name, val in (("owner", owner), ("repo", repo), ("path", path)):
        if not val or not isinstance(val, str) or not val.strip():
            return {"content": "", "url": "", "error": f"{name} is required"}
    if ".." in path or "://" in path:
        return {"content": "", "url": "", "error": "invalid path"}

    url = GITHUB_CONTENTS_URL.format(
        owner=quote(owner.strip(), safe=""),
        repo=quote(repo.strip(), safe=""),
        path=quote(path.strip().lstrip("/"), safe="/"),
    )
    params = {"ref": ref} if ref else {}
    token = os.environ.get("GITHUB_TOKEN")

    try:
        with httpx.Client(timeout=timeout, headers=_headers(token)) as client:
            resp = client.get(url, params=params)

        if resp.status_code in (403, 429):
            msg = _rate_limit_error(resp)
            if msg:
                return {"content": "", "url": "", "error": msg}
        if resp.status_code == 404:
            return {"content": "", "url": "", "error": "not found (check owner, repo, path, ref)"}
        resp.raise_for_status()

        data = resp.json()
        if isinstance(data, list):
            return {"content": "", "url": "", "error": "that path is a directory, name a file"}
        # A file over 1MB comes back with empty content and a download_url instead.
        if data.get("encoding") != "base64" or not data.get("content"):
            return {
                "content": "", "url": data.get("html_url", ""),
                "error": "file too large for the contents API; fetch its download_url directly: "
                         + (data.get("download_url") or ""),
            }
        raw = base64.b64decode(data["content"])
        text = _clean_code(raw.decode("utf-8", errors="replace"), is_html=False, max_chars=max_chars)
        return {
            "content": text,
            "url": data.get("html_url", ""),
            "size": data.get("size", 0),
            "truncated": len(text) >= max_chars,
            "error": None,
        }

    except httpx.TimeoutException:
        return {"content": "", "url": "", "error": f"GitHub file fetch timed out after {timeout}s"}
    except httpx.HTTPStatusError as e:
        msg = _rate_limit_error(e.response) or f"GitHub file fetch failed: HTTP {e.response.status_code}"
        return {"content": "", "url": "", "error": msg}
    except httpx.HTTPError as e:
        logger.warning("GitHub file fetch HTTP error: %s", e)
        return {"content": "", "url": "", "error": f"GitHub file fetch failed: {e}"}
    except Exception as e:  # noqa: BLE001
        logger.error("Unexpected GitHub file fetch error: %s", e, exc_info=True)
        return {"content": "", "url": "", "error": f"GitHub file fetch error: {e}"}
