"""PDF text extraction and chunking for research RAG.

Uses PyMuPDF (fitz) for fast, reliable text extraction. Splits at section
boundaries detected from heading-like lines, falling back to paragraph splits.
"""

import logging
import re
import tempfile
from pathlib import Path

from rag_server.indexing.markdown_chunker import RawChunk, estimate_tokens

logger = logging.getLogger(__name__)

# Pages with fewer than this many chars are image-only or blank — skip
MIN_PAGE_CHARS = 50


def chunk_pdf_file(
    path: str,
    source_url: str | None = None,
    max_tokens: int = 512,
) -> list[RawChunk]:
    """Extract text from a local PDF and return chunks.

    Args:
        path: Absolute path to the PDF file.
        source_url: Original URL if the PDF was downloaded (used in metadata).
        max_tokens: Target maximum tokens per chunk.

    Returns:
        List of RawChunk objects, empty if PDF is unreadable or empty.
    """
    try:
        import fitz  # PyMuPDF
    except ImportError:
        logger.error("PyMuPDF not installed. Run: pip install pymupdf")
        return []

    try:
        doc = fitz.open(path)
    except Exception as e:
        logger.warning("Cannot open PDF %s: %s", path, e)
        return []

    if doc.page_count == 0:
        logger.warning("Empty PDF: %s", path)
        doc.close()
        return []

    # Extract per-page text, skip image-only pages
    pages: list[tuple[int, str]] = []  # (page_number, text)
    for page_num, page in enumerate(doc, start=1):
        text = page.get_text("text")  # plain text extraction
        if text and len(text.strip()) >= MIN_PAGE_CHARS:
            pages.append((page_num, text.strip()))

    doc.close()

    if not pages:
        logger.warning("No extractable text in PDF: %s", path)
        return []

    # Concatenate all page text with page boundary markers
    full_text = "\n\n".join(f"[Page {pn}]\n{text}" for pn, text in pages)

    # Detect title from first page (first non-empty line)
    first_page_lines = pages[0][1].split("\n")
    title = next((ln.strip() for ln in first_page_lines if ln.strip()), Path(path).stem)

    return _chunk_pdf_text(full_text, title=title, max_tokens=max_tokens)


def chunk_pdf_bytes(
    data: bytes,
    source_id: str,
    max_tokens: int = 512,
) -> list[RawChunk]:
    """Extract text from PDF bytes (e.g., downloaded from a URL) and return chunks.

    Writes to a temp file since PyMuPDF requires a file path or file-like object.
    """
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(data)
        tmp_path = tmp.name

    try:
        return chunk_pdf_file(tmp_path, source_url=source_id, max_tokens=max_tokens)
    finally:
        try:
            Path(tmp_path).unlink()
        except OSError:
            pass


def chunk_pdf_url(url: str, max_tokens: int = 512) -> list[RawChunk]:
    """Download a PDF from a URL and return chunks.

    Uses httpx for downloading. Falls back to an empty list on network errors.
    """
    import httpx

    logger.info("Downloading PDF: %s", url)
    try:
        with httpx.Client(
            headers={"User-Agent": "Mozilla/5.0 (research-rag/1.0)"},
            follow_redirects=True,
            timeout=30,  # PDFs can be large
        ) as client:
            response = client.get(url)
            response.raise_for_status()
            return chunk_pdf_bytes(response.content, source_id=url, max_tokens=max_tokens)
    except httpx.HTTPStatusError as e:
        logger.warning("HTTP %d downloading PDF %s", e.response.status_code, url)
        return []
    except httpx.RequestError as e:
        logger.warning("Network error downloading PDF %s: %s", url, e)
        return []


# ─── Internal helpers ────────────────────────────────────────────────────────

def _is_heading_line(line: str) -> bool:
    """Heuristic: detect section headings in PDF-extracted text.

    PDFs don't have semantic heading tags, so we use patterns:
    - All uppercase line, 3-80 chars (e.g., "INTRODUCTION")
    - Numbered heading: "1.", "1.1", "2.3.1" followed by text
    - Short line that's entirely bold/distinct (hard to detect without layout info,
      so we rely on length and capitalization)
    """
    stripped = line.strip()
    if not stripped or len(stripped) < 3 or len(stripped) > 120:
        return False

    # Numbered heading: "1. Introduction" / "2.3 Related Work"
    if re.match(r"^\d+(\.\d+)*\.?\s+[A-Z]", stripped):
        return True

    # All-caps heading (allow spaces and some punctuation)
    if stripped.isupper() and len(stripped) <= 80 and not stripped.isdigit():
        return True

    return False


def _chunk_pdf_text(
    text: str,
    title: str,
    max_tokens: int = 512,
    min_tokens: int = 40,
) -> list[RawChunk]:
    """Split PDF text into chunks at detected section boundaries."""
    lines = text.split("\n")
    sections: list[tuple[str, list[str]]] = []  # (heading, lines)
    current_heading = title
    current_lines: list[str] = []

    for line in lines:
        if _is_heading_line(line):
            if current_lines:
                sections.append((current_heading, current_lines))
            current_heading = line.strip()
            current_lines = []
        else:
            current_lines.append(line)

    if current_lines:
        sections.append((current_heading, current_lines))

    chunks: list[RawChunk] = []
    chunk_index = 0

    for heading, section_lines in sections:
        section_text = "\n".join(section_lines).strip()
        if not section_text:
            continue

        # Clean up excessive whitespace common in PDF extractions
        section_text = re.sub(r"\n{3,}", "\n\n", section_text)
        section_text = re.sub(r" {2,}", " ", section_text)

        section_tokens = estimate_tokens(section_text)

        if section_tokens <= max_tokens:
            if section_tokens >= min_tokens:
                chunks.append(RawChunk(
                    content=section_text,
                    section=heading,
                    line_start=chunk_index,
                    line_end=chunk_index,
                    token_count_approx=section_tokens,
                ))
                chunk_index += 1
        else:
            # Split large sections at paragraph boundaries
            paragraphs = re.split(r"\n\n+", section_text)
            current_parts: list[str] = []
            current_tokens = 0

            for para in paragraphs:
                para = para.strip()
                if not para:
                    continue
                para_tokens = estimate_tokens(para)

                if current_tokens + para_tokens > max_tokens and current_parts:
                    combined = "\n\n".join(current_parts)
                    if estimate_tokens(combined) >= min_tokens:
                        chunks.append(RawChunk(
                            content=combined,
                            section=heading,
                            line_start=chunk_index,
                            line_end=chunk_index,
                            token_count_approx=estimate_tokens(combined),
                        ))
                        chunk_index += 1
                    current_parts = [para]
                    current_tokens = para_tokens
                else:
                    current_parts.append(para)
                    current_tokens += para_tokens

            if current_parts:
                combined = "\n\n".join(current_parts)
                if estimate_tokens(combined) >= min_tokens:
                    chunks.append(RawChunk(
                        content=combined,
                        section=heading,
                        line_start=chunk_index,
                        line_end=chunk_index,
                        token_count_approx=estimate_tokens(combined),
                    ))
                    chunk_index += 1

    return chunks
