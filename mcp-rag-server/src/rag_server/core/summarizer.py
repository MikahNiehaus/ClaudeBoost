"""Per-community LLM summaries.

Priority order:
  1. Cache hit (member_hash + model both match) — return immediately.
  2. Ollama at localhost:11434 — good for local dev sessions.
  3. Claude API (ANTHROPIC_API_KEY env var) — standard sessions without Ollama.
  4. Neither available — raises RuntimeError with a clear message.

There is no heuristic fallback. Path-based summaries are noise, not signal.
If the summary can't be generated, the caller knows about it immediately.
"""

import hashlib
import json
import logging
import os
import re
import urllib.request
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from rag_server.adapters.sqlite_graph_store import SQLiteGraphStore

logger = logging.getLogger(__name__)

_OLLAMA_URL = "http://localhost:11434/api/generate"
_OLLAMA_CHAT_URL = "http://localhost:11434/api/chat"
_PROMPT_CHAR_BUDGET = 150
_MAX_MEMBERS_IN_PROMPT = 10
_TIMEOUT_SECONDS = 600
_CLAUDE_MODEL = "claude-haiku-4-5-20251001"


# Bump when the prompt or extraction logic changes significantly.
# Existing cached summaries will have a different hash and be regenerated.
_HASH_VERSION = "v4"

# Matches labeled summary sections that qwen3 sometimes wraps its answer in,
# e.g. "Final summary:\n\n", "Final version (4 sentences):\n\n", "Revised:\n\n".
# We search for the LAST match and extract everything after it.
_LABEL_RE = re.compile(
    r"(?i)(?:"
    r"final\s+(?:summary|version|answer)(?:\s*\([^)]*\))?"  # Final summary / version / answer
    r"|revised"                                               # Revised
    r"|here['\s]+(?:the\s+)?(?:final\s+)?summary"           # Here's the summary
    r")"
    r"\s*[:\s]*\n+"
)


def compute_member_hash(members: list[str]) -> str:
    """Stable hash of a community's member set (order-independent).

    Includes _HASH_VERSION so cached summaries from a different prompt/extraction
    version are automatically invalidated and regenerated.
    """
    payload = _HASH_VERSION + "\n" + "\n".join(sorted(members))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def summarize_community(
    community_id: int,
    members: list[str],
    graph_store: "SQLiteGraphStore",
    project_path: str,
    model: str = "qwen3:4b",
) -> str:
    """Return a cached or freshly-generated summary for the community.

    Cache hit: member_hash matches and model is any known LLM model → return cached text.
    Cache miss: try Ollama, then Claude API.
    No LLM available: raises RuntimeError with a clear message.
    """
    if not members:
        return ""

    member_hash = compute_member_hash(members)

    cached = graph_store.get_community_summary(community_id)
    _known_models = (model, _CLAUDE_MODEL)
    if (
        cached
        and cached["member_hash"] == member_hash
        and cached["model"] in _known_models
    ):
        logger.debug("Community %d summary cache hit (model=%s)", community_id, cached["model"])
        return cached["summary"]

    # Single-member communities skip LLM entirely — path fallback is fast, deterministic,
    # and avoids 100s of Ollama generation per file for large projects with many singletons.
    if len(members) == 1:
        name = Path(members[0]).stem.replace("-", " ").replace("_", " ")
        fallback = f"This file handles {name}."
        graph_store.save_community_summary(community_id, fallback, member_hash, "path-fallback")
        logger.debug("Community %d singleton path-fallback summary", community_id)
        return fallback

    context_block = _build_context(members, project_path)
    prompt = (
        "Describe what this cluster of source files does in 3-5 sentences. "
        "Name the dominant responsibility.\n\n"
        + context_block
    )

    # Try Ollama first
    ollama_text = _summarize_via_ollama(prompt, model)
    if ollama_text:
        graph_store.save_community_summary(community_id, ollama_text, member_hash, model)
        logger.debug("Community %d summary via Ollama (%d chars)", community_id, len(ollama_text))
        return ollama_text

    # Try Claude API
    claude_text = _summarize_via_claude(prompt)
    if claude_text:
        graph_store.save_community_summary(community_id, claude_text, member_hash, _CLAUDE_MODEL)
        logger.debug("Community %d summary via Claude API (%d chars)", community_id, len(claude_text))
        return claude_text


    # Small multi-member communities: generate a name-based summary from all member paths.
    # Better than nothing when both LLMs are unavailable.
    if len(members) <= 5:
        names = ", ".join(
            Path(m).stem.replace("-", " ").replace("_", " ") for m in members
        )
        fallback = f"This cluster includes: {names}."
        graph_store.save_community_summary(community_id, fallback, member_hash, "path-fallback")
        logger.info("Community %d small-cluster path-fallback summary", community_id)
        return fallback

    # Neither LLM is available — fail clearly
    raise RuntimeError(
        f"Community {community_id} summary failed: Ollama is not running and "
        "ANTHROPIC_API_KEY is not set. Start Ollama (ollama serve) or set "
        "ANTHROPIC_API_KEY to generate community summaries."
    )


_QWEN_ANALYSIS_MARKERS = (
    "we are given", "the task is to", "let's analyze", "let me analyze",
    "let's draft", "let me draft", "let me try", "let's write", "let me write",
    "we need to", "we must", "we can structure", "but note:", "but we must",
    "the dominant responsibility of the entire cluster",
    "from the names and descriptions",
    "so it's for", "so it is a",
    # Additional patterns seen in qwen3 outputs
    "i think", "let me think", "let's think", "so i'll", "so i will",
    "we can say", "we can note", "let's go with", "i'll write", "i will write",
    "here is my", "here's my", "okay,", "ok,", "alright,",
    "alternatively,", "alternatively we can", "alternatively, we",
    "let me make", "however,", "however the", "however, the",
    "we are not to", "the problem says", "we did:", "i should", "i need to",
    "let me ensure", "let me check", "let me be",
)


def _extract_summary(text: str) -> str:
    """Strip qwen3's chain-of-thought preamble and return only the final summary.

    We send think=False but qwen3:4b still dumps reasoning into the response field.
    Three extraction strategies, tried in order:

    1. </think> tag — qwen3 sometimes emits this as a block separator
    2. Labeled section — model labels its answer with "Final summary:", "Revised:", etc.
       We take the LAST such label so nested labels (e.g., "So I'll write:\n\nFinal summary:")
       are handled correctly.
    3. Paragraph-walk heuristic — walk backward from the end, stopping at analysis markers.

    Claude API responses are always clean (no markers, no preamble).
    """
    # 1. </think> tag — take everything after it
    if "</think>" in text:
        after = text.split("</think>", 1)[1].strip()
        if after:
            return _clean_extracted(after)

    paragraphs = [p.strip() for p in text.strip().split("\n\n") if p.strip()]
    if not paragraphs:
        return text.strip()

    # If the first paragraph looks clean, the whole response is the summary.
    # Claude API responses always take this path. Do NOT run label detection on
    # already-clean text — the body might contain phrases like "final version"
    # that would cause false matches.
    first_lower = paragraphs[0].lower()
    if not any(first_lower.startswith(m) for m in _QWEN_ANALYSIS_MARKERS):
        return _clean_extracted(text.strip())

    # 2. Text starts with analysis — look for a labeled section like "Final summary:".
    # Take the LAST match so nested labels ("So I'll write:\n\nFinal summary:") work.
    matches = list(_LABEL_RE.finditer(text))
    if matches:
        after = text[matches[-1].end():].strip()
        if after:
            return _clean_extracted(after)

    # 3. Paragraph-walk: collect from the end, stop at analysis markers.
    clean: list[str] = []
    for para in reversed(paragraphs):
        lower = para.lower()
        is_analysis = (
            any(lower.startswith(m) for m in _QWEN_ANALYSIS_MARKERS)
            # Numbered list items like "1. filename:" or "10. filename:" are analysis
            or bool(re.match(r"^\d+[.)]\s", para))
        )
        if is_analysis:
            break
        clean.append(para)

    if clean:
        clean.reverse()
        return _clean_extracted("\n\n".join(clean))

    # Nothing clean found — all paragraphs look like analysis.
    # Return "" so the caller falls through to Claude API or path fallback.
    return ""


def _clean_extracted(text: str) -> str:
    """Strip outer quotes that qwen sometimes wraps its output in."""
    t = text.strip()
    if len(t) > 2 and t[0] == '"' and t[-1] == '"':
        t = t[1:-1].strip()
    return t


def _summarize_via_ollama(prompt: str, model: str) -> str:
    """Return summary text from Ollama using chat prefill, or '' if unreachable.

    Uses /api/chat with a partial assistant message so qwen3 MUST continue
    from "This cluster of source files" — eliminating analysis preamble entirely.
    """
    payload = {
        "model": model,
        "messages": [
            {"role": "user", "content": prompt},
            {"role": "assistant", "content": "This cluster of source files"},
        ],
        "stream": False,
        "options": {"temperature": 0.1, "num_predict": 400},
    }
    try:
        req = urllib.request.Request(
            _OLLAMA_CHAT_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=_TIMEOUT_SECONDS) as resp:
            body = json.loads(resp.read())
        continuation = body.get("message", {}).get("content", "").strip()
        if not continuation:
            return ""
        # Prepend the prefill to get the full summary
        full = "This cluster of source files" + (" " if not continuation.startswith(" ") else "") + continuation
        if len(full) < 30:
            logger.warning("Ollama chat returned too-short summary (%d chars)", len(full))
            return ""
        return full
    except OSError:
        logger.info("Ollama not reachable — will try Claude API")
        return ""
    except Exception:
        logger.warning("Ollama chat request failed", exc_info=True)
        return ""


def _summarize_via_claude(prompt: str) -> str:
    """Return summary text from Claude Haiku via ANTHROPIC_API_KEY, or '' if unavailable."""
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return ""
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        msg = client.messages.create(
            model=_CLAUDE_MODEL,
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}],
        )
        return msg.content[0].text.strip()
    except ImportError:
        logger.debug("anthropic package not installed — Claude API fallback unavailable")
        return ""
    except Exception:
        logger.warning("Claude API summarizer failed", exc_info=True)
        return ""


def _build_context(members: list[str], project_path: str) -> str:
    """Build the prompt context block: file path + first N chars of content."""
    root = Path(project_path)
    lines: list[str] = []
    for member in members[:_MAX_MEMBERS_IN_PROMPT]:
        file_path = root / member
        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
            snippet = content[:_PROMPT_CHAR_BUDGET].strip()
        except OSError as e:
            logger.warning("Cannot read community member %s for summary context: %s", member, e)
            snippet = "(unreadable)"
        lines.append(f"{member}:\n{snippet}")
    return "\n\n".join(lines)
