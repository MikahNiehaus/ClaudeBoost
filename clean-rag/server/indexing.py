"""Indexing engine for clean-rag. Handles chunking, embedding, and storage.

Extracted from ClaudeBoost mcp-rag-server, simplified for project indexing.
"""

import gc
import hashlib
import json
import logging
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .config import (
    CHUNK_OVERLAP_TOKENS,
    DATABASES_DIR,
    DEGENERATE_CHUNK_MIN_TOKENS,
    MAX_CHUNK_TOKENS,
    MIN_CHUNK_TOKENS,
    STATE_DIR,
)
from .store import Chunk, ChromaStore

logger = logging.getLogger(__name__)


def _mem_mb() -> float:
    """Current process RSS in MB. Returns 0.0 if psutil is not installed."""
    try:
        import psutil
        return round(psutil.Process(os.getpid()).memory_info().rss / 1024**2, 1)
    except (ImportError, Exception):
        return 0.0


def _gc_cleanup(label: str = "") -> None:
    """Run garbage collection and log memory. Call between indexing batches."""
    before = _mem_mb()
    gc.collect()
    after = _mem_mb()
    freed = round(before - after, 1)
    if freed > 1:
        logger.info("GC after %s: %.1f MB -> %.1f MB (freed %.1f MB)", label, before, after, freed)


# ---------------------------------------------------------------------------
# Index lock (prevents concurrent bulk indexing from stacking processes)
# ---------------------------------------------------------------------------

_INDEX_LOCK_PATH = STATE_DIR / "index-lock.json"


def acquire_index_lock(operation: str = "index") -> bool:
    """Try to acquire the indexing lock. Returns True if acquired, False if busy.

    The lock includes a PID so stale locks from crashed processes are auto-cleared.
    """
    if _INDEX_LOCK_PATH.exists():
        try:
            lock_data = json.loads(_INDEX_LOCK_PATH.read_text(encoding="utf-8"))
            lock_pid = lock_data.get("pid", -1)
            try:
                import psutil
                if psutil.pid_exists(lock_pid):
                    logger.warning(
                        "Index lock held by PID %d (%s), started %s",
                        lock_pid, lock_data.get("operation", "?"), lock_data.get("started", "?"),
                    )
                    return False
                else:
                    logger.info("Clearing stale index lock from dead PID %d", lock_pid)
            except ImportError:
                try:
                    os.kill(lock_pid, 0)
                    return False
                except OSError:
                    logger.info("Clearing stale index lock from dead PID %d", lock_pid)
        except (json.JSONDecodeError, Exception):
            logger.info("Clearing corrupt index lock file")

    _INDEX_LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    _INDEX_LOCK_PATH.write_text(json.dumps({
        "pid": os.getpid(),
        "operation": operation,
        "started": datetime.now(timezone.utc).isoformat(),
    }), encoding="utf-8")
    return True


def release_index_lock() -> None:
    """Release the indexing lock."""
    try:
        if _INDEX_LOCK_PATH.exists():
            lock_data = json.loads(_INDEX_LOCK_PATH.read_text(encoding="utf-8"))
            if lock_data.get("pid") == os.getpid():
                _INDEX_LOCK_PATH.unlink(missing_ok=True)
    except Exception:
        _INDEX_LOCK_PATH.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------

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


def file_hash(content: str) -> str:
    """SHA-256 hash prefix for change detection."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


def chunk_id(source_file: str, chunk_index: int) -> str:
    """Generate a deterministic chunk ID."""
    raw = f"{source_file}::{chunk_index}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def build_metadata(
    source_file: str,
    scope: str,
    section: str,
    line_start: int,
    line_end: int,
    content_hash: str,
    chunk_index: int,
    token_count: int,
) -> dict:
    # Preserve directory tree path for organized retrieval
    parts = source_file.replace("\\", "/").split("/")
    tree_path = "/".join(parts[:-1]) if len(parts) > 1 else ""

    return {
        "source_file": source_file,
        "scope": scope,
        "section": section,
        "tree_path": tree_path,
        "line_start": line_start,
        "line_end": line_end,
        "file_hash": content_hash,
        "indexed_at": datetime.now(timezone.utc).isoformat(),
        "chunk_index": chunk_index,
        "token_count": token_count,
    }


def chunk_markdown(
    text: str,
    source_file: str,
    max_tokens: int = 500,
    min_tokens: int = 50,
    chunk_overlap: int = 0,
) -> list[RawChunk]:
    """Split a markdown file into chunks based on heading boundaries."""
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


def chunk_code(
    content: str,
    source_file: str,
    max_tokens: int = 500,
    min_tokens: int = 50,
    chunk_overlap: int = 0,
) -> list[RawChunk]:
    """Split source code into chunks. Uses blank-line boundaries for splitting."""
    lines = content.split("\n")
    total_tokens = estimate_tokens(content)

    if total_tokens <= max_tokens:
        if total_tokens < min_tokens:
            return []
        return [RawChunk(
            content=content,
            section=Path(source_file).stem,
            line_start=1,
            line_end=len(lines),
            token_count_approx=total_tokens,
        )]

    # Split on double-newline boundaries (function/class gaps)
    chunks = []
    current_lines: list[str] = []
    current_start = 1
    overlap_lines: list[str] = []

    for i, line in enumerate(lines, 1):
        current_lines.append(line)
        current_text = "\n".join(current_lines)
        current_tokens = estimate_tokens(current_text)

        is_boundary = (line.strip() == "" and i < len(lines))
        is_last = (i == len(lines))

        if (current_tokens >= max_tokens and is_boundary) or is_last:
            text = current_text.strip()
            if text and estimate_tokens(text) >= min_tokens:
                chunks.append(RawChunk(
                    content=text,
                    section=Path(source_file).stem,
                    line_start=current_start,
                    line_end=i,
                    token_count_approx=estimate_tokens(text),
                ))
            if chunk_overlap > 0 and current_lines:
                # Carry last few lines as overlap
                overlap_count = max(1, chunk_overlap // 10)
                overlap_lines = current_lines[-overlap_count:]
            current_lines = list(overlap_lines)
            overlap_lines = []
            current_start = i + 1

    return chunks


@dataclass
class _Section:
    heading: str
    content: str
    line_start: int
    line_end: int


def _split_into_sections(lines: list[str]) -> list[_Section]:
    """Split lines into sections based on H1/H2/H3 headers."""
    sections = []
    current_heading = "Introduction"
    current_lines: list[str] = []
    current_start = 1

    for i, line in enumerate(lines):
        if re.match(r"^#{1,3}\s+", line):
            if current_lines or sections == []:
                content = "\n".join(current_lines).strip()
                if content:
                    sections.append(_Section(
                        heading=current_heading,
                        content=content,
                        line_start=current_start,
                        line_end=i,
                    ))
            current_heading = re.sub(r"^#{1,3}\s+", "", line).strip()
            current_lines = []
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
    section: _Section, max_tokens: int, min_tokens: int, chunk_overlap: int = 0,
) -> list[RawChunk]:
    """Process a single section, splitting at paragraph boundaries if too large."""
    tokens = estimate_tokens(section.content)

    if tokens <= max_tokens:
        return [RawChunk(
            content=section.content,
            section=section.heading,
            line_start=section.line_start,
            line_end=section.line_end,
            token_count_approx=tokens,
        )]

    paragraphs = re.split(r"\n\n+", section.content)
    chunks = []
    current_text = ""
    current_start = section.line_start
    _overlap_text = ""

    for para in paragraphs:
        para_tokens = estimate_tokens(para)
        current_tokens = estimate_tokens(current_text)

        if current_text and (current_tokens + para_tokens) > max_tokens:
            line_count = current_text.count("\n") + 1
            chunks.append(RawChunk(
                content=current_text.strip(),
                section=section.heading,
                line_start=current_start,
                line_end=current_start + line_count - 1,
                token_count_approx=current_tokens,
            ))
            if chunk_overlap > 0:
                tail = current_text.rsplit("\n\n", 1)[-1].strip()
                _overlap_text = tail if tail and estimate_tokens(tail) <= chunk_overlap else ""
            else:
                _overlap_text = ""
            current_start = current_start + line_count
            current_text = (_overlap_text + "\n\n" + para).strip() if _overlap_text else para
        else:
            current_text = (current_text + "\n\n" + para).strip() if current_text else para

    if current_text.strip():
        chunks.append(RawChunk(
            content=current_text.strip(),
            section=section.heading,
            line_start=current_start,
            line_end=section.line_end,
            token_count_approx=estimate_tokens(current_text),
        ))

    return chunks


# ---------------------------------------------------------------------------
# Code file scanning (for project indexing)
# ---------------------------------------------------------------------------

# Extensions considered indexable source code
CODE_EXTENSIONS = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".mjs",
    ".go", ".rs", ".java", ".kt", ".scala",
    ".cs", ".fs", ".vb",
    ".c", ".cpp", ".cc", ".h", ".hpp",
    ".rb", ".php", ".swift", ".m",
    ".lua", ".r", ".jl", ".dart", ".zig",
    ".sh", ".bash", ".zsh", ".ps1",
    ".sql", ".graphql", ".proto",
    ".html", ".css", ".scss", ".less", ".vue", ".svelte",
    ".yaml", ".yml", ".toml", ".json", ".xml",
    ".md", ".mdx", ".rst", ".txt",
}

# Directories to skip during project scanning
SKIP_DIRS = {
    "node_modules", ".git", "__pycache__", ".venv", "venv",
    "dist", "build", ".next", ".nuxt", "target",
    "vendor", ".tox", ".mypy_cache", ".pytest_cache",
    "coverage", ".coverage", "bin", "obj",
    "workspace",  # ClaudeBoost workspace dirs
    ".rag-index",  # ClaudeBoost RAG index
    ".claude",  # Claude config
    "knowledge",  # clean-rag knowledge (indexed separately as topics)
    "databases",  # clean-rag databases
    # Installed dependency trees. The site packages dir is the big one: a single
    # venv leaks thousands of dependency files into the graph without it (measured
    # on ClaudeBoost, 9330 of 9721 scanned files were venv contents).
    "site-packages", ".eggs", "env", ".conda",
    # IDE and editor state (these pass the extension allowlist otherwise).
    ".idea", ".vscode",
    # Build, cache, and generated output across ecosystems.
    "htmlcov", ".ruff_cache", ".ipynb_checkpoints", ".gradle", "out",
    ".terraform", ".serverless", ".turbo", ".parcel-cache",
    ".svelte-kit", ".angular",
    # Apple and iOS dependency and build dirs.
    "Pods", "Carthage", "DerivedData",
}

# Generated files to skip (exact filenames)
SKIP_FILES = {
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "Packages.lock.json",
    "packages.lock.json",
    "npm-shrinkwrap.json",
    # Lockfiles across ecosystems: data, not code, zero graph value.
    "Cargo.lock", "Gemfile.lock", "poetry.lock", "Pipfile.lock",
    "composer.lock", "mix.lock", "go.sum",
    # Coverage and report artifacts.
    "coverage.xml", "coverage.json", "lcov.info",
}

# Generated file suffixes to skip
SKIP_SUFFIXES = (
    ".min.js",
    ".min.css",
    ".bundle.js",
    ".d.ts",
    ".generated.cs",
    ".Designer.cs",
    ".g.cs",
    ".AssemblyInfo.cs",
    # Generated code (protobuf, dart codegen), per linguist patterns.
    "_pb2.py", "_pb2_grpc.py", ".pb.go", ".g.dart", ".freezed.dart",
)

MAX_FILE_SIZE = 500_000  # 500KB


def _venv_roots(root: Path) -> set:
    """Directories that are Python virtualenvs, found by their pyvenv.cfg marker.

    Skipping these catches any venv (venv, .venv, graphrag-venv, whatever it is
    named) without maintaining a name list. A venv's installed packages are the
    single biggest source of graph pollution, so this is the general catch behind
    the site packages entry in SKIP_DIRS.
    """
    roots = set()
    try:
        for cfg in root.rglob("pyvenv.cfg"):
            roots.add(cfg.parent)
    except OSError:
        pass
    return roots


def scan_project(project_path: str) -> list[str]:
    """Scan a project directory for indexable source files.

    Returns a list of absolute file paths.
    """
    root = Path(project_path).resolve()
    venv_roots = _venv_roots(root)
    files = []

    for path in root.rglob("*"):
        if not path.is_file():
            continue
        # A file inside any virtualenv is a dependency, not project source.
        if any(vr in path.parents for vr in venv_roots):
            continue
        # Skip directories in SKIP_DIRS
        if any(part in SKIP_DIRS for part in path.relative_to(root).parts):
            continue
        if path.name in SKIP_FILES:
            continue
        if any(path.name.endswith(s) for s in SKIP_SUFFIXES):
            continue
        if path.suffix.lower() not in CODE_EXTENSIONS:
            continue
        try:
            if path.stat().st_size > MAX_FILE_SIZE:
                continue
        except OSError:
            continue
        files.append(str(path))

    return sorted(files)


# ---------------------------------------------------------------------------
# Project indexing
# ---------------------------------------------------------------------------

def _save_project_manifest(
    manifest_path: Path, manifest: dict, project_path: str,
) -> None:
    """Save project manifest to disk with metadata."""
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    save_data = {"__project_path__": project_path}
    save_data.update(manifest)
    manifest_path.write_text(json.dumps(save_data, indent=2), encoding="utf-8")


def _project_paths(project_path: str) -> tuple[Path, str, Path, Path, Path]:
    """Resolve project root, project ID, index dir, chroma dir, manifest path."""
    project_root = Path(project_path).resolve()
    pid = hashlib.sha256(str(project_root).encode("utf-8")).hexdigest()[:12]
    index_dir = DATABASES_DIR / "_projects" / pid
    chroma_dir = index_dir / "chroma"
    manifest_path = index_dir / "manifest.json"
    return project_root, pid, index_dir, chroma_dir, manifest_path


# ---------------------------------------------------------------------------
# Graph store helpers
# ---------------------------------------------------------------------------

def _init_graph_store(index_dir: Path, force: bool = False):
    """Create or open a SQLiteGraphStore at index_dir/graph.db.

    On force=True, deletes the existing DB so edges rebuild from scratch.
    Returns a SQLiteGraphStore instance.
    """
    from .graph_store import SQLiteGraphStore

    db_path = index_dir / "graph.db"
    if force and db_path.exists():
        db_path.unlink()
    return SQLiteGraphStore(str(db_path))


def _register_file_variants(rel_path: str, file_map: dict[str, str]) -> None:
    """Register multiple name variants for a file path in the resolution map.

    Symbol resolution tries several forms when matching an import target
    to a project file. This pre-builds all the variants so resolve_target_files
    can do fast dict lookups.

    Variants registered:
      - rel_path itself (path/to/file.py)
      - stem only (file)
      - extensionless path (path/to/file)
      - dotted form (path.to.file)
      - for JS/TS index files: parent directory (path/to)
    """
    file_map[rel_path] = rel_path

    p = Path(rel_path)
    stem = p.stem
    no_ext = str(p.with_suffix("")).replace("\\", "/")
    dotted = no_ext.replace("/", ".")

    # Only set if not already claimed by another file (first wins)
    if stem not in file_map:
        file_map[stem] = rel_path
    if no_ext not in file_map:
        file_map[no_ext] = rel_path
    if dotted not in file_map:
        file_map[dotted] = rel_path

    # JS/TS barrel exports: importing "components/Button" resolves to
    # "components/Button/index.ts"
    if stem == "index" and p.parent != Path("."):
        parent_str = str(p.parent).replace("\\", "/")
        if parent_str not in file_map:
            file_map[parent_str] = rel_path


def index_project(
    project_path: str,
    code_embedder,
    force: bool = False,
) -> dict:
    """Index a project's source code into databases/_projects/<hash>/chroma/.

    Also builds a structural graph (graph.db) of import/inheritance edges
    for mode=graph search.

    Returns stats dict.
    """
    project_root, pid, index_dir, chroma_dir, manifest_path = _project_paths(project_path)

    # Load manifest
    manifest: dict = {}
    if not force and manifest_path.exists():
        try:
            raw = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest = {k: v for k, v in raw.items() if not k.startswith("__")}
        except Exception:
            manifest = {}

    store = ChromaStore(persist_dir=str(chroma_dir))
    collection = "codebase"

    if force and store.collection_exists(collection):
        store.delete_collection(collection)

    store.create_collection(collection)

    file_paths = scan_project(project_path)

    # Initialize the graph store for structural edges
    graph = _init_graph_store(index_dir, force=force)

    # Pre-build file map for symbol resolution and track current files
    file_map: dict[str, str] = {}
    current_files: set[str] = set()

    for fp in file_paths:
        try:
            rp = str(Path(fp).relative_to(project_root)).replace("\\", "/")
        except ValueError:
            rp = fp.replace("\\", "/")
        current_files.add(rp)
        _register_file_variants(rp, file_map)

    # Lazy import edge extraction (only needed for code files)
    try:
        from .edge_extraction import extract_edges, get_language
        has_edge_extraction = True
    except ImportError:
        logger.warning("edge_extraction not available, skipping graph build")
        has_edge_extraction = False

    files_indexed = 0
    chunks_created = 0
    files_unchanged = 0
    files_failed = 0
    edges_extracted = 0
    start_time = time.time()

    for file_path in file_paths:
        try:
            rel_path = str(Path(file_path).relative_to(project_root)).replace("\\", "/")
        except ValueError:
            rel_path = file_path.replace("\\", "/")

        suffix = Path(rel_path).suffix.lower()
        is_doc = suffix in {".md", ".mdx", ".rst", ".txt"}

        try:
            content = Path(file_path).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            logger.warning("Failed to read %s: %s", rel_path, e)
            files_failed += 1
            continue

        current_hash = file_hash(content)
        if not force and manifest.get(rel_path) == current_hash:
            files_unchanged += 1
            continue

        store.delete_by_source(collection, rel_path)

        # Route to the right chunker
        if is_doc:
            raw_chunks = chunk_markdown(
                content, rel_path,
                max_tokens=MAX_CHUNK_TOKENS,
                min_tokens=MIN_CHUNK_TOKENS,
                chunk_overlap=CHUNK_OVERLAP_TOKENS,
            )
        else:
            raw_chunks = chunk_code(
                content, rel_path,
                max_tokens=MAX_CHUNK_TOKENS,
                min_tokens=MIN_CHUNK_TOKENS,
                chunk_overlap=CHUNK_OVERLAP_TOKENS,
            )

        # Extract graph edges for code files
        if has_edge_extraction and not is_doc:
            lang = get_language(file_path)
            if lang:
                try:
                    edges = extract_edges(content, lang, rel_path)
                    if edges:
                        graph.delete_edges_for_file(rel_path)
                        graph.add_edges(edges)
                        edges_extracted += len(edges)
                except Exception as e:
                    logger.warning("Edge extraction failed for %s: %s", rel_path, e)

        if not raw_chunks:
            files_unchanged += 1
            continue

        try:
            texts = [c.content for c in raw_chunks]
            embeddings = code_embedder.embed(texts)

            store_chunks = []
            for i, (raw, embedding) in enumerate(zip(raw_chunks, embeddings)):
                if raw.token_count_approx < DEGENERATE_CHUNK_MIN_TOKENS:
                    continue
                cid = chunk_id(rel_path, i)
                metadata = build_metadata(
                    source_file=rel_path,
                    scope="project",
                    section=raw.section,
                    line_start=raw.line_start,
                    line_end=raw.line_end,
                    content_hash=current_hash,
                    chunk_index=i,
                    token_count=raw.token_count_approx,
                )
                store_chunks.append(Chunk(
                    id=cid,
                    content=raw.content,
                    embedding=embedding,
                    metadata=metadata,
                ))

            added = store.add_chunks(collection, store_chunks)
            chunks_created += added
            files_indexed += 1
            manifest[rel_path] = current_hash
            del texts, embeddings, store_chunks
        except Exception as e:
            logger.error("Failed to embed/store %s: %s", rel_path, e)
            files_failed += 1

    # GC before graph post-processing
    _gc_cleanup(f"project:{project_path}")

    # Post-processing: resolve graph targets and clean up ghost edges
    graph_stats = {}
    if has_edge_extraction:
        try:
            resolved_count = graph.resolve_target_files(file_map)
            ghost_count = graph.delete_ghost_edges(current_files)
            graph_stats = {
                "edges_total": graph.count_edges(),
                "edges_resolved": graph.count_resolved_edges(),
                "edges_unresolved": graph.count_unresolved_edges(),
                "edges_extracted_this_run": edges_extracted,
                "targets_resolved": resolved_count,
                "ghosts_cleaned": ghost_count,
            }
            logger.info(
                "Graph built for %s: %d edges (%d resolved, %d unresolved, %d ghosts cleaned)",
                pid, graph_stats["edges_total"], graph_stats["edges_resolved"],
                graph_stats["edges_unresolved"], ghost_count,
            )
            # PageRank: used as a tiebreaker when pruning deep graph
            # traversals in get_neighbours() (search.py mode=graph). Cheap
            # relative to the embedding work already done above, so compute
            # it on every index rather than making it opt-in.
            try:
                from .graph_store import compute_pagerank
                pr_scores = compute_pagerank(graph)
                graph.save_pagerank(pr_scores)
                graph_stats["pagerank_nodes"] = len(pr_scores)
            except Exception as e:
                logger.warning("PageRank computation failed for %s: %s", pid, e)
        except Exception as e:
            logger.error("Graph post-processing failed: %s", e)
            graph_stats = {"error": str(e)}

    # Save manifest
    _save_project_manifest(manifest_path, manifest, str(project_root))

    # Update project registry
    _update_project_registry(
        pid, str(project_root), files_indexed, chunks_created,
        graph_stats=graph_stats,
    )

    # Evict project ChromaDB client + GC
    ChromaStore.evict_cache(str(chroma_dir))
    _gc_cleanup(f"project-final:{pid}")

    elapsed = round(time.time() - start_time, 1)
    mem = _mem_mb()
    logger.info("index_project(%s) done: %d files, %d chunks, %.1fs, RAM=%.1f MB",
                pid, files_indexed, chunks_created, elapsed, mem)
    result = {
        "project_id": pid,
        "project_path": str(project_root),
        "files_indexed": files_indexed,
        "chunks_created": chunks_created,
        "files_unchanged": files_unchanged,
        "files_failed": files_failed,
        "elapsed_s": elapsed,
        "ram_mb": mem,
    }
    if graph_stats:
        result["graph"] = graph_stats
    return result


def reindex_file(
    project_path: str,
    file_path: str,
    code_embedder,
) -> dict:
    """Reindex a single file within an already-indexed project.

    Much faster than index_project() because it skips scanning the whole
    project tree. Only re-embeds the specified file if its content hash
    changed since the last index. Also updates graph edges for the file.

    Returns stats dict.
    """
    project_root, pid, index_dir, chroma_dir, manifest_path = _project_paths(project_path)

    # Project must already be indexed
    if not chroma_dir.exists():
        return {"error": f"Project not indexed: {project_path}. Run index-project first."}

    # Load manifest
    manifest: dict = {}
    if manifest_path.exists():
        try:
            raw = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest = {k: v for k, v in raw.items() if not k.startswith("__")}
        except Exception:
            manifest = {}

    abs_file = Path(file_path).resolve()
    try:
        rel_path = str(abs_file.relative_to(project_root)).replace("\\", "/")
    except ValueError:
        return {"error": f"File {file_path} is not under project root {project_path}"}

    if not abs_file.is_file():
        return {"error": f"File not found: {file_path}"}

    suffix = abs_file.suffix.lower()
    if suffix not in CODE_EXTENSIONS:
        return {"skipped": True, "reason": f"Extension {suffix} not indexable"}

    try:
        if abs_file.stat().st_size > MAX_FILE_SIZE:
            return {"skipped": True, "reason": "File too large"}
    except OSError:
        return {"error": f"Cannot stat {file_path}"}

    try:
        content = abs_file.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        return {"error": f"Cannot read {file_path}: {e}"}

    current_hash = file_hash(content)
    if manifest.get(rel_path) == current_hash:
        return {"unchanged": True, "file": rel_path}

    # File changed: re-embed it
    store = ChromaStore(persist_dir=str(chroma_dir))
    collection = "codebase"

    if not store.collection_exists(collection):
        return {"error": "Project collection does not exist. Run index-project first."}

    is_doc = suffix in {".md", ".mdx", ".rst", ".txt"}

    store.delete_by_source(collection, rel_path)

    if is_doc:
        raw_chunks = chunk_markdown(
            content, rel_path,
            max_tokens=MAX_CHUNK_TOKENS,
            min_tokens=MIN_CHUNK_TOKENS,
            chunk_overlap=CHUNK_OVERLAP_TOKENS,
        )
    else:
        raw_chunks = chunk_code(
            content, rel_path,
            max_tokens=MAX_CHUNK_TOKENS,
            min_tokens=MIN_CHUNK_TOKENS,
            chunk_overlap=CHUNK_OVERLAP_TOKENS,
        )

    if not raw_chunks:
        manifest[rel_path] = current_hash
        _save_project_manifest(manifest_path, manifest, str(project_root))
        return {"file": rel_path, "chunks_created": 0, "reason": "no indexable content"}

    start_time = time.time()
    try:
        texts = [c.content for c in raw_chunks]
        embeddings = code_embedder.embed(texts)

        store_chunks = []
        for i, (raw, embedding) in enumerate(zip(raw_chunks, embeddings)):
            if raw.token_count_approx < DEGENERATE_CHUNK_MIN_TOKENS:
                continue
            cid = chunk_id(rel_path, i)
            metadata = build_metadata(
                source_file=rel_path,
                scope="project",
                section=raw.section,
                line_start=raw.line_start,
                line_end=raw.line_end,
                content_hash=current_hash,
                chunk_index=i,
                token_count=raw.token_count_approx,
            )
            store_chunks.append(Chunk(
                id=cid,
                content=raw.content,
                embedding=embedding,
                metadata=metadata,
            ))

        added = store.add_chunks(collection, store_chunks)
    except Exception as e:
        logger.error("Failed to reindex %s: %s", rel_path, e)
        return {"error": f"Embedding failed for {rel_path}: {e}"}

    # Update graph edges for this file
    graph_updated = False
    if not is_doc:
        graph_db_path = index_dir / "graph.db"
        if graph_db_path.exists():
            try:
                from .graph_store import SQLiteGraphStore
                from .edge_extraction import extract_edges, get_language

                graph = SQLiteGraphStore(str(graph_db_path))
                graph.delete_edges_for_file(rel_path)

                lang = get_language(file_path)
                if lang:
                    edges = extract_edges(content, lang, rel_path)
                    if edges:
                        graph.add_edges(edges)

                        # Re-register this file's variants and re-resolve
                        file_map: dict[str, str] = {}
                        _register_file_variants(rel_path, file_map)
                        graph.resolve_target_files(file_map)

                    graph_updated = True
            except ImportError:
                pass
            except Exception as e:
                logger.warning("Graph update failed for %s: %s", rel_path, e)

    manifest[rel_path] = current_hash
    _save_project_manifest(manifest_path, manifest, str(project_root))

    elapsed = round(time.time() - start_time, 3)
    result = {
        "file": rel_path,
        "chunks_created": added,
        "elapsed_s": elapsed,
    }
    if graph_updated:
        result["graph_updated"] = True
    return result


def _update_project_registry(
    pid: str,
    project_path: str,
    files_indexed: int,
    chunks_created: int,
    graph_stats: dict | None = None,
) -> None:
    """Update state/projects.json with current project stats."""
    registry_path = STATE_DIR / "projects.json"
    registry: dict = {}
    if registry_path.exists():
        try:
            registry = json.loads(registry_path.read_text(encoding="utf-8"))
        except Exception:
            registry = {}

    entry = {
        "project_path": project_path,
        "source": "clean-rag",
        "server": "http://127.0.0.1:8613",
        "files_indexed": files_indexed,
        "chunks_created": chunks_created,
        "indexed_at": datetime.now(timezone.utc).isoformat(),
    }
    if graph_stats:
        entry["graph"] = graph_stats

    registry[pid] = entry

    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text(json.dumps(registry, indent=2), encoding="utf-8")
