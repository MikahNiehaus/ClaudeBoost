"""Per-community LLM summaries via local Ollama. Synchronous, best-effort.

Requires Ollama running at localhost:11434 with the target model pulled.
If Ollama is unreachable, summarize_community returns "" — never raises.
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
        logger.info("Ollama not reachable — community %d summary skipped", community_id)
        return ""
    except Exception:
        logger.warning("Community %d summary failed", community_id, exc_info=True)
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
        except OSError:
            snippet = "(unreadable)"
        lines.append(f"{member}:\n{snippet}")
    return "\n\n".join(lines)
