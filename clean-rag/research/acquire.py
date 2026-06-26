"""Auto-research orchestrator for clean-rag.

When the Haiku verifier says RESEARCH_MORE, this module orchestrates
the four-layer acquisition waterfall for a topic:

  Layer 1: Git sparse checkout (if source_map has a GitHub entry)
  Layer 2: llms.txt check (if source_map has a doc_root)
  Layer 3: BFS crawl (if source_map has a doc_root)
  Layer 4: WebSearch fallback (handled by Claude, not this script)

After acquisition, indexes the topic into clean-rag's database.
"""

import logging
import os
import pathlib
from typing import Any

from .source_map import SOURCE_MAP, get_category
from server.config import KNOWLEDGE_DIR

logger = logging.getLogger(__name__)

MIN_FILES_COVERED = 5  # entity is "covered" when a layer produces this many files


def acquire_topic(
    topic: str,
    max_pages: int = 200,
    crawl_depth: int = 3,
    category: str | None = None,
) -> dict[str, Any]:
    """Run the four-layer waterfall for a single topic.

    Returns a summary dict with layer results and files_acquired count.
    Layer 4 (WebSearch) is not run here since it requires Claude's WebSearch tool.
    """
    # Resolve category from source_map if not provided
    if not category:
        category = get_category(topic)
    if category == "uncategorized":
        category = None

    # Place in category subdirectory if known
    if category:
        kb_dir = KNOWLEDGE_DIR / category / topic
    else:
        kb_dir = KNOWLEDGE_DIR / topic
    kb_dir.mkdir(parents=True, exist_ok=True)

    source = SOURCE_MAP.get(topic, {})
    result: dict[str, Any] = {
        "topic": topic,
        "category": category,
        "kb_dir": str(kb_dir),
        "source_map_hit": bool(source),
        "layers": {},
        "files_acquired": 0,
        "covered": False,
    }

    # Track how many files we have before and after each layer
    def _count_files() -> int:
        return len(list(kb_dir.rglob("*")))

    initial_count = _count_files()

    # ── Layer 1: GitHub sparse checkout ──
    github_repo = source.get("github")
    docs_path = source.get("docs_path")

    if github_repo and docs_path:
        try:
            from .clone_docs import clone_docs
            extensions_str = source.get("extensions", ".md,.mdx,.rst")
            extensions = {ext.strip() for ext in extensions_str.split(",")}

            stats = clone_docs(
                repo=github_repo,
                docs_path=docs_path,
                topic=topic,
                branch=source.get("branch", "main"),
                extensions=extensions,
                kb_dir=kb_dir,
            )
            result["layers"]["github"] = {
                "files_copied": stats["files_copied"],
                "files_skipped": stats["files_skipped"],
                "errors": len(stats.get("errors", [])),
            }

            if stats["files_copied"] >= MIN_FILES_COVERED:
                result["covered"] = True
                result["files_acquired"] = _count_files() - initial_count
                logger.info("Layer 1 (GitHub) covered topic '%s' with %d files",
                            topic, stats["files_copied"])
                return result

        except Exception as e:
            logger.warning("Layer 1 (GitHub) failed for '%s': %s", topic, e)
            result["layers"]["github"] = {"error": str(e)}

    # ── Layer 2: llms.txt check ──
    doc_root = source.get("doc_root")

    if doc_root and not result["covered"]:
        try:
            from .fetch_docs import check_llms_txt
            import time
            fetched_date = time.strftime("%Y-%m-%d")

            stats = check_llms_txt(doc_root, kb_dir, topic, fetched_date)
            result["layers"]["llms_txt"] = {
                "found": stats["found"],
                "files_saved": stats["files_saved"],
                "urls_discovered": len(stats.get("urls_discovered", [])),
            }

            # If llms-full.txt was found, that's a single comprehensive file
            if stats["found"] == "llms-full.txt":
                result["covered"] = True
                result["files_acquired"] = _count_files() - initial_count
                logger.info("Layer 2 (llms-full.txt) covered topic '%s'", topic)
                return result

            # If llms.txt was found with URLs, fetch them
            if stats.get("urls_discovered"):
                from .fetch_docs import fetch_queue
                import json
                import tempfile

                queue_items = [
                    {"url": u, "topic": topic, "tier": "A"}
                    for u in stats["urls_discovered"]
                ]
                fd, tmp_name = tempfile.mkstemp(suffix=".json")
                queue_path = pathlib.Path(tmp_name)
                try:
                    os.close(fd)
                    queue_path.write_text(json.dumps(queue_items), encoding="utf-8")
                    fetch_result = fetch_queue(queue_path, kb_dir)
                finally:
                    try:
                        queue_path.unlink()
                    except OSError:
                        pass

                total_saved = fetch_result.get("saved", 0) + stats["files_saved"]
                if total_saved >= MIN_FILES_COVERED:
                    result["covered"] = True
                    result["files_acquired"] = _count_files() - initial_count
                    logger.info("Layer 2 (llms.txt + fetch) covered topic '%s'", topic)
                    return result

        except Exception as e:
            logger.warning("Layer 2 (llms.txt) failed for '%s': %s", topic, e)
            result["layers"]["llms_txt"] = {"error": str(e)}

    # ── Layer 3: BFS crawl ──
    if doc_root and not result["covered"]:
        try:
            from .fetch_docs import bfs_crawl

            stats = bfs_crawl(
                start_url=doc_root,
                kb_dir=kb_dir,
                topic=topic,
                max_pages=max_pages,
                max_depth=crawl_depth,
            )
            result["layers"]["crawl"] = {
                "pages_crawled": stats["pages_crawled"],
                "pages_saved": stats["pages_saved"],
                "pages_failed": stats["pages_failed"],
            }

            if stats["pages_saved"] >= MIN_FILES_COVERED:
                result["covered"] = True
                result["files_acquired"] = _count_files() - initial_count
                logger.info("Layer 3 (BFS crawl) covered topic '%s' with %d pages",
                            topic, stats["pages_saved"])
                return result

        except Exception as e:
            logger.warning("Layer 3 (crawl) failed for '%s': %s", topic, e)
            result["layers"]["crawl"] = {"error": str(e)}

    # If we get here, layers 1-3 didn't produce enough files.
    # Layer 4 (WebSearch) must be handled by Claude using the WebSearch tool.
    result["files_acquired"] = _count_files() - initial_count
    result["needs_websearch"] = True
    logger.info(
        "Layers 1-3 produced %d files for '%s'. WebSearch needed.",
        result["files_acquired"], topic,
    )
    return result
