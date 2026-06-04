"""SCIP code graph extractor — optional accuracy upgrade over tree-sitter.

Runs scip-python against Python files to produce type-resolved, file-level
reference edges. Tree-sitter edges have confidence="EXTRACTED" (approximate);
SCIP edges have confidence="SCIP" (type-resolved). Both coexist in the store.

Falls back to [] when scip-python is not installed — never blocks indexing.

Install: pip install 'rag-server[scip]'
"""

import logging
import subprocess
import sys
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

# Limit files passed per SCIP run to avoid hitting OS arg-length limits on Windows.
_MAX_FILES_PER_RUN = 500


def is_available() -> bool:
    """Return True if scip-python is installed and callable."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "scip_python", "--help"],
            capture_output=True,
            timeout=10,
        )
        return result.returncode == 0
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        return False


def extract_project_edges(project_path: str, py_files: list[str]) -> list:
    """Run scip-python on Python files and return file-level GraphEdge objects.

    py_files: project-relative paths of Python files already discovered
    by the indexing engine.

    Returns [] when scip-python is unavailable or on any error.
    """
    if not py_files:
        return []
    if not is_available():
        return []

    try:
        return _run_and_parse(project_path, py_files[:_MAX_FILES_PER_RUN])
    except Exception:
        logger.debug("SCIP extraction failed", exc_info=True)
        return []


def extract_typescript_edges(project_path: str) -> list:
    """Run scip-typescript on the project and return file-level GraphEdge objects.

    Requires: npm install -g @sourcegraph/scip-typescript
    Returns [] when the tool is not installed or on any error.
    """
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "index-ts.scip"
            result = subprocess.run(
                ["scip-typescript", "index", "--output", str(output_path)],
                cwd=project_path,
                capture_output=True,
                timeout=300,
            )
            if result.returncode != 0:
                logger.debug(
                    "scip-typescript returned %d: %s",
                    result.returncode,
                    result.stderr[:300].decode(errors="replace"),
                )
                return []
            if not output_path.exists():
                return []
            edges = _parse_index(output_path)
            logger.info("SCIP TypeScript: extracted %d reference edges", len(edges))
            return edges
    except FileNotFoundError:
        logger.debug("scip-typescript not found — skipping TypeScript SCIP pass")
        return []
    except Exception:
        logger.debug("SCIP TypeScript extraction failed", exc_info=True)
        return []


def extract_go_edges(project_path: str) -> list:
    """Run scip-go on the project and return file-level GraphEdge objects.

    Requires: go install github.com/sourcegraph/scip-go/cmd/scip-go@latest
    Returns [] when the tool is not installed or on any error.
    """
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "index-go.scip"
            result = subprocess.run(
                ["scip-go", "--output", str(output_path)],
                cwd=project_path,
                capture_output=True,
                timeout=300,
            )
            if result.returncode != 0:
                logger.debug(
                    "scip-go returned %d: %s",
                    result.returncode,
                    result.stderr[:300].decode(errors="replace"),
                )
                return []
            if not output_path.exists():
                return []
            edges = _parse_index(output_path)
            logger.info("SCIP Go: extracted %d reference edges", len(edges))
            return edges
    except FileNotFoundError:
        logger.debug("scip-go not found — skipping Go SCIP pass")
        return []
    except Exception:
        logger.debug("SCIP Go extraction failed", exc_info=True)
        return []


def _run_and_parse(project_path: str, py_files: list[str]) -> list:
    from rag_server.ports.graph_port import GraphEdge  # noqa: F401 — used via list type

    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "index.scip"

        # scip-python takes file paths relative to project root
        cmd = [
            sys.executable, "-m", "scip_python", "index",
            "--project-name", Path(project_path).name,
            "--output", str(output_path),
        ] + py_files

        result = subprocess.run(
            cmd,
            cwd=project_path,
            capture_output=True,
            timeout=180,
        )
        if result.returncode != 0:
            logger.debug(
                "scip-python returned %d: %s",
                result.returncode,
                result.stderr[:300].decode(errors="replace"),
            )
            return []
        if not output_path.exists():
            return []

        return _parse_index(output_path)


def _parse_index(scip_path: Path) -> list:
    """Parse a SCIP binary index into file-level GraphEdge reference edges."""
    from rag_server.ports.graph_port import GraphEdge

    # scip-python bundles its protobuf module; try common locations
    scip_pb2 = None
    for mod in ("scip_python.scip.scip_pb2", "scip.scip_pb2", "scip_pb2"):
        try:
            import importlib
            scip_pb2 = importlib.import_module(mod)
            break
        except ImportError:
            continue

    if scip_pb2 is None:
        logger.debug("SCIP protobuf bindings not found — cannot parse index")
        return []

    index = scip_pb2.Index()
    try:
        index.ParseFromString(scip_path.read_bytes())
    except Exception as e:
        logger.debug("SCIP index parse error: %s", e)
        return []

    # Phase 1: build symbol → file mapping from all document symbol definitions
    symbol_to_file: dict[str, str] = {}
    for doc in index.documents:
        rp = doc.relative_path.replace("\\", "/")
        for sym_info in doc.symbols:
            if sym_info.symbol:
                symbol_to_file[sym_info.symbol] = rp

    DEFINITION_ROLE = 1  # scip.SymbolRole.Definition bit
    seen: set[tuple[str, str]] = set()
    edges: list[GraphEdge] = []

    # Phase 2: occurrences that are references (not definitions) become edges
    for doc in index.documents:
        src = doc.relative_path.replace("\\", "/")
        for occ in doc.occurrences:
            if occ.symbol_roles & DEFINITION_ROLE:
                continue  # skip definitions
            tgt = symbol_to_file.get(occ.symbol, "")
            if not tgt or tgt == src:
                continue
            key = (src, tgt)
            if key in seen:
                continue
            seen.add(key)
            edges.append(GraphEdge(
                source_file=src,
                source_symbol="<scip>",
                target_file=tgt,
                target_symbol=occ.symbol,
                edge_type="references",
                confidence="SCIP",
            ))

    logger.info("SCIP: extracted %d unique file-level reference edges", len(edges))
    return edges
