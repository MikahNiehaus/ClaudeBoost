"""Code chunking via tree-sitter AST parsing.

Extracts functions, classes, and file-level summaries as RawChunks.
Falls back to blank-line splitting for unsupported languages or parse failures.
"""

import logging
from pathlib import Path

from rag_server.indexing.markdown_chunker import RawChunk, estimate_tokens

logger = logging.getLogger(__name__)

# Tree-sitter language modules — imported lazily to avoid hard failure
_PARSERS = {}

# Node types that represent top-level definitions per language
_DEFINITION_TYPES = {
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
}

# Map file extensions to tree-sitter language key
_EXT_TO_LANG = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
}


def _get_parser(language: str):
    """Lazy-load a tree-sitter parser for the given language."""
    if language in _PARSERS:
        return _PARSERS[language]

    try:
        from tree_sitter import Language, Parser

        if language == "python":
            import tree_sitter_python as ts_mod
        elif language == "javascript":
            import tree_sitter_javascript as ts_mod
        elif language == "typescript":
            import tree_sitter_typescript as ts_mod
            # tree-sitter-typescript exposes .language_typescript() and .language_tsx()
            lang_obj = Language(ts_mod.language_typescript())
            parser = Parser(lang_obj)
            _PARSERS[language] = parser
            # Also set up tsx
            tsx_lang = Language(ts_mod.language_tsx())
            tsx_parser = Parser(tsx_lang)
            _PARSERS["tsx"] = tsx_parser
            return parser
        else:
            _PARSERS[language] = None
            return None

        lang_obj = Language(ts_mod.language())
        parser = Parser(lang_obj)
        _PARSERS[language] = parser
        return parser
    except (ImportError, Exception) as e:
        logger.warning("Failed to load tree-sitter for %s: %s", language, e)
        _PARSERS[language] = None
        return None


def chunk_code(
    text: str,
    source_file: str,
    max_tokens: int = 500,
    min_tokens: int = 50,
) -> list[RawChunk]:
    """Split source code into semantic chunks using tree-sitter AST.

    Strategy:
    1. Parse with tree-sitter to identify top-level definitions
    2. Each function/class becomes a chunk
    3. Imports and non-definition code become a file-summary chunk
    4. Large definitions are split at logical boundaries
    5. Falls back to blank-line splitting if tree-sitter unavailable

    Returns list[RawChunk] matching the interface of other chunkers.
    """
    ext = Path(source_file).suffix
    language = _EXT_TO_LANG.get(ext)

    if not language:
        return _fallback_chunk(text, source_file, max_tokens, min_tokens)

    # Use tsx parser for .tsx files
    parser_key = "tsx" if ext == ".tsx" else language
    # Ensure base language parser is loaded first (triggers tsx setup for typescript)
    if parser_key == "tsx" and "tsx" not in _PARSERS:
        _get_parser("typescript")
    parser = _get_parser(parser_key) if parser_key != "tsx" else _PARSERS.get("tsx")

    if parser is None:
        parser = _get_parser(language)
    if parser is None:
        return _fallback_chunk(text, source_file, max_tokens, min_tokens)

    try:
        source_bytes = text.encode("utf-8")
        tree = parser.parse(source_bytes)
        return _chunk_from_tree(tree, text, source_file, language, max_tokens, min_tokens)
    except Exception as e:
        logger.warning("Tree-sitter parse failed for %s: %s", source_file, e)
        return _fallback_chunk(text, source_file, max_tokens, min_tokens)


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

    # File-summary chunk: everything before the first definition
    first_def_line = definitions[0].start_point[0]
    if first_def_line > 0:
        summary_text = "\n".join(lines[:first_def_line]).strip()
        if summary_text:
            tokens = estimate_tokens(summary_text)
            if tokens >= min_tokens:
                chunks.append(RawChunk(
                    content=summary_text,
                    section="[imports]",
                    line_start=1,
                    line_end=first_def_line,
                    token_count_approx=tokens,
                ))

    # Each definition becomes a chunk
    for node in definitions:
        start_line = node.start_point[0]
        end_line = node.end_point[0]
        chunk_text = "\n".join(lines[start_line:end_line + 1])
        section_name = _extract_name(node, language)
        tokens = estimate_tokens(chunk_text)

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


def _walk(node):
    """Depth-first walk of AST nodes."""
    yield node
    for child in node.children:
        yield from _walk(child)


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
    """Split lines at blank-line boundaries, respecting token limits."""
    chunks = []
    current_lines = []
    current_start = offset

    for i, line in enumerate(lines):
        current_lines.append(line)
        is_blank = line.strip() == ""
        is_last = i == len(lines) - 1

        if (is_blank or is_last) and current_lines:
            current_text = "\n".join(current_lines)
            tokens = estimate_tokens(current_text)

            if tokens >= max_tokens or is_last:
                chunks.append(RawChunk(
                    content=current_text.strip(),
                    section=section,
                    line_start=current_start + 1,
                    line_end=offset + i + 1,
                    token_count_approx=tokens,
                ))
                current_lines = []
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
    text: str, source_file: str, max_tokens: int, min_tokens: int,
) -> list[RawChunk]:
    """Fallback: split at double-blank-line boundaries."""
    import re
    blocks = re.split(r"\n\n+", text)
    chunks = []
    current_text = ""
    current_start = 1
    line_cursor = 1

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
            current_text = block
            current_start = line_cursor
        else:
            current_text = (current_text + "\n\n" + block).strip()

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
