"""Structure-aware chunking for official documents (statutes, regulations, etc).

Clone-and-patch of mcp-rag-server's markdown_chunker.py (chunk_markdown_text /
_split_into_sections / _process_section): same heading-split-then-paragraph-
overflow strategy, the only real change is that the heading boundary is a
caller-supplied regex instead of a hardcoded '#'/'##'/'###' markdown pattern,
so a source list entry can point this at "^§\\s*\\d" (CFR), "^Sec\\.\\s*\\d"
(Texas statutes), or any other citation-numbered heading shape.

A chunk boundary must land on a real citation boundary, never mid-section:
that's what makes every stored chunk traceable back to an exact citation
instead of an arbitrary slice of text (see clean-rag/CLAUDE.md, "Why the KB
is gone" -- a chunk with no falsifiable citation is exactly the failure mode
that got the old topic KB removed).
"""

import re
from collections.abc import Callable
from dataclasses import dataclass

DEFAULT_HEADING_PATTERN = r"^#{1,3}\s+"


@dataclass
class DocChunk:
    """A structure-bound chunk of a legal/official text, before embedding."""
    content: str
    heading: str
    line_start: int
    line_end: int
    token_count_approx: int


def estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 chars per token for English."""
    return len(text) // 4


def heading_pattern_matches(text: str, heading_pattern: str) -> bool:
    """True if `heading_pattern` matches at least one line of `text`.

    Tested per line with re.match, exactly the way _split_into_sections finds
    section boundaries, so this answers "does this text actually contain the
    sections this source claims to have" without duplicating the split logic.
    """
    heading_re = re.compile(heading_pattern)
    return any(heading_re.match(line) for line in text.split("\n"))


def chunk_by_heading(
    text: str,
    heading_pattern: str = DEFAULT_HEADING_PATTERN,
    max_tokens: int = 500,
    min_tokens: int = 50,
    token_counter: Callable[[str], int] = estimate_tokens,
) -> list[DocChunk]:
    """Split text into chunks at heading-pattern boundaries.

    Args:
        text: Plain text or markdown to chunk.
        heading_pattern: Regex (re.match, tested per line) identifying a line
            that starts a new section/citation, e.g. r"^Sec\\.\\s*\\d+\\.\\d+".
            The matched line becomes the chunk's `heading`.
        max_tokens: Max tokens per chunk, measured by `token_counter`. Sections
            over this are split at paragraph boundaries, never mid-heading.
        min_tokens: Drop chunks below this size as noise.
        token_counter: How a chunk's token count is measured. Defaults to the
            rough 4-chars-per-token estimate for standalone use; callers that
            embed pass the embedder's real subword tokenizer so no chunk can
            exceed what the model actually encodes (the estimate under-counts
            dense legal text and let oversized chunks through).
    """
    lines = text.split("\n")
    sections = _split_into_sections(lines, heading_pattern)

    chunks = []
    for section in sections:
        chunks.extend(_process_section(section, max_tokens, min_tokens, token_counter))

    if len(chunks) > 1 and chunks[-1].token_count_approx < min_tokens:
        last = chunks[-1]
        prev = chunks[-2]
        # Only merge a runt tail back if the result still fits the limit;
        # merging blindly could push the combined chunk past what the embedder
        # can encode, reintroducing the very overflow this guard prevents.
        if prev.token_count_approx + last.token_count_approx <= max_tokens:
            chunks.pop()
            chunks[-1] = DocChunk(
                content=prev.content + "\n\n" + last.content,
                heading=prev.heading,
                line_start=prev.line_start,
                line_end=last.line_end,
                token_count_approx=token_counter(prev.content + "\n\n" + last.content),
            )

    return chunks


@dataclass
class _Section:
    heading: str
    content: str
    line_start: int
    line_end: int


def _split_into_sections(lines: list[str], heading_pattern: str) -> list[_Section]:
    """Split lines into sections based on the caller-supplied heading regex."""
    heading_re = re.compile(heading_pattern)
    sections = []
    current_heading = "Preamble"
    current_lines: list[str] = []
    current_start = 1  # 1-indexed

    for i, line in enumerate(lines):
        if heading_re.match(line):
            if current_lines or sections == []:
                content = "\n".join(current_lines).strip()
                if content:
                    sections.append(_Section(
                        heading=current_heading,
                        content=content,
                        line_start=current_start,
                        line_end=i,
                    ))
            current_heading = line.strip()
            current_lines = [line]
            current_start = i + 1
        else:
            current_lines.append(line)

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
    section: _Section, max_tokens: int, min_tokens: int,
    token_counter: Callable[[str], int],
) -> list[DocChunk]:
    """Process a single section, splitting at paragraph boundaries if too large."""
    tokens = token_counter(section.content)

    if tokens <= max_tokens:
        return [DocChunk(
            content=section.content,
            heading=section.heading,
            line_start=section.line_start,
            line_end=section.line_end,
            token_count_approx=tokens,
        )]

    # Split on any run of newlines, not just blank-line gaps: markdown
    # separates paragraphs with a blank line ("\n\n"), but real eCFR text puts
    # each <P> on its own single-newline-separated line, so a "\n\n+" split
    # found nothing to split on and the whole oversized section stayed one
    # chunk that the embedder then silently truncated. Any single paragraph
    # still over the limit is broken finer (sentences, then words) so no chunk
    # can exceed what the embedder actually encodes.
    paragraphs: list[str] = []
    for block in re.split(r"\n+", section.content):
        block = block.strip()
        if block:
            paragraphs.extend(_split_to_limit(block, max_tokens, token_counter))

    chunks = []
    current_text = ""
    current_start = section.line_start

    for para in paragraphs:
        para_tokens = token_counter(para)
        current_tokens = token_counter(current_text) if current_text else 0

        if current_text and (current_tokens + para_tokens) > max_tokens:
            line_count = current_text.count("\n") + 1
            chunks.append(DocChunk(
                content=current_text.strip(),
                heading=section.heading,
                line_start=current_start,
                line_end=current_start + line_count - 1,
                token_count_approx=current_tokens,
            ))
            current_start = current_start + line_count
            current_text = para
        else:
            current_text = (current_text + "\n\n" + para).strip() if current_text else para

    if current_text.strip():
        chunks.append(DocChunk(
            content=current_text.strip(),
            heading=section.heading,
            line_start=current_start,
            line_end=section.line_end,
            token_count_approx=token_counter(current_text),
        ))

    return chunks


def _split_to_limit(
    text: str, max_tokens: int, token_counter: Callable[[str], int],
) -> list[str]:
    """Break one paragraph into pieces each within max_tokens.

    Splits on the coarsest boundary that helps: sentence ends first, then any
    whitespace, then a last-resort character cut for an unsplittable run. This
    only fires for a single paragraph that alone exceeds the embedder's limit;
    normal paragraphs pass straight through.
    """
    if token_counter(text) <= max_tokens:
        return [text]

    for pattern in (r"(?<=[.;:])\s+", r"\s+"):
        parts = [p for p in re.split(pattern, text) if p]
        if len(parts) < 2:
            continue
        pieces: list[str] = []
        buf = ""
        for part in parts:
            candidate = f"{buf} {part}".strip() if buf else part
            if buf and token_counter(candidate) > max_tokens:
                pieces.append(buf)
                buf = part
            else:
                buf = candidate
        if buf:
            pieces.append(buf)
        result: list[str] = []
        for piece in pieces:
            if token_counter(piece) <= max_tokens:
                result.append(piece)
            else:
                result.extend(_split_to_limit(piece, max_tokens, token_counter))
        return result

    # A single token run longer than the limit (no whitespace to split on):
    # cut on character count, conservatively sized so no piece can overflow.
    approx = max(1, max_tokens * 3)
    return [text[i:i + approx] for i in range(0, len(text), approx)]
