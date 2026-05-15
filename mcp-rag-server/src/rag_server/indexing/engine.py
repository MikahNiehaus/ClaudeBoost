"""Indexing engine. Orchestrates chunking, embedding, and storage."""

import json
import logging
import time
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

CODE_EXTENSIONS = {".py", ".js", ".jsx", ".ts", ".tsx", ".mjs"}  # legacy; project.py is authoritative


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

    def index_project(
        self,
        project_path: str,
        languages: list[str] | None = None,
        force: bool = False,
    ) -> dict:
        """Index an external project's source code into a per-project store.

        Creates a separate ChromaDB + manifest at <project_path>/workspace/.rag-index/.
        """
        import hashlib as _hashlib
        from rag_server.core.project import project_index_dir
        from rag_server.core.store import ChromaStore

        # Compute project ID from path only — avoids subprocess (git remote) which
        # hangs when called from a run_in_executor thread in the MCP server context.
        pid = _hashlib.sha256(
            str(Path(project_path).resolve()).encode("utf-8")
        ).hexdigest()[:12]

        index_dir = project_index_dir(project_path)
        index_dir.mkdir(parents=True, exist_ok=True)

        # Per-project vector store + graph store (separate from main ClaudeBoost index)
        project_store = ChromaStore(persist_dir=str(index_dir / "chroma"))
        from rag_server.adapters.sqlite_graph_store import SQLiteGraphStore
        graph_store = SQLiteGraphStore(index_dir / "graph.db")
        project_manifest_path = index_dir / "manifest.json"
        project_manifest = {}
        if not force and project_manifest_path.exists():
            project_manifest = json.loads(
                project_manifest_path.read_text(encoding="utf-8")
            )

        collection = "codebase"

        # Auto-detect embedding dimension mismatch (e.g. model swap nomic 768d → MiniLM 384d).
        # If the stored vectors don't match the current model, force a full re-index so
        # searches don't fail with dimension errors. Mirrors the same check in sync_init().
        if not force and project_store.collection_exists(collection) and project_store.count(collection) > 0:
            sample_dim = project_store.sample_dimension(collection)
            if sample_dim and sample_dim != self._embedder.dimensions():
                logger.warning(
                    "Dimension mismatch in project codebase: index=%dd, model=%dd. Forcing re-index.",
                    sample_dim, self._embedder.dimensions(),
                )
                force = True

        if force and project_store.collection_exists(collection):
            project_store.delete_collection(collection)
        project_store.create_collection(collection)

        # Scan project — respects .gitignore, filters generated/large files
        from rag_server.core.scanner import scan_project
        scan = scan_project(project_path, languages=languages)
        file_paths = scan.files
        lang_summary = ", ".join(f"{lang}:{n}" for lang, n in scan.files_by_language.items())
        logger.info(
            "Scan complete: %d files to index (%s). "
            "Skipped: %d gitignore, %d too-large, %d generated.",
            len(file_paths), lang_summary,
            scan.skipped_gitignore, scan.skipped_too_large, scan.skipped_generated,
        )

        project_root = Path(project_path).resolve()

        # Remove stale chunks for files that no longer exist on disk (e.g. deleted after
        # a branch switch). Scoped to the extensions included in this run so a
        # language-filtered run (e.g. "python only") doesn't evict chunks from a language
        # that wasn't part of this scan.
        if not force and project_manifest:
            from rag_server.core.project import ALL_CODE_EXTENSIONS, LANGUAGE_EXTENSIONS
            if languages:
                scoped_exts = set()
                for lang in languages:
                    scoped_exts |= LANGUAGE_EXTENSIONS.get(lang.lower(), set())
            else:
                scoped_exts = ALL_CODE_EXTENSIONS

            current_rel_paths = set()
            for fp in file_paths:
                try:
                    current_rel_paths.add(
                        str(Path(fp).relative_to(project_root)).replace("\\", "/")
                    )
                except ValueError:
                    current_rel_paths.add(fp.replace("\\", "/"))

            stale = [
                f for f in list(project_manifest)
                if Path(f).suffix in scoped_exts and f not in current_rel_paths
            ]
            if stale:
                logger.info("Removing %d stale file(s) from index (not found on disk).", len(stale))
                for f in stale:
                    project_store.delete_by_source(collection, f)
                    graph_store.delete_edges_for_file(f)
                    del project_manifest[f]

        files_indexed = 0
        chunks_created = 0
        files_skipped = 0
        start_time = time.time()

        for file_path in file_paths:
            # Relative path within the target project
            try:
                rel_path = str(
                    Path(file_path).relative_to(project_root)
                ).replace("\\", "/")
            except ValueError:
                rel_path = file_path.replace("\\", "/")

            try:
                content = Path(file_path).read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as e:
                logger.warning("Skipping %s: %s", rel_path, e)
                files_skipped += 1
                continue

            current_hash = file_hash(content)

            if not force and project_manifest.get(rel_path) == current_hash:
                files_skipped += 1
                continue

            project_store.delete_by_source(collection, rel_path)
            graph_store.delete_edges_for_file(rel_path)

            # Always use code chunker for project files
            from rag_server.indexing.code_chunker import chunk_code, extract_edges
            raw_chunks = chunk_code(
                content, rel_path,
                max_tokens=MAX_CHUNK_TOKENS,
                min_tokens=MIN_CHUNK_TOKENS,
            )
            if not raw_chunks:
                files_skipped += 1
                continue

            # Extract and store graph edges (import/inherit/calls)
            from rag_server.core.project import extension_to_language
            file_language = extension_to_language(Path(rel_path).suffix)
            if file_language:
                edges = extract_edges(content, file_language, rel_path)
                if edges:
                    graph_store.add_edges(edges)

            texts = [c.content for c in raw_chunks]
            embeddings = self._embedder.embed(texts)

            store_chunks = []
            for i, (raw, embedding) in enumerate(zip(raw_chunks, embeddings)):
                cid = chunk_id(rel_path, i)
                metadata = build_metadata(
                    source_file=rel_path,
                    scope="codebase",
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

            added = project_store.add_chunks(collection, store_chunks)
            chunks_created += added
            files_indexed += 1
            project_manifest[rel_path] = current_hash

            # Progress log every 25 files
            if files_indexed % 25 == 0:
                elapsed = time.time() - start_time
                rate = files_indexed / elapsed if elapsed > 0 else 0
                remaining = (len(file_paths) - files_indexed) / rate if rate > 0 else 0
                logger.info(
                    "Progress: %d/%d files (%.1f files/sec, ~%ds remaining)",
                    files_indexed, len(file_paths), rate, int(remaining),
                )

        # Save project manifest
        project_manifest_path.write_text(
            json.dumps(project_manifest, indent=2), encoding="utf-8",
        )

        logger.info(
            "Indexed project %s (%s): %d files, %d chunks (%d skipped)",
            pid, project_path, files_indexed, chunks_created, files_skipped,
        )
        return {
            "project_id": pid,
            "files_indexed": files_indexed,
            "chunks_created": chunks_created,
            "files_skipped": files_skipped,
            "index_path": str(index_dir),
        }

    def _chunk_file(self, content: str, rel_path: str):
        """Route to the right chunker based on file extension."""
        if Path(rel_path).suffix in CODE_EXTENSIONS:
            from rag_server.indexing.code_chunker import chunk_code
            return chunk_code(
                content, rel_path,
                max_tokens=MAX_CHUNK_TOKENS,
                min_tokens=MIN_CHUNK_TOKENS,
            )
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
