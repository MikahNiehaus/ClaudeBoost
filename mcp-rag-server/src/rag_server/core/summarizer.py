"""Per-community LLM summaries via local Ollama, with a path-based fallback.

Tries Ollama at localhost:11434 first. If unreachable, generates a heuristic
summary from file paths and caches it as model="heuristic". A real Ollama
summary will replace the heuristic the next time Ollama is available, because
the model name won't match on cache lookup.
"""

import hashlib
import json
import logging
import urllib.request
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from rag_server.adapters.sqlite_graph_store import SQLiteGraphStore

logger = logging.getLogger(__name__)

_OLLAMA_URL = "http://localhost:11434/api/generate"
_PROMPT_CHAR_BUDGET = 600
_MAX_MEMBERS_IN_PROMPT = 30
_TIMEOUT_SECONDS = 60


def compute_member_hash(members: list[str]) -> str:
    """Stable hash of a community's member set (order-independent)."""
    return hashlib.sha256("\n".join(sorted(members)).encode("utf-8")).hexdigest()


def summarize_community(
    community_id: int,
    members: list[str],
    graph_store: "SQLiteGraphStore",
    project_path: str,
    model: str = "qwen2.5-coder:7b",
) -> str:
    """Return a cached or freshly-generated summary for the community.

    Cache hit: member_hash and model both match → return cached text.
    Cache miss: call Ollama, persist result, return text.
    Fallback: any error → log + return "".
    """
    if not members:
        return ""

    member_hash = compute_member_hash(members)

    cached = graph_store.get_community_summary(community_id)
    if (
        cached
        and cached["member_hash"] == member_hash
        and cached["model"] == model
    ):
        logger.debug("Community %d summary cache hit", community_id)
        return cached["summary"]

    context_block = _build_context(members, project_path)
    prompt = (
        "You are summarizing a cluster of related source files in one codebase. "
        "In 3-5 sentences, describe what this group of files collectively does "
        "and how they relate. Be concrete; name the dominant responsibility.\n\n"
        + context_block
    )

    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.1},
    }

    try:
        req = urllib.request.Request(
            _OLLAMA_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=_TIMEOUT_SECONDS) as resp:
            body = json.loads(resp.read())
        text = body.get("response", "").strip()
        if text:
            graph_store.save_community_summary(community_id, text, member_hash, model)
            logger.debug(
                "Community %d summary generated (%d chars)", community_id, len(text)
            )
        return text
    except OSError:
        logger.info("Ollama not reachable — using heuristic summary for community %d", community_id)
        text = _heuristic_summary(members)
        graph_store.save_community_summary(community_id, text, member_hash, "heuristic")
        return text
    except Exception:
        logger.warning("Community %d summary failed", community_id, exc_info=True)
        return _heuristic_summary(members)


def _build_context(members: list[str], project_path: str) -> str:
    """Build the prompt context block: file path + first N chars of content."""
    root = Path(project_path)
    lines: list[str] = []
    for member in members[:_MAX_MEMBERS_IN_PROMPT]:
        file_path = root / member
        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
            snippet = content[:_PROMPT_CHAR_BUDGET].strip()
        except OSError:
            snippet = "(unreadable)"
        lines.append(f"{member}:\n{snippet}")
    return "\n\n".join(lines)


def _heuristic_summary(members: list[str]) -> str:
    """Path-based summary when Ollama is unavailable.

    Groups files by their immediate parent directory, names the top dirs,
    and lists up to 4 file stems. Replaced by a real LLM summary when Ollama
    becomes available (cache key includes model name, so 'heuristic' != 'qwen2.5-coder:7b').
    """
    from collections import Counter
    dirs: Counter = Counter()
    for m in members:
        parts = Path(m).parts
        dirs[parts[-2] if len(parts) >= 2 else "(root)"] += 1

    top_dirs = ", ".join(f"{d}/" for d, _ in dirs.most_common(3))
    stems = [Path(m).stem for m in members[:4]]
    extra = max(0, len(members) - 4)
    stem_str = ", ".join(stems) + (f" +{extra} more" if extra else "")
    return f"{len(members)} files in {top_dirs} — {stem_str}"
