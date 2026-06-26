"""Search logic for clean-rag. Searches across topics and projects."""

import hashlib
import json
import logging
import re
from pathlib import Path

from .config import DATABASES_DIR, DEFAULT_MIN_SCORE, DEFAULT_SEARCH_LIMIT, STATE_DIR
from .store import ChromaStore, SearchResult

_TOPIC_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")

logger = logging.getLogger(__name__)


def _read_topic_registry() -> dict:
    """Read topics.json for category lookups."""
    reg_path = STATE_DIR / "topics.json"
    if reg_path.exists():
        try:
            return json.loads(reg_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _resolve_chroma_dir(topic: str) -> Path | None:
    """Find the chroma directory for a topic using registry or tree walk.

    Checks in order:
    1. Registry category: databases/<category>/<topic>/chroma/
    2. Source map category: databases/<category>/<topic>/chroma/
    3. Flat fallback: databases/<topic>/chroma/
    4. Tree walk: scan databases/ recursively for <topic>/chroma/
    """
    # 1. Registry
    reg = _read_topic_registry()
    cat = reg.get(topic, {}).get("category")
    if cat:
        p = DATABASES_DIR / cat / topic / "chroma"
        if p.exists():
            return p

    # 2. Source map
    try:
        from research.source_map import get_category
        cat = get_category(topic)
        if cat != "uncategorized":
            p = DATABASES_DIR / cat / topic / "chroma"
            if p.exists():
                return p
    except ImportError:
        pass

    # 3. Flat fallback
    p = DATABASES_DIR / topic / "chroma"
    if p.exists():
        return p

    # 4. Tree walk (last resort)
    if DATABASES_DIR.exists():
        for d in DATABASES_DIR.rglob(f"{topic}/chroma"):
            if d.is_dir():
                return d

    return None


def search(
    query: str,
    sources: list[str],
    embedder,
    code_embedder,
    limit: int = DEFAULT_SEARCH_LIMIT,
    min_score: float = DEFAULT_MIN_SCORE,
) -> list[dict]:
    """Search across topic databases and/or project indexes.

    Args:
        query: The search query text.
        sources: List of source specifiers:
            - "topic:<name>" to search a specific topic database
            - "project:<path>" to search a project's codebase index
            - "all_topics" to search all topic databases
        embedder: Knowledge/topic embedder (bge-base-en-v1.5).
        code_embedder: Code embedder (st-codesearch-distilroberta-base).
        limit: Max results per source.
        min_score: Minimum similarity score.

    Returns:
        List of result dicts sorted by score (highest first).
    """
    all_results: list[dict] = []

    for source in sources:
        if source.startswith("topic:"):
            topic = source[6:]
            if not _TOPIC_NAME_RE.match(topic):
                logger.warning("Invalid topic name in search: %s", topic)
                continue
            results = _search_topic(query, topic, embedder, limit, min_score)
            all_results.extend(results)
        elif source.startswith("project:"):
            project_path = source[8:]
            results = _search_project(query, project_path, code_embedder, limit, min_score)
            all_results.extend(results)
        elif source == "all_topics":
            results = _search_all_topics(query, embedder, limit, min_score)
            all_results.extend(results)
        else:
            logger.warning("Unknown source specifier: %s", source)

    # Sort by score descending, trim to limit
    all_results.sort(key=lambda r: r["score"], reverse=True)
    return all_results[:limit]


def _search_topic(
    query: str, topic: str, embedder, limit: int, min_score: float,
) -> list[dict]:
    """Search a single topic database (category-aware)."""
    chroma_dir = _resolve_chroma_dir(topic)
    if chroma_dir is None:
        logger.warning("Topic database not found: %s (checked registry, source map, flat, tree)", topic)
        return []

    logger.debug("Searching topic '%s' at %s", topic, chroma_dir)
    store = ChromaStore(persist_dir=str(chroma_dir))
    if not store.collection_exists("docs"):
        return []

    query_embedding = embedder.embed_query(query)
    results = store.search("docs", query_embedding, limit=limit, min_score=min_score)

    return [
        {
            "content": r.content,
            "score": r.score,
            "source_type": "topic",
            "topic": topic,
            "file": r.metadata.get("source_file", ""),
            "tree_path": r.metadata.get("tree_path", ""),
            "section": r.metadata.get("section", ""),
            "line_start": r.metadata.get("line_start", 0),
            "line_end": r.metadata.get("line_end", 0),
        }
        for r in results
    ]


def _search_all_topics(
    query: str, embedder, limit: int, min_score: float,
) -> list[dict]:
    """Search across all topic databases (walks category tree recursively)."""
    all_results: list[dict] = []

    if not DATABASES_DIR.exists():
        return []

    # Find all chroma/ dirs under databases/, skipping _projects/
    topic_count = 0
    for chroma_dir in DATABASES_DIR.rglob("chroma"):
        if not chroma_dir.is_dir():
            continue
        # Skip project indexes
        rel = chroma_dir.relative_to(DATABASES_DIR)
        if str(rel).startswith("_projects"):
            continue

        # Derive topic name from parent of chroma/
        topic_name = chroma_dir.parent.name
        store = ChromaStore(persist_dir=str(chroma_dir))
        if not store.collection_exists("docs"):
            continue

        topic_count += 1
        query_embedding = embedder.embed_query(query)
        results = store.search("docs", query_embedding, limit=limit, min_score=min_score)

        for r in results:
            all_results.append({
                "content": r.content,
                "score": r.score,
                "source_type": "topic",
                "topic": topic_name,
                "file": r.metadata.get("source_file", ""),
                "tree_path": r.metadata.get("tree_path", ""),
                "section": r.metadata.get("section", ""),
                "line_start": r.metadata.get("line_start", 0),
                "line_end": r.metadata.get("line_end", 0),
            })

    logger.info("Searched %d topic databases, found %d results", topic_count, len(all_results))

    # Sort and trim
    all_results.sort(key=lambda r: r["score"], reverse=True)
    return all_results[:limit]


def _search_project(
    query: str, project_path: str, code_embedder, limit: int, min_score: float,
) -> list[dict]:
    """Search a project's codebase index."""
    project_root = Path(project_path).resolve()
    pid = hashlib.sha256(str(project_root).encode("utf-8")).hexdigest()[:12]

    chroma_dir = DATABASES_DIR / "_projects" / pid / "chroma"
    if not chroma_dir.exists():
        logger.warning("Project index not found for: %s (pid=%s)", project_path, pid)
        return []

    store = ChromaStore(persist_dir=str(chroma_dir))
    if not store.collection_exists("codebase"):
        return []

    query_embedding = code_embedder.embed_query(query)
    results = store.search("codebase", query_embedding, limit=limit, min_score=min_score)

    return [
        {
            "content": r.content,
            "score": r.score,
            "source_type": "project",
            "file": r.metadata.get("source_file", ""),
            "tree_path": r.metadata.get("tree_path", ""),
            "section": r.metadata.get("section", ""),
            "line_start": r.metadata.get("line_start", 0),
            "line_end": r.metadata.get("line_end", 0),
        }
        for r in results
    ]
