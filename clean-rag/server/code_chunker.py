"""AST-aware code chunking using tree-sitter.

Replaces the blank-line heuristic in indexing.py with function/class boundary
splitting. Falls back to blank-line chunking for languages without a tree-sitter
grammar installed.

Ported from mcp-rag-server/src/rag_server/indexing/code_chunker.py.
Parser infrastructure (parsers, language maps) imported from edge_extraction.py
to avoid duplicating the cache.
"""

import logging
import re
from dataclasses import dataclass
from pathlib import Path

from .edge_extraction import _EXT_TO_LANG, _get_parser, _walk

logger = logging.getLogger(__name__)


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


def _force_split(text: str, max_tokens: int) -> list[str]:
    """Cut *text* into pieces no larger than *max_tokens*, whatever it contains.

    The last resort behind every other splitter here. Those all cut at a natural
    boundary, a definition, a blank line, a paragraph, which works right up until
    the text has no such boundary in it. A minified bundle is one line; a wall of
    legal prose is one paragraph. Neither offers anywhere to cut, so a splitter
    that only knows natural boundaries returns the whole file as one piece.

    That is not a cosmetic problem. An oversized chunk goes straight to
    SentenceTransformer.encode, whose attention allocation grows with sequence
    length, and a single 500KB file (the MAX_FILE_SIZE ceiling in file_scan) was
    observed asking the allocator for 9663676416 bytes, 9 GB, and taking the
    indexer down with it. The model's own limit is 512 tokens. Nothing between
    the chunker and the encoder enforced it.

    So this cuts at a line boundary when there is one inside the budget, and
    slices mid line when there is not. Slicing mid line loses the tail of a token
    and can split an identifier, which is a real cost, accepted deliberately: a
    slightly ragged chunk still embeds and still retrieves, while an unsplit one
    stops the whole run.
    """
    if max_tokens <= 0:
        return [text] if text else []
    limit = max_tokens * 4  # estimate_tokens is len // 4, so invert it
    if len(text) <= limit:
        return [text] if text.strip() else []

    pieces: list[str] = []
    start = 0
    while start < len(text):
        end = start + limit
        if end >= len(text):
            piece = text[start:]
        else:
            # Prefer the last newline inside the budget. Only accept one past
            # the halfway mark, otherwise a file whose newlines cluster early
            # produces a long tail of tiny pieces.
            cut = text.rfind("\n", start + limit // 2, end)
            end = cut + 1 if cut != -1 else end
            piece = text[start:end]
        if piece.strip():
            pieces.append(piece)
        start = end
    return pieces


# Node types that represent top-level definitions per language
_DEFINITION_TYPES: dict[str, set[str]] = {
    "python": {
        "function_definition",
        "class_definition",
        "decorated_definition",
    },
    "javascript": {
        "function_declaration",
        "class_declaration",
        "export_statement",
        "lexical_declaration",
        "variable_declaration",
    },
    "typescript": {
        "function_declaration",
        "class_declaration",
        "export_statement",
        "lexical_declaration",
        "variable_declaration",
        "interface_declaration",
        "type_alias_declaration",
        "enum_declaration",
    },
    "go": {
        "function_declaration",
        "method_declaration",
        "type_declaration",
    },
    "rust": {
        "function_item",
        "impl_item",
        "struct_item",
        "trait_item",
        "enum_item",
        "mod_item",
    },
    "java": {
        "class_declaration",
        "interface_declaration",
        "enum_declaration",
        "method_declaration",
    },
    "c": {
        "function_definition",
        "declaration",
    },
    "cpp": {
        "function_definition",
        "class_specifier",
        "namespace_definition",
        "template_declaration",
    },
    "ruby": {
        "method",
        "class",
        "module",
        "singleton_method",
    },
    "bash": {
        "function_definition",
    },
    "lua": {
        "function_declaration",
        "local_function",
        "function_definition",
    },
    "kotlin": {
        "function_declaration",
        "class_declaration",
        "object_declaration",
        "companion_object",
    },
    "swift": {
        "function_declaration",
        "class_declaration",
        "struct_declaration",
        "protocol_declaration",
        "extension_declaration",
    },
    "php": {
        "function_definition",
        "class_declaration",
        "interface_declaration",
    },
    "csharp": {
        "class_declaration",
        "interface_declaration",
        "method_declaration",
        "namespace_declaration",
        "enum_declaration",
        "struct_declaration",
    },
}


def chunk_code(
    text: str,
    source_file: str,
    max_tokens: int = 500,
    min_tokens: int = 50,
    chunk_overlap: int = 0,
) -> list[RawChunk]:
    """Split source code into semantic chunks using tree-sitter AST.

    Strategy:
    1. Parse with tree-sitter to identify top-level definitions
    2. Each function/class becomes a chunk
    3. Imports and non-definition code become a file-summary chunk
    4. Large definitions are split at logical boundaries
    5. Falls back to blank-line splitting if tree-sitter unavailable

    chunk_overlap is passed to the fallback path only — AST-level chunks already
    land at logical unit boundaries (functions, classes) where overlap adds noise.
    """
    ext = Path(source_file).suffix
    language = _EXT_TO_LANG.get(ext)

    if not language:
        return _fallback_chunk(text, source_file, max_tokens, min_tokens, chunk_overlap)

    # tsx has its own parser but shares typescript's definition types
    parser_key = "tsx" if ext == ".tsx" else language
    lang_for_types = "typescript" if parser_key == "tsx" else language

    parser = _get_parser(parser_key)
    if parser is None:
        return _fallback_chunk(text, source_file, max_tokens, min_tokens, chunk_overlap)

    try:
        source_bytes = text.encode("utf-8")
        tree = parser.parse(source_bytes)
        return _chunk_from_tree(tree, text, source_file, lang_for_types, max_tokens, min_tokens)
    except Exception as e:
        logger.warning("Tree-sitter parse failed for %s: %s", source_file, e)
        return _fallback_chunk(text, source_file, max_tokens, min_tokens, chunk_overlap)


def _chunk_from_tree(
    tree, text: str, source_file: str, language: str,
    max_tokens: int, min_tokens: int,
) -> list[RawChunk]:
    """Extract chunks from a parsed tree-sitter AST."""
    lines = text.split("\n")
    root = tree.root_node
    definition_types = _DEFINITION_TYPES.get(language, set())

    # Collect top-level definition spans
    definitions = []
    for child in root.children:
        if child.type in definition_types:
            definitions.append(child)

    # If no definitions found, treat the whole file as one chunk
    if not definitions:
        return _fallback_chunk(text, source_file, max_tokens, min_tokens)

    chunks = []

    # Small import blocks (< threshold tokens) are merged into the first class/method
    # chunk rather than emitted separately. This prevents import stubs from outranking
    # the actual implementation in semantic search results.
    _SMALL_IMPORT_MERGE_THRESHOLD = 150
    _pending_import: RawChunk | None = None

    # File-summary chunk: everything before the first definition
    first_def_line = definitions[0].start_point[0]
    if first_def_line > 0:
        summary_text = "\n".join(lines[:first_def_line]).strip()
        if summary_text:
            tokens = estimate_tokens(summary_text)
            if tokens >= min_tokens:
                import_chunk = RawChunk(
                    content=summary_text,
                    section="[imports]",
                    line_start=1,
                    line_end=first_def_line,
                    token_count_approx=tokens,
                )
                if tokens < _SMALL_IMPORT_MERGE_THRESHOLD and definitions:
                    _pending_import = import_chunk
                else:
                    chunks.append(import_chunk)

    # Each definition becomes a chunk
    for i, node in enumerate(definitions):
        start_line = node.start_point[0]
        end_line = node.end_point[0]
        chunk_text = "\n".join(lines[start_line:end_line + 1])
        section_name = _extract_name(node, language)
        tokens = estimate_tokens(chunk_text)

        if _pending_import is not None and i == 0:
            merged_text = _pending_import.content + "\n\n" + chunk_text
            merged_tokens = estimate_tokens(merged_text)
            if merged_tokens <= max_tokens:
                chunk_text = merged_text
                tokens = merged_tokens
                start_line = 0  # merged chunk starts at line 1
            else:
                chunks.append(_pending_import)  # too large to merge — emit separately
            _pending_import = None

        if tokens > max_tokens:
            # Split large definitions
            sub_chunks = _split_large_definition(
                node, lines, section_name, language, max_tokens, min_tokens,
            )
            chunks.extend(sub_chunks)
        else:
            chunks.append(RawChunk(
                content=chunk_text,
                section=section_name,
                line_start=start_line + 1,
                line_end=end_line + 1,
                token_count_approx=tokens,
            ))

    # Merge trailing small chunks
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


def _extract_name(node, language: str) -> str:
    """Extract a human-readable name from an AST node."""
    # For decorated definitions, look at the inner definition
    if node.type == "decorated_definition":
        for child in node.children:
            if child.type in ("function_definition", "class_definition"):
                return _extract_name(child, language)

    # For export statements, look at the inner declaration
    if node.type == "export_statement":
        for child in node.children:
            if child.type in _DEFINITION_TYPES.get(language, set()):
                return f"export {_extract_name(child, language)}"
            if child.type in ("function_declaration", "class_declaration",
                              "interface_declaration", "type_alias_declaration",
                              "enum_declaration", "lexical_declaration",
                              "variable_declaration"):
                return f"export {_extract_name(child, language)}"
        return "export"

    # Find the name child node
    for child in node.children:
        if child.type in ("identifier", "property_identifier"):
            prefix = {
                "function_definition": "def",
                "function_declaration": "function",
                "class_definition": "class",
                "class_declaration": "class",
                "interface_declaration": "interface",
                "type_alias_declaration": "type",
                "enum_declaration": "enum",
            }.get(node.type, "")
            name = child.text.decode("utf-8") if isinstance(child.text, bytes) else child.text
            return f"{prefix} {name}" if prefix else name

    # Variable/lexical declarations: grab first identifier
    if node.type in ("variable_declaration", "lexical_declaration"):
        for desc in _walk(node):
            if desc.type in ("identifier", "property_identifier"):
                name = desc.text.decode("utf-8") if isinstance(desc.text, bytes) else desc.text
                return f"const {name}"

    return node.type


def _split_large_definition(
    node, lines: list[str], section_name: str, language: str,
    max_tokens: int, min_tokens: int,
) -> list[RawChunk]:
    """Split a large class/function into sub-chunks at method boundaries."""
    start_line = node.start_point[0]
    end_line = node.end_point[0]

    # For classes, try to split at method definitions
    if node.type in ("class_definition", "class_declaration", "decorated_definition"):
        inner = node
        if node.type == "decorated_definition":
            for child in node.children:
                if child.type == "class_definition":
                    inner = child
                    break

        methods = []
        body = None
        for child in inner.children:
            if child.type in ("block", "class_body", "statement_block"):
                body = child
                break

        if body:
            for child in body.children:
                if child.type in ("function_definition", "method_definition",
                                  "function_declaration", "decorated_definition"):
                    methods.append(child)

        if methods:
            chunks = []
            # Class header: everything before the first method
            first_method_line = methods[0].start_point[0]
            header_text = "\n".join(lines[start_line:first_method_line]).strip()
            if header_text:
                tokens = estimate_tokens(header_text)
                chunks.append(RawChunk(
                    content=header_text,
                    section=f"{section_name} [header]",
                    line_start=start_line + 1,
                    line_end=first_method_line,
                    token_count_approx=tokens,
                ))

            # Each method as its own chunk
            for method_node in methods:
                m_start = method_node.start_point[0]
                m_end = method_node.end_point[0]
                method_text = "\n".join(lines[m_start:m_end + 1])
                method_name = _extract_name(method_node, language)
                tokens = estimate_tokens(method_text)

                chunks.append(RawChunk(
                    content=method_text,
                    section=f"{section_name}.{method_name}",
                    line_start=m_start + 1,
                    line_end=m_end + 1,
                    token_count_approx=tokens,
                ))

            return chunks

    # Fallback for large functions: split at blank-line boundaries
    chunk_lines = lines[start_line:end_line + 1]
    return _split_at_blank_lines(chunk_lines, section_name, start_line, max_tokens, min_tokens)


def _split_at_blank_lines(
    lines: list[str], section: str, offset: int,
    max_tokens: int, min_tokens: int,
) -> list[RawChunk]:
    """Split lines at blank-line boundaries, respecting token limits.

    Two guards here rather than one, because blank lines cannot be relied on.
    The token check used to sit inside the "is this a blank line" branch, so a
    run of code with no blank line in it never reached the check and came out as
    one chunk however long it was. And a single minified line can exceed the
    budget on its own, which no line based accumulation can fix. So over long
    lines are cut up first, and the size check now applies on every line instead
    of only at a blank one.
    """
    chunks = []
    current_lines = []
    current_start = offset

    # A single line can be larger than the whole budget. Cut those up before
    # accumulating, otherwise the loop below has nothing it can do about them.
    lines = [piece for line in lines for piece in (_force_split(line, max_tokens) or [line])]

    current_chars = 0
    limit_chars = max_tokens * 4
    for i, line in enumerate(lines):
        current_lines.append(line)
        current_chars += len(line) + 1
        is_blank = line.strip() == ""
        is_last = i == len(lines) - 1
        # Tracked as a running total rather than re-joining the buffer on every
        # line, which would be quadratic on exactly the huge files this guards.
        over_budget = current_chars >= limit_chars

        if (is_blank or is_last or over_budget) and current_lines:
            current_text = "\n".join(current_lines)
            tokens = estimate_tokens(current_text)

            if tokens >= max_tokens or is_last or over_budget:
                chunks.append(RawChunk(
                    content=current_text.strip(),
                    section=section,
                    line_start=current_start + 1,
                    line_end=offset + i + 1,
                    token_count_approx=tokens,
                ))
                current_lines = []
                current_chars = 0
                current_start = offset + i + 1

    # Merge small trailing chunk
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


def _fallback_chunk(
    text: str, source_file: str, max_tokens: int, min_tokens: int, chunk_overlap: int = 0,
) -> list[RawChunk]:
    """Fallback: split at double-blank-line boundaries."""
    # Force-split every block before the accumulation loop sees it. The loop's
    # own size check (below) compares current + next against max_tokens, and it
    # only fires when current is not empty, so the FIRST block was emitted at
    # whatever size it happened to be. A file with no blank line in it is one
    # block, which is how a 500KB minified file became a single chunk and asked
    # the allocator for 9 GB. Splitting here means no block reaching the loop is
    # ever oversized, so the existing logic is correct again rather than patched.
    blocks = [
        piece
        for block in re.split(r"\n\n+", text)
        for piece in _force_split(block, max_tokens)
    ]
    chunks = []
    current_text = ""
    current_start = 1
    line_cursor = 1
    _overlap_text = ""

    for block in blocks:
        block_lines = block.count("\n") + 1
        block_tokens = estimate_tokens(block)
        current_tokens = estimate_tokens(current_text)

        if current_text and (current_tokens + block_tokens) > max_tokens:
            if current_tokens >= min_tokens:
                chunks.append(RawChunk(
                    content=current_text.strip(),
                    section=Path(source_file).stem,
                    line_start=current_start,
                    line_end=line_cursor - 1,
                    token_count_approx=current_tokens,
                ))
            # Carry last block as overlap
            if chunk_overlap > 0:
                tail = current_text.rsplit("\n\n", 1)[-1].strip()
                _overlap_text = tail if tail and estimate_tokens(tail) <= chunk_overlap else ""
            else:
                _overlap_text = ""
            current_text = (_overlap_text + "\n\n" + block).strip() if _overlap_text else block
            current_start = line_cursor
        else:
            current_text = (current_text + "\n\n" + block).strip() if current_text else block

        line_cursor += block_lines + 1  # +1 for the blank line between blocks

    # Final block
    if current_text.strip():
        tokens = estimate_tokens(current_text)
        if tokens >= min_tokens:
            chunks.append(RawChunk(
                content=current_text.strip(),
                section=Path(source_file).stem,
                line_start=current_start,
                line_end=line_cursor,
                token_count_approx=tokens,
            ))

    return chunks
