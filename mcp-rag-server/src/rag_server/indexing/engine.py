"""Indexing engine. Orchestrates chunking, embedding, and storage."""

import json
import logging
import time
from glob import glob
from pathlib import Path

from rag_server.config import (
    CHUNK_OVERLAP_TOKENS,
    DEGENERATE_CHUNK_MIN_TOKENS,
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

MANIFEST_VERSION = 3

# Module-level progress state — updated live by _index_files and _do_index_project.
# Read via GET /index/progress without any locking; values are ints/strings so
# individual reads are atomic on CPython (GIL). Callers should treat the snapshot
# as advisory (file counts can shift slightly under concurrent requests).
_progress: dict = {
    "active": False,
    "phase": "idle",
    "files_total": 0,
    "files_done": 0,
    "files_indexed": 0,
    "chunks_created": 0,
    "files_skipped": 0,
    "files_failed": 0,
    "pct": 0,
    "current_file": None,
    "started_at": None,
    "elapsed_s": 0.0,
    "eta_s": None,
}


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

        # Scopes with no file patterns are managed by dedicated indexers (e.g. rag_index_memories).
        # Skip them here so force=True doesn't wipe their collection.
        if not scope_config["patterns"]:
            return {"files_indexed": 0, "chunks_created": 0, "files_unchanged": 0, "files_failed": 0}

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
        total: dict = {
            "files_indexed": 0,
            "chunks_created": 0,
            "files_unchanged": 0,
            "files_failed": 0,
        }
        all_errors: list[dict] = []
        with index_write_lock(RAG_INDEX_DIR / "index.lock"):
            for scope in SCOPES:
                result = self._index_scope_impl(scope, force)
                total["files_indexed"] += result["files_indexed"]
                total["chunks_created"] += result["chunks_created"]
                total["files_unchanged"] += result.get("files_unchanged", 0)
                total["files_failed"] += result.get("files_failed", 0)
                all_errors.extend(result.get("errors", []))
            self._save_manifest()
            # Build category-based graph over knowledge/agents files and run
            # community detection. Runs after all scopes so the full file list
            # is in the manifest. Non-critical — never blocks the index result.
            community_stats: dict = {"communities": 0, "summaries_generated": 0, "summaries_failed": 0}
            if total["files_indexed"] > 0 or total["files_unchanged"] > 0:
                try:
                    community_stats = self._build_knowledge_communities()
                except Exception:
                    logger.error("Knowledge community detection failed", exc_info=True)
                    community_stats["summaries_failed"] = -1  # signals total failure
        if all_errors:
            total["errors"] = all_errors
        total["communities"] = community_stats
        # Summaries run in background — log that they're pending so callers know to check later.
        if community_stats.get("communities", 0) > 0 and community_stats.get("summaries_generated") == "pending":
            logger.info(
                "Community summaries running in background — check server logs in ~60s "
                "to confirm all %d communities got summaries.",
                community_stats["communities"],
            )
        return total

    def _index_files(
        self, file_paths: list[str], collection: str, scope: str, force: bool
    ) -> dict:
        files_indexed = 0
        chunks_created = 0
        files_unchanged = 0
        files_failed = 0
        file_errors: list[dict] = []

        _total = len(file_paths)
        _start = time.monotonic()
        _progress.update({
            "active": True, "phase": scope,
            "files_total": _total, "files_done": 0,
            "files_indexed": 0, "chunks_created": 0,
            "files_skipped": 0, "files_failed": 0,
            "pct": 0, "current_file": None,
            "started_at": time.time(), "elapsed_s": 0.0, "eta_s": None,
        })

        for _i, file_path in enumerate(file_paths):
            rel_path = self._relative_path(file_path)

            # Update progress before each file so polling sees the current filename.
            _elapsed = time.monotonic() - _start
            _done = _i
            _pct = int(100 * _done / _total) if _total else 100
            _eta = (_elapsed / _done * (_total - _done)) if _done > 0 else None
            _progress.update({
                "files_done": _done, "current_file": rel_path,
                "files_indexed": files_indexed, "chunks_created": chunks_created,
                "files_skipped": files_unchanged, "files_failed": files_failed,
                "pct": _pct, "elapsed_s": round(_elapsed, 1),
                "eta_s": round(_eta, 0) if _eta is not None else None,
            })

            try:
                content = Path(file_path).read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as e:
                logger.warning("Failed to read %s: %s", rel_path, e)
                files_failed += 1
                file_errors.append({"file": rel_path, "type": "read_error", "message": str(e)})
                continue

            current_hash = file_hash(content)

            # Incremental: skip if unchanged
            if not force and self._manifest.get(rel_path) == current_hash:
                files_unchanged += 1
                continue

            # Delete old chunks for this file
            self._store.delete_by_source(collection, rel_path)

            # Chunk the file
            raw_chunks = self._chunk_file(content, rel_path)
            if not raw_chunks:
                files_unchanged += 1
                continue

            try:
                # Prepend file path + section to each chunk before embedding so the
                # vector captures where the content lives, not just what it says.
                # This matches the pattern used for code files in _do_index_project
                # and improves recall for knowledge/agents queries like "security XML".
                texts = [
                    f"[{rel_path}] [{c.section}]\n{c.content}" for c in raw_chunks
                ]
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
                self._manifest[rel_path] = current_hash
            except Exception as e:
                logger.error("Failed to embed/store %s: %s", rel_path, e)
                files_failed += 1
                file_errors.append({"file": rel_path, "type": "embed_error", "message": str(e)})

        _progress.update({
            "active": False, "phase": "idle", "pct": 100,
            "files_done": _total, "current_file": None,
            "files_indexed": files_indexed, "chunks_created": chunks_created,
            "files_skipped": files_unchanged, "files_failed": files_failed,
            "elapsed_s": round(time.monotonic() - _start, 1), "eta_s": 0,
        })
        self._save_manifest()
        if files_failed:
            logger.warning(
                "Indexed %s: %d files, %d chunks (%d unchanged, %d FAILED)",
                collection, files_indexed, chunks_created, files_unchanged, files_failed,
            )
        else:
            logger.info(
                "Indexed %s: %d files, %d chunks (%d unchanged)",
                collection, files_indexed, chunks_created, files_unchanged,
            )
        result: dict = {
            "files_indexed": files_indexed,
            "chunks_created": chunks_created,
            "files_unchanged": files_unchanged,
            "files_failed": files_failed,
        }
        if file_errors:
            result["errors"] = file_errors
        return result

    def _build_knowledge_communities(self) -> dict:
        """Build a category graph over knowledge/agents files and detect communities.

        Groups files into four categories:
          fw-*    → all framework guides (33 files)
          lang-*  → all language guides (17+ files)
          _agents → all agent definitions (regardless of filename prefix)
          _domain → everything else in knowledge/

        Communities are assigned directly from the groups — no external Leiden
        dependency needed. Edges are still written to kb_graph.db so has_graph()
        returns True and the search annotator can find summaries.
        """
        import re
        from rag_server.adapters.sqlite_graph_store import SQLiteGraphStore
        from rag_server.core.summarizer import summarize_community
        from rag_server.ports.graph_port import GraphEdge

        kb_graph_db = RAG_INDEX_DIR / "kb_graph.db"

        # Collect knowledge/agents files from the manifest
        kb_files = [
            f for f in self._manifest.keys()
            if f.startswith("knowledge/") or f.startswith("agents/")
        ]
        if not kb_files:
            return {"communities": 0, "summaries_generated": 0, "summaries_failed": 0}

        # Only fw- and lang- have enough files to be useful standalone communities.
        # Everything else in knowledge/ is domain knowledge; all agents/ files are agents.
        _KNOWN_PREFIXES = {"fw", "lang"}
        prefix_groups: dict[str, list[str]] = {}
        for f in kb_files:
            if f.startswith("agents/"):
                group = "_agents"
            else:
                name = Path(f).stem
                m = re.match(r"^([a-z]+)-", name)
                group = m.group(1) if (m and m.group(1) in _KNOWN_PREFIXES) else "_domain"
            prefix_groups.setdefault(group, []).append(f)

        # Build undirected edges: every pair within a group (2+ members)
        edges = []
        for members in prefix_groups.values():
            if len(members) < 2:
                continue
            for i, a in enumerate(members):
                for b in members[i + 1:]:
                    edges.append(GraphEdge(
                        source_file=a, source_symbol="<kb>",
                        target_file=b, target_symbol="<kb>",
                        edge_type="same_category",
                        confidence="PATTERN",
                    ))

        if not edges:
            logger.debug("Knowledge community detection: no multi-file groups — skipping")
            return {"communities": 0, "summaries_generated": 0, "summaries_failed": 0}

        # Rebuild graph structure while preserving existing summaries as cache.
        # Deleting kb_graph.db on every index run throws away valid summaries —
        # each regeneration takes 4+ minutes per community on typical hardware.
        # Instead: clear edges + communities, then repopulate. Summaries survive.
        graph_store = SQLiteGraphStore(kb_graph_db)
        graph_store.clear_graph_structure()
        graph_store.add_edges(edges)

        # Assign community IDs directly from prefix groups — no Leiden needed.
        # Each group (fw, lang, _agents, _domain) becomes one community.
        communities: dict[str, int] = {}
        for cid, (_, members) in enumerate(prefix_groups.items()):
            for f in members:
                communities[f] = cid

        graph_store.save_communities(communities)
        num_communities = len(set(communities.values()))
        logger.info(
            "Knowledge communities: %d files in %d communities",
            len(communities), num_communities,
        )

        # Count how many summaries already exist (cache hits — no LLM call needed).
        existing_summaries = len(graph_store.get_all_community_ids_with_summaries())
        communities_needing_summary = num_communities - existing_summaries
        if existing_summaries == num_communities:
            logger.info(
                "Community summaries: all %d cached — no LLM calls needed",
                num_communities,
            )
            return {
                "communities": num_communities,
                "summaries_generated": existing_summaries,
                "summaries_cached": existing_summaries,
                "summaries_failed": 0,
            }

        # Run summarization in a background thread so it never blocks the index response.
        # Results are logged and written to kb_graph.db; callers can check summaries
        # via the status endpoint after a short wait (~30-60s for 4 communities).
        import threading

        def _run_summaries():
            generated = 0
            cached = 0
            failed = 0
            for cid in graph_store.get_all_community_ids():
                members = graph_store.get_community_members(cid)
                try:
                    result = summarize_community(cid, members, graph_store, str(PROJECT_ROOT))
                    if result:
                        # summarize_community returns cached text on cache hit
                        existing = graph_store.get_community_summary(cid)
                        if existing and existing.get("summary") == result:
                            cached += 1
                        else:
                            generated += 1
                    else:
                        failed += 1
                        logger.error(
                            "Community %d summary returned empty — Ollama or Claude API may be failing",
                            cid,
                        )
                except Exception:
                    failed += 1
                    logger.error("Community %d summary FAILED", cid, exc_info=True)

            # Health check: validate ALL communities have summaries
            final_count = len(graph_store.get_all_community_ids_with_summaries())
            if final_count < num_communities:
                logger.error(
                    "SUMMARY HEALTH CHECK FAILED: only %d/%d community summaries exist "
                    "(%d generated, %d cached, %d failed). "
                    "Run POST /index with force=true to retry.",
                    final_count, num_communities, generated, cached, failed,
                )
            else:
                logger.info(
                    "Community summaries: %d/%d complete (%d generated, %d cached, %d failed)",
                    final_count, num_communities, generated, cached, failed,
                )

        threading.Thread(target=_run_summaries, daemon=True, name="kb-summarizer").start()
        logger.info(
            "Community summarization started in background: %d cached, %d need generation",
            existing_summaries, communities_needing_summary,
        )

        return {
            "communities": num_communities,
            "summaries_generated": "pending",  # background thread running
            "summaries_cached": existing_summaries,
            "summaries_failed": 0,
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
        # STOP: fail fast if model isn't loaded yet — avoids blocking on _load_lock for minutes.
        if not self._embedder.is_loaded:
            return {
                "error": (
                    "Embedding model not ready yet — server is still warming up. "
                    "Wait 30-60 seconds and retry."
                )
            }

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
        import gc
        import shutil
        from rag_server.core.store import ChromaStore
        from rag_server.adapters.sqlite_graph_store import SQLiteGraphStore

        chroma_dir = index_dir / "chroma"
        project_manifest_path = index_dir / "manifest.json"
        project_manifest = {}
        stored_version = MANIFEST_VERSION
        if not force and project_manifest_path.exists():
            raw = json.loads(project_manifest_path.read_text(encoding="utf-8"))
            project_manifest = {k: v for k, v in raw.items() if k != "__schema_version__"}
            stored_version = raw.get("__schema_version__", 1)

        collection = "codebase"

        # When not forcing: open stores for health check and dimension detection.
        # When forcing: skip opening entirely so we can wipe on Windows without file-lock errors.
        if not force:
            project_store = ChromaStore(persist_dir=str(chroma_dir))
            graph_store = SQLiteGraphStore(index_dir / "graph.db")

            # Health check: detect broken/stale index before scanning
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
            if project_store.collection_exists(collection) and project_store.count(collection) > 0:
                sample_dim = project_store.sample_dimension(collection)
                if sample_dim and sample_dim != self._embedder.dimensions():
                    logger.warning(
                        "Dimension mismatch in project codebase: index=%dd, model=%dd. Forcing re-index.",
                        sample_dim, self._embedder.dimensions(),
                    )
                    # Release file handles before wiping (critical on Windows)
                    del project_store
                    del graph_store
                    gc.collect()
                    force = True

        if force:
            # Wipe the stale chroma directory so a fresh store is created below.
            if chroma_dir.exists():
                last_err = None
                for attempt in range(4):
                    try:
                        shutil.rmtree(chroma_dir)
                        last_err = None
                        break
                    except PermissionError as e:
                        # Windows: SQLite WAL file still held by a previous connection.
                        # Force GC to release any lingering ChromaDB handles, then retry.
                        last_err = e
                        gc.collect()
                        time.sleep(0.5 * (attempt + 1))
                    except Exception as e:
                        last_err = e
                        break
                if last_err:
                    # Python shutil.rmtree failed on Windows (file lock or OneDrive holding the
                    # directory). Try PowerShell Remove-Item which handles these cases better.
                    import sys as _sys, subprocess as _sub
                    if _sys.platform == "win32":
                        logger.info("shutil.rmtree failed (%s), trying PowerShell Remove-Item", last_err)
                        _ps = _sub.run(
                            ["powershell", "-Command",
                             f"Remove-Item -Path '{chroma_dir}' -Recurse -Force -ErrorAction Stop"],
                            capture_output=True, text=True,
                        )
                        if _ps.returncode == 0:
                            logger.info("PowerShell Remove-Item succeeded on %s", chroma_dir)
                            last_err = None
                        else:
                            last_err = Exception(
                                f"shutil.rmtree + PowerShell both failed: {_ps.stderr.strip()}"
                            )
                    if last_err:
                        # shutil.rmtree + PowerShell both failed: another process (a
                        # concurrent search request or OneDrive) still holds the SQLite
                        # WAL file. Fall back to API-level collection clear — ChromaDB
                        # handles its own locking and works even with active readers.
                        logger.warning(
                            "Could not wipe chroma dir (%s). Clearing collection in-place.",
                            last_err,
                        )
                        _fb_store = ChromaStore(persist_dir=str(chroma_dir))
                        if _fb_store.collection_exists(collection):
                            _fb_store.delete_collection(collection)
                        del _fb_store
                        gc.collect()
                        logger.info("In-place collection clear succeeded — proceeding with reindex.")
                if not last_err:
                    # Directory was deleted (rmtree or PowerShell). Evict the cached client
                    # so the next ChromaStore() opens fresh files — a cached client holds
                    # SQLite handles to the deleted inodes and every write fails with
                    # "attempt to write a readonly database". rmtree succeeds first try on
                    # macOS/Linux, so this must run outside the failure-fallback block.
                    logger.info("Wiped stale chroma directory for clean re-index: %s", chroma_dir)
                    ChromaStore.evict_cache(str(chroma_dir))
            project_store = ChromaStore(persist_dir=str(chroma_dir))
            graph_store = SQLiteGraphStore(index_dir / "graph.db")

        project_store.create_collection(collection)

        # FTS5 store — optional BM25 layer alongside ChromaDB vectors.
        # Silently disabled if SQLite FTS5 isn't available in this Python build.
        fts_store = None
        try:
            from rag_server.adapters.fts_store import FTSStore
            fts_store = FTSStore(index_dir / "fts.db")
            if force:
                fts_store.clear()
        except Exception as _fts_init_err:
            logger.debug("FTS store init skipped (non-fatal): %s", _fts_init_err)

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
        files_unchanged = 0
        files_failed = 0
        file_errors: list[dict] = []
        start_time = time.time()
        total_files = len(file_paths)

        _proj_label = f"project:{Path(project_path).name}"
        _proj_start = time.monotonic()
        _progress.update({
            "active": True, "phase": _proj_label,
            "files_total": total_files, "files_done": 0,
            "files_indexed": 0, "chunks_created": 0,
            "files_skipped": 0, "files_failed": 0,
            "pct": 0, "current_file": None,
            "started_at": time.time(), "elapsed_s": 0.0, "eta_s": None,
        })

        for _pi, file_path in enumerate(file_paths):
            # Relative path within the target project
            try:
                rel_path = str(
                    Path(file_path).relative_to(project_root)
                ).replace("\\", "/")
            except ValueError:
                rel_path = file_path.replace("\\", "/")

            # Live progress update — visible via GET /index/progress
            _p_elapsed = time.monotonic() - _proj_start
            _p_eta = (_p_elapsed / _pi * (total_files - _pi)) if _pi > 0 else None
            _progress.update({
                "files_done": _pi, "current_file": rel_path,
                "files_indexed": files_indexed, "chunks_created": chunks_created,
                "files_skipped": files_unchanged, "files_failed": files_failed,
                "pct": int(100 * _pi / total_files) if total_files else 100,
                "elapsed_s": round(_p_elapsed, 1),
                "eta_s": round(_p_eta, 0) if _p_eta is not None else None,
            })

            _ext = Path(rel_path).suffix.lower()
            _is_pdf = _ext == ".pdf"
            _is_doc = _ext in {".md", ".mdx", ".rst", ".txt"}

            # PDFs need binary reads; all other file types use UTF-8 text
            content = None
            if _is_pdf:
                try:
                    _pdf_bytes = Path(file_path).read_bytes()
                except OSError as e:
                    logger.warning("Failed to read %s: %s", rel_path, e)
                    files_failed += 1
                    file_errors.append({"file": rel_path, "type": "read_error", "message": str(e)})
                    continue
                import hashlib as _hl
                current_hash = _hl.sha256(_pdf_bytes).hexdigest()[:16]
            else:
                try:
                    content = Path(file_path).read_text(encoding="utf-8")
                except (OSError, UnicodeDecodeError) as e:
                    logger.warning("Failed to read %s: %s", rel_path, e)
                    files_failed += 1
                    file_errors.append({"file": rel_path, "type": "read_error", "message": str(e)})
                    continue
                current_hash = file_hash(content)

            if not force and project_manifest.get(rel_path) == current_hash:
                files_unchanged += 1
                continue

            project_store.delete_by_source(collection, rel_path)
            graph_store.delete_edges_for_file(rel_path)
            if fts_store:
                fts_store.delete_by_source(rel_path)

            # Route to the correct chunker by file type
            if _is_pdf:
                from rag_server.indexing.pdf_chunker import chunk_pdf_file
                raw_chunks = chunk_pdf_file(file_path, source_url=rel_path)
            elif _is_doc:
                raw_chunks = chunk_markdown(
                    content, rel_path,
                    max_tokens=MAX_CHUNK_TOKENS,
                    min_tokens=MIN_CHUNK_TOKENS,
                    chunk_overlap=CHUNK_OVERLAP_TOKENS,
                )
            else:
                from rag_server.indexing.code_chunker import chunk_code
                raw_chunks = chunk_code(
                    content, rel_path,
                    max_tokens=MAX_CHUNK_TOKENS,
                    min_tokens=MIN_CHUNK_TOKENS,
                    chunk_overlap=CHUNK_OVERLAP_TOKENS,
                )

            if not raw_chunks:
                files_unchanged += 1
                continue

            # Graph edges — code files only, not docs
            if not _is_pdf and not _is_doc:
                from rag_server.core.project import extension_to_language
                from rag_server.indexing.code_chunker import extract_edges
                file_language = extension_to_language(Path(rel_path).suffix)
                if file_language:
                    edges = extract_edges(content, file_language, rel_path)
                    if edges:
                        try:
                            graph_store.add_edges(edges)
                        except Exception as e:
                            logger.warning("Graph edge add failed for %s: %s", rel_path, e)

            try:
                # Embed raw content without path/section prefix for code files.
                # Benchmark (CodeSearchNet 21K, MiniLM): prefix drops MRR from
                # 0.868 → 0.587 because it dilutes code semantics with path
                # metadata, creating a mismatch with natural-language queries.
                # File/function-name search is handled by the FTS5 index, which
                # indexes raw content — the embedding doesn't need the prefix.
                # Doc files (.md, .pdf) also embed without prefix: they already
                # have rich prose so no prefix was ever added for them.
                if not _is_pdf and not _is_doc:
                    from rag_server.indexing.code_preprocessor import preprocess_chunk
                    from rag_server.core.project import extension_to_language as _ext_to_lang
                    _chunk_lang = _ext_to_lang(Path(rel_path).suffix)
                    texts = [preprocess_chunk(c.content, _chunk_lang) for c in raw_chunks]
                else:
                    texts = [c.content for c in raw_chunks]
                embeddings = self._embedder.embed(texts)

                store_chunks = []
                for i, (raw, embedding) in enumerate(zip(raw_chunks, embeddings)):
                    # Fix 3: skip truly degenerate chunks (empty stubs, import-only lines)
                    if raw.token_count_approx < DEGENERATE_CHUNK_MIN_TOKENS:
                        continue
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
                # Fix 2: write to FTS5 index alongside ChromaDB
                if fts_store and store_chunks:
                    fts_store.insert_chunks([
                        {
                            "content": c.content,
                            "source_file": c.metadata.get("source_file", rel_path),
                            "section": c.metadata.get("section", ""),
                            "line_start": c.metadata.get("line_start", 0),
                        }
                        for c in store_chunks
                    ])
                chunks_created += added
                files_indexed += 1
                project_manifest[rel_path] = current_hash
            except Exception as e:
                logger.error("Failed to embed/store %s: %s", rel_path, e)
                files_failed += 1
                file_errors.append({"file": rel_path, "type": "embed_error", "message": str(e)})

            # Progress log every 25 files
            processed = files_indexed + files_failed
            if processed > 0 and processed % 25 == 0:
                elapsed = time.time() - start_time
                rate = processed / elapsed if elapsed > 0 else 0
                remaining = (total_files - processed) / rate if rate > 0 else 0
                pct = int(processed / total_files * 100) if total_files else 0
                logger.info(
                    "Progress [%s]: %d/%d files (%d%%) — %.1f files/sec, ~%ds remaining%s",
                    pid, processed, total_files, pct, rate, int(remaining),
                    f", {files_failed} failed" if files_failed else "",
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

        # SCIP graph enrichment (optional — augments tree-sitter with resolved edges).
        # Only runs for Python files; silently skips if scip-python is not installed.
        if files_indexed > 0:
            try:
                from rag_server.indexing.scip_extractor import extract_project_edges, is_available
                if is_available():
                    py_files = [p for p in project_manifest.keys() if p.endswith(".py")]
                    scip_edges = extract_project_edges(project_path, py_files)
                    if scip_edges:
                        graph_store.add_edges(scip_edges)
                        logger.info("SCIP: added %d reference edges", len(scip_edges))
            except Exception:
                logger.debug("SCIP pass failed (non-fatal)", exc_info=True)

        # TypeScript SCIP enrichment (optional — runs if scip-typescript is installed globally).
        # Install: npm install -g @sourcegraph/scip-typescript
        if files_indexed > 0:
            try:
                ts_files = [p for p in project_manifest.keys() if p.endswith((".ts", ".tsx"))]
                if ts_files:
                    from rag_server.indexing.scip_extractor import extract_typescript_edges
                    ts_edges = extract_typescript_edges(project_path)
                    if ts_edges:
                        graph_store.add_edges(ts_edges)
                        logger.info("SCIP TypeScript: added %d reference edges", len(ts_edges))
            except Exception:
                logger.debug("SCIP TypeScript pass failed (non-fatal)", exc_info=True)

        # Go SCIP enrichment (optional — runs if scip-go is installed).
        # Install: go install github.com/sourcegraph/scip-go/cmd/scip-go@latest
        if files_indexed > 0:
            try:
                go_files = [p for p in project_manifest.keys() if p.endswith(".go")]
                if go_files:
                    from rag_server.indexing.scip_extractor import extract_go_edges
                    go_edges = extract_go_edges(project_path)
                    if go_edges:
                        graph_store.add_edges(go_edges)
                        logger.info("SCIP Go: added %d reference edges", len(go_edges))
            except Exception:
                logger.debug("SCIP Go pass failed (non-fatal)", exc_info=True)

        # Co-change graph: files that change together in git history often have
        # implicit coupling not captured by imports. Pairs seen in >= 2 commits become edges.
        # Requires PyDriller: pip install pydriller
        if files_indexed > 0:
            try:
                from rag_server.indexing.git_extractor import extract_co_change_edges
                co_change_edges = extract_co_change_edges(project_path)
                if co_change_edges:
                    graph_store.add_edges(co_change_edges)
                    logger.info("Co-change graph: added %d edges", len(co_change_edges))
            except Exception:
                logger.warning("Co-change extractor import/run failed (non-fatal)", exc_info=True)

        # C# namespace-resolution graph enrichment (pure Python, no external tools).
        # Skipped on zero-change incremental runs unless this is the first time CSHARP
        # edges are being built (e.g. after a ClaudeBoost update that added this extractor).
        try:
            cs_files = [p for p in project_manifest.keys() if p.endswith(".cs")]
            _needs_cs = cs_files and (
                files_indexed > 0
                or graph_store.count_edges_by_confidence("CSHARP") == 0
            )
            if _needs_cs:
                from rag_server.indexing.csharp_extractor import extract_project_edges as extract_cs_edges
                cs_edges = extract_cs_edges(project_path, cs_files)
                if cs_edges:
                    graph_store.add_edges(cs_edges)
                    logger.info("C# extractor: added %d reference edges", len(cs_edges))
        except Exception:
            logger.debug("C# extractor pass failed (non-fatal)", exc_info=True)

        # Community detection + summaries (optional deps — never blocks indexing).
        # Run when files were indexed OR when communities table is empty (recovery from
        # a previous failed run — e.g. pre-leiden-fix index where detection silently threw).
        _need_communities = files_indexed > 0 or not graph_store.get_all_community_ids()
        if _need_communities and graph_store.has_graph():
            try:
                from rag_server.core.community import detect_communities
                from rag_server.core.summarizer import summarize_community
                import threading

                communities = detect_communities(graph_store)
                if communities:
                    graph_store.save_communities(communities)
                    num_communities = len(set(communities.values()))
                    logger.info(
                        "Community detection: %d files in %d communities",
                        len(communities), num_communities,
                    )
                    # Summarization runs in background — each community takes ~130s with
                    # qwen3:4b on this hardware. Don't block the HTTP index response.
                    def _summarize_project_communities(
                        _cids=graph_store.get_all_community_ids(),
                        _gs=graph_store,
                        _pp=project_path,
                    ):
                        generated = cached = failed = 0
                        for cid in _cids:
                            members = _gs.get_community_members(cid)
                            try:
                                result = summarize_community(cid, members, _gs, _pp)
                                if result:
                                    cached += 1
                                else:
                                    generated += 1
                            except Exception:
                                logger.exception("Community summary failed for community %d", cid)
                                failed += 1
                        logger.info(
                            "Project community summaries complete: %d generated, %d cached, %d failed",
                            generated, cached, failed,
                        )
                    t = threading.Thread(
                        target=_summarize_project_communities, daemon=True,
                    )
                    t.start()
                    logger.info(
                        "Project community summaries running in background (%d communities).",
                        num_communities,
                    )
            except ImportError:
                logger.debug("Community detection modules not available — skipping")
            except Exception:
                logger.exception("Community detection failed unexpectedly")
                # don't re-raise — community detection is non-critical

        # PageRank: score each file by how many other files import or reference it.
        # High-scoring files (core modules, shared utilities) get a boost in graph search.
        # Runs on the same condition as community detection — same edge data, same timing.
        if _need_communities and graph_store.has_graph():
            try:
                from rag_server.core.community import compute_pagerank
                pr_scores = compute_pagerank(graph_store)
                if pr_scores:
                    graph_store.save_pagerank(pr_scores)
            except Exception:
                logger.debug("PageRank computation failed (non-fatal)", exc_info=True)

        # Save project manifest (C3: include schema version)
        try:
            manifest_to_write = {"__schema_version__": MANIFEST_VERSION, **project_manifest}
            project_manifest_path.write_text(
                json.dumps(manifest_to_write, indent=2), encoding="utf-8",
            )
        except OSError as e:
            logger.error("Failed to write project manifest to %s: %s", project_manifest_path, e)

        elapsed_s = round(time.time() - start_time, 1)
        _progress.update({
            "active": False, "phase": "idle", "pct": 100,
            "files_done": total_files, "current_file": None,
            "files_indexed": files_indexed, "chunks_created": chunks_created,
            "files_skipped": files_unchanged, "files_failed": files_failed,
            "elapsed_s": elapsed_s, "eta_s": 0,
        })
        if files_failed:
            logger.warning(
                "Indexed project %s (%s): %d files, %d chunks (%d unchanged, %d FAILED) in %.1fs",
                pid, project_path, files_indexed, chunks_created,
                files_unchanged, files_failed, elapsed_s,
            )
            for err in file_errors:
                logger.warning("  %s — %s: %s", err["file"], err["type"], err["message"])
        else:
            logger.info(
                "Indexed project %s (%s): %d files, %d chunks (%d unchanged) in %.1fs",
                pid, project_path, files_indexed, chunks_created, files_unchanged, elapsed_s,
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
                "files_failed": files_failed,
                "graph_edges": edge_count,
                "graph_resolved": resolved,
                "graph_active": edge_count > 0 and resolved > 0,
            }
            registry_path.write_text(json.dumps(registry, indent=2), encoding="utf-8")
        except Exception as e:
            logger.warning("Failed to write project registry: %s", e)

        result: dict = {
            "project_id": pid,
            "files_indexed": files_indexed,
            "chunks_created": chunks_created,
            "files_unchanged": files_unchanged,
            "files_failed": files_failed,
            "elapsed_s": elapsed_s,
            "graph": {
                "edges": graph_store.count_edges() if hasattr(graph_store, "count_edges") else 0,
                "resolved": graph_store.count_resolved_edges() if hasattr(graph_store, "count_resolved_edges") else 0,
                "unresolved": graph_store.count_unresolved_edges() if hasattr(graph_store, "count_unresolved_edges") else 0,
            },
            "index_path": str(index_dir),
        }
        if file_errors:
            result["errors"] = file_errors
        return result

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

        issues = self._check_project_health(
            index_dir, project_store, graph_store, project_manifest, stored_version
        )
        # Release SQLite handles — prevents accumulating open connections on Windows
        # when health checks are called repeatedly without the server restarting.
        import gc as _gc
        try:
            project_store.close()
        except Exception:
            pass
        del project_store
        del graph_store
        _gc.collect()
        return issues

    def _chunk_file(self, content: str, rel_path: str):
        """Route to the right chunker based on file extension.

        Document formats must be checked before extension_to_language() because
        .md/.rst/.txt/.pdf are all in LANGUAGE_EXTENSIONS (truthy) but need their
        own chunkers — code chunker produces nothing for them.
        """
        suffix = Path(rel_path).suffix.lower()

        # Document formats — must come first
        if suffix in {".md", ".mdx"}:
            return chunk_markdown(
                content, rel_path,
                max_tokens=MAX_CHUNK_TOKENS,
                min_tokens=MIN_CHUNK_TOKENS,
                chunk_overlap=CHUNK_OVERLAP_TOKENS,
            )
        if suffix in {".rst", ".txt"}:
            return chunk_markdown(
                content, rel_path,
                max_tokens=MAX_CHUNK_TOKENS,
                min_tokens=MIN_CHUNK_TOKENS,
                chunk_overlap=CHUNK_OVERLAP_TOKENS,
            )
        if suffix == ".xml":
            from rag_server.indexing.xml_chunker import chunk_xml
            return chunk_xml(
                content, rel_path,
                max_tokens=MAX_CHUNK_TOKENS,
                min_tokens=MIN_CHUNK_TOKENS,
            )

        # Code files — only after document types are ruled out
        from rag_server.core.project import extension_to_language
        from rag_server.indexing.code_chunker import chunk_code
        if extension_to_language(suffix):
            return chunk_code(
                content, rel_path,
                max_tokens=MAX_CHUNK_TOKENS,
                min_tokens=MIN_CHUNK_TOKENS,
                chunk_overlap=CHUNK_OVERLAP_TOKENS,
            )

        # Unsupported file type — skip
        return []

    def _relative_path(self, file_path: str) -> str:
        """Convert absolute path to relative (forward slashes)."""
        try:
            return str(Path(file_path).relative_to(PROJECT_ROOT)).replace("\\", "/")
        except ValueError:
            return file_path.replace("\\", "/")
