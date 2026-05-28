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
    RAG_INDEX_DIR,
    SCOPES,
)
from rag_server.core.metadata import build_metadata, chunk_id, file_hash
from rag_server.indexing.markdown_chunker import chunk_markdown
from rag_server.ports.embedding_port import EmbeddingPort
from rag_server.ports.store_port import Chunk, StorePort

logger = logging.getLogger(__name__)

MANIFEST_VERSION = 2


def _find_go_modules(project_path: str) -> dict[str, str]:
    """Find all go.mod files and return {mod_dir → module_name}.

    mod_dir is the directory containing go.mod, as a forward-slash project-relative path
    (empty string "" means the project root itself).  Skips vendor/, testdata/, .git/.
    """
    import re as _re
    result: dict[str, str] = {}
    root = Path(project_path)
    try:
        go_mods = sorted(root.rglob("go.mod"))
    except (OSError, RecursionError):
        return result
    for go_mod in go_mods:
        try:
            rel_parts = go_mod.relative_to(root).parts
        except ValueError:
            continue
        if any(p in {"vendor", "testdata", ".git", "node_modules"} for p in rel_parts):
            continue
        if len(rel_parts) > 5:  # don't recurse too deep
            continue
        try:
            text = go_mod.read_text(encoding="utf-8")
            m = _re.search(r"^module\s+(\S+)", text, _re.MULTILINE)
            if m:
                mod_dir = "/".join(rel_parts[:-1])  # drop "go.mod" filename; "" = root
                result[mod_dir] = m.group(1)
        except OSError:
            continue
    return result


def _build_file_map(rel_paths: list[str], go_modules: dict[str, str] | None = None) -> dict[str, str]:
    """Build a lookup table from module-name variants to project-relative file paths.

    For each indexed file we generate the key forms that might appear in import statements:
    - Python: "foo/bar.py" → keys "foo.bar", "foo/bar", "foo/bar.py"
    - Python __init__: "foo/bar/__init__.py" → keys "foo/bar", "foo.bar"
    - JS/TS: "foo/bar.ts" → keys "foo/bar", "foo.bar"
    - JS/TS index: "foo/index.ts" → keys "foo", "foo/index"
    - Go: "gastown/internal/cmd/server.go" → keys "internal/cmd", "github.com/x/gastown/internal/cmd"

    **Suffix keys for src-layout projects**: for Python and JS/TS files, we also
    generate keys for every trailing sub-path, so that a file at
    "mcp-rag-server/src/rag_server/ports/graph_port.py" matches the import
    "rag_server.ports.graph_port" (which starts mid-path). First-wins on collision
    (deeper/more-specific paths are registered first, then broader suffix keys fill
    gaps only if no more-specific key already claimed the slot).

    Returns a dict mapping each key to the canonical rel_path.
    """
    file_map: dict[str, str] = {}

    # Pass 1: full-path keys (most specific — registered first, never overwritten).
    for rel_path in rel_paths:
        p = Path(rel_path)
        suffix = p.suffix.lower()
        stem = p.stem
        no_ext = rel_path[: -len(suffix)] if suffix else rel_path
        parts = no_ext.split("/")  # forward-slash normalised

        if suffix == ".py":
            if stem == "__init__":
                pkg_slash = "/".join(parts[:-1])  # drop "__init__" component
                if pkg_slash:
                    file_map.setdefault(pkg_slash, rel_path)
                    file_map.setdefault(pkg_slash.replace("/", "."), rel_path)
            else:
                file_map.setdefault(no_ext, rel_path)
                file_map.setdefault(no_ext.replace("/", "."), rel_path)
                file_map.setdefault(rel_path, rel_path)
        elif suffix in {".js", ".jsx", ".ts", ".tsx", ".mjs"}:
            if stem in {"index", "index.d"}:
                parent_slash = "/".join(parts[:-1])
                if parent_slash:
                    file_map.setdefault(parent_slash, rel_path)
                file_map.setdefault(no_ext, rel_path)
            else:
                file_map.setdefault(no_ext, rel_path)
                file_map.setdefault(no_ext.replace("/", "."), rel_path)
        elif suffix == ".go":
            # Go packages are identified by directory, not individual files.
            # Register the parent directory as the key — first .go file in the dir wins.
            parent_slash = "/".join(parts[:-1])
            if parent_slash:
                file_map.setdefault(parent_slash, rel_path)
            if go_modules:
                # Find the go.mod that governs this file (longest matching mod_dir prefix).
                best_mod_dir = None
                best_len = -1
                for mod_dir, module_name in go_modules.items():
                    if mod_dir == "":
                        if best_len < 0:
                            best_mod_dir = mod_dir
                            best_len = 0
                    elif rel_path.startswith(mod_dir + "/") and len(mod_dir) > best_len:
                        best_mod_dir = mod_dir
                        best_len = len(mod_dir)
                if best_mod_dir is not None:
                    module_name = go_modules[best_mod_dir]
                    # Package import path = module_name + "/" + path-within-module
                    if best_mod_dir:
                        # e.g. rel_path = "gastown/internal/cmd/server.go"
                        #      best_mod_dir = "gastown", parent_slash = "gastown/internal/cmd"
                        within_module = parent_slash[len(best_mod_dir):].lstrip("/")
                    else:
                        within_module = parent_slash
                    if within_module:
                        import_path = f"{module_name}/{within_module}"
                    else:
                        import_path = module_name
                    file_map.setdefault(import_path, rel_path)
        elif suffix in {".cs", ".cshtml"}:
            # C# namespace key: convert path separators to dots.
            # ViveryAscend.Core/Services/AgencyService.cs →
            #   "ViveryAscend.Core.Services.AgencyService"  (full class key)
            #   "ViveryAscend.Core.Services"               (namespace/dir key, first file wins)
            dot_full = no_ext.replace("/", ".")
            file_map.setdefault(dot_full, rel_path)
            if len(parts) > 1:
                dir_dot = ".".join(parts[:-1])
                file_map.setdefault(dir_dot, rel_path)
        else:
            file_map.setdefault(rel_path, rel_path)
            file_map.setdefault(no_ext, rel_path)

    # Pass 2: suffix keys for src-layout / sub-package imports.
    # For "a/b/c/d.py" add "b/c/d", "c/d", "d" (slash + dotted) only if slot is empty.
    for rel_path in rel_paths:
        p = Path(rel_path)
        suffix = p.suffix.lower()
        stem = p.stem
        no_ext = rel_path[: -len(suffix)] if suffix else rel_path
        parts = no_ext.split("/")

        if suffix == ".py":
            if stem == "__init__":
                pkg_parts = parts[:-1]  # drop "__init__"
                for start in range(1, len(pkg_parts)):
                    sub = "/".join(pkg_parts[start:])
                    if sub:
                        file_map.setdefault(sub, rel_path)
                        file_map.setdefault(sub.replace("/", "."), rel_path)
            else:
                for start in range(1, len(parts)):
                    sub = "/".join(parts[start:])
                    if sub:
                        file_map.setdefault(sub, rel_path)
                        file_map.setdefault(sub.replace("/", "."), rel_path)
        elif suffix in {".js", ".jsx", ".ts", ".tsx", ".mjs"}:
            if stem in {"index", "index.d"}:
                pkg_parts = parts[:-1]
                for start in range(1, len(pkg_parts)):
                    sub = "/".join(pkg_parts[start:])
                    if sub:
                        file_map.setdefault(sub, rel_path)
            else:
                for start in range(1, len(parts)):
                    sub = "/".join(parts[start:])
                    if sub:
                        file_map.setdefault(sub, rel_path)
                        file_map.setdefault(sub.replace("/", "."), rel_path)
        elif suffix in {".cs", ".cshtml"}:
            # Suffix variants: "Core.Services.AgencyService", "Services.AgencyService", etc.
            for start in range(1, len(parts)):
                sub_parts = parts[start:]
                sub = ".".join(sub_parts)
                if sub:
                    file_map.setdefault(sub, rel_path)
                if len(sub_parts) > 1:
                    dir_sub = ".".join(sub_parts[:-1])
                    if dir_sub:
                        file_map.setdefault(dir_sub, rel_path)

    return file_map


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

    def _index_scope_impl(self, scope: str, force: bool = False) -> dict:
        """Index a predefined scope (knowledge, agents). Caller must hold write lock.

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

    def index_scope(self, scope: str, force: bool = False) -> dict:
        """Index a predefined scope (acquires write lock)."""
        from rag_server.core.locking import index_write_lock
        with index_write_lock(RAG_INDEX_DIR / "index.lock"):
            return self._index_scope_impl(scope, force)

    def index_all(self, force: bool = False) -> dict:
        """Index all predefined scopes (acquires write lock once for the full run)."""
        from rag_server.core.locking import index_write_lock
        total = {"files_indexed": 0, "chunks_created": 0, "files_skipped": 0}
        with index_write_lock(RAG_INDEX_DIR / "index.lock"):
            for scope in SCOPES:
                result = self._index_scope_impl(scope, force)
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
        """Index an external project's source code. Acquires write lock.

        Creates a separate ChromaDB + manifest at <project_path>/workspace/.rag-index/.
        """
        import hashlib as _hashlib
        from rag_server.core.locking import index_write_lock
        from rag_server.core.project import project_index_dir

        # Compute project ID from path only — avoids subprocess (git remote) which
        # hangs when called from a run_in_executor thread in the MCP server context.
        pid = _hashlib.sha256(
            str(Path(project_path).resolve()).encode("utf-8")
        ).hexdigest()[:12]

        index_dir = project_index_dir(project_path)
        index_dir.mkdir(parents=True, exist_ok=True)

        with index_write_lock(index_dir / "index.lock"):
            return self._do_index_project(project_path, languages, force, pid, index_dir)

    def _do_index_project(
        self,
        project_path: str,
        languages: list[str] | None,
        force: bool,
        pid: str,
        index_dir: Path,
    ) -> dict:
        """Internal: index a project. Caller holds write lock."""
        from rag_server.core.store import ChromaStore

        # Per-project vector store + graph store (separate from main ClaudeBoost index)
        project_store = ChromaStore(persist_dir=str(index_dir / "chroma"))
        from rag_server.adapters.sqlite_graph_store import SQLiteGraphStore
        graph_store = SQLiteGraphStore(index_dir / "graph.db")
        project_manifest_path = index_dir / "manifest.json"
        project_manifest = {}
        stored_version = MANIFEST_VERSION
        if not force and project_manifest_path.exists():
            raw = json.loads(project_manifest_path.read_text(encoding="utf-8"))
            project_manifest = {k: v for k, v in raw.items() if k != "__schema_version__"}
            stored_version = raw.get("__schema_version__", 1)

        collection = "codebase"

        # Health check: detect broken/stale index before scanning
        if not force:
            health_issues = self._check_project_health(
                index_dir, project_store, graph_store, project_manifest, stored_version
            )
            if health_issues:
                return {
                    "project_id": pid,
                    "needs_reindex": True,
                    "health_issues": health_issues,
                    "suggestion": "Run rag_index_project with force=True to rebuild cleanly, or pass force=True to continue anyway.",
                }

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
            try:
                project_store.delete_collection(collection)
            except Exception as e:
                logger.error("Failed to drop collection for re-index: %s", e)
                return {"error": f"Re-index aborted: could not drop collection: {e}"}
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
                    try:
                        graph_store.add_edges(edges)
                    except Exception as e:
                        logger.warning("Graph edge add failed for %s: %s", rel_path, e)

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

        # Resolve graph edge target_files now that all files are indexed.
        # Edges are stored with target_file="" during the loop because we process
        # one file at a time and can't know where an import target lives until
        # the full manifest is complete. This pass fills them in.
        # Build file_map from the full manifest so historical files can still be resolved,
        # but validate resolved targets against the current scan to avoid ghost edges.
        go_modules = _find_go_modules(project_path)
        if go_modules:
            logger.info(
                "Go modules found: %s",
                ", ".join(f"{d or '(root)'}={n}" for d, n in go_modules.items()),
            )
        all_rel_paths = list(project_manifest.keys())
        file_map = _build_file_map(all_rel_paths, go_modules=go_modules)
        go_module_prefixes = set(go_modules.values()) if go_modules else None
        resolved_count = None
        try:
            resolved_count = graph_store.resolve_target_files(
                file_map, go_module_prefixes=go_module_prefixes
            )
            if resolved_count:
                logger.info("Graph edge resolution: %d target_file entries resolved", resolved_count)
        except Exception as e:
            logger.error("Graph edge resolution failed: %s", e)
            resolved_count = 0

        # Prune ghost edges: remove edges whose resolved target_file is no longer in the manifest
        try:
            current_files = set(project_manifest.keys())
            graph_store.delete_ghost_edges(current_files)
        except Exception as e:
            logger.warning("Ghost edge pruning failed: %s", e)

        # Community detection + summaries (optional deps — never blocks indexing).
        if files_indexed > 0 and graph_store.has_graph():
            try:
                from rag_server.core.community import detect_communities
                from rag_server.core.summarizer import summarize_community

                communities = detect_communities(graph_store)
                if communities:
                    graph_store.save_communities(communities)
                    num_communities = len(set(communities.values()))
                    logger.info(
                        "Community detection: %d files in %d communities",
                        len(communities), num_communities,
                    )
                    for cid in graph_store.get_all_community_ids():
                        members = graph_store.get_community_members(cid)
                        try:
                            summarize_community(cid, members, graph_store, project_path)
                        except Exception:
                            logger.exception(
                                "Community summary failed for community %d", cid
                            )
            except ImportError:
                logger.debug("Community detection modules not available — skipping")
            except Exception:
                logger.exception("Community detection failed unexpectedly")
                # don't re-raise — community detection is non-critical

        # Save project manifest (C3: include schema version)
        try:
            manifest_to_write = {"__schema_version__": MANIFEST_VERSION, **project_manifest}
            project_manifest_path.write_text(
                json.dumps(manifest_to_write, indent=2), encoding="utf-8",
            )
        except OSError as e:
            logger.error("Failed to write project manifest to %s: %s", project_manifest_path, e)

        logger.info(
            "Indexed project %s (%s): %d files, %d chunks (%d skipped)",
            pid, project_path, files_indexed, chunks_created, files_skipped,
        )

        # Register project in global registry so rag_status can surface graph state
        # to any new Claude instance without requiring a project-specific query.
        try:
            import datetime
            registry_path = MANIFEST_PATH.parent / "projects.json"
            registry: dict = {}
            if registry_path.exists():
                registry = json.loads(registry_path.read_text(encoding="utf-8"))
            edge_count = graph_store.count_edges()
            resolved = graph_store.count_resolved_edges()
            registry[pid] = {
                "project_path": project_path,
                "indexed_at": datetime.datetime.utcnow().isoformat() + "Z",
                "files_indexed": files_indexed,
                "chunks_created": chunks_created,
                "graph_edges": edge_count,
                "graph_resolved": resolved,
                "graph_active": edge_count > 0 and resolved > 0,
            }
            registry_path.write_text(json.dumps(registry, indent=2), encoding="utf-8")
        except Exception as e:
            logger.warning("Failed to write project registry: %s", e)

        return {
            "project_id": pid,
            "files_indexed": files_indexed,
            "chunks_created": chunks_created,
            "files_skipped": files_skipped,
            "index_path": str(index_dir),
        }

    def _check_project_health(
        self, index_dir, project_store, graph_store, project_manifest, stored_version
    ) -> list[str]:
        """Check for signs of a broken or stale project index.

        Returns a list of issue strings. Empty list means healthy.
        """
        issues = []
        if stored_version < MANIFEST_VERSION:
            issues.append(
                f"manifest schema v{stored_version} < current v{MANIFEST_VERSION} (schema changed)"
            )
        if project_store.collection_exists("codebase"):
            manifest_count = len(project_manifest)
            chroma_count = project_store.count("codebase")
            if manifest_count > 0 and chroma_count == 0:
                issues.append(
                    "manifest has entries but codebase collection is empty (index may be corrupt)"
                )
            elif manifest_count > 0 and chroma_count < manifest_count * 0.5:
                issues.append(
                    f"codebase collection has {chroma_count} chunks but manifest has "
                    f"{manifest_count} files (possible partial index)"
                )
        if graph_store.has_graph():
            try:
                current_files = set(project_manifest.keys())
                ghost_count = graph_store.count_ghost_edges(current_files)
                if ghost_count > 10:
                    issues.append(
                        f"{ghost_count} ghost edges pointing to files no longer in manifest"
                    )
                unresolved = graph_store.count_unresolved_edges()
                total = graph_store.count_edges() if hasattr(graph_store, 'count_edges') else None
                if total and total > 0:
                    unresolved_pct = unresolved / total * 100
                    if unresolved_pct > 50:
                        issues.append(
                            f"{unresolved_pct:.0f}% of graph edges unresolved "
                            f"({unresolved}/{total}) — import resolution may have failed"
                        )
            except Exception as e:
                logger.debug("Graph health check skipped due to error: %s", e)
        return issues

    def check_project_health(self, project_path: str) -> list[str]:
        """Run health checks on a previously-indexed project without re-indexing.

        Returns a list of issue strings. Empty list means healthy.
        Called by rag_status to surface problems without requiring a re-index run.
        """
        from rag_server.adapters.sqlite_graph_store import SQLiteGraphStore
        from rag_server.core.project import project_index_dir
        from rag_server.core.store import ChromaStore

        index_dir = project_index_dir(project_path)
        if not index_dir.exists():
            return ["project index directory not found — run rag_index_project first"]

        project_store = ChromaStore(persist_dir=str(index_dir / "chroma"))
        graph_store = SQLiteGraphStore(index_dir / "graph.db")

        manifest_path = index_dir / "manifest.json"
        project_manifest: dict = {}
        stored_version = MANIFEST_VERSION
        if manifest_path.exists():
            try:
                raw = json.loads(manifest_path.read_text(encoding="utf-8"))
                project_manifest = {k: v for k, v in raw.items() if k != "__schema_version__"}
                stored_version = raw.get("__schema_version__", 1)
            except Exception as e:
                return [f"manifest read failed: {e}"]

        return self._check_project_health(
            index_dir, project_store, graph_store, project_manifest, stored_version
        )

    def _chunk_file(self, content: str, rel_path: str):
        """Route to the right chunker based on file extension."""
        from rag_server.core.project import extension_to_language
        from rag_server.indexing.code_chunker import chunk_code
        if extension_to_language(Path(rel_path).suffix):
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
