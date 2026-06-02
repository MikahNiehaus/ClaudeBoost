"""C# namespace-resolution graph extractor.

Improves on tree-sitter by resolving 'using' directives to actual project files
via a namespace-to-file map built from the codebase's own namespace declarations.

No external tools required — pure Python, regex-based parsing.
Edges are produced with target_file already resolved, so they bypass
resolve_target_files() and immediately activate graph augmentation.

Confidence tag: "CSHARP" (distinguishable from tree-sitter's "EXTRACTED" and SCIP's "SCIP").
"""

import bisect
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

# Matches both block-scoped and file-scoped namespace declarations:
#   namespace Foo.Bar { ... }   (traditional)
#   namespace Foo.Bar;          (file-scoped, C# 10+)
_NAMESPACE_RE = re.compile(r"^\s*namespace\s+([\w.]+)", re.MULTILINE)

# Matches all forms of using directive:
#   using Foo.Bar;
#   using static Foo.Bar.Baz;
#   using Alias = Foo.Bar;
#   global using Foo.Bar;
#   global using static Foo.Bar.Baz;
_USING_RE = re.compile(
    r"^\s*(?:global\s+)?using\s+(?:static\s+)?(?:\w+\s*=\s*)?([\w.]+)\s*;",
    re.MULTILINE,
)

# Safety cap — avoids OOM on enormous solutions
_MAX_FILES = 2000


def is_available() -> bool:
    """Always available — pure Python, no external tools required."""
    return True


def extract_project_edges(project_path: str, cs_files: list[str]) -> list:
    """Build file-to-file reference edges for C# files via namespace mapping.

    cs_files: project-relative paths of C# files already discovered by the indexing engine.

    Returns list of GraphEdge objects with confidence="CSHARP" and target_file already
    set to a real project file path.  These edges bypass resolve_target_files() and
    immediately activate graph augmentation in search results.
    """
    if not cs_files:
        return []
    try:
        return _extract(project_path, cs_files[:_MAX_FILES])
    except Exception:
        logger.debug("C# namespace extraction failed", exc_info=True)
        return []


def _extract(project_path: str, cs_files: list[str]) -> list:
    from rag_server.ports.graph_port import GraphEdge

    root = Path(project_path)

    # Phase 1: single-pass read — collect declared namespaces and using directives per file
    file_namespaces: dict[str, list[str]] = {}   # rel_path → declared namespaces
    file_usings: dict[str, set[str]] = {}         # rel_path → imported namespaces/types

    for rel_path in cs_files:
        abs_path = root / rel_path
        try:
            content = abs_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        declared = [m.strip() for m in _NAMESPACE_RE.findall(content)]
        imported = {m.strip() for m in _USING_RE.findall(content)}

        if declared:
            file_namespaces[rel_path] = declared
        if imported:
            file_usings[rel_path] = imported

    # Phase 2: build namespace → [files] lookup
    ns_to_files: dict[str, list[str]] = {}
    for rel_path, namespaces in file_namespaces.items():
        for ns in namespaces:
            ns_to_files.setdefault(ns, []).append(rel_path)

    logger.debug(
        "C# extractor: %d namespaces across %d files",
        len(ns_to_files), len(file_namespaces),
    )

    # Phase 3: for each file, resolve its using directives to target project files.
    # Sort namespace keys once so prefix matches use bisect (O(log N)) instead of a
    # full linear scan (O(N)) per unresolved using directive.
    sorted_ns = sorted(ns_to_files.keys())
    seen: set[tuple[str, str]] = set()
    edges: list[GraphEdge] = []

    for src_path, usings in file_usings.items():
        src = src_path.replace("\\", "/")

        for ns in usings:
            # Exact namespace match first
            targets: set[str] = set(ns_to_files.get(ns, []))

            # Prefix match: 'using Foo.Bar' also reaches files in 'Foo.Bar.Baz' sub-namespaces.
            # bisect jumps to the first candidate; the loop stops at the first non-match.
            if not targets:
                prefix = ns + "."
                lo = bisect.bisect_left(sorted_ns, prefix)
                for mapped_ns in sorted_ns[lo:]:
                    if not mapped_ns.startswith(prefix):
                        break
                    targets.update(ns_to_files[mapped_ns])

            for tgt_path in targets:
                tgt = tgt_path.replace("\\", "/")
                if tgt == src:
                    continue
                key = (src, tgt)
                if key in seen:
                    continue
                seen.add(key)
                edges.append(GraphEdge(
                    source_file=src,
                    source_symbol="<csharp>",
                    target_file=tgt,
                    target_symbol=ns,
                    edge_type="imports",
                    confidence="CSHARP",
                ))

    logger.info(
        "C# extractor: %d resolved file-level edges from %d files",
        len(edges), len(cs_files),
    )
    return edges
