"""Fetchers for official document sources.

Two shapes, matched to what's actually available per source (confirmed by
research, not assumed):

- eCFR has a real, documented, bulk REST API (ecfr.gov/developers) -- no
  scraping needed for federal regulations.
- Most state-level sources (e.g. Texas statutes) have no bulk API and need a
  plain HTML fetch + text extraction, the same html2text-based approach
  mcp-rag-server's url_chunker.py already uses elsewhere in this codebase.
"""

import html
import logging
import re

import html2text
import httpx

logger = logging.getLogger(__name__)

# eCFR bulk XML wraps regulatory prose in tags (<HEAD>, <P>, <I>, <CITA>, ...)
# and stamps structural noise (an XML declaration, a hierarchy_metadata JSON
# blob on the section DIV, a Federal Register citation footer in <CITA>). None
# of that is prose, so none of it belongs in an embedding or a returned
# `content` field. These strip it back to clean text, the same standard
# fetch_html_as_text already meets via html2text.
_XML_DECL_RE = re.compile(r"<\?xml[^>]*\?>", re.IGNORECASE)
_CITA_RE = re.compile(r"<CITA\b[^>]*>.*?</CITA>", re.IGNORECASE | re.DOTALL)
_BLOCK_END_RE = re.compile(
    r"</(?:HEAD|HED|P|FP|EAR|AUTH|SOURCE|NOTE|DIV\d+)>", re.IGNORECASE,
)
_XML_TAG_RE = re.compile(r"<[^>]+>")


def ecfr_xml_to_text(xml_text: str) -> str:
    """Convert eCFR section XML into clean regulatory prose.

    Keeps the <HEAD> section title and the <P> regulatory text; drops the XML
    declaration, the section DIV's hierarchy_metadata JSON attribute (removed
    with its tag), and the <CITA> Federal Register citation footer. Each block
    element ends on its own newline so the chunker sees real paragraph
    boundaries (eCFR uses one <P> per paragraph, single-newline separated).
    """
    text = _XML_DECL_RE.sub("", xml_text)
    text = _CITA_RE.sub("", text)
    # Close each block element with a newline before stripping tags, so
    # paragraph structure survives as single-newline-separated lines.
    text = _BLOCK_END_RE.sub("\n", text)
    text = _XML_TAG_RE.sub("", text)
    text = html.unescape(text)
    lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in text.split("\n")]
    return "\n".join(ln for ln in lines if ln)


_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

ECFR_BASE = "https://www.ecfr.gov/api/versioner/v1"


def fetch_ecfr_section(title: int, date: str, section: str | None = None, timeout: int = 30) -> str:
    """Fetch federal regulation text from eCFR's versioner API.

    Args:
        title: CFR title number, e.g. 45.
        date: Point-in-time date, YYYY-MM-DD, e.g. "2024-02-01".
        section: Optional section to scope the request, e.g. "160.103".
        timeout: HTTP timeout in seconds.

    Returns:
        Clean regulatory prose (XML markup stripped) on success, "" on failure
        (caller should skip, not crash -- one bad source in a source list must
        not abort the whole ingest run).
    """
    url = f"{ECFR_BASE}/full/{date}/title-{title}.xml"
    params = {"section": section} if section else {}
    try:
        with httpx.Client(headers={"User-Agent": _USER_AGENT}, timeout=timeout) as client:
            resp = client.get(url, params=params)
            resp.raise_for_status()
            return ecfr_xml_to_text(resp.text)
    except httpx.HTTPStatusError as e:
        logger.warning("eCFR HTTP %d for title %s section %s: %s", e.response.status_code, title, section, e)
        return ""
    except httpx.RequestError as e:
        logger.warning("eCFR request error for title %s section %s: %s", title, section, e)
        return ""


def fetch_html_as_text(url: str, timeout: int = 15) -> str:
    """Fetch an HTML page and convert its body to plain markdown-ish text.

    No structural extraction beyond stripping script/style noise -- callers
    supply their own heading regex to docs_chunker.chunk_by_heading() for the
    source's actual citation format (e.g. Texas statute "Sec. 392.001." lines
    survive this conversion as plain text lines, which the chunker's regex
    then splits on).
    """
    try:
        with httpx.Client(
            headers={"User-Agent": _USER_AGENT}, follow_redirects=True, timeout=timeout,
        ) as client:
            resp = client.get(url)
            resp.raise_for_status()
            html = resp.text
    except httpx.HTTPStatusError as e:
        logger.warning("HTTP %d fetching %s: %s", e.response.status_code, url, e)
        return ""
    except httpx.RequestError as e:
        logger.warning("Request error fetching %s: %s", url, e)
        return ""

    converter = html2text.HTML2Text()
    converter.ignore_links = True
    converter.ignore_images = True
    converter.body_width = 0
    converter.unicode_snob = True
    converter.single_line_break = False
    converter.bypass_tables = True

    text = converter.handle(html)
    return re.sub(r"\n{3,}", "\n\n", text).strip()
