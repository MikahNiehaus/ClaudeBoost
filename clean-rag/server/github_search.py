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
import html
import logging
import os
import re
import time
from datetime import datetime, timezone
from urllib.parse import quote

import httpx

from .web_search import _clean_code, _clean_snippet

logger = logging.getLogger(__name__)

GITHUB_SEARCH_URL = "https://api.github.com/search/repositories"
GITHUB_CODE_SEARCH_URL = "https://api.github.com/search/code"
GITHUB_CONTENTS_URL = "https://api.github.com/repos/{owner}/{repo}/contents/{path}"

# grep.app indexes over a million public repos and needs no key, which makes it
# the fallback when GITHUB_TOKEN is unset (GitHub's own code search API returns
# 401 without one). Measured caveat: it throttles hard and answers a throttle
# with an HTML page, not JSON, so it is a fallback and not the default.
GREP_APP_URL = "https://grep.app/api/search"

_TAG_RE = re.compile(r"<[^>]+>")

# Measured, not guessed: a successful unauthenticated repository search takes
# ~7s. The old 6.0s default therefore timed out on the HAPPY path, and returned
# {"results": [], "error": "timed out"} — which a caller reads as "nothing
# exists" rather than "the search never ran". That is the worst failure mode for
# a swipe check, so the floor is well clear of real latency now.
DEFAULT_TIMEOUT = 20.0

# GitHub's search API returns a transient 5xx under load often enough that one
# attempt is not a real attempt. Retries are only for transient failures; a 4xx
# is answered, not retried.
_MAX_ATTEMPTS = 3
_RETRY_STATUS = {502, 503, 504}

# Backoff before attempts 2 and 3. Without a wait, three attempts land inside a
# second and re-ask a server that is busy or throttling for the same reason it
# just refused, which is not a retry, it is the same request three times.
_BACKOFF_S = (1.5, 4.0)

# Unauthenticated search answers a throttle with 504, not 403, so the rate limit
# headers _rate_limit_error looks for are absent and the useful advice never
# reaches the caller. Say it on a persistent 5xx too when no token is set.
_NO_TOKEN_HINT = (" Unauthenticated search is limited to 10 requests per minute and "
                  "GitHub answers a throttle with 5xx rather than 429, so this is the "
                  "likely cause. Set GITHUB_TOKEN in clean-rag/.env for 30 per minute.")

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


def _get_with_retry(url, params, token, timeout, label, headers=None):
    """GET with retries on transient failures only. Returns (resp, error_str).

    Exactly one of the two is set. A 4xx is a real answer and is returned as a
    response for the caller to interpret; only a timeout, a transport error, or
    a 5xx in _RETRY_STATUS is retried. Pass headers to override the defaults
    (code search needs a different Accept to get match fragments back).
    """
    last_err = None
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        if attempt > 1:
            time.sleep(_BACKOFF_S[min(attempt - 2, len(_BACKOFF_S) - 1)])
        try:
            with httpx.Client(timeout=timeout, headers=headers or _headers(token)) as client:
                resp = client.get(url, params=params)
            if resp.status_code in _RETRY_STATUS and attempt < _MAX_ATTEMPTS:
                last_err = f"HTTP {resp.status_code}"
                logger.warning("%s transient %s, attempt %d of %d",
                               label, last_err, attempt, _MAX_ATTEMPTS)
                continue
            return resp, None
        except httpx.TimeoutException:
            last_err = f"timed out after {timeout}s"
        except httpx.HTTPError as e:
            last_err = f"{type(e).__name__}: {e}"
        logger.warning("%s attempt %d of %d failed: %s",
                       label, attempt, _MAX_ATTEMPTS, last_err)
    err = f"{label} failed after {_MAX_ATTEMPTS} attempts ({last_err})"
    if not token:
        err += _NO_TOKEN_HINT
    return None, err


def _parse_json(resp, label):
    """Return (data, error_str). GitHub answers 403 and 451 with an HTML body,
    so .json() raising is a normal outcome, not an unexpected one. Reporting
    'Expecting value: line 1 column 1' tells the caller nothing about why."""
    try:
        return resp.json(), None
    except ValueError:
        body = (resp.text or "")[:200].replace("\n", " ")
        return None, (f"{label} returned HTTP {resp.status_code} with a non-JSON body. "
                      f"First 200 chars: {body!r}")


def github_search(query, max_results=5, sort="stars", timeout=DEFAULT_TIMEOUT):
    """Search GitHub repositories, best maintained first.

    Returns {"results": [{full_name, url, stars, forks, language, updated,
    archived, description}], "error": None or str}. sort="stars" ranks by
    popularity; pass sort="" for GitHub's own relevance ordering.

    This finds REPOS, matching name, description, README and topics. It cannot
    find a file that contains a given line of code; that is github_code_search.
    Looking for an implementation of a pattern here returns nothing however good
    the query, because a repo description does not contain the pattern.
    """
    if not query or not isinstance(query, str) or not query.strip():
        return {"results": [], "error": "Invalid query"}

    per_page = max(1, min(int(max_results), 100))
    params = {"q": query.strip(), "order": "desc", "per_page": per_page}
    if sort in _SORTS:
        params["sort"] = sort

    token = os.environ.get("GITHUB_TOKEN")

    resp, err = _get_with_retry(GITHUB_SEARCH_URL, params, token, timeout, "GitHub search")
    if err:
        return {"results": [], "error": err}

    # Check rate limiting before anything else so we can give the useful
    # "add a token" message instead of a bare HTTP error.
    if resp.status_code in (403, 429):
        msg = _rate_limit_error(resp)
        if msg:
            return {"results": [], "error": msg}
    if resp.status_code >= 400:
        data, _ = _parse_json(resp, "GitHub search")
        detail = (data or {}).get("message", "")
        msg = (f"GitHub search failed: HTTP {resp.status_code}"
               + (f" ({detail})" if detail else ""))
        if resp.status_code in _RETRY_STATUS and not token:
            msg += _NO_TOKEN_HINT
        return {"results": [], "error": msg}

    data, err = _parse_json(resp, "GitHub search")
    if err:
        return {"results": [], "error": err}

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
    return {"results": results, "error": None, "total_count": data.get("total_count", 0)}


def _strip_html(s):
    """grep.app returns each match as an HTML table row with <mark> tags round
    the hit. Take the text. Callers sanitize it afterwards; this only unwraps."""
    return html.unescape(_TAG_RE.sub("", s or "")).strip()


def grep_app_code_search(query, max_results=10, language=None, timeout=DEFAULT_TIMEOUT):
    """Search public GitHub file contents via grep.app. No key required.

    The free path, used when GITHUB_TOKEN is unset. Endpoint and response shape
    taken from a working client (popovicn/grepgithub, fetch_grep_app), not from
    a guess: GET /api/search with q, and matches under
    data["hits"]["hits"][i]["content"]["snippet"] as HTML.

    Returns the same shape as github_code_search plus source="grep.app".
    """
    if not query or not isinstance(query, str) or not query.strip():
        return {"results": [], "total_count": 0, "source": "grep.app",
                "error": "Invalid query"}

    per_page = max(1, min(int(max_results), 100))
    params = {"q": query.strip()}
    if language:
        params["f.lang"] = language

    resp, err = _get_with_retry(GREP_APP_URL, params, None, timeout,
                                "grep.app code search")
    if err:
        return {"results": [], "total_count": 0, "source": "grep.app", "error": err}

    if resp.status_code == 429:
        return {"results": [], "total_count": 0, "source": "grep.app", "error":
                "grep.app rate limited this request (HTTP 429). It throttles "
                "aggressively and has no key to raise the limit."}
    if resp.status_code >= 400:
        return {"results": [], "total_count": 0, "source": "grep.app",
                "error": f"grep.app code search failed: HTTP {resp.status_code}"}

    data, err = _parse_json(resp, "grep.app code search")
    if err:
        return {"results": [], "total_count": 0, "source": "grep.app", "error": err}

    hits = ((data.get("hits") or {}).get("hits") or [])
    results = []
    for hit in hits[:per_page]:
        snippet = ((hit.get("content") or {}).get("snippet")) or ""
        text = _strip_html(snippet)
        results.append({
            "repo": ((hit.get("repo") or {}).get("raw")) or "",
            "path": ((hit.get("path") or {}).get("raw")) or "",
            "url": "",  # grep.app does not return a blob URL; build one if needed
            "stars": 0,  # not provided, so do not invent a number
            "matches": [_clean_code(text)] if text else [],
        })
    total = ((data.get("facets") or {}).get("count"))
    return {"results": results, "source": "grep.app",
            "total_count": total if isinstance(total, int) else len(results),
            "error": None}


def github_code_search(query, max_results=10, timeout=DEFAULT_TIMEOUT, language=None):
    """Search FILE CONTENTS across public GitHub. Requires GITHUB_TOKEN.

    This is the route a swipe check actually needs: it answers "who has already
    written this line" rather than "whose README mentions this topic". Repository
    search cannot answer that at all, and returning nothing was previously
    indistinguishable from nothing existing.

    Supports GitHub code search qualifiers in the query: language:, repo:,
    org:, path:, filename:, extension:, in:file, NOT, OR, "exact phrase".

    Returns {"results": [{repo, path, url, stars, matches}], "error": None|str,
    "total_count": int}. `matches` are the matched line fragments GitHub returns,
    sanitized; they are untrusted reference text like any other web content.
    """
    if not query or not isinstance(query, str) or not query.strip():
        return {"results": [], "error": "Invalid query"}

    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        # GitHub's code search API returns 401 without a token, so fall back to
        # grep.app rather than returning an empty list. An empty list reads as
        # "no code like this exists on GitHub", which is a false and expensive
        # thing for a swipe check to conclude.
        out = grep_app_code_search(query, max_results=max_results,
                                   language=language, timeout=timeout)
        if out["results"] or not out.get("error"):
            return out
        # Both paths are unavailable. Now the user genuinely has to act, so say
        # so with a distinct flag a caller can branch on, not just prose.
        out["error"] = (f"No code search available. grep.app: {out['error']} "
                        "GitHub code search needs GITHUB_TOKEN in clean-rag/.env "
                        "(a classic token with public_repo scope is enough), then "
                        "restart the server.")
        out["needs_user_action"] = True
        return out

    per_page = max(1, min(int(max_results), 100))
    params = {"q": query.strip(), "per_page": per_page}

    # text-match returns the matched fragments, which is the whole point: a path
    # without the matching line means opening every file to find out why it hit.
    headers = _headers(token)
    headers["Accept"] = "application/vnd.github.text-match+json"

    resp, err = _get_with_retry(GITHUB_CODE_SEARCH_URL, params, token, timeout,
                                "GitHub code search", headers=headers)
    if err:
        return {"results": [], "total_count": 0, "error": err}

    if resp.status_code in (403, 429):
        msg = _rate_limit_error(resp)
        if msg:
            return {"results": [], "total_count": 0, "error": msg}
    if resp.status_code == 401:
        # A configured but rejected token is squarely a user action. Flag it so a
        # caller can branch on it rather than having to read the prose.
        return {"results": [], "total_count": 0, "source": "github",
                "needs_user_action": True, "error":
                "GitHub rejected GITHUB_TOKEN (HTTP 401). The token is missing, "
                "expired, or lacks public_repo scope."}
    if resp.status_code >= 400:
        data, _ = _parse_json(resp, "GitHub code search")
        detail = (data or {}).get("message", "")
        return {"results": [], "total_count": 0, "error":
                f"GitHub code search failed: HTTP {resp.status_code}"
                + (f" ({detail})" if detail else "")}

    data, err = _parse_json(resp, "GitHub code search")
    if err:
        return {"results": [], "total_count": 0, "error": err}

    results = []
    for item in data.get("items", [])[:per_page]:
        repo = item.get("repository") or {}
        fragments = [
            _clean_code(m.get("fragment", ""))
            for m in (item.get("text_matches") or [])
            if m.get("fragment")
        ]
        results.append({
            "repo": repo.get("full_name", ""),
            "path": item.get("path", ""),
            "url": item.get("html_url", ""),
            "stars": repo.get("stargazers_count", 0),
            "matches": fragments,
        })
    # total_count is the honest signal a swipe check needs: 0 results with
    # total_count 4992 means the query matched plenty and the page was empty,
    # which is a different problem from nothing existing.
    return {"results": results, "source": "github",
            "total_count": data.get("total_count", 0), "error": None}


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
