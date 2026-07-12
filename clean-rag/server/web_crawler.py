"""Web crawler for fallback indexing. Extracts text from URLs without LLM."""

import logging
import re
from pathlib import Path
from typing import Optional

import httpx
from html2text import html2text

from .config import KNOWLEDGE_DIR

logger = logging.getLogger(__name__)

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
CRAWL_TIMEOUT = 10.0


def crawl_and_index_urls(urls: list[str], topic_slug: str, source_query: str) -> dict:
    """Crawl URLs and index their content without LLM processing.

    Args:
        urls: list of URLs to crawl
        topic_slug: topic name (e.g., 'flappy_bird_game')
        source_query: original search query (for metadata)

    Returns:
        {
            "files_created": N,
            "urls_failed": N,
            "total_bytes": N,
        }
    """
    kb_dir = KNOWLEDGE_DIR / "fallback" / topic_slug
    kb_dir.mkdir(parents=True, exist_ok=True)

    stats = {
        "files_created": 0,
        "urls_failed": 0,
        "total_bytes": 0,
    }

    for idx, url in enumerate(urls):
        try:
            content = _fetch_and_extract(url)
            if not content or len(content.strip()) < 50:
                logger.debug("Skipped URL (too short): %s", url)
                stats["urls_failed"] += 1
                continue

            file_path = kb_dir / f"{idx:02d}_{_url_to_filename(url)}.md"
            _write_content_file(file_path, content, url, source_query)
            stats["files_created"] += 1
            stats["total_bytes"] += len(content.encode("utf-8"))

        except Exception as e:
            logger.debug("Failed to crawl %s: %s", url, e)
            stats["urls_failed"] += 1

    # Quick index the new files
    if stats["files_created"] > 0:
        try:
            from .indexing import index_topic
            index_topic(topic_slug, force=False)
            logger.info("Indexed %d files for topic: %s", stats["files_created"], topic_slug)
        except Exception as e:
            logger.warning("Failed to index topic %s: %s", topic_slug, e)

    return stats


def _fetch_and_extract(url: str, timeout: float = CRAWL_TIMEOUT) -> Optional[str]:
    """Fetch URL and extract text content via html2text."""
    if not url or not url.startswith(("http://", "https://")):
        return None

    try:
        headers = {"User-Agent": USER_AGENT}
        client = httpx.Client(timeout=timeout, headers=headers, follow_redirects=True)
        response = client.get(url)
        response.raise_for_status()
        client.close()

        html = response.text
        if not html or len(html) < 100:
            return None

        text = html2text(html)
        text = text.strip()

        if not text or len(text) < 50:
            return None

        return text

    except httpx.TimeoutException:
        logger.debug("Timeout crawling %s", url)
        return None
    except httpx.HTTPError as e:
        logger.debug("HTTP error crawling %s: %s", url, e)
        return None
    except Exception as e:
        logger.debug("Error extracting content from %s: %s", url, e)
        return None


def _url_to_filename(url: str) -> str:
    """Convert URL to safe filename."""
    safe = re.sub(r"[^a-z0-9]+", "_", url.lower())
    safe = safe.strip("_")[:40]
    return safe or "untitled"


def _write_content_file(
    path: Path,
    content: str,
    source_url: str,
    source_query: str,
) -> None:
    """Write extracted content to markdown file with metadata header."""
    header = f"""<!-- Source: {source_url}
Query: {source_query}
-->

"""
    full_content = header + content
    path.write_text(full_content, encoding="utf-8")
