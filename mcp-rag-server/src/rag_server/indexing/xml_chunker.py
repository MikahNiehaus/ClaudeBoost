"""XML chunking strategy. Splits on top-level element boundaries."""

import re

from rag_server.indexing.markdown_chunker import RawChunk, estimate_tokens


def chunk_xml(text: str, source_file: str, max_tokens: int = 500, min_tokens: int = 50) -> list[RawChunk]:
    """Split XML into chunks based on top-level element boundaries.

    Strategy:
    - Find top-level elements (direct children of root)
    - Each element becomes a chunk
    - If an element exceeds max_tokens, split at nested element boundaries
    - Merge very small elements with the next one
    """
    lines = text.split("\n")

    # Find top-level elements by tracking tag depth
    elements = _extract_elements(lines)

    chunks = []
    pending = None  # Small element waiting to merge

    for element in elements:
        tokens = estimate_tokens(element.content)

        if pending:
            if tokens + pending.token_count_approx < max_tokens:
                # Merge small pending with this element
                element = RawChunk(
                    content=pending.content + "\n" + element.content,
                    section=pending.section,
                    line_start=pending.line_start,
                    line_end=element.line_end,
                    token_count_approx=pending.token_count_approx + tokens,
                )
                tokens = element.token_count_approx
                pending = None
            else:
                chunks.append(pending)
                pending = None

        if tokens < min_tokens:
            pending = element
        elif tokens > max_tokens:
            sub_chunks = _split_large_element(element, max_tokens)
            chunks.extend(sub_chunks)
        else:
            chunks.append(element)

    if pending:
        if chunks:
            last = chunks[-1]
            chunks[-1] = RawChunk(
                content=last.content + "\n" + pending.content,
                section=last.section,
                line_start=last.line_start,
                line_end=pending.line_end,
                token_count_approx=last.token_count_approx + pending.token_count_approx,
            )
        else:
            chunks.append(pending)

    return chunks


def _extract_elements(lines: list[str]) -> list[RawChunk]:
    """Extract top-level XML elements as chunks."""
    elements = []
    current_lines = []
    current_start = 1
    current_tag = "root"
    depth = 0
    in_element = False

    for i, line in enumerate(lines):
        stripped = line.strip()

        # Skip XML declaration and comments
        if stripped.startswith("<?") or stripped.startswith("<!--"):
            continue

        # Detect opening tags
        open_match = re.match(r"<(\w[\w-]*)[\s>]", stripped)
        close_match = re.search(r"</(\w[\w-]*)>", stripped)
        self_closing = stripped.endswith("/>")

        if open_match and depth == 1:
            # Starting a new top-level child element
            if current_lines and in_element:
                content = "\n".join(current_lines).strip()
                if content:
                    elements.append(RawChunk(
                        content=content,
                        section=current_tag,
                        line_start=current_start,
                        line_end=i,
                        token_count_approx=estimate_tokens(content),
                    ))
            current_lines = [line]
            current_start = i + 1
            current_tag = open_match.group(1)
            in_element = True
            if self_closing:
                content = line.strip()
                elements.append(RawChunk(
                    content=content,
                    section=current_tag,
                    line_start=current_start,
                    line_end=i + 1,
                    token_count_approx=estimate_tokens(content),
                ))
                current_lines = []
                in_element = False
                continue
        elif in_element:
            current_lines.append(line)

        # Track depth
        if open_match and not self_closing:
            depth += 1
        if close_match:
            depth -= 1
            if depth == 1 and in_element:
                # Closing a top-level child element
                content = "\n".join(current_lines).strip()
                if content:
                    elements.append(RawChunk(
                        content=content,
                        section=current_tag,
                        line_start=current_start,
                        line_end=i + 1,
                        token_count_approx=estimate_tokens(content),
                    ))
                current_lines = []
                in_element = False

    # Remaining content
    if current_lines:
        content = "\n".join(current_lines).strip()
        if content:
            elements.append(RawChunk(
                content=content,
                section=current_tag,
                line_start=current_start,
                line_end=len(lines),
                token_count_approx=estimate_tokens(content),
            ))

    # If no elements found, treat the whole file as one chunk
    if not elements:
        full_text = "\n".join(lines).strip()
        if full_text:
            elements.append(RawChunk(
                content=full_text,
                section="document",
                line_start=1,
                line_end=len(lines),
                token_count_approx=estimate_tokens(full_text),
            ))

    return elements


def _split_large_element(element: RawChunk, max_tokens: int) -> list[RawChunk]:
    """Split a large element at line boundaries."""
    lines = element.content.split("\n")
    chunks = []
    current_lines = []
    current_tokens = 0
    current_start = element.line_start

    for i, line in enumerate(lines):
        line_tokens = estimate_tokens(line)
        if current_tokens + line_tokens > max_tokens and current_lines:
            chunks.append(RawChunk(
                content="\n".join(current_lines),
                section=element.section,
                line_start=current_start,
                line_end=current_start + len(current_lines) - 1,
                token_count_approx=current_tokens,
            ))
            current_start = current_start + len(current_lines)
            current_lines = [line]
            current_tokens = line_tokens
        else:
            current_lines.append(line)
            current_tokens += line_tokens

    if current_lines:
        chunks.append(RawChunk(
            content="\n".join(current_lines),
            section=element.section,
            line_start=current_start,
            line_end=element.line_end,
            token_count_approx=current_tokens,
        ))

    return chunks
