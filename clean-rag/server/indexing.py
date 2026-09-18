"""Indexing engine for clean-rag. Handles chunking, embedding, and storage.

Extracted from ClaudeBoost mcp-rag-server, simplified for project indexing.
"""

import gc
import hashlib
import json
import logging
import os
import re
import shutil
import stat
import sys
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
    INDEX_MANIFEST_CHECKPOINT_S,
    MAX_CHUNK_TOKENS,
    MIN_CHUNK_TOKENS,
    PIPELINE_VERSION,
    STATE_DIR,
)
from .lang_router import get_model_for_project
from .project_id import (
    leaf_only_dir_name,
    legacy_project_dir_name,
    project_dir_name,
    resolve_project_dir,
)
from .file_scan import (
    CODE_EXTENSIONS,
    MAX_FILE_SIZE,
    SKIP_DIRS,
    SKIP_FILES,
    SKIP_SUFFIXES,
    exclusion_reason,
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


#: How long an unreadable lock file is treated as "someone is mid-claim" rather
#: than "corrupt, clear it". A winner of the atomic create below is a few
#: microseconds away from writing its payload, and during that gap the file is
#: zero bytes. Without this grace a loser would read those zero bytes, call the
#: lock corrupt, delete the winner's claim and take the lock itself, which is
#: the same two holders bug by a different route. A real corrupt lock is cleared
#: on the next attempt after the grace expires.
_LOCK_CLAIM_GRACE_S = 10


def _pid_is_alive(pid: int) -> bool:
    """Is this PID a running process? True whenever we cannot tell.

    The direction matters. Answering "alive" for a process we cannot inspect
    keeps a lock that may already be dead, which costs a delayed reindex until
    the file is cleared by hand. Answering "dead" would break a live holder's
    lock and put two indexers on one collection, which is the failure the lock
    exists to prevent. So this fails toward keeping the lock.
    """
    if not isinstance(pid, int) or pid <= 0:
        return False
    try:
        import psutil

        return psutil.pid_exists(pid)
    except ImportError:
        pass

    if os.name == "nt":
        # No os.kill probe here. On Windows os.kill passes any signal other
        # than CTRL_C_EVENT/CTRL_BREAK_EVENT straight to TerminateProcess, so
        # the POSIX `os.kill(pid, 0)` liveness idiom does not ask whether the
        # process is alive, it kills it (python/cpython#70538). Without psutil
        # there is no safe probe, so report the holder as alive and let the
        # lock be cleared by hand rather than terminate somebody's process.
        logger.warning(
            "psutil is not installed, so the liveness of index lock holder PID "
            "%d cannot be checked on Windows; treating the lock as held. "
            "Install psutil, or delete %s if you are sure no indexer is running.",
            pid, _INDEX_LOCK_PATH,
        )
        return True

    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        # Running, owned by another user.
        return True
    except OSError:
        return True
    return True


def _break_stale_lock() -> bool:
    """Clear the lock file if its holder is gone. True if the path is now free.

    Separate from the claim on purpose: this only removes a lock, it never
    grants one. The caller re-runs the same atomic create afterwards, so two
    callers that both spot the same dead holder still race for a single winner.
    """
    try:
        raw = _INDEX_LOCK_PATH.read_bytes()
    except FileNotFoundError:
        # Released between the failed claim and this read. Free to retry.
        return True
    except OSError as e:
        logger.error("Could not read the index lock at %s: %s", _INDEX_LOCK_PATH, e)
        return False

    try:
        lock_data = json.loads(raw.decode("utf-8"))
        lock_pid = int(lock_data.get("pid", -1))
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError):
        try:
            age_s = time.time() - _INDEX_LOCK_PATH.stat().st_mtime
        except OSError:
            return False
        if age_s < _LOCK_CLAIM_GRACE_S:
            # Almost certainly a claim in flight, not corruption. Stay out.
            return False
        logger.info("Clearing corrupt index lock file at %s", _INDEX_LOCK_PATH)
    else:
        if _pid_is_alive(lock_pid):
            logger.warning(
                "Index lock held by PID %d (%s), started %s",
                lock_pid, lock_data.get("operation", "?"), lock_data.get("started", "?"),
            )
            return False
        logger.info("Clearing stale index lock from dead PID %d", lock_pid)

    # Re-read before unlinking. Between the read above and here the dead
    # holder's lock can have been cleared and a live caller can have claimed it
    # for real; deleting that would hand the lock to two callers at once.
    # Identical bytes means it is still the same abandoned claim.
    try:
        if _INDEX_LOCK_PATH.read_bytes() != raw:
            return False
        _INDEX_LOCK_PATH.unlink()
    except FileNotFoundError:
        pass
    except OSError as e:
        logger.error("Could not clear the stale index lock at %s: %s", _INDEX_LOCK_PATH, e)
        return False
    return True


def acquire_index_lock(operation: str = "index", project: str = "") -> bool:
    """Try to acquire the indexing lock. Returns True if acquired, False if busy.

    The claim is one ``os.open(O_CREAT | O_EXCL)``, not an ``exists()`` check
    followed by a write. That is the whole lock. The previous form left a gap
    between the two halves in which every caller saw "not locked", so all of
    them wrote and all of them believed they held it, and two indexers then
    wrote the same manifest.json and chroma collection. "Create if absent, else
    fail" inside O_EXCL is a single kernel operation with no such gap, and it
    behaves the same on POSIX and on Windows, where CPython maps it to
    ``CreateFile`` with ``CREATE_NEW``.

    Stdlib rather than filelock or portalocker. filelock is only present here
    transitively (huggingface_hub, torch and transformers each require it) and
    nothing in requirements.txt declares it, and moving to an OS advisory lock
    would also replace the PID convention that release_index_lock and
    cli/reindex_batch.py are both written against. O_EXCL buys the atomicity
    without taking on either.

    Known limit, inherited from the technique: O_EXCL is not atomic over NFS.
    The lock lives in the local ``state/`` directory, so this does not apply;
    a network mounted state directory would need a real lock manager.

    The PID is still recorded, so a crashed holder's lock is cleared rather
    than wedging indexing forever. See _break_stale_lock for how that stays
    exclusive.
    """
    try:
        _INDEX_LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        logger.error(
            "Could not create the index lock directory %s: %s", _INDEX_LOCK_PATH.parent, e,
        )
        return False

    payload = json.dumps({
        "pid": os.getpid(),
        "operation": operation,
        # Which project, so a reader can say WHICH row is indexing rather than
        # only that something is. Empty when the caller does not know yet.
        "project": str(project or ""),
        "started": datetime.now(timezone.utc).isoformat(),
    }).encode("utf-8")

    # One retry, and only after a stale lock was actually cleared. Looping here
    # would turn a contended lock into a spin against whoever keeps winning.
    for attempt in range(2):
        try:
            fd = os.open(_INDEX_LOCK_PATH, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            if attempt == 0 and _break_stale_lock():
                continue
            return False
        except OSError as e:
            logger.error("Could not claim the index lock at %s: %s", _INDEX_LOCK_PATH, e)
            return False

        # os.write, not fdopen: no newline translation, so the bytes on disk are
        # identical on Windows and POSIX and _break_stale_lock's byte comparison
        # means the same thing on both.
        try:
            os.write(fd, payload)
        except OSError as e:
            # The claim landed but the payload did not. An empty lock file would
            # park every later caller behind the grace window for no reason, so
            # hand it straight back.
            logger.error("Could not write the index lock payload: %s", e)
            _INDEX_LOCK_PATH.unlink(missing_ok=True)
            return False
        finally:
            os.close(fd)
        return True

    return False


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


def _rel_path(file_path: str, project_root: Path) -> str:
    """The manifest key for *file_path*: project relative, forward slashed.

    One function rather than the same four lines at each site, because every
    reader of the manifest has to derive the key the exact same way the writer
    did. A site that derived it differently would look up a hash that is on
    disk under another spelling and conclude the file was never indexed.

    Falls back to the absolute path for anything outside the root, which is
    what the manifest has always keyed such a file on.
    """
    try:
        return str(Path(file_path).relative_to(project_root)).replace("\\", "/")
    except ValueError:
        return file_path.replace("\\", "/")


def _pressure_reason(
    should_abort: Callable[[], str | None], project_path: str
) -> str | None:
    """Ask *should_abort* whether to stop, treating its own failure as carry on.

    psutil can fail on exactly the machine this guard exists for, and the
    manifest entries for everything embedded since the last checkpoint live in
    memory until the run ends. So an exception escaping here would throw away
    real work in order to report a failed memory read. Logged at error level
    because "this run is now unguarded" is not something to discover later.
    """
    try:
        return should_abort()
    except Exception as e:
        logger.error(
            "Pressure check failed for %s, continuing unguarded: %s: %s",
            project_path, type(e).__name__, e,
        )
        return None


def _count_absent_from_manifest(
    file_paths: list[str], manifest: dict, project_root: Path
) -> int:
    """How many of *file_paths* the manifest holds no entry for.

    A file the manifest already knows has its chunks in the store, so a run that
    stops before revisiting it costs nothing: at worst its hash is stale, which
    is the ordinary changed file case the next run picks up. A file with no
    entry is genuinely missing from the index. That distinction is what separates
    a run that stopped with work outstanding from one that stopped having
    confirmed there was none.
    """
    return sum(
        1 for fp in file_paths if _rel_path(fp, project_root) not in manifest
    )


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
            The background sweep and POST /index-project both pass one; left
            unset nothing is checked. An exception out of it is logged and
            treated as "no pressure" rather than allowed to end the run, because
            a probe that cannot answer must not discard work already done.

    Returns stats dict. A run that stopped early carries ``stopped_early`` with
    the reason, ``files_pending`` with the number of files it never looked at,
    and ``index_incomplete`` saying whether any of those still need indexing.
    Only that last case marks the manifest incomplete for the next pass to
    resume from: a run that stopped having confirmed every remaining file was
    already indexed leaves a complete index complete.
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

    # `with`, not a bare constructor: this run holds the shared sqlite handle for
    # hours, the sweep can ask for that handle to be closed while it does, and the
    # close waits for this holder to check in. See ChromaStore.__del__ for why the
    # check in cannot be left to garbage collection.
    with ChromaStore(persist_dir=str(chroma_dir)) as store:
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
            rp = _rel_path(fp, project_root)
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
        # Files this run never looked at, and how many of those the manifest has
        # never held an entry for. Both stay 0 unless the run stops early.
        files_pending = 0
        files_never_indexed = 0
        start_time = time.time()

        # Next wall clock moment the manifest gets flushed. Monotonic, so a system
        # clock change part way through a multi hour run cannot stall the
        # checkpointing or fire it every iteration.
        next_checkpoint_at = time.monotonic() + INDEX_MANIFEST_CHECKPOINT_S

        for position, file_path in enumerate(file_paths):
            # Cooperative abort point: between files, never part way through one.
            # A file only enters the manifest once its chunks are actually in the
            # store, so stopping here always leaves the manifest and the store
            # agreeing about what is indexed.
            if should_abort is not None:
                reason = _pressure_reason(should_abort, project_path)
                if reason:
                    stopped_early = reason
                    pending = file_paths[position:]
                    files_pending = len(pending)
                    files_never_indexed = _count_absent_from_manifest(
                        pending, manifest, project_root
                    )
                    logger.warning(
                        "Giving the machine back part way through %s: %s "
                        "(%d of %d files done, %d not looked at, %d of those "
                        "never indexed)",
                        project_path, reason, files_indexed, len(file_paths),
                        files_pending, files_never_indexed,
                    )
                    break

            rel_path = _rel_path(file_path, project_root)

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
                # Record it anyway. Same reasoning as UNREADABLE_SENTINEL above,
                # for the sibling case: a file the chunker had nothing to say
                # about still has to be a file the manifest KNOWS about, or
                # find_changed_files sees a path it holds no hash for, calls it
                # changed, and hands it back here to produce nothing again.
                # Forever. Measured: 67 such files on one project drove a
                # complete 1818 file index to be wiped and rebuilt every 10
                # hours, because 67 crosses FULL_REINDEX_THRESHOLD every sweep.
                #
                # A real hash, not a sentinel. Unlike the unreadable case there
                # is no strict versus permissive read disagreement to paper
                # over: both functions read this file fine and compute the same
                # hash, so ordinary hash comparison already reprocesses it the
                # moment its content changes.
                #
                # reindex_file already does this at the identical branch. The
                # two entry points into this pipeline disagreed, and this one
                # was wrong.
                manifest[rel_path] = current_hash
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

            # Flush what has actually been indexed so far.
            #
            # Placed here, after add_chunks has already committed (store.py wraps
            # its inserts in `with self._conn:`), never before. The manifest is a
            # claim that a file's chunks are in the store, so writing it ahead of
            # the chunks would survive a crash as a permanent lie: neither
            # find_changed_files nor the unchanged hash skip above compares against
            # store contents, so nothing would ever notice the file was missing and
            # nothing would reindex it. Late is recoverable, early is not.
            #
            # incomplete=True on every intermediate write, explicitly. Passing None
            # would let _save_project_manifest carry over whatever __incomplete__ is
            # already on disk, so a project whose previous run finished cleanly
            # would keep claiming it was complete all the way through this one, and
            # index_is_incomplete() would tell the next sweep to rebuild instead of
            # resume. The end of run save below is what clears it back to False.
            #
            # Outside the try above on purpose. A failed manifest write has nothing
            # to do with embedding, and letting it land in that except would count a
            # file whose chunks are safely stored as a failure. It is also not worth
            # killing an hours long run over: the dict is still intact in memory, so
            # the next checkpoint or the final save picks it up.
            if time.monotonic() >= next_checkpoint_at:
                try:
                    _save_project_manifest(
                        manifest_path, manifest, str(project_root),
                        pipeline_version=PIPELINE_VERSION,
                        model_id=model_id or None,
                        incomplete=True,
                    )
                except OSError as e:
                    logger.warning("Manifest checkpoint failed for %s: %s", project_path, e)
                next_checkpoint_at = time.monotonic() + INDEX_MANIFEST_CHECKPOINT_S

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
        # exactly the files this run embedded (plus, when force is off, the ones
        # already there and untouched). The files never reached are simply absent,
        # so the next sweep sees them as changed and finishes the job.
        #
        # Not saving would be worse, specifically on a force rebuild: the
        # collection is emptied at the top of this function, so keeping the old
        # manifest would claim files are indexed whose chunks no longer exist, and
        # nothing would ever notice or reindex them. __incomplete__ is what stops
        # the resume from being a restart, see index_is_incomplete().
        #
        # Stopping early is not the same thing as being incomplete, which is why
        # this asks how many pending files the manifest never knew about rather
        # than just whether the run stopped. A routine incremental resync whose
        # guard fires before file 0 has confirmed nothing and changed nothing, and
        # every file is still indexed from the run before; marking that incomplete
        # would make a complete project report itself stale to /search until some
        # later run happened to clear it. A force run always has work outstanding
        # after a break, because the collection was emptied above and the manifest
        # starts empty with it.
        index_incomplete = stopped_early is not None and files_never_indexed > 0
        _save_project_manifest(
            manifest_path, manifest, str(project_root),
            pipeline_version=PIPELINE_VERSION,
            incomplete=index_incomplete,
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
        # files_indexed and files_unchanged only count files this run actually
        # looked at, so on their own they read the same for "nothing here" and
        # "everything here, already done, never looked at". files_pending says
        # how many files went unexamined and index_incomplete says whether any of
        # them still need indexing, which is the difference between "retry this"
        # and "nothing to do".
        result["stopped_early"] = stopped_early
        result["files_pending"] = files_pending
        result["index_incomplete"] = index_incomplete
    return result


def drop_manifest_key(project_path: str, rel_path: str) -> dict:
    """Evict one manifest key: its chunks, its graph edges, and its entry.

    Takes the manifest KEY itself, never a filesystem path, and that is the
    whole point of the function existing.

    The sweep knows exactly which key it wants gone: it read the string out of
    the manifest. What it used to do was rebuild an absolute path around that
    string, hand the path to reindex_file, and let reindex_file derive a key
    back out of it. That round trip is lossy, and three separate rounds of
    adversarial review each found a different shape it loses:

      * a case only rename, where Path.resolve() rewrote the key to the real
        on disk spelling and the eviction deleted a key nobody asked about,
      * an absolute key from outside the root, where relative_to refused and
        the entry could never be dropped at all,
      * a relative key containing '..', where the rebuilt path collapsed
        somewhere else entirely and the drop reported success against a string
        matching neither the manifest nor the store.

    Each was fixed in turn by another guard on the path derivation, and each
    fix was followed by a new shape. The shapes are not the bug. Converting a
    key to a path and back is the bug, so this does not do it. Nothing here
    consults the filesystem: the file may be present, absent, renamed, or
    outside the project root, and none of that changes which rows are stale.
    delete_by_source and delete_edges_referencing_file are plain SQL deletes
    keyed on the stored string, so they never needed a real file either.

    Caller must hold ``acquire_index_lock()``. May run VACUUM, which needs
    exclusive access.
    """
    project_root, _pid, index_dir, chroma_dir, manifest_path = _project_paths(project_path)

    if not chroma_dir.exists():
        return {"error": f"Project not indexed: {project_path}. Run index-project first."}

    manifest: dict = {}
    if manifest_path.exists():
        try:
            raw = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest = {k: v for k, v in raw.items() if not k.startswith("__")}
        except Exception:
            manifest = {}

    # `with`: the shared handle has to be checked back in on the raising path
    # too, see ChromaStore.__del__.
    with ChromaStore(persist_dir=str(chroma_dir)) as store:
        # No collection means no chunks, which is a reason to skip the store and
        # nothing else. The manifest entry still has to go: it is the manifest,
        # not the store, that find_changed_files reads to decide a key is
        # deleted, so returning early here leaves the key to be rediscovered on
        # every sweep forever. That is the exact loop this function exists to
        # end, and it survived every test because they all stubbed the store
        # with collection_exists() -> True. It took running the real sweep
        # against a project whose store was empty (todaymechanic, 377 keys, a
        # populated manifest and a vectors.db holding zero tables) to see it.
        collection = store.collection_exists("codebase")
        removed = store.delete_by_source("codebase", rel_path) if collection else 0

        # Unconditional, unlike the update path, which skips docs. Skipping here
        # would rely on the extension to decide whether edges can exist, and if
        # that guess is ever wrong the edges are orphaned permanently with
        # nothing left to reindex them. Deleting zero rows costs nothing, so ask
        # the question rather than predict the answer.
        #
        # Both directions, also unlike the update path. That one re-extracts the
        # file and adds its outgoing edges straight back, so it must keep the
        # inbound ones it cannot re-derive. Here nothing will ever reindex this
        # key, so an edge from a surviving file INTO it would leak permanently
        # and keep mode=graph search returning something that is not there.
        graph_db_path = index_dir / "graph.db"
        if graph_db_path.exists():
            try:
                from .graph_store import SQLiteGraphStore
                edges_removed = SQLiteGraphStore(
                    str(graph_db_path)
                ).delete_edges_referencing_file(rel_path)
                logger.debug(
                    "Removed %d graph edge(s) referencing dropped %s",
                    edges_removed, rel_path,
                )
            except ImportError:
                pass
            except Exception as e:
                logger.warning("Graph edge cleanup failed for dropped %s: %s", rel_path, e)

        # Dropping the entry, not blanking it. A leftover entry would keep
        # claiming chunks that are gone, and find_changed_files reports a path as
        # deleted for exactly as long as the manifest still lists it, so leaving
        # it hands the same key back on every sweep from now on.
        #
        # `present` is reported rather than assumed. An eviction that matched no
        # manifest entry is the signature of a caller that respelled the key, and
        # the sweep logging "Dropped 1 of 1" for that was how a stuck entry hid.
        present = rel_path in manifest
        manifest.pop(rel_path, None)
        _save_project_manifest(manifest_path, manifest, str(project_root))

        # Deletes are what grow the freelist, so this is the path that most wants
        # the reclaim. Threshold guarded, so it is a no-op until it isn't. Only
        # worth asking when something was actually deleted.
        if collection:
            store.vacuum_if_needed()

        logger.info("Dropped %s from the index", rel_path)
        return {
            "file": rel_path,
            "deleted": True,
            "chunks_removed": removed,
            "was_in_manifest": present,
            # False means the store held no collection, so only the manifest
            # entry was dropped. Surfaced because a project in that state has an
            # empty index and needs a real reindex, which the sweep cannot infer
            # from a per key drop.
            "collection_present": collection,
        }


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

    This takes a filesystem PATH and asks what should happen to the file there,
    so it resolves that path against the filesystem. Evicting a known manifest
    key is the other question and belongs to drop_manifest_key, which takes the
    key and never touches the filesystem at all. Keeping the two apart is what
    stopped a sweep from respelling a key on its way to being deleted.

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

    # Resolved before the embedder on purpose: a file that has been deleted is
    # handled below without ever loading a model, and an embedder is 1 to 2 GB
    # resident. Nothing here depends on the embedder.
    #
    # resolve() is right here and only here. This function was handed a path and
    # asked about the file at it, so the key it derives has to be the one
    # index_project would have stored, which is the file's real on disk
    # spelling. A caller that already holds a manifest key wants
    # drop_manifest_key instead, which takes the key and never derives one.
    abs_file = Path(file_path).resolve()
    try:
        rel_path = str(abs_file.relative_to(project_root)).replace("\\", "/")
    except ValueError:
        return {"error": f"File {file_path} is not under project root {project_path}"}

    if not abs_file.is_file():
        # The file is gone, so its rows are stale. Same work as an eviction the
        # sweep asks for by key, so it is the same function rather than a second
        # copy of it: two copies of a delete are how the two drifted apart in the
        # first place. rel_path is the key derived above from the real on disk
        # spelling, which is what index_project stored.
        return drop_manifest_key(project_path, rel_path)

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

    suffix = abs_file.suffix.lower()

    # The same per file rules scan_project applies, from the same function
    # rather than a second copy. The copy that used to live here checked only
    # the extension and the size, so every rule added to scan_project since
    # (the credential config globs, the binary sniff, the credential content
    # check) was silently not applied on the per edit path, which is the path
    # that runs most often.
    reason = exclusion_reason(abs_file)
    if reason is not None:
        return {"skipped": True, "reason": reason}

    try:
        content = abs_file.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        return {"error": f"Cannot read {file_path}: {e}"}

    current_hash = file_hash(content)
    if manifest.get(rel_path) == current_hash:
        return {"unchanged": True, "file": rel_path}

    # File changed: re-embed it
    # `with`: the shared handle has to be checked back in on the raising path too,
    # see ChromaStore.__del__.
    with ChromaStore(persist_dir=str(chroma_dir)) as store:
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


def _clear_readonly_and_retry(func, path, _exc):
    """shutil.rmtree error handler for Windows.

    Git writes pack/idx files read-only (-r--r--r--), and Windows refuses to
    delete a read-only file, so rmtree raises PermissionError [Errno 13] on
    them. Clear the read-only bit and reattempt the removal. This is the
    canonical CPython-documented workaround (shutil.rmtree onexc example).
    The third argument is the exception (onexc) or exc_info tuple (onerror);
    unused, so the handler works for either signature.
    """
    os.chmod(path, stat.S_IWRITE)
    func(path)


def _rmtree_clearing_readonly(path: Path) -> None:
    """rmtree that survives read only files, on either handler signature."""
    # onerror was deprecated in 3.12 and onexc replaced it. Passing the wrong
    # one is a TypeError on some versions and a silent DeprecationWarning on
    # others, so pick by what this interpreter actually accepts.
    if sys.version_info >= (3, 12):
        shutil.rmtree(path, onexc=_clear_readonly_and_retry)
    else:
        shutil.rmtree(path, onerror=_clear_readonly_and_retry)


def project_index_dirs(project_path: str) -> list[Path]:
    """Every database directory that exists on disk for *project_path*.

    Three naming schemes have coexisted (project_id.py:149-170), and
    resolve_project_dir deliberately returns only the first match. A delete
    that used it would leave the other directories behind: invisible to
    search, still holding disk, and ready to confuse a later reindex.
    """
    root = DATABASES_DIR / "_projects"
    names = {
        project_dir_name(project_path),
        leaf_only_dir_name(project_path),
        legacy_project_dir_name(project_path),
    }
    found = []
    for name in sorted(names):
        candidate = root / name
        if _is_inside_projects_root(candidate, root) and candidate.is_dir():
            found.append(candidate)
    return found


def _is_inside_projects_root(candidate: Path, root: Path) -> bool:
    """True only for a direct child of databases/_projects.

    The names above are hashes and slugs this module computes, so they cannot
    currently escape. This checks anyway, because the guard costs nothing and
    the thing on the other side of it is an rmtree. A future caller passing a
    name through from a request body would otherwise turn this into a path
    traversal that deletes outside the database directory.
    """
    try:
        resolved = candidate.resolve()
        root_resolved = root.resolve()
    except OSError:
        return False
    return resolved.parent == root_resolved and resolved != root_resolved


def delete_project_index(project_path: str) -> dict:
    """Remove clean-rag's index of *project_path*. Never touches its source.

    Caller must hold the index lock for the whole call. Without it the auto
    reindex sweep can rebuild the directory mid removal, or rewrite the
    registry entry after this function has removed it.

    Disk first, registry second, on purpose. An orphaned directory is visible
    and recoverable: the project reads as unindexed and a later index run
    overwrites it. An orphaned registry entry is the opposite, and it is the
    exact failure project_id.py's docstring exists to prevent, because the
    project then reads as indexed while every search against it silently
    returns nothing.

    Reports per step rather than a bare ok, matching index_project's
    stopped_early shape, so a caller can tell "nothing was there" from "two of
    three directories went and the third is locked".
    """
    removed: list[str] = []
    failed: list[dict] = []

    for directory in project_index_dirs(project_path):
        # Release our own SQLite handle on this project's vectors.db first.
        # The connection cache is process wide (store.py:123), so on Windows an
        # rmtree with it still open fails with WinError 32 rather than doing
        # anything. evict_cache closes it now when nothing holds it, and marks
        # it to close on the last holder's exit when something does.
        ChromaStore.evict_cache(str(directory / "chroma"))
        try:
            _rmtree_clearing_readonly(directory)
            removed.append(str(directory))
        except OSError as e:
            logger.error(
                "Could not remove index directory %s: %s: %s",
                directory, type(e).__name__, e,
            )
            failed.append({"path": str(directory), "error": f"{type(e).__name__}: {e}"})

    result: dict = {
        "project_path": project_path,
        "dirs_removed": removed,
        "dirs_failed": failed,
        "registry_removed": [],
    }

    # A directory that refused to go means the index is still partly on disk.
    # Removing the registry entry now would hide it from every tool that could
    # find it again, so stop and say so instead.
    if failed:
        result["error"] = (
            f"{len(failed)} index director(ies) could not be removed, so the "
            f"registry entry was left in place. The project is unchanged from "
            f"the caller's point of view. Retry once whatever holds the files "
            f"has let go."
        )
        return result

    result["registry_removed"] = _remove_from_project_registry(project_path)
    return result


def _remove_from_project_registry(project_path: str) -> list[str]:
    """Drop every registry entry pointing at *project_path*. Returns their pids.

    Matched on the resolved path rather than the pid, because the pid is
    derived from a naming scheme that has changed three times and an entry
    written under an older one would otherwise survive the delete.
    """
    registry_path = STATE_DIR / "projects.json"
    if not registry_path.exists():
        return []
    try:
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if not isinstance(registry, dict):
        return []

    try:
        target = Path(project_path).resolve()
    except OSError:
        return []

    dropped = []
    for pid, entry in list(registry.items()):
        entry_path = (entry or {}).get("project_path") if isinstance(entry, dict) else None
        if not entry_path:
            continue
        try:
            if Path(entry_path).resolve() == target:
                del registry[pid]
                dropped.append(pid)
        except OSError:
            continue

    if dropped:
        registry_path.write_text(json.dumps(registry, indent=2), encoding="utf-8")
    return dropped
