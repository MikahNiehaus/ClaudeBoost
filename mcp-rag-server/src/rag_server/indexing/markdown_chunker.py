"""Markdown chunking strategy. Splits on ## and ### headers."""

import re
from dataclasses import dataclass


@dataclass
class RawChunk:
    """A chunk of text before embedding."""
    content: str
    section: str
    line_start: int
    line_end: int
    token_count_approx: int


def estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 chars per token for English."""
    return len(text) // 4


def chunk_markdown_text(
    text: str,
    source_id: str,
    max_tokens: int = 512,
    min_tokens: int = 40,
    chunk_overlap: int = 0,
) -> list[RawChunk]:
    """Split a markdown string into chunks at heading boundaries.

    Shared implementation used by both chunk_markdown (local files) and
    url_chunker (HTML pages converted to markdown). Splits on H1, H2, and H3;
    overflows to paragraph splits when a section is too large.

    Args:
        text: Markdown text to chunk.
        source_id: File path or URL — for logging only; not stored in chunks.
        max_tokens: Approximate max tokens per chunk (4 chars per token).
        min_tokens: Drop chunks below this size as noise.
        chunk_overlap: If > 0, carry the last paragraph of each chunk into the next.
    """
    lines = text.split("\n")
    sections = _split_into_sections(lines)

    chunks = []
    for section in sections:
        section_chunks = _process_section(section, max_tokens, min_tokens, chunk_overlap)
        chunks.extend(section_chunks)

    # Merge trailing small chunks into the previous one
    if len(chunks) > 1 and chunks[-1].token_count_approx < min_tokens:
        last = chunks.pop()
        chunks[-1] = RawChunk(
            content=chunks[-1].content + "\n\n" + last.content,
            section=chunks[-1].section,
            line_start=chunks[-1].line_start,
            line_end=last.line_end,
            token_count_approx=chunks[-1].token_count_approx + last.token_count_approx,
        )

    return chunks


def chunk_markdown(
    text: str,
    source_file: str,
    max_tokens: int = 500,
    min_tokens: int = 50,
    chunk_overlap: int = 0,
) -> list[RawChunk]:
    """Split a local markdown file into chunks based on section headers.

    Delegates to chunk_markdown_text with local-file defaults.
    """
    return chunk_markdown_text(text, source_file, max_tokens, min_tokens, chunk_overlap)


@dataclass
class _Section:
    heading: str
    content: str
    line_start: int
    line_end: int


def _split_into_sections(lines: list[str]) -> list[_Section]:
    """Split lines into sections based on ## and ### headers."""
    sections = []
    current_heading = "Introduction"
    current_lines = []
    current_start = 1  # 1-indexed

    for i, line in enumerate(lines):
        if re.match(r"^#{1,3}\s+", line):
            # Save previous section
            if current_lines or sections == []:
                content = "\n".join(current_lines).strip()
                if content:
                    sections.append(_Section(
                        heading=current_heading,
                        content=content,
                        line_start=current_start,
                        line_end=i,  # line before this header
                    ))
            current_heading = re.sub(r"^#{1,3}\s+", "", line).strip()
            current_lines = []
            current_start = i + 1  # 1-indexed
        else:
            current_lines.append(line)

    # Don't forget the last section
    if current_lines:
        content = "\n".join(current_lines).strip()
        if content:
            sections.append(_Section(
                heading=current_heading,
                content=content,
                line_start=current_start,
                line_end=len(lines),
            ))

    return sections


def _process_section(
    section: _Section, max_tokens: int, min_tokens: int, chunk_overlap: int = 0,
) -> list[RawChunk]:
    """Process a single section, splitting if too large."""
    tokens = estimate_tokens(section.content)

    if tokens <= max_tokens:
        return [RawChunk(
            content=section.content,
            section=section.heading,
            line_start=section.line_start,
            line_end=section.line_end,
            token_count_approx=tokens,
        )]

    # Section is too large — split at paragraph boundaries
    paragraphs = re.split(r"\n\n+", section.content)
    chunks = []
    current_text = ""
    current_start = section.line_start
    _overlap_text = ""  # last paragraph of the previous chunk, carried forward

    for para in paragraphs:
        para_tokens = estimate_tokens(para)
        current_tokens = estimate_tokens(current_text)

        if current_text and (current_tokens + para_tokens) > max_tokens:
            # Save current chunk
            line_count = current_text.count("\n") + 1
            chunks.append(RawChunk(
                content=current_text.strip(),
                section=section.heading,
                line_start=current_start,
                line_end=current_start + line_count - 1,
                token_count_approx=current_tokens,
            ))
            # Carry the last paragraph into the next chunk when overlap is enabled.
            # This preserves context at split points without duplicating full chunks.
            if chunk_overlap > 0:
                tail = current_text.rsplit("\n\n", 1)[-1].strip()
                _overlap_text = tail if tail and estimate_tokens(tail) <= chunk_overlap else ""
            else:
                _overlap_text = ""
            current_start = current_start + line_count
            current_text = (_overlap_text + "\n\n" + para).strip() if _overlap_text else para
        else:
            current_text = (current_text + "\n\n" + para).strip() if current_text else para

    # Last paragraph group
    if current_text.strip():
        chunks.append(RawChunk(
            content=current_text.strip(),
            section=section.heading,
            line_start=current_start,
            line_end=section.line_end,
            token_count_approx=estimate_tokens(current_text),
        ))

    return chunks
