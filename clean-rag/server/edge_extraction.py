"""Tree-sitter AST based edge extraction for code graph building.

Extracts import/inheritance/call edges from source code files.
Supports Python, JS/TS, Go, Rust, Java, C#, Ruby, Kotlin, Swift, PHP, C/C++, Lua.

Ported from ClaudeBoost mcp-rag-server code_chunker.py. Fully self-contained.
"""

import importlib
import logging
from pathlib import Path

from .graph_store import GraphEdge

logger = logging.getLogger(__name__)

# Tree-sitter language modules, imported lazily to avoid hard failure
_PARSERS: dict = {}

#: Extensions this module has hand mapped, kept ONLY where our name differs
#: from grep-ast's or where grep-ast has no entry. Everything else now comes
#: from grep_ast.filename_to_lang, which carries 45 extensions on its own and
#: 150+ alongside tree-sitter-language-pack.
#:
#: The hand kept version of this map was 24 entries, and its gaps were not
#: cosmetic. Language detection feeds the embedding model router, so an
#: unmapped extension counted as "unknown", and enough unknowns made "unknown"
#: win the vote: Nectar's 3138 unmapped .html/.yml/.cshtml files outvoted its
#: 1323 real C# files and routed the project to bigcode/starencoder, a gated
#: model that cannot load. Eight of sixteen projects went the same way.
_EXT_OVERRIDES: dict[str, str] = {
    # grep-ast returns "c_sharp"; the router, DOC_LANGUAGES and the routing
    # table all speak "csharp". Normalize here rather than in five places.
    ".cs": "csharp",
    # grep-ast maps .h to "c"; keep that explicit since it is genuinely
    # ambiguous with C++ and we index far more C than C++.
    ".h": "c",
}


def ext_to_lang(path: str) -> str | None:
    """Language name for a path, or None when nothing recognises it.

    Delegates to grep-ast, Aider's extracted extension map, so new languages
    arrive with a dependency bump rather than when somebody notices.
    """
    override = _EXT_OVERRIDES.get(Path(path).suffix.lower())
    if override:
        return override
    try:
        from grep_ast import filename_to_lang

        return filename_to_lang(path)
    except Exception:
        logger.debug("grep-ast could not classify %s", path, exc_info=True)
        return None


class _ExtToLangCompat(dict):
    """Keeps the ``_EXT_TO_LANG.get(suffix, "unknown")`` call shape working.

    Several callers treat this as a plain dict keyed by suffix. Rather than
    edit each one and risk missing a call site, the lookup itself now resolves
    through grep-ast.
    """

    def get(self, key, default=None):  # type: ignore[override]
        return ext_to_lang(f"x{key}") or default

    def __getitem__(self, key):
        value = self.get(key)
        if value is None:
            raise KeyError(key)
        return value

    def __contains__(self, key) -> bool:  # type: ignore[override]
        return self.get(key) is not None


_EXT_TO_LANG = _ExtToLangCompat()

def _get_parser(language: str):
    """Lazy load a tree-sitter parser for the given language.

    Backed by tree-sitter-language-pack, which ships prebuilt wheels for 300+
    grammars. This replaced one pinned ``tree-sitter-<lang>`` dependency per
    language plus an importlib map that had to name the module and the accessor
    function for each: fourteen entries that only ever grew when someone
    remembered to add one, and where a missing grammar degraded to "this
    language contributes zero edges" with nothing but a warning.

    Returns None (and caches None) when the pack has no such grammar. Callers
    handle None, so an unknown language still degrades rather than raising.
    """
    if language in _PARSERS:
        return _PARSERS[language]

    try:
        from tree_sitter_language_pack import get_parser

        # No alias table: the pack accepts both its own grammar names and the
        # common spellings, so "csharp" and "c_sharp" both resolve. One less
        # hand kept map to drift.
        _PARSERS[language] = get_parser(language)
    except Exception as e:
        # LookupError for a language the pack does not carry, ImportError if
        # the pack itself is missing. Neither should stop the rest of a scan.
        logger.warning("tree-sitter grammar not available for %s: %s", language, e)
        _PARSERS[language] = None
    return _PARSERS[language]


def _walk(node):
    """Depth first walk of AST nodes."""
    yield node
    for child in node.children:
        yield from _walk(child)


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


def get_language(filepath: str) -> str | None:
    """Get the tree-sitter language key for a file path. Returns None if unsupported.

    Takes the whole path, not just the suffix, because grep-ast also recognises
    extensionless files by name (Dockerfile, go.mod, Makefile).
    """
    return ext_to_lang(filepath)


def extract_edges(text: str, language: str, filepath: str) -> list[GraphEdge]:
    """Extract structural edges from source code via tree-sitter AST.

    Returns a list of GraphEdge. Never raises. Returns [] for unsupported
    languages, unparseable files, or files with no detectable edges.

    Edge types:
        "imports"    import/require/use statements         confidence: EXTRACTED
        "inherits"   class A extends/inherits B            confidence: EXTRACTED
        "implements" class A implements B                  confidence: EXTRACTED
        "calls"      function calls to imported names      confidence: INFERRED
    """
    parser_key = "tsx" if filepath.endswith(".tsx") else language
    parser = _get_parser(parser_key)
    if parser is None:
        return []

    try:
        tree = parser.parse(text.encode("utf-8"))
    except Exception as e:
        logger.debug("extract_edges: parse failed for %s: %s", filepath, e)
        return []

    edges: list[GraphEdge] = []
    lang_for_walk = "typescript" if parser_key == "tsx" else language

    import_aliases: dict[str, str] = {}
    if lang_for_walk in ("python", "javascript", "typescript"):
        _build_import_aliases(tree.root_node, lang_for_walk, import_aliases)

    _walk_for_edges(tree.root_node, text, filepath, lang_for_walk, edges, import_aliases)
    return edges


def _build_import_aliases(root_node, language: str, aliases: dict) -> None:
    """Pre-pass: map local names to their imported module paths.

    Used to detect calls to imported symbols and link them
    back to the source file they came from (confidence=INFERRED).
    """
    for node in _walk(root_node):
        if language == "python":
            if node.type == "import_statement":
                for child in node.children:
                    if child.type == "aliased_import":
                        parts = [c for c in child.children
                                 if c.type in ("dotted_name", "identifier")]
                        if len(parts) >= 2:
                            aliases[_node_text(parts[-1])] = _node_text(parts[0])
                    elif child.type == "dotted_name":
                        name = _node_text(child)
                        aliases[name.split(".")[0]] = name
            elif node.type == "import_from_statement":
                module = next(
                    (_node_text(c) for c in node.children if c.type == "dotted_name"), ""
                )
                if not module:
                    continue
                for child in node.children:
                    if child.type == "aliased_import":
                        parts = [c for c in child.children
                                 if c.type in ("identifier", "dotted_name")]
                        if parts:
                            aliases[_node_text(parts[-1])] = module
                    elif child.type == "dotted_name" and _node_text(child) != module:
                        name = _node_text(child)
                        aliases[name.split(".")[-1]] = module
                    elif child.type == "identifier" and _node_text(child) not in ("import", "from"):
                        aliases[_node_text(child)] = module
        elif language in ("javascript", "typescript"):
            if node.type in ("import_statement", "import_declaration"):
                source = next(
                    (_node_text(c).strip("'\"") for c in node.children if c.type == "string"), ""
                )
                if not source:
                    continue
                for child in node.children:
                    if child.type == "import_clause":
                        for clause_child in child.children:
                            if clause_child.type == "identifier":
                                aliases[_node_text(clause_child)] = source
                            elif clause_child.type == "named_imports":
                                for spec in clause_child.children:
                                    if spec.type == "import_specifier":
                                        names = [x for x in spec.children
                                                 if x.type == "identifier"]
                                        if names:
                                            aliases[_node_text(names[-1])] = source
                    elif child.type in ("identifier", "type_identifier"):
                        aliases[_node_text(child)] = source


def _walk_for_edges(
    node, text: str, filepath: str, language: str, edges: list,
    import_aliases: dict | None = None,
) -> None:
    """Recursive AST walk that fills edges in place."""
    node_type = node.type

    # ------------------------------------------------------------------
    # Import edges (EXTRACTED)
    # ------------------------------------------------------------------
    if language == "python":
        if node_type == "import_statement":
            for child in node.children:
                if child.type in ("dotted_name", "aliased_import"):
                    name = _node_text(child)
                    edges.append(GraphEdge(
                        source_file=filepath, source_symbol="<module>",
                        target_file="", target_symbol=name,
                        edge_type="imports", confidence="EXTRACTED",
                    ))

        elif node_type == "import_from_statement":
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
                for hchild in heritage.children:
                    if hchild.type == "extends_clause":
                        base = _first_identifier(hchild)
                        if base:
                            edges.append(GraphEdge(
                                source_file=filepath, source_symbol=class_name,
                                target_file="", target_symbol=base,
                                edge_type="inherits", confidence="EXTRACTED",
                            ))
                    elif hchild.type == "implements_clause":
                        for iface_child in hchild.children:
                            if iface_child.type in (
                                "type_identifier", "identifier", "generic_type",
                            ):
                                iface = _first_identifier(iface_child) or _node_text(iface_child)
                                if iface:
                                    edges.append(GraphEdge(
                                        source_file=filepath, source_symbol=class_name,
                                        target_file="", target_symbol=iface,
                                        edge_type="implements", confidence="EXTRACTED",
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
                (_node_text(c) for c in _walk(node)
                 if c.type in ("scoped_identifier", "identifier")),
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
            interfaces = node.child_by_field_name("interfaces")
            if interfaces and class_name:
                for iface in _walk(interfaces):
                    if iface.type in ("type_identifier", "scoped_type_identifier"):
                        edges.append(GraphEdge(
                            source_file=filepath, source_symbol=class_name,
                            target_file="", target_symbol=_node_text(iface),
                            edge_type="implements", confidence="EXTRACTED",
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
        elif node_type == "class_declaration":
            class_name = _first_identifier(node)
            base_list = next((c for c in node.children if c.type == "base_list"), None)
            if base_list and class_name:
                for base in base_list.children:
                    if base.type in ("identifier", "qualified_name", "generic_name"):
                        base_name = _node_text(base)
                        is_iface = (
                            len(base_name) > 1
                            and base_name[0] == "I"
                            and base_name[1].isupper()
                        )
                        edges.append(GraphEdge(
                            source_file=filepath, source_symbol=class_name,
                            target_file="", target_symbol=base_name,
                            edge_type="implements" if is_iface else "inherits",
                            confidence="EXTRACTED",
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

    elif language == "kotlin":
        if node_type == "import_header":
            path = ".".join(
                _node_text(c) for c in node.children if c.type == "identifier"
            )
            if path:
                edges.append(GraphEdge(
                    source_file=filepath, source_symbol="<module>",
                    target_file="", target_symbol=path,
                    edge_type="imports", confidence="EXTRACTED",
                ))
        elif node_type == "class_declaration":
            class_name = _first_identifier(node)
            delegation = node.child_by_field_name("delegation_specifiers")
            if delegation and class_name:
                for spec in delegation.children:
                    if spec.type in ("constructor_invocation", "user_type"):
                        base = _first_identifier(spec) or _node_text(spec)
                        if base:
                            edges.append(GraphEdge(
                                source_file=filepath, source_symbol=class_name,
                                target_file="", target_symbol=base,
                                edge_type="inherits", confidence="EXTRACTED",
                            ))

    elif language == "swift":
        if node_type == "import_declaration":
            name = " ".join(
                _node_text(c) for c in node.children if c.type == "identifier"
            )
            if name:
                edges.append(GraphEdge(
                    source_file=filepath, source_symbol="<module>",
                    target_file="", target_symbol=name,
                    edge_type="imports", confidence="EXTRACTED",
                ))
        elif node_type == "class_declaration":
            class_name = _first_identifier(node)
            type_inheritance = node.child_by_field_name("type_inheritance_clause")
            if type_inheritance and class_name:
                for iface in type_inheritance.children:
                    if iface.type in ("type_identifier", "user_type"):
                        base = _node_text(iface)
                        if base:
                            edges.append(GraphEdge(
                                source_file=filepath, source_symbol=class_name,
                                target_file="", target_symbol=base,
                                edge_type="inherits", confidence="EXTRACTED",
                            ))

    elif language == "php":
        if node_type == "namespace_use_declaration":
            name = next(
                (_node_text(c) for c in _walk(node)
                 if c.type in ("qualified_name", "name")), ""
            )
            if name:
                edges.append(GraphEdge(
                    source_file=filepath, source_symbol="<module>",
                    target_file="", target_symbol=name,
                    edge_type="imports", confidence="EXTRACTED",
                ))
        elif node_type == "class_declaration":
            class_name = _first_identifier(node)
            base = node.child_by_field_name("base_clause")
            if base and class_name:
                edges.append(GraphEdge(
                    source_file=filepath, source_symbol=class_name,
                    target_file="", target_symbol=_first_identifier(base) or "",
                    edge_type="inherits", confidence="EXTRACTED",
                ))
            interfaces = node.child_by_field_name("class_implements")
            if interfaces and class_name:
                for iface in _walk(interfaces):
                    if iface.type == "named_type":
                        edges.append(GraphEdge(
                            source_file=filepath, source_symbol=class_name,
                            target_file="", target_symbol=_node_text(iface),
                            edge_type="implements", confidence="EXTRACTED",
                        ))

    elif language in ("c", "cpp"):
        if node_type == "preproc_include":
            path_node = next(
                (c for c in node.children
                 if c.type in ("string_literal", "system_lib_string")), None
            )
            if path_node:
                mod = _node_text(path_node).strip('"<>')
                edges.append(GraphEdge(
                    source_file=filepath, source_symbol="<module>",
                    target_file="", target_symbol=mod,
                    edge_type="imports", confidence="EXTRACTED",
                ))
        elif node_type in ("struct_specifier", "class_specifier") and language == "cpp":
            class_name = _first_identifier(node)
            base_list = node.child_by_field_name("bases")
            if base_list and class_name:
                for base in _walk(base_list):
                    if base.type in ("type_identifier", "qualified_identifier"):
                        edges.append(GraphEdge(
                            source_file=filepath, source_symbol=class_name,
                            target_file="", target_symbol=_node_text(base),
                            edge_type="inherits", confidence="EXTRACTED",
                        ))

    elif language == "lua":
        if node_type == "function_call":
            fn_name = _first_identifier(node)
            if fn_name == "require":
                args = node.child_by_field_name("args")
                if args:
                    for child in args.children:
                        if child.type == "string":
                            mod = _node_text(child).strip("\"'")
                            edges.append(GraphEdge(
                                source_file=filepath, source_symbol="<module>",
                                target_file="", target_symbol=mod,
                                edge_type="imports", confidence="EXTRACTED",
                            ))

    # ------------------------------------------------------------------
    # Calls edges (INFERRED): Python, JS, TS only
    # Detect calls to symbols that were imported at the top of the file
    # ------------------------------------------------------------------
    if import_aliases and language in ("python", "javascript", "typescript"):
        if language == "python" and node_type == "call":
            func = node.child_by_field_name("function")
            if func:
                if func.type == "attribute":
                    obj = next((c for c in func.children if c.type == "identifier"), None)
                    if obj:
                        caller = _node_text(obj)
                        if caller in import_aliases:
                            edges.append(GraphEdge(
                                source_file=filepath, source_symbol="<call>",
                                target_file="", target_symbol=import_aliases[caller],
                                edge_type="calls", confidence="INFERRED",
                            ))
                elif func.type == "identifier":
                    caller = _node_text(func)
                    if caller in import_aliases:
                        edges.append(GraphEdge(
                            source_file=filepath, source_symbol="<call>",
                            target_file="", target_symbol=import_aliases[caller],
                            edge_type="calls", confidence="INFERRED",
                        ))
        elif language in ("javascript", "typescript") and node_type == "call_expression":
            fn = node.child_by_field_name("function")
            if fn:
                if fn.type == "member_expression":
                    obj = fn.child_by_field_name("object")
                    if obj:
                        caller = _node_text(obj)
                        if caller in import_aliases:
                            edges.append(GraphEdge(
                                source_file=filepath, source_symbol="<call>",
                                target_file="", target_symbol=import_aliases[caller],
                                edge_type="calls", confidence="INFERRED",
                            ))
                elif fn.type == "identifier":
                    caller = _node_text(fn)
                    if caller in import_aliases:
                        edges.append(GraphEdge(
                            source_file=filepath, source_symbol="<call>",
                            target_file="", target_symbol=import_aliases[caller],
                            edge_type="calls", confidence="INFERRED",
                        ))

    # Recurse into children
    for child in node.children:
        _walk_for_edges(child, text, filepath, language, edges, import_aliases)
