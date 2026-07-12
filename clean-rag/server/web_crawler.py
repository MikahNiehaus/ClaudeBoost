"""Web crawler for fallback indexing. Extracts text from URLs without LLM.

For code files, uses AST parsing to extract semantic structure (functions,
classes, docstrings) instead of plain text extraction.
"""

import ast
import logging
import re
from pathlib import Path
from typing import Optional

import httpx
from html2text import html2text

from .config import KNOWLEDGE_DIR, STANDALONE_PORT

logger = logging.getLogger(__name__)

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
CRAWL_TIMEOUT = 10.0

# Admission filter: no quality signal existed before this. Confirmed by
# reading _fetch_and_extract() that nothing checked domain reputation or
# content quality, only whether a page loaded at all (>100 raw chars). The
# only prior signal was DuckDuckGo's own search ranking, with no second
# opinion before content got written into the permanent KB.
MIN_CONTENT_LENGTH = 200  # was 50, too low to filter thin/broken pages
# unique_words / total_words. Measured directly, not guessed: a real 41KB
# Flappy Bird tutorial article scored 0.17 (long form text naturally repeats
# common words across length), a synthetic spam sample scored 0.02. 0.25 sat
# above both and rejected legitimate content — recalibrated to 0.08, which
# sits below the real article and above the spam sample with margin on
# both sides.
MIN_WORD_DIVERSITY = 0.08
URL_SHORTENER_DOMAINS = {
    "bit.ly", "tinyurl.com", "t.co", "goo.gl", "ow.ly", "is.gd", "buff.ly",
}


def _is_low_quality(content: str, url: str) -> tuple[bool, str]:
    """Mechanical admission check, not an LLM judgment call.

    Returns (is_low_quality, reason).
    """
    if len(content) < MIN_CONTENT_LENGTH:
        return True, f"content too short ({len(content)} chars, min {MIN_CONTENT_LENGTH})"

    try:
        from urllib.parse import urlparse
        domain = urlparse(url).netloc.lower().removeprefix("www.")
    except Exception:
        domain = ""
    if domain in URL_SHORTENER_DOMAINS:
        return True, f"URL shortener domain: {domain}"

    words = re.findall(r"\b[a-z]+\b", content.lower())
    if len(words) < 20:
        return True, f"too few words ({len(words)})"
    diversity = len(set(words)) / len(words)
    if diversity < MIN_WORD_DIVERSITY:
        return True, f"low word diversity ({diversity:.2f}, min {MIN_WORD_DIVERSITY}) — likely repeated boilerplate"

    return False, ""


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
        "urls_rejected_low_quality": 0,
        "total_bytes": 0,
    }

    for idx, url in enumerate(urls):
        try:
            content = _fetch_and_extract(url)
            if not content:
                logger.debug("Skipped URL (fetch failed): %s", url)
                stats["urls_failed"] += 1
                continue

            content = content.strip()
            is_low_quality, reason = _is_low_quality(content, url)
            if is_low_quality:
                logger.info("Rejected from KB (stricter than fallback display): %s — %s", url, reason)
                stats["urls_rejected_low_quality"] += 1
                continue

            file_path = kb_dir / f"{idx:02d}_{_url_to_filename(url)}.md"
            _write_content_file(file_path, content, url, source_query)
            stats["files_created"] += 1
            stats["total_bytes"] += len(content.encode("utf-8"))

        except Exception as e:
            logger.debug("Failed to crawl %s: %s", url, e)
            stats["urls_failed"] += 1

    # Quick index the new files. index_topic() needs a loaded embedder
    # instance (confirmed: calling it directly here raises "missing 1
    # required positional argument: 'embedder'" — this function has no
    # embedder to pass, whether called in-process from the server or from a
    # standalone script). Call the server's own /index-topic HTTP endpoint
    # instead, which already has the embedder loaded.
    if stats["files_created"] > 0:
        try:
            import json
            import urllib.request

            req_data = json.dumps({
                "topic": topic_slug,
                "category": "fallback",
                "force": False,
            }).encode("utf-8")
            req = urllib.request.Request(
                f"http://127.0.0.1:{STANDALONE_PORT}/index-topic",
                data=req_data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                json.loads(resp.read().decode("utf-8"))
            logger.info("Indexed %d files for topic: %s", stats["files_created"], topic_slug)
        except Exception as e:
            logger.warning("Failed to index topic %s: %s", topic_slug, e)

    return stats


def _is_code_file(url: str, content_type: str = "") -> bool:
    """Check if URL points to a code file."""
    code_extensions = (".py", ".js", ".ts", ".go", ".java", ".rs", ".cpp", ".c")
    code_types = ("application/x-python", "text/javascript", "text/x-typescript")
    return url.endswith(code_extensions) or any(ct in content_type for ct in code_types)


def _extract_code_structure(code: str) -> str:
    """Extract semantic structure from code via AST (Python)."""
    try:
        tree = ast.parse(code)
        lines = ["# Code Structure\n"]

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                docstring = ast.get_docstring(node) or ""
                lines.append(f"## Function: {node.name}")
                if docstring:
                    lines.append(docstring)
                lines.append("")

            elif isinstance(node, ast.ClassDef):
                docstring = ast.get_docstring(node) or ""
                lines.append(f"## Class: {node.name}")
                if docstring:
                    lines.append(docstring)
                lines.append("")

        # Append actual code for reference
        lines.append("## Code\n")
        lines.append("```python")
        lines.append(code[:2000])  # First 2000 chars
        lines.append("```")

        return "\n".join(lines)
    except Exception:
        # If AST parsing fails, return original code
        return code


def _fetch_and_extract(url: str, timeout: float = CRAWL_TIMEOUT) -> Optional[str]:
    """Fetch URL and extract content.

    For code files: use AST-based extraction for semantic structure.
    For web pages: use html2text for plain text.
    """
    if not url or not url.startswith(("http://", "https://")):
        return None

    try:
        headers = {"User-Agent": USER_AGENT}
        client = httpx.Client(timeout=timeout, headers=headers, follow_redirects=True)
        response = client.get(url)
        response.raise_for_status()
        content_type = response.headers.get("content-type", "")
        client.close()

        html = response.text
        if not html or len(html) < 100:
            return None

        # Use AST extraction for code files
        if _is_code_file(url, content_type):
            text = _extract_code_structure(html)
        else:
            # Use html2text for web pages
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
