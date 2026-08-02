"""Web search client for fallback injection. Uses DuckDuckGo (no API key needed)."""

import html
import logging
import re
import unicodedata
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# DuckDuckGo instant answer endpoint (no auth required). Only returns results
# for factual/definitional queries ("capital of France") — confirmed by
# direct call to return {"results": [], "error": None} for how-to queries
# like "make flappy bird game html". Kept as the first attempt since it's
# faster when it does have an answer.

# DuckDuckGo's HTML results page (html.duckduckgo.com), no API key needed.
# Used as fallback when the Instant Answer API returns nothing, since it
# returns real search results instead of only factual instant-answers.
DUCKDUCKGO_HTML_URL = "https://html.duckduckgo.com/html/"

# User agent to avoid blocks

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
    """Search the web via DuckDuckGo.

    Transport is `ddgs`, the maintained DuckDuckGo client. What used to live
    here was ~140 lines that hit the Instant Answer API, fell through to
    regex scraping html.duckduckgo.com's result markup, and hand unwrapped its
    `uddg=` redirect parameter. That broke every time DuckDuckGo touched their
    HTML, which is often, and the breakage was silent: the regex simply matched
    nothing and the search returned no results.

    What stays here is the part that is actually ours: source ranking, so
    GitHub and StackOverflow come before content farms, and snippet
    sanitizing, because these strings reach a model's context and homoglyphs
    and bidi controls survive plain HTML stripping.

    Returns:
        {"results": [{"title", "url", "snippet"}, ...], "error": None | str}
    """
    if not query or not isinstance(query, str):
        return {"results": [], "error": "Invalid query"}

    query = query.strip()
    if not query:
        return {"results": [], "error": "Empty query"}

    try:
        from ddgs import DDGS
    except ImportError:
        logger.warning("ddgs is not installed, web search unavailable")
        return {"results": [], "error": "ddgs not installed"}

    try:
        # ddgs owns backend rotation and the HTML shape. Ask for more than we
        # need so source ranking has something to actually reorder: trimming
        # to max_results before ranking would make the ranking decorative.
        raw = DDGS(timeout=timeout).text(
            query,
            region="us-en",
            backend="auto",
            max_results=max(max_results * 3, 10),
        )
    except Exception as e:
        # ddgs raises its own exception types for rate limits and timeouts.
        # Catching broadly on purpose: a failed web search is a degraded
        # answer, never a failed request.
        logger.warning("Web search failed: %s: %s", type(e).__name__, e)
        return {"results": [], "error": f"Web search failed: {e}"}

    results = []
    for item in raw or []:
        url = item.get("href") or ""
        if not url:
            continue
        results.append({
            "title": _clean_snippet(item.get("title") or ""),
            "url": url,
            "snippet": _clean_snippet(item.get("body") or ""),
        })

    if not results:
        return {"results": [], "error": None}

    return {"results": _rank_by_source(results)[:max_results], "error": None}


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


def _clean_code(text: str, is_html: bool = False, max_chars: int = 40000) -> str:
    """Sanitize a code file or an answer body for a model's context without wrecking it.

    _clean_snippet collapses whitespace, which is fine for a prose snippet and fatal
    for code, it flattens every newline and indent. This is the version for a
    fetched source file or a Stack Overflow answer: same injection defense (fold
    homoglyphs with NFKC, strip the invisible zero width, bidi, and control chars a
    payload hides in), but it NEVER collapses the whitespace that carries the code's
    structure. Cap by size and truncate whole, do not cut mid line.
    """
    if not text:
        return ""

    if is_html:
        # Pull the text out of <pre> blocks first, keeping their newlines, and fence
        # them, then strip the remaining tags from the surrounding prose. This keeps
        # the code an answer is about instead of flattening it into one line.
        parts = []
        last = 0
        for m in re.finditer(r"<pre[^>]*>(.*?)</pre>", text, re.DOTALL | re.IGNORECASE):
            parts.append(re.sub(r"<[^>]+>", "", text[last:m.start()]))
            parts.append("\n```\n" + re.sub(r"<[^>]+>", "", m.group(1)).strip("\n") + "\n```\n")
            last = m.end()
        parts.append(re.sub(r"<[^>]+>", "", text[last:]))
        text = html.unescape("".join(parts))

    text = unicodedata.normalize("NFKC", text)
    # Zero width, bidi overrides, word joiners, BOM: the invisible injection vector.
    text = re.sub(r"[​-‏‪-‮⁠-⁤﻿]", "", text)
    # Any other control characters, keeping tab, newline, and carriage return.
    text = "".join(c for c in text if unicodedata.category(c) != "Cc" or c in "\t\n\r")

    if len(text) > max_chars:
        text = text[:max_chars] + "\n... [truncated]"

    return text
