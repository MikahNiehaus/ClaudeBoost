"""StackOverflow search for clean-rag.

For "I need the few lines that do X", a top voted or accepted Stack Overflow answer
beats a whole repo (GitHub) or an SEO blog (DuckDuckGo). This searches StackOverflow
via the StackExchange API and returns the accepted answer body with its code, so the
research agent can hand the build agent a real, human voted snippet instead of the
model guessing from memory.

Two calls, because the API keeps questions and answers separate: search/advanced
finds accepted questions, then a single batched /answers call pulls the accepted
answer bodies. No key needed (about 300 requests per day per IP); set
STACKEXCHANGE_KEY in .env for about 10000 per day.

Answer bodies are HTML with code blocks and are attacker controllable free text
(anyone can post an answer), so they go through _clean_code (is_html=True), which
keeps the code and strips the invisible injection characters, and the caller labels
them untrusted, same as web results.
"""

import logging
import os

import httpx

from .web_search import _clean_code, _clean_snippet

logger = logging.getLogger(__name__)

SEARCH_URL = "https://api.stackexchange.com/2.3/search/advanced"
ANSWERS_URL = "https://api.stackexchange.com/2.3/answers/{ids}"
SITE = "stackoverflow"


def _base_params():
    params = {"site": SITE}
    key = os.environ.get("STACKEXCHANGE_KEY")
    if key:
        params["key"] = key
    return params


def stackoverflow_search(query, max_results=3, timeout=8.0):
    """Search StackOverflow, return accepted answers with their code.

    Returns {"results": [{title, question_url, score, answer_score, answer_url,
    answer}], "error": None or str}. answer is the accepted answer body with code
    preserved.
    """
    if not query or not isinstance(query, str) or not query.strip():
        return {"results": [], "error": "Invalid query"}

    n = max(1, min(int(max_results), 10))
    base = _base_params()

    try:
        with httpx.Client(timeout=timeout) as client:
            qr = client.get(SEARCH_URL, params={
                **base,
                "q": query.strip(),
                "accepted": "True",     # only questions that have an accepted answer
                "sort": "votes",
                "order": "desc",
                "filter": "withbody",   # default filter omits bodies entirely
                "pagesize": n,
            })
            qr.raise_for_status()
            questions = qr.json().get("items", [])
            if not questions:
                return {"results": [], "error": None}

            # One batched call for all the accepted answers, not one per question.
            ans_ids = [str(q["accepted_answer_id"]) for q in questions if q.get("accepted_answer_id")]
            answers = {}
            if ans_ids:
                ar = client.get(
                    ANSWERS_URL.format(ids=";".join(ans_ids)),
                    params={**base, "sort": "votes", "order": "desc", "filter": "withbody"},
                )
                ar.raise_for_status()
                for a in ar.json().get("items", []):
                    answers[a.get("answer_id")] = a

        results = []
        for q in questions:
            aid = q.get("accepted_answer_id")
            a = answers.get(aid, {})
            results.append({
                "title": _clean_snippet(q.get("title", "")),
                "question_url": q.get("link", ""),
                "score": q.get("score", 0),
                "answer_score": a.get("score", 0),
                "answer_url": (q.get("link", "") + f"#{aid}") if aid else "",
                "answer": _clean_code(a.get("body", ""), is_html=True),
            })
        return {"results": results, "error": None}

    except httpx.TimeoutException:
        return {"results": [], "error": f"StackOverflow search timed out after {timeout}s"}
    except httpx.HTTPStatusError as e:
        return {"results": [], "error": f"StackOverflow search failed: HTTP {e.response.status_code}. "
                                        "If this is a quota error, set STACKEXCHANGE_KEY in .env."}
    except httpx.HTTPError as e:
        logger.warning("StackOverflow search HTTP error: %s", e)
        return {"results": [], "error": f"StackOverflow search failed: {e}"}
    except Exception as e:  # noqa: BLE001
        logger.error("Unexpected StackOverflow search error: %s", e, exc_info=True)
        return {"results": [], "error": f"StackOverflow search error: {e}"}
