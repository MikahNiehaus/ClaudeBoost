"""rag_index_docs tool: indexes project markdown/rst docs into scope=project-docs."""

import hashlib
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from rag_server.core.metadata import chunk_id
from rag_server.core.project import load_ragignore
from rag_server.indexing.markdown_chunker import chunk_markdown
from rag_server.ports.embedding_port import EmbeddingPort
from rag_server.ports.store_port import Chunk

logger = logging.getLogger(__name__)

COLLECTION = "project-docs"
_DOC_EXTENSIONS = {".md", ".rst"}

# Directory names always excluded from doc scanning
_DOC_EXCLUDES = {
    ".git", ".hg", "node_modules", "__pycache__", ".venv", "venv", "env",
    ".tox", "dist", "build", "target", "obj", "bin", ".rag-index", "workspace",
    ".claudeboost",
}


def _docs_index_dir(project_path: str) -> Path:
    """Return the docs index directory for a project."""
    return Path(project_path).resolve() / ".rag-index" / "docs"


def _load_manifest(index_dir: Path) -> dict:
    manifest_path = index_dir / "manifest.json"
    if manifest_path.exists():
        try:
            return json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save_manifest(index_dir: Path, manifest: dict) -> None:
    index_dir.mkdir(parents=True, exist_ok=True)
    (index_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )


def _content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


def _scan_docs(project_path: str, paths: list[str] | None = None) -> list[Path]:
    """Collect markdown and rst files under project_path, respecting .ragignore."""
    root = Path(project_path).resolve()

    if paths:
        result = []
        for p in paths:
            fp = Path(p)
            if fp.exists() and fp.suffix.lower() in _DOC_EXTENSIONS:
                result.append(fp.resolve())
        return result

    ragignore_raw = load_ragignore(project_path)
    ragignore_dir_excludes = {e for e in ragignore_raw if "/" not in e}
    ragignore_path_patterns = [e for e in ragignore_raw if "/" in e]
    excludes = _DOC_EXCLUDES | ragignore_dir_excludes

    found: list[Path] = []
    for dirpath_str, dirnames, filenames in os.walk(root):
        dirpath = Path(dirpath_str)
        # Prune excluded and hidden directories in-place
        dirnames[:] = [d for d in dirnames if d not in excludes and not d.startswith(".")]
        for fname in filenames:
            fp = dirpath / fname
            if fp.suffix.lower() in _DOC_EXTENSIONS:
                found.append(fp)

    # Apply .ragignore path patterns (entries with a slash, e.g. docs/internal/)
    if ragignore_path_patterns and found:
        try:
            import pathspec as _ps
            ragignore_spec = _ps.PathSpec.from_lines("gitwildmatch", ragignore_path_patterns)
            found = [
                fp for fp in found
                if not ragignore_spec.match_file(fp.relative_to(root).as_posix())
            ]
        except Exception as e:
            logger.warning(".ragignore path patterns could not be applied: %s", e)

    return sorted(found)


def rag_index_docs(
    embedder: EmbeddingPort,
    project_path: str,
    paths: list[str] | None = None,
    force: bool = False,
) -> dict:
    """Index project documentation files into the per-project docs collection.

    Args:
        embedder: Shared embedding model instance.
        project_path: Absolute path to the project root.
        paths: Optional explicit list of file paths to index. Defaults to scanning
               all **/*.md and **/*.rst files under project_path.
        force: If True, re-index even if content hash matches.

    Returns:
        Dict with files_indexed, files_skipped, files_failed, chunks_created, collection_path.
    """
    if not embedder.is_loaded:
        return {"error": "Embedding model not ready yet. Retry in 30-60 seconds."}

    import shutil
    from rag_server.core.store import ChromaStore

    index_dir = _docs_index_dir(project_path)
    index_dir.mkdir(parents=True, exist_ok=True)

    chroma_dir = index_dir / "chroma"
    manifest = _load_manifest(index_dir)
    model_dim = embedder.dimensions()

    # Detect dimension mismatch and force rebuild
    stored_dim = manifest.get("_meta", {}).get("embedding_dim")
    if stored_dim and stored_dim != model_dim:
        logger.warning(
            "Docs dimension mismatch: index=%dd, model=%dd. Wiping and re-indexing.",
            stored_dim, model_dim,
        )
        force = True

    if force and chroma_dir.exists():
        ChromaStore.evict_cache(str(chroma_dir))
        shutil.rmtree(chroma_dir)
        manifest = {}

    docs_store = ChromaStore(persist_dir=str(chroma_dir))
    docs_store.create_collection(COLLECTION)

    doc_files = _scan_docs(project_path, paths)
    logger.info("Docs scan: found %d files in %s", len(doc_files), project_path)

    files_indexed = files_skipped = files_failed = total_chunks = 0
    start = time.time()

    for fp in doc_files:
        source = str(fp)
        try:
            content = fp.read_text(encoding="utf-8", errors="replace")
            content_hash = _content_hash(content)

            manifest_entry = manifest.get(source, {})
            if not force and manifest_entry.get("content_hash") == content_hash:
                files_skipped += 1
                continue

            raw_chunks = chunk_markdown(content, source_file=source)
            if not raw_chunks:
                logger.debug("No chunks from %s, skipping", source)
                files_skipped += 1
                continue

            docs_store.delete_by_source(COLLECTION, source)

            texts = [c.content for c in raw_chunks]
            embeddings = embedder.embed(texts)

            store_chunks = []
            for i, (raw, embedding) in enumerate(zip(raw_chunks, embeddings)):
                cid = chunk_id(source, i)
                meta = {
                    "source_file": source,
                    "scope": COLLECTION,
                    "section": raw.section,
                    "line_start": raw.line_start,
                    "line_end": raw.line_end,
                    "file_hash": content_hash,
                    "indexed_at": datetime.now(timezone.utc).isoformat(),
                    "chunk_index": i,
                    "token_count": raw.token_count_approx,
                    "format": "markdown",
                }
                store_chunks.append(Chunk(
                    id=cid,
                    content=raw.content,
                    embedding=embedding,
                    metadata=meta,
                ))

            added = docs_store.add_chunks(COLLECTION, store_chunks)
            total_chunks += added
            files_indexed += 1

            manifest[source] = {
                "chunk_count": added,
                "indexed_at": datetime.now(timezone.utc).isoformat(),
                "content_hash": content_hash,
            }

        except Exception as e:
            logger.error("Failed to index doc %s: %s", source, e, exc_info=True)
            files_failed += 1

    manifest["_meta"] = {"embedding_dim": model_dim}
    _save_manifest(index_dir, manifest)
    docs_store.close()

    elapsed_ms = int((time.time() - start) * 1000)
    logger.info(
        "Docs indexing complete: %d indexed, %d skipped, %d failed, %d chunks in %dms",
        files_indexed, files_skipped, files_failed, total_chunks, elapsed_ms,
    )

    return {
        "files_indexed": files_indexed,
        "files_skipped": files_skipped,
        "files_failed": files_failed,
        "chunks_created": total_chunks,
        "files_scanned": len(doc_files),
        "collection_path": str(index_dir),
        "elapsed_ms": elapsed_ms,
    }
