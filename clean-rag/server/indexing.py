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
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .code_chunker import RawChunk, chunk_code, estimate_tokens
from .config import (
    CHUNK_OVERLAP_TOKENS,
    DATABASES_DIR,
    DEGENERATE_CHUNK_MIN_TOKENS,
    MAX_CHUNK_TOKENS,
    MIN_CHUNK_TOKENS,
    PIPELINE_VERSION,
    STATE_DIR,
)
from .lang_router import get_model_for_project
from .project_id import resolve_project_dir
from .file_scan import (
    CODE_EXTENSIONS,
    MAX_FILE_SIZE,
    SKIP_DIRS,
    SKIP_FILES,
    SKIP_SUFFIXES,
    scan_project,
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

#: Manifest value for a file that exists, passed every scan filter, and still
#: could not be read as text. Safe against collision by construction:
#: file_hash() returns exactly 16 lowercase hex characters, so no real hash can
#: ever equal this.
UNREADABLE_SENTINEL = "__unreadable__"


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

# File selection (CODE_EXTENSIONS, SKIP_DIRS, SKIP_FILES, SKIP_SUFFIXES,
# MAX_FILE_SIZE, scan_project) now lives in file_scan.py, imported at the top, so
# the isolated GraphRAG venv can reuse the exact same hardened rules.


# ---------------------------------------------------------------------------
# Project indexing
# ---------------------------------------------------------------------------

def _save_project_manifest(
    manifest_path: Path, manifest: dict, project_path: str,
    pipeline_version: int | None = None,
    model_id: str | None = None,
    embedding_dim: int | None = None,
    incomplete: bool | None = None,
) -> None:
    """Save project manifest to disk with metadata.

    Metadata keys the caller does not supply are carried over from whatever is
    already on disk rather than dropped. reindex_file() calls this on every
    single edit and knows nothing about the pipeline version or the embedding
    model, so without the carry over each per file reindex silently erased
    ``__pipeline_version__`` and ``__model_id__``. That erasure is why every
    manifest in databases/_projects/ holds only ``__project_path__``: it made
    index_project() force a full rebuild every run (stored version always read
    back as None), and it destroyed the provenance record that tells search
    which embedding space a project's vectors actually live in.
    """
    manifest_path.parent.mkdir(parents=True, exist_ok=True)

    prior: dict = {}
    if manifest_path.exists():
        try:
            raw = json.loads(manifest_path.read_text(encoding="utf-8"))
            prior = {k: v for k, v in raw.items() if k.startswith("__")}
        except Exception:
            prior = {}

    save_data = {"__project_path__": project_path}
    for key, value in (
        ("__pipeline_version__", pipeline_version),
        ("__model_id__", model_id),
        ("__embedding_dim__", embedding_dim),
        ("__incomplete__", incomplete),
    ):
        if value is not None:
            save_data[key] = value
        elif key in prior:
            save_data[key] = prior[key]

    save_data.update(manifest)
    manifest_path.write_text(json.dumps(save_data, indent=2), encoding="utf-8")


def read_project_provenance(project_path: str) -> dict:
    """Return the embedding provenance recorded for *project_path*.

    Keys: ``model_id`` and ``embedding_dim``, either of which may be None when
    the project was indexed before provenance was recorded. A None model_id
    means "unknown", which search must treat as unsafe rather than assume it
    matches the current model: an index built by a different model of the same
    width returns confident nonsense instead of an error.
    """
    _root, _pid, _index_dir, _chroma_dir, manifest_path = _project_paths(project_path)
    if not manifest_path.exists():
        return {"model_id": None, "embedding_dim": None}
    try:
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        return {"model_id": None, "embedding_dim": None}
    return {
        "model_id": raw.get("__model_id__"),
        "embedding_dim": raw.get("__embedding_dim__"),
    }


def index_is_incomplete(project_path: str) -> bool:
    """Did the last index of *project_path* stop before it reached every file?

    True means the manifest lists a real subset of the project: every file in
    it is genuinely in the store, and the rest were never reached. A resume can
    therefore run with force off and keep the work already done, instead of
    wiping the collection and starting the same large project from zero every
    time the machine is busy.
    """
    _root, _pid, _index_dir, _chroma_dir, manifest_path = _project_paths(project_path)
    if not manifest_path.exists():
        return False
    try:
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        logger.error("Manifest unreadable for %s: %s", project_path, e)
        return False
    return bool(raw.get("__incomplete__"))


def _project_paths(project_path: str) -> tuple[Path, str, Path, Path, Path]:
    """Resolve project root, project ID, index dir, store dir, manifest path.

    The name comes from server/project_id.py, which every other lookup site
    also uses. It used to be computed here and hand copied into five other
    files, and a disagreement between any two of them read as "never
    indexed" rather than as an error.
    """
    project_root = Path(project_path).resolve()
    index_dir = resolve_project_dir(DATABASES_DIR / "_projects", project_root)
    pid = index_dir.name
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
    model_cache,
    force: bool = False,
    should_abort: Callable[[], str | None] | None = None,
) -> dict:
    """Index a project's source code into databases/_projects/<hash>/chroma/.

    Also builds a structural graph (graph.db) of import/inheritance edges
    for mode=graph search.

    Args:
        model_cache: A ModelCache instance (from lang_router) or a plain
            embedder with an ``embed(texts)`` method for backward compat.
        should_abort: Optional zero-argument callable consulted before each
            file. Return a reason string to stop the run there; return None to
            carry on. This is the only way a background sweep can give the
            machine back part way through one project: index_project runs
            inside a run_in_executor worker, and a Future that has already
            started cannot be cancelled, so stopping has to be cooperative --
            the worker checks a flag at a safe point and returns by itself.
            Left unset (the manual /index-project path) nothing is checked and
            behaviour is exactly as before.

    Returns stats dict. A run that stopped early carries ``stopped_early`` with
    the reason, and its manifest is marked incomplete so the next pass resumes.
    """
    project_root, pid, index_dir, chroma_dir, manifest_path = _project_paths(project_path)

    # Load manifest and check pipeline version
    manifest: dict = {}
    stored_model_id: str | None = None
    if not force and manifest_path.exists():
        try:
            raw = json.loads(manifest_path.read_text(encoding="utf-8"))
            stored_version = raw.get("__pipeline_version__")
            stored_model_id = raw.get("__model_id__")
            if stored_version != PIPELINE_VERSION:
                logger.info(
                    "Pipeline version changed (%s -> %s), forcing full reindex of %s",
                    stored_version, PIPELINE_VERSION, project_path,
                )
                force = True
            manifest = {k: v for k, v in raw.items() if not k.startswith("__")}
        except Exception:
            manifest = {}

    if force:
        ChromaStore.evict_cache(str(chroma_dir))
        _gc_cleanup("force-pre-evict")

    store = ChromaStore(persist_dir=str(chroma_dir))
    collection = "codebase"

    if force and store.collection_exists(collection):
        deleted = store.delete_collection(collection)
        if not deleted:
            raise RuntimeError(
                f"Force-rebuild of {project_path!r}: could not delete existing "
                f"collection after 3 attempts — aborting to prevent double-indexing. "
                f"Restart the RAG server and retry."
            )

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

    # _EXT_TO_LANG is always available (code_chunker depends on edge_extraction
    # at the top level, so if it were missing indexing.py wouldn't load at all).
    from .edge_extraction import _EXT_TO_LANG

    # extract_edges and get_language are only needed for graph building.
    try:
        from .edge_extraction import extract_edges, get_language
        has_edge_extraction = True
    except ImportError:
        logger.warning("edge_extraction not available, skipping graph build")
        has_edge_extraction = False

    # Detect dominant language and pick the right embedding model.
    # If model_cache is a ModelCache, use lang routing; otherwise it's a plain
    # embedder passed directly (backward compat with auto_reindex).
    from .lang_router import ModelCache
    if isinstance(model_cache, ModelCache):
        lang_counts: dict[str, int] = {}
        for fp in file_paths:
            ext = Path(fp).suffix.lower()
            lang = _EXT_TO_LANG.get(ext, "unknown")
            lang_counts[lang] = lang_counts.get(lang, 0) + 1
        model_id = get_model_for_project(lang_counts)
        code_embedder = model_cache.get(model_id)
        # Record the model that actually produced the vectors, not the one we
        # asked for. ModelCache.get falls back to CODE_EMBEDDING_MODEL when the
        # routed model cannot load (bigcode/starencoder, the router's own
        # fallback entry, currently fails this way), and writing the requested
        # id would make the manifest claim an embedding space the vectors are
        # not in. Search compares this id against the live embedder, so a wrong
        # value here marks a freshly indexed project permanently stale.
        actual_model_id = getattr(code_embedder, "model_name", None)
        if actual_model_id and actual_model_id != model_id:
            logger.info(
                "Model %s unavailable, vectors produced by %s -- recording the latter",
                model_id, actual_model_id,
            )
            model_id = actual_model_id
    else:
        # Plain embedder passed directly (backward compat)
        code_embedder = model_cache
        model_id = stored_model_id or ""

    files_indexed = 0
    chunks_created = 0
    files_unchanged = 0
    files_failed = 0
    edges_extracted = 0
    stopped_early: str | None = None
    start_time = time.time()

    for file_path in file_paths:
        # Cooperative abort point: between files, never part way through one.
        # A file only enters the manifest once its chunks are actually in the
        # store, so stopping here always leaves the manifest and the store
        # agreeing about what is indexed.
        if should_abort is not None:
            reason = should_abort()
            if reason:
                stopped_early = reason
                logger.warning(
                    "Giving the machine back part way through %s: %s "
                    "(%d of %d files done, resuming next sweep)",
                    project_path, reason, files_indexed, len(file_paths),
                )
                break

        try:
            rel_path = str(Path(file_path).relative_to(project_root)).replace("\\", "/")
        except ValueError:
            rel_path = file_path.replace("\\", "/")

        suffix = Path(rel_path).suffix.lower()
        is_doc = suffix in {".md", ".mdx", ".rst", ".txt"}

        try:
            content = Path(file_path).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            # Record the failure instead of just counting it.
            #
            # Leaving no manifest entry meant find_changed_files (which reads
            # with errors="replace" and so always succeeds) saw a file it had
            # no hash for, called it changed, and handed it back here to fail
            # identically. Forever: one real file logged the same
            # UnicodeDecodeError on 98 consecutive passes and was never
            # indexed. The sentinel is what lets the two agree the file is
            # known and unreadable rather than perpetually new.
            #
            # UNREADABLE_SENTINEL cannot collide with a real entry because
            # file_hash() returns exactly 16 lowercase hex characters.
            logger.warning("Failed to read %s: %s", rel_path, e)
            manifest[rel_path] = UNREADABLE_SENTINEL
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

    # Save manifest with pipeline version and model info. The dimension is
    # recorded alongside the model id because a same width model swap (both
    # CodeRankEmbed and st-codesearch-distilroberta-base are 768) passes every
    # width check there is while still returning results from a different
    # embedding space, so width alone cannot detect it.
    embedding_dim: int | None = None
    try:
        embedding_dim = store.sample_dimension(collection)
    except Exception:
        logger.debug("Could not sample embedding dimension for %s", pid, exc_info=True)

    # A run that stopped early still saves, and that is the deliberate choice
    # over leaving the previous manifest untouched. The manifest is the record
    # of what is actually in the store, and after the break above it holds
    # A run that stopped early still saves, and that is the deliberate choice
    # over leaving the previous manifest untouched. The manifest is the record
    # of what is actually in the store, and after the break above it holds
    # exactly the files this run embedded (plus, when force is off, the ones
    # already there and untouched). The files never reached are simply absent,
    # so the next sweep sees them as changed and finishes the job.
    #
    # Not saving would be worse, specifically on a force rebuild: the
    # collection is emptied at the top of this function, so keeping the old
    # manifest would claim files are indexed whose chunks no longer exist, and
    # nothing would ever notice or reindex them. __incomplete__ is what stops
    # the resume from being a restart, see index_is_incomplete().
    _save_project_manifest(
        manifest_path, manifest, str(project_root),
        pipeline_version=PIPELINE_VERSION,
        incomplete=stopped_early is not None,
        # The backward compat branch above sets model_id to "" when a plain
        # embedder was passed instead of a ModelCache. Empty is "unknown", not
        # a real model id, so normalize it to None and let the carry over keep
        # any genuine value already on disk.
        model_id=model_id or None,
        embedding_dim=embedding_dim,
    )

    # Update project registry
    _update_project_registry(
        pid, str(project_root), files_indexed, chunks_created,
        graph_stats=graph_stats,
    )

    # Reclaim any free pages after the bulk delete+insert cycle.
    store.vacuum()

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
    if stopped_early:
        result["stopped_early"] = stopped_early
    return result


def reindex_file(
    project_path: str,
    file_path: str,
    model_cache,
) -> dict:
    """Reindex a single file within an already-indexed project.

    Much faster than index_project() because it skips scanning the whole
    project tree. Only re-embeds the specified file if its content hash
    changed since the last index. Also updates graph edges for the file.

    Args:
        model_cache: A ModelCache instance or plain embedder (backward compat).

    Caller must hold ``acquire_index_lock()`` before calling.  The function
    may run VACUUM on the SQLite file, which requires exclusive access.

    Returns stats dict.
    """
    project_root, pid, index_dir, chroma_dir, manifest_path = _project_paths(project_path)

    # Project must already be indexed
    if not chroma_dir.exists():
        return {"error": f"Project not indexed: {project_path}. Run index-project first."}

    # Load manifest and read the model this project was indexed with
    manifest: dict = {}
    stored_model_id: str | None = None
    if manifest_path.exists():
        try:
            raw = json.loads(manifest_path.read_text(encoding="utf-8"))
            stored_model_id = raw.get("__model_id__")
            manifest = {k: v for k, v in raw.items() if not k.startswith("__")}
        except Exception:
            manifest = {}

    # Resolve the embedder: use the project's stored model from ModelCache,
    # or fall back to the passed object if it's a plain embedder.
    from .lang_router import ModelCache
    if isinstance(model_cache, ModelCache):
        if stored_model_id:
            code_embedder = model_cache.get(stored_model_id)
        else:
            from .config import CODE_EMBEDDING_MODEL
            code_embedder = model_cache.get(CODE_EMBEDDING_MODEL)
    else:
        code_embedder = model_cache

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

    # Reclaim dead pages if the freelist has grown past the threshold.
    # Full VACUUM runs after index_project(); this catches the incremental
    # accumulation from repeated per-file delete+insert cycles.
    store.vacuum_if_needed()

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
