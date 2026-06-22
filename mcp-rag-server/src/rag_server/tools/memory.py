"""rag_index_memories — index the file-based memory system into the memories collection."""

import hashlib
import logging
import time
from pathlib import Path

from rag_server.ports.embedding_port import EmbeddingPort
from rag_server.ports.store_port import StorePort

logger = logging.getLogger(__name__)

COLLECTION = "memories"


def _chunk_memory_file(path: Path) -> list[dict]:
    """Read a memory markdown file and return chunks with metadata."""
    try:
        text = path.read_text(encoding="utf-8")
    except Exception as e:
        logger.warning("Could not read memory file %s: %s", path, e)
        return []

    if not text.strip():
        return []

    # Extract frontmatter fields (name, description, type)
    name = path.stem
    description = ""
    mem_type = "unknown"
    body_lines = []
    in_frontmatter = False
    past_frontmatter = False

    for i, line in enumerate(text.splitlines()):
        if i == 0 and line.strip() == "---":
            in_frontmatter = True
            continue
        if in_frontmatter and line.strip() == "---":
            in_frontmatter = False
            past_frontmatter = True
            continue
        if in_frontmatter:
            if line.startswith("name:"):
                name = line.split(":", 1)[1].strip().strip('"')
            elif line.startswith("description:"):
                description = line.split(":", 1)[1].strip().strip('"')
            elif line.startswith("  type:") or line.startswith("type:"):
                mem_type = line.split(":", 1)[1].strip()
        else:
            body_lines.append(line)

    body = "\n".join(body_lines).strip()
    if not body:
        return []

    content = f"[{mem_type}] {name}: {description}\n\n{body}" if description else f"[{mem_type}] {name}\n\n{body}"

    return [{
        "content": content,
        "source": str(path.name),
        "name": name,
        "mem_type": mem_type,
        "description": description,
    }]


def rag_index_memories(
    embedder: EmbeddingPort,
    store: StorePort,
    memory_dir: Path,
    force: bool = False,
) -> dict:
    """Index the file-based memory system into the memories collection.

    Reads all *.md files in memory_dir (skipping MEMORY.md index file).
    Incremental: re-indexes only files whose content has changed.
    """
    if not embedder.is_loaded:
        return {"error": "Embedding model not ready yet — retry in 30-60 seconds."}

    if not memory_dir or not memory_dir.exists():
        return {
            "error": f"Memory directory not found: {memory_dir}. "
                     "Set RAG_MEMORY_DIR env var or ensure CLAUDEBOOST_HOME is set."
        }

    # When force=True, drop the collection first so a model swap (e.g. 384d → 768d)
    # doesn't leave a stale schema that rejects the new-dimension embeddings.
    if force and store.collection_exists(COLLECTION):
        store.delete_collection(COLLECTION)
        logger.info("Dropped memories collection for clean re-index (force=True)")

    if not store.collection_exists(COLLECTION):
        store.create_collection(COLLECTION)

    # Load existing manifest (source_file -> content_hash)
    manifest: dict[str, str] = {}
    if not force and store.collection_exists(COLLECTION):
        try:
            col = store._get_collection(COLLECTION)
            results = col.get(include=["metadatas"])
            for m in results.get("metadatas") or []:
                src = m.get("source_file", "")
                ch = m.get("content_hash", "")
                if src and ch:
                    manifest[src] = ch
        except Exception:
            pass  # start fresh if manifest read fails

    memory_files = [
        p for p in memory_dir.glob("*.md")
        if p.name.upper() != "MEMORY.MD"
    ]

    indexed = 0
    skipped = 0
    failed = 0
    start = time.time()

    from rag_server.indexing.engine import chunk_id, build_metadata
    from rag_server.ports.store_port import Chunk

    for path in memory_files:
        chunks_data = _chunk_memory_file(path)
        if not chunks_data:
            continue

        content = chunks_data[0]["content"]
        content_hash = hashlib.sha256(content.encode()).hexdigest()[:16]
        source_key = path.name

        if not force and manifest.get(source_key) == content_hash:
            skipped += 1
            continue

        store.delete_by_source(COLLECTION, source_key)

        try:
            embeddings = embedder.embed([content])
            from rag_server.indexing.engine import build_metadata as _bm
            meta = {
                "source_file": source_key,
                "scope": COLLECTION,
                "section": chunks_data[0]["name"],
                "mem_type": chunks_data[0]["mem_type"],
                "content_hash": content_hash,
                "chunk_index": 0,
                "token_count": len(content.split()),
                "line_start": 0,
                "line_end": 0,
            }
            cid = f"mem_{hashlib.sha256(source_key.encode()).hexdigest()[:12]}_0"
            store.add_chunks(COLLECTION, [Chunk(
                id=cid,
                content=content,
                embedding=embeddings[0],
                metadata=meta,
            )])
            indexed += 1
        except Exception as e:
            logger.error("Failed to embed memory %s: %s", path.name, e)
            failed += 1

    elapsed_ms = int((time.time() - start) * 1000)
    total = store.count(COLLECTION) if store.collection_exists(COLLECTION) else 0

    return {
        "indexed": indexed,
        "skipped": skipped,
        "failed": failed,
        "total_in_collection": total,
        "memory_dir": str(memory_dir),
        "elapsed_ms": elapsed_ms,
    }
