"""Indexing engine. Orchestrates chunking, embedding, and storage."""

import json
import logging
from glob import glob
from pathlib import Path

from rag_server.config import (
    MANIFEST_PATH,
    MAX_CHUNK_TOKENS,
    MIN_CHUNK_TOKENS,
    PROJECT_ROOT,
    SCOPES,
)
from rag_server.core.metadata import build_metadata, chunk_id, file_hash
from rag_server.indexing.markdown_chunker import chunk_markdown
from rag_server.ports.embedding_port import EmbeddingPort
from rag_server.ports.store_port import Chunk, StorePort

logger = logging.getLogger(__name__)


class IndexingEngine:
    """Indexes files into the vector store with incremental support."""

    def __init__(self, embedder: EmbeddingPort, store: StorePort):
        self._embedder = embedder
        self._store = store
        self._manifest = self._load_manifest()

    def _load_manifest(self) -> dict:
        """Load file hash manifest for incremental indexing."""
        if MANIFEST_PATH.exists():
            return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        return {}

    def _save_manifest(self) -> None:
        MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
        MANIFEST_PATH.write_text(
            json.dumps(self._manifest, indent=2),
            encoding="utf-8",
        )

    def index_scope(self, scope: str, force: bool = False) -> dict:
        """Index a predefined scope (knowledge, agents).

        Returns dict with files_indexed, chunks_created, files_skipped.
        """
        if scope not in SCOPES:
            raise ValueError(f"Unknown scope: {scope}. Valid: {list(SCOPES.keys())}")

        scope_config = SCOPES[scope]
        collection = scope_config["collection"]

        # If force and collection exists, drop it first to handle dimension changes
        # (e.g. switching from 384d to 768d embedding model)
        if force and self._store.collection_exists(collection):
            self._store.delete_collection(collection)
            logger.info("Dropped collection %s for clean re-index", collection)

        self._store.create_collection(collection)

        files = []
        for pattern in scope_config["patterns"]:
            matched = glob(str(PROJECT_ROOT / pattern), recursive=False)
            files.extend(matched)

        return self._index_files(files, collection, scope, force)

    def index_all(self, force: bool = False) -> dict:
        """Index all predefined scopes."""
        total = {"files_indexed": 0, "chunks_created": 0, "files_skipped": 0}
        for scope in SCOPES:
            result = self.index_scope(scope, force)
            total["files_indexed"] += result["files_indexed"]
            total["chunks_created"] += result["chunks_created"]
            total["files_skipped"] += result["files_skipped"]
        self._save_manifest()
        return total

    def _index_files(
        self, file_paths: list[str], collection: str, scope: str, force: bool
    ) -> dict:
        files_indexed = 0
        chunks_created = 0
        files_skipped = 0

        for file_path in file_paths:
            rel_path = self._relative_path(file_path)

            try:
                content = Path(file_path).read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as e:
                logger.warning("Skipping %s: %s", rel_path, e)
                files_skipped += 1
                continue

            current_hash = file_hash(content)

            # Incremental: skip if unchanged
            if not force and self._manifest.get(rel_path) == current_hash:
                files_skipped += 1
                continue

            # Delete old chunks for this file
            self._store.delete_by_source(collection, rel_path)

            # Chunk the file
            raw_chunks = self._chunk_file(content, rel_path)
            if not raw_chunks:
                files_skipped += 1
                continue

            # Embed all chunks in one batch
            texts = [c.content for c in raw_chunks]
            embeddings = self._embedder.embed(texts)

            # Build storage chunks
            store_chunks = []
            for i, (raw, embedding) in enumerate(zip(raw_chunks, embeddings)):
                cid = chunk_id(rel_path, i)
                metadata = build_metadata(
                    source_file=rel_path,
                    scope=scope,
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

            added = self._store.add_chunks(collection, store_chunks)
            chunks_created += added
            files_indexed += 1

            # Update manifest
            self._manifest[rel_path] = current_hash

        self._save_manifest()
        logger.info(
            "Indexed %s: %d files, %d chunks (%d skipped)",
            collection, files_indexed, chunks_created, files_skipped,
        )
        return {
            "files_indexed": files_indexed,
            "chunks_created": chunks_created,
            "files_skipped": files_skipped,
        }

    def _chunk_file(self, content: str, rel_path: str):
        """Route to the right chunker based on file extension."""
        if rel_path.endswith(".xml"):
            from rag_server.indexing.xml_chunker import chunk_xml
            return chunk_xml(
                content, rel_path,
                max_tokens=MAX_CHUNK_TOKENS,
                min_tokens=MIN_CHUNK_TOKENS,
            )
        if rel_path.endswith(".md"):
            return chunk_markdown(
                content, rel_path,
                max_tokens=MAX_CHUNK_TOKENS,
                min_tokens=MIN_CHUNK_TOKENS,
            )
        # Unsupported file type — skip
        return []

    def _relative_path(self, file_path: str) -> str:
        """Convert absolute path to relative (forward slashes)."""
        try:
            return str(Path(file_path).relative_to(PROJECT_ROOT)).replace("\\", "/")
        except ValueError:
            return file_path.replace("\\", "/")
