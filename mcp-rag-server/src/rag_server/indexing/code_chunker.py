"""Code chunking and graph-edge extraction via tree-sitter AST parsing.

Public API:
    chunk_code(text, source_file, ...) -> list[RawChunk]
    extract_edges(text, language, filepath) -> list[GraphEdge]

chunk_code falls back to blank-line splitting for unsupported languages.
extract_edges returns [] for unsupported/unparseable files — never raises.
"""

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from rag_server.indexing.markdown_chunker import RawChunk, estimate_tokens

if TYPE_CHECKING:
    from rag_server.ports.graph_port import GraphEdge

logger = logging.getLogger(__name__)

# Tree-sitter language modules — imported lazily to avoid hard failure
_PARSERS: dict = {}

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
    # css, html, json, toml, yaml: no top-level definitions — fallback chunker handles them
}

# Map file extensions to tree-sitter language key (AST-aware languages only)
# Data formats (css/html/json/toml/yaml) are discovered by project.py but chunked
# via _fallback_chunk — they intentionally do not appear here.
_EXT_TO_LANG: dict[str, str] = {
    ".py":   "python",
    ".js":   "javascript",
    ".jsx":  "javascript",
    ".mjs":  "javascript",
    ".ts":   "typescript",
    ".tsx":  "typescript",
    ".go":   "go",
    ".rs":   "rust",
    ".java": "java",
    ".c":    "c",
    ".h":    "c",
    ".cpp":  "cpp",
    ".cc":   "cpp",
    ".cxx":  "cpp",
    ".hpp":  "cpp",
    ".rb":   "ruby",
    ".sh":   "bash",
    ".bash": "bash",
    ".lua":  "lua",
    ".kt":   "kotlin",
    ".kts":  "kotlin",
    ".swift": "swift",
    ".php":  "php",
    ".cs":   "csharp",
}

# Map language key -> (module_name, method_name) for dynamic import.
# TypeScript is handled separately (exposes language_typescript + language_tsx).
_LANG_MODULE_MAP: dict[str, tuple[str, str]] = {
    "python":     ("tree_sitter_python",     "language"),
    "javascript": ("tree_sitter_javascript", "language"),
    "go":         ("tree_sitter_go",         "language"),
    "rust":       ("tree_sitter_rust",       "language"),
    "c":          ("tree_sitter_c",          "language"),
    "cpp":        ("tree_sitter_cpp",        "language"),
    "java":       ("tree_sitter_java",       "language"),
    "ruby":       ("tree_sitter_ruby",       "language"),
    "bash":       ("tree_sitter_bash",       "language"),
    "lua":        ("tree_sitter_lua",        "language"),
    "kotlin":     ("tree_sitter_kotlin",     "language"),
    "swift":      ("tree_sitter_swift",      "language"),
    "php":        ("tree_sitter_php",        "language"),
    "csharp":     ("tree_sitter_c_sharp",    "language"),
}


def _get_parser(language: str):
    """Lazy-load a tree-sitter parser for the given language.

    Returns None (and caches None) if the tree-sitter grammar package is not
    installed — callers fall back to blank-line chunking.
    """
    if language in _PARSERS:
        return _PARSERS[language]

    # tsx shares the typescript grammar package
    if language == "tsx":
        _get_parser("typescript")
        return _PARSERS.get("tsx")

    # TypeScript exposes two parsers via non-standard method names
    if language == "typescript":
        return _load_typescript_parsers()

    if language not in _LANG_MODULE_MAP:
        _PARSERS[language] = None
        return None

    module_name, method_name = _LANG_MODULE_MAP[language]
    try:
        import importlib
        from tree_sitter import Language, Parser
        ts_mod = importlib.import_module(module_name)
        lang_fn = getattr(ts_mod, method_name)
        parser = Parser(Language(lang_fn()))
        _PARSERS[language] = parser
        return parser
    except (ImportError, AttributeError, Exception) as e:
        logger.warning("tree-sitter grammar not available for %s: %s", language, e)
        _PARSERS[language] = None
        return None


def _load_typescript_parsers():
    """Load tree-sitter-typescript, which exposes ts and tsx as separate parsers."""
    try:
        import tree_sitter_typescript as ts_mod
        from tree_sitter import Language, Parser
        _PARSERS["typescript"] = Parser(Language(ts_mod.language_typescript()))
        _PARSERS["tsx"] = Parser(Language(ts_mod.language_tsx()))
        return _PARSERS["typescript"]
    except (ImportError, Exception) as e:
        logger.warning("tree-sitter grammar not available for typescript: %s", e)
        _PARSERS["typescript"] = None
        _PARSERS["tsx"] = None
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

    # tsx has its own parser but shares typescript's definition types
    parser_key = "tsx" if ext == ".tsx" else language
    lang_for_types = "typescript" if parser_key == "tsx" else language

    parser = _get_parser(parser_key)
    if parser is None:
        return _fallback_chunk(text, source_file, max_tokens, min_tokens)

    try:
        source_bytes = text.encode("utf-8")
        tree = parser.parse(source_bytes)
        return _chunk_from_tree(tree, text, source_file, lang_for_types, max_tokens, min_tokens)
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

    # Small import blocks (< threshold tokens) are merged into the first class/method
    # chunk rather than emitted separately. This prevents import stubs from outranking
    # the actual implementation in semantic search results.
    _SMALL_IMPORT_MERGE_THRESHOLD = 150
    _pending_import: "RawChunk | None" = None

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


# ---------------------------------------------------------------------------
# Graph edge extraction
# ---------------------------------------------------------------------------

def extract_edges(text: str, language: str, filepath: str) -> "list[GraphEdge]":
    """Extract structural edges from source code via tree-sitter AST.

    Returns a list of GraphEdge — never raises.  Returns [] for unsupported
    languages, unparseable files, or files with no detectable edges.

    Edge types:
        "imports"  — import/require/use statements          confidence: EXTRACTED
        "inherits" — class A extends/inherits B             confidence: EXTRACTED
        "calls"    — function calls to names defined        confidence: INFERRED
                     elsewhere (approximate — name-match only)

    The *filepath* is stored on edges as-is (usually a project-relative path).
    """
    from rag_server.ports.graph_port import GraphEdge  # avoid circular at module level

    parser_key = "tsx" if filepath.endswith(".tsx") else language
    parser = _get_parser(parser_key)
    if parser is None:
        return []

    try:
        tree = parser.parse(text.encode("utf-8"))
    except Exception as e:
        logger.debug("extract_edges: parse failed for %s: %s", filepath, e)
        return []

    edges: list = []
    lang_for_walk = "typescript" if parser_key == "tsx" else language

    _walk_for_edges(tree.root_node, text, filepath, lang_for_walk, edges)
    return edges


def _walk_for_edges(node, text: str, filepath: str, language: str, edges: list) -> None:
    """Recursive AST walk — fills *edges* in place."""
    from rag_server.ports.graph_port import GraphEdge

    node_type = node.type

    # ------------------------------------------------------------------
    # Import edges (EXTRACTED)
    # ------------------------------------------------------------------
    if language == "python":
        if node_type == "import_statement":
            # import foo.bar  →  target_symbol = "foo.bar"
            for child in node.children:
                if child.type in ("dotted_name", "aliased_import"):
                    name = _node_text(child)
                    edges.append(GraphEdge(
                        source_file=filepath, source_symbol="<module>",
                        target_file="", target_symbol=name,
                        edge_type="imports", confidence="EXTRACTED",
                    ))

        elif node_type == "import_from_statement":
            # from foo import bar  →  target_symbol = "foo"
            module_name = ""
            for child in node.children:
                if child.type == "dotted_name":
                    module_name = _node_text(child)
                    break
            if module_name:
                edges.append(GraphEdge(
                    source_file=filepath, source_symbol="<module>",
                    target_file="", target_symbol=module_name,
                    edge_type="imports", confidence="EXTRACTED",
                ))

        elif node_type == "class_definition":
            # class A(B, C):  →  inherits edges
            class_name = _first_identifier(node)
            arg_list = next((c for c in node.children if c.type == "argument_list"), None)
            if arg_list and class_name:
                for child in arg_list.children:
                    if child.type in ("identifier", "attribute"):
                        base = _node_text(child)
                        edges.append(GraphEdge(
                            source_file=filepath, source_symbol=class_name,
                            target_file="", target_symbol=base,
                            edge_type="inherits", confidence="EXTRACTED",
                        ))

    elif language in ("javascript", "typescript"):
        if node_type in ("import_statement", "import_declaration"):
            # import X from "module"
            source = next(
                (_node_text(c) for c in node.children if c.type == "string"), ""
            ).strip("'\"")
            if source:
                edges.append(GraphEdge(
                    source_file=filepath, source_symbol="<module>",
                    target_file="", target_symbol=source,
                    edge_type="imports", confidence="EXTRACTED",
                ))

        elif node_type == "call_expression":
            # require("module")
            fn = node.child_by_field_name("function")
            args = node.child_by_field_name("arguments")
            if fn and _node_text(fn) == "require" and args:
                for child in args.children:
                    if child.type == "string":
                        mod = _node_text(child).strip("'\"")
                        edges.append(GraphEdge(
                            source_file=filepath, source_symbol="<module>",
                            target_file="", target_symbol=mod,
                            edge_type="imports", confidence="EXTRACTED",
                        ))

        elif node_type in ("class_declaration", "class_expression"):
            class_name = _first_identifier(node)
            heritage = next(
                (c for c in node.children if c.type == "class_heritage"), None
            )
            if heritage and class_name:
                base = _first_identifier(heritage)
                if base:
                    edges.append(GraphEdge(
                        source_file=filepath, source_symbol=class_name,
                        target_file="", target_symbol=base,
                        edge_type="inherits", confidence="EXTRACTED",
                    ))

    elif language == "go":
        if node_type == "import_declaration":
            for child in _walk(node):
                if child.type == "interpreted_string_literal":
                    mod = _node_text(child).strip('"')
                    edges.append(GraphEdge(
                        source_file=filepath, source_symbol="<module>",
                        target_file="", target_symbol=mod,
                        edge_type="imports", confidence="EXTRACTED",
                    ))

    elif language == "rust":
        if node_type == "use_declaration":
            path = next(
                (_node_text(c) for c in _walk(node) if c.type in ("scoped_identifier", "identifier")),
                "",
            )
            if path:
                edges.append(GraphEdge(
                    source_file=filepath, source_symbol="<module>",
                    target_file="", target_symbol=path,
                    edge_type="imports", confidence="EXTRACTED",
                ))

    elif language == "java":
        if node_type == "import_declaration":
            name = next(
                (_node_text(c) for c in node.children if c.type == "scoped_identifier"), ""
            )
            if name:
                edges.append(GraphEdge(
                    source_file=filepath, source_symbol="<module>",
                    target_file="", target_symbol=name,
                    edge_type="imports", confidence="EXTRACTED",
                ))
        elif node_type == "class_declaration":
            class_name = _first_identifier(node)
            superclass = node.child_by_field_name("superclass")
            if superclass and class_name:
                edges.append(GraphEdge(
                    source_file=filepath, source_symbol=class_name,
                    target_file="", target_symbol=_first_identifier(superclass) or "",
                    edge_type="inherits", confidence="EXTRACTED",
                ))

    elif language == "csharp":
        if node_type == "using_directive":
            name = next(
                (_node_text(c) for c in _walk(node)
                 if c.type in ("qualified_name", "identifier")), ""
            )
            if name:
                edges.append(GraphEdge(
                    source_file=filepath, source_symbol="<module>",
                    target_file="", target_symbol=name,
                    edge_type="imports", confidence="EXTRACTED",
                ))

    elif language == "ruby":
        if node_type == "call" and _first_identifier(node) in ("require", "require_relative"):
            args = node.child_by_field_name("arguments")
            if args:
                for child in args.children:
                    if child.type == "string":
                        mod = _node_text(child).strip("'\"")
                        edges.append(GraphEdge(
                            source_file=filepath, source_symbol="<module>",
                            target_file="", target_symbol=mod,
                            edge_type="imports", confidence="EXTRACTED",
                        ))

    # Recurse into children
    for child in node.children:
        _walk_for_edges(child, text, filepath, language, edges)


def _node_text(node) -> str:
    """Decode a tree-sitter node's source text."""
    if node.text is None:
        return ""
    return node.text.decode("utf-8") if isinstance(node.text, bytes) else str(node.text)


def _first_identifier(node) -> str:
    """Return text of the first identifier child, or ''."""
    for child in node.children:
        if child.type in ("identifier", "type_identifier"):
            return _node_text(child)
    return ""
