"""URL fetching and chunking for research RAG.

Fetches web pages, strips noise (nav/footer/ads), converts to Markdown,
and splits into chunks at heading boundaries.
"""

import logging
import re
from datetime import datetime, timezone

from rag_server.indexing.markdown_chunker import RawChunk, chunk_markdown_text

logger = logging.getLogger(__name__)

# Browser-like UA to avoid bot-blocking on most sites
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

# Tags that are pure chrome — remove before text extraction
_NOISE_TAGS = [
    "nav", "header", "footer", "aside", "script", "style",
    "noscript", "iframe", "form", "button", "dialog",
    "[class*='cookie']", "[class*='banner']", "[class*='popup']",
    "[id*='cookie']", "[id*='banner']",
]


def fetch_url(url: str, timeout: int = 15) -> tuple[str | bytes, str]:
    """Fetch a URL and return (raw_content, content_type).

    Returns ("", "") on failure — callers should check for empty string.
    """
    import httpx

    try:
        with httpx.Client(
            headers={"User-Agent": _USER_AGENT},
            follow_redirects=True,
            timeout=timeout,
        ) as client:
            response = client.get(url)
            response.raise_for_status()
            content_type = response.headers.get("content-type", "").lower()
            return response.content if "pdf" in content_type else response.text, content_type
    except httpx.HTTPStatusError as e:
        logger.warning("HTTP %d fetching %s: %s", e.response.status_code, url, e)
        return "", ""
    except httpx.RequestError as e:
        logger.warning("Request error fetching %s: %s", url, e)
        return "", ""


def is_pdf_url(url: str, content_type: str = "") -> bool:
    """Return True if the URL or content-type indicates a PDF."""
    if "pdf" in content_type:
        return True
    lower = url.lower().split("?")[0]  # strip query params before checking extension
    return lower.endswith(".pdf")


def extract_text(html: str, url: str) -> tuple[str, str]:
    """Extract (title, markdown_text) from raw HTML.

    Strips navigation chrome and converts article content to Markdown.
    """
    from bs4 import BeautifulSoup
    import html2text

    soup = BeautifulSoup(html, "lxml")

    # Extract title before stripping elements
    title = ""
    title_tag = soup.find("title")
    if title_tag:
        title = title_tag.get_text(strip=True)
    if not title:
        h1 = soup.find("h1")
        if h1:
            title = h1.get_text(strip=True)

    # Remove noise tags
    for tag_name in ["nav", "header", "footer", "aside", "script", "style",
                      "noscript", "iframe", "form", "button", "dialog"]:
        for el in soup.find_all(tag_name):
            el.decompose()

    # Remove cookie banners and other common noise by class/id patterns
    for el in soup.find_all(True, {"class": re.compile(r"cookie|banner|popup|modal|overlay|ad-", re.I)}):
        el.decompose()
    for el in soup.find_all(True, {"id": re.compile(r"cookie|banner|popup|modal|overlay", re.I)}):
        el.decompose()

    # Try to find the main content area
    main_content = (
        soup.find("article")
        or soup.find("main")
        or soup.find("div", {"class": re.compile(r"content|article|post|body|entry", re.I)})
        or soup.find("body")
        or soup
    )

    # Convert to Markdown
    converter = html2text.HTML2Text()
    converter.ignore_links = False
    converter.ignore_images = True
    converter.body_width = 0  # Don't wrap lines
    converter.unicode_snob = True
    converter.single_line_break = False

    markdown = converter.handle(str(main_content))

    # Clean up excessive blank lines
    markdown = re.sub(r"\n{3,}", "\n\n", markdown).strip()

    return title, markdown


def chunk_url(url: str, max_tokens: int = 512) -> list[RawChunk]:
    """Fetch a URL and return text chunks split at heading boundaries.

    Returns an empty list if the URL is unreachable or returns no content.
    Routes PDF URLs to the pdf_chunker automatically.
    """
    raw_content, content_type = fetch_url(url)
    if not raw_content:
        logger.warning("No content fetched from %s", url)
        return []

    # PDF detected via content-type — delegate to pdf_chunker
    if is_pdf_url(url, content_type):
        from rag_server.indexing.pdf_chunker import chunk_pdf_bytes
        if isinstance(raw_content, bytes):
            return chunk_pdf_bytes(raw_content, source_id=url, max_tokens=max_tokens)
        logger.warning("PDF URL %s returned text instead of bytes — skipping", url)
        return []

    # HTML page
    if isinstance(raw_content, bytes):
        raw_content = raw_content.decode("utf-8", errors="replace")

    title, markdown = extract_text(raw_content, url)
    if not markdown or len(markdown) < 100:
        logger.warning("Insufficient content extracted from %s (%d chars)", url, len(markdown))
        return []

    chunks = chunk_markdown_text(markdown, source_id=url, max_tokens=max_tokens)

    # Pages with no headings produce chunks with empty section names.
    # Fall back to the page title so search metadata is never blank.
    if title:
        for chunk in chunks:
            if not chunk.section:
                chunk.section = title

    return chunks
