"""rag_index_research tool — builds a per-task research RAG from URLs and PDFs."""

import hashlib
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

from rag_server.core.metadata import chunk_id
from rag_server.indexing.markdown_chunker import estimate_tokens
from rag_server.ports.embedding_port import EmbeddingPort
from rag_server.ports.store_port import Chunk

logger = logging.getLogger(__name__)

COLLECTION = "research"


def _research_index_dir(workspace_path: str) -> Path:
    """Return the research index directory for a task workspace."""
    return Path(workspace_path).resolve() / ".rag-index" / "research"


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
    manifest_path = index_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def _content_hash(content: str | bytes) -> str:
    if isinstance(content, str):
        content = content.encode("utf-8")
    return hashlib.sha256(content).hexdigest()[:16]


def _is_pdf(source: str) -> bool:
    """Return True if source is a local PDF path or a PDF URL."""
    lower = source.lower().split("?")[0]
    return lower.endswith(".pdf")


def _is_url(source: str) -> bool:
    return source.startswith("http://") or source.startswith("https://")


def _build_metadata(
    source: str,
    section: str,
    chunk_index: int,
    token_count: int,
    fmt: str,
) -> dict:
    return {
        "source_file": source,
        "scope": "research",
        "section": section,
        "line_start": chunk_index,
        "line_end": chunk_index,
        "file_hash": "",  # set per-source after fetching
        "indexed_at": datetime.now(timezone.utc).isoformat(),
        "chunk_index": chunk_index,
        "token_count": token_count,
        "format": fmt,
    }


def rag_index_research(
    embedder: EmbeddingPort,
    sources: list[str],
    workspace_path: str,
    force: bool = False,
) -> dict:
    """Index a list of URLs/PDFs/local files into the per-task research collection.

    Args:
        embedder: Shared embedding model instance from the server.
        sources: List of URLs (web pages or PDFs) or absolute local file paths.
        workspace_path: Absolute path to the task workspace directory.
                        Research index is stored at workspace_path/.rag-index/research/.
        force: If True, re-index even if a source's content hash matches the manifest.

    Returns:
        Dict with indexed_count, source_results list, and collection_path.
    """
    # STOP: fail fast if model isn't loaded — avoids blocking on _load_lock.
    if not embedder.is_loaded:
        return {"error": "Embedding model not ready yet — retry in 30-60 seconds."}

    from rag_server.core.store import ChromaStore

    index_dir = _research_index_dir(workspace_path)
    index_dir.mkdir(parents=True, exist_ok=True)

    chroma_dir = index_dir / "chroma"
    research_store = ChromaStore(persist_dir=str(chroma_dir))

    manifest = _load_manifest(index_dir)

    if not research_store.collection_exists(COLLECTION):
        research_store.create_collection(COLLECTION)

    source_results = []
    total_chunks = 0
    start = time.time()

    for source in sources:
        result = _index_single_source(
            source=source,
            embedder=embedder,
            store=research_store,
            manifest=manifest,
            force=force,
        )
        source_results.append(result)
        if result["status"] == "ok":
            total_chunks += result["chunks"]

    _save_manifest(index_dir, manifest)

    elapsed_ms = int((time.time() - start) * 1000)
    logger.info(
        "Research indexing complete: %d sources, %d chunks in %dms",
        len(sources), total_chunks, elapsed_ms,
    )

    return {
        "indexed_count": total_chunks,
        "sources_indexed": sum(1 for r in source_results if r["status"] == "ok"),
        "sources_skipped": sum(1 for r in source_results if r["status"] == "skipped"),
        "sources_failed": sum(1 for r in source_results if r["status"] == "error"),
        "sources": source_results,
        "collection_path": str(index_dir),
        "elapsed_ms": elapsed_ms,
    }


def _index_single_source(
    source: str,
    embedder: EmbeddingPort,
    store,
    manifest: dict,
    force: bool,
) -> dict:
    """Index one source (URL, PDF URL, or local file path) into the research store."""
    try:
        # Determine source type and fetch chunks
        if _is_url(source):
            if _is_pdf(source):
                from rag_server.indexing.pdf_chunker import chunk_pdf_url
                raw_chunks = chunk_pdf_url(source)
                fmt = "pdf"
            else:
                from rag_server.indexing.url_chunker import chunk_url, fetch_url, is_pdf_url
                # Peek at content-type first to handle URLs that redirect to PDF
                raw_content, content_type = fetch_url(source)
                if not raw_content:
                    return {"source": source, "status": "error", "chunks": 0,
                            "error": "unreachable or empty", "format": "unknown"}

                if is_pdf_url(source, content_type):
                    from rag_server.indexing.pdf_chunker import chunk_pdf_bytes
                    if isinstance(raw_content, bytes):
                        raw_chunks = chunk_pdf_bytes(raw_content, source_id=source)
                        fmt = "pdf"
                    else:
                        raw_chunks = []
                        fmt = "pdf"
                else:
                    # HTML page — re-use fetched content
                    from rag_server.indexing.url_chunker import extract_text, _chunk_markdown_text
                    if isinstance(raw_content, bytes):
                        raw_content = raw_content.decode("utf-8", errors="replace")
                    title, markdown = extract_text(raw_content, source)
                    raw_chunks = _chunk_markdown_text(markdown, source_url=source, title=title)
                    fmt = "html"
        else:
            # Local file path
            path = Path(source)
            if not path.exists():
                return {"source": source, "status": "error", "chunks": 0,
                        "error": f"file not found: {source}", "format": "unknown"}

            if path.suffix.lower() == ".pdf":
                from rag_server.indexing.pdf_chunker import chunk_pdf_file
                raw_chunks = chunk_pdf_file(str(path), source_url=source)
                fmt = "pdf"
            elif path.suffix.lower() in {".md", ".txt"}:
                from rag_server.indexing.markdown_chunker import chunk_markdown
                content = path.read_text(encoding="utf-8")
                raw_chunks = chunk_markdown(content, source)
                fmt = "text"
            else:
                return {"source": source, "status": "error", "chunks": 0,
                        "error": f"unsupported file type: {path.suffix}", "format": "unknown"}

        if not raw_chunks:
            return {"source": source, "status": "error", "chunks": 0,
                    "error": "no content extracted (page may be blocked or empty)", "format": fmt}

        # Compute content hash for incremental support
        combined = "".join(c.content for c in raw_chunks)
        content_hash = _content_hash(combined)

        manifest_entry = manifest.get(source, {})
        if not force and manifest_entry.get("content_hash") == content_hash:
            return {"source": source, "status": "skipped", "chunks": manifest_entry.get("chunk_count", 0),
                    "format": fmt, "reason": "content unchanged"}

        # Delete old chunks for this source before re-indexing
        store.delete_by_source(COLLECTION, source)

        # Embed all chunks in one batch
        texts = [c.content for c in raw_chunks]
        embeddings = embedder.embed(texts)

        store_chunks = []
        for i, (raw, embedding) in enumerate(zip(raw_chunks, embeddings)):
            cid = chunk_id(source, i)
            meta = _build_metadata(
                source=source,
                section=raw.section,
                chunk_index=i,
                token_count=raw.token_count_approx,
                fmt=fmt,
            )
            meta["file_hash"] = content_hash
            store_chunks.append(Chunk(
                id=cid,
                content=raw.content,
                embedding=embedding,
                metadata=meta,
            ))

        added = store.add_chunks(COLLECTION, store_chunks)

        manifest[source] = {
            "chunk_count": added,
            "indexed_at": datetime.now(timezone.utc).isoformat(),
            "content_hash": content_hash,
            "format": fmt,
        }

        if added < 5:
            logger.warning(
                "Only %d chunks from %s — content may be sparse or blocked", added, source
            )

        return {"source": source, "status": "ok", "chunks": added, "format": fmt}

    except Exception as e:
        logger.error("Failed to index %s: %s", source, e, exc_info=True)
        return {"source": source, "status": "error", "chunks": 0, "error": str(e), "format": "unknown"}
