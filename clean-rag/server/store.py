"""sqlite-vec vector store implementation.

Replaces the previous ChromaDB backed store to eliminate the bloat bug
(orphaned HNSW segments, unpruned WAL, insufficient VACUUM on Windows).
Uses a single SQLite file with the sqlite-vec extension for KNN search.

Based on the LangChain SQLiteVec integration (PR #25024) adapted to
match the existing ChromaStore interface.
"""

import json
import logging
import sqlite3
import struct
import threading
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class Chunk:
    """A text chunk with metadata, ready for storage."""
    id: str
    content: str
    embedding: list[float]
    metadata: dict


@dataclass
class SearchResult:
    """A search result with score."""
    content: str
    metadata: dict
    score: float


def _serialize_f32(vector: list[float]) -> bytes:
    """Serialize a float list to compact bytes for sqlite-vec."""
    return struct.pack(f"{len(vector)}f", *vector)


# Process-wide connection cache keyed by canonical db file path.
_conn_cache: dict[str, sqlite3.Connection] = {}
_conn_cache_lock = threading.Lock()
# Per-database write lock: serializes all write operations on a shared
# connection so that last_insert_rowid() cannot return another thread's
# rowid and _ensure_vec_table cannot race on check-then-create.
_write_lock_cache: dict[str, threading.Lock] = {}


def _open_connection(db_path: str) -> sqlite3.Connection:
    """Open a new SQLite connection with sqlite-vec loaded.

    Sets WAL mode with hardened pragmas to prevent bloat:
    - journal_size_limit caps the WAL file at 64 MB between checkpoints.
    - busy_timeout gives VACUUM enough room (30 s, matches graph_store).
    - synchronous=NORMAL is safe with WAL and avoids an fsync per commit.
    - wal_autocheckpoint is explicit (SQLite default is 1000 pages).
    - auto_vacuum=INCREMENTAL on brand new databases so deleted pages are
      reclaimable via incremental_vacuum without a full VACUUM.
    """
    import sqlite_vec

    is_new = not Path(db_path).exists()
    conn = sqlite3.connect(db_path, check_same_thread=False)
    if is_new:
        conn.execute("PRAGMA auto_vacuum=INCREMENTAL")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("PRAGMA journal_size_limit=67108864")
    conn.execute("PRAGMA wal_autocheckpoint=1000")
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    return conn


def _safe_name(collection: str) -> str:
    """Sanitize a collection name for use in SQL identifiers."""
    return "".join(c if c.isalnum() or c == "_" else "_" for c in collection)


class ChromaStore:
    """Vector store backed by sqlite-vec.

    Drop in replacement for the previous ChromaDB implementation.
    Constructor takes a directory path (persist_dir); the actual database
    file is ``persist_dir/vectors.db``.
    """

    @staticmethod
    def evict_cache(persist_dir: str) -> None:
        """Remove cached connection for a persist directory."""
        db_path = str((Path(persist_dir).resolve() / "vectors.db"))
        with _conn_cache_lock:
            conn = _conn_cache.pop(db_path, None)
            _write_lock_cache.pop(db_path, None)
        if conn is not None:
            try:
                conn.close()
            except Exception as e:
                logger.debug("Connection close during evict (non-fatal): %s", e)

    @staticmethod
    def clear_cache() -> None:
        """Close all cached connections. Called during graceful shutdown."""
        with _conn_cache_lock:
            for key, conn in list(_conn_cache.items()):
                try:
                    conn.close()
                except Exception as e:
                    logger.debug("Connection close for %s (non-fatal): %s", key, e)
            _conn_cache.clear()
            _write_lock_cache.clear()

    def __init__(self, persist_dir: str):
        self._persist_dir = Path(persist_dir).resolve()
        self._persist_dir.mkdir(parents=True, exist_ok=True)
        self._db_path = str(self._persist_dir / "vectors.db")

        with _conn_cache_lock:
            if self._db_path not in _conn_cache:
                _conn_cache[self._db_path] = _open_connection(self._db_path)
                logger.info("sqlite-vec store opened at %s", self._db_path)
            else:
                logger.debug("sqlite-vec connection reused for %s", self._db_path)
            self._conn = _conn_cache[self._db_path]
            if self._db_path not in _write_lock_cache:
                _write_lock_cache[self._db_path] = threading.Lock()
            self._write_lock = _write_lock_cache[self._db_path]

    def close(self) -> None:
        """Drop this store's reference to the shared connection."""
        self._conn = None

    def vacuum(self) -> None:
        """Reclaim free pages and truncate the WAL file.

        VACUUM alone in WAL mode does not shrink the on-disk file: it
        rebuilds inside the WAL, but the WAL itself stays at its high
        water mark until a TRUNCATE checkpoint physically resets it.
        Running both inside the write lock is safe because no other
        writer can be active and the lock serializes readers too.
        """
        if self._conn is None:
            return
        with self._write_lock:
            try:
                size_before = Path(self._db_path).stat().st_size
                self._conn.execute("VACUUM")
                self._conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                size_after = Path(self._db_path).stat().st_size
                freed_mb = round((size_before - size_after) / 1024 ** 2, 1)
                if freed_mb > 0.1:
                    logger.info(
                        "VACUUM %s: %.1f MB -> %.1f MB (freed %.1f MB)",
                        self._db_path,
                        round(size_before / 1024 ** 2, 1),
                        round(size_after / 1024 ** 2, 1),
                        freed_mb,
                    )
            except Exception as e:
                logger.warning("VACUUM failed (non-fatal): %s", e)

    def vacuum_if_needed(self, threshold: float = 0.15) -> bool:
        """Run VACUUM only when freelist pages exceed a ratio of total pages.

        Returns True if VACUUM actually ran, False otherwise.  Used after
        incremental reindexes to prevent unbounded freelist growth without
        the cost of vacuuming on every single file edit.
        """
        if self._conn is None:
            return False
        try:
            freelist = self._conn.execute("PRAGMA freelist_count").fetchone()[0]
            if freelist < 100:
                return False
            page_count = self._conn.execute("PRAGMA page_count").fetchone()[0]
            if page_count == 0:
                return False
            if (freelist / page_count) < threshold:
                return False
        except Exception:
            return False
        logger.info(
            "Freelist ratio %.1f%% exceeds threshold in %s, vacuuming",
            (freelist / page_count) * 100, self._db_path,
        )
        self.vacuum()
        return True

    # ------------------------------------------------------------------
    # Collection management
    # ------------------------------------------------------------------

    def create_collection(self, collection: str) -> None:
        safe = _safe_name(collection)
        with self._write_lock:
            self._conn.execute(f"""
                CREATE TABLE IF NOT EXISTS chunks_{safe} (
                    rowid INTEGER PRIMARY KEY AUTOINCREMENT,
                    chunk_id TEXT UNIQUE NOT NULL,
                    content TEXT NOT NULL,
                    source_file TEXT NOT NULL DEFAULT '',
                    metadata TEXT NOT NULL DEFAULT '{{}}',
                    embedding BLOB NOT NULL
                )
            """)
            self._conn.execute(
                f"CREATE INDEX IF NOT EXISTS idx_chunks_{safe}_source "
                f"ON chunks_{safe}(source_file)"
            )
            self._conn.commit()

    def _ensure_vec_table(self, collection: str, dim: int) -> None:
        """Create the vec0 virtual table if it doesn't exist yet.

        Deferred to first add_chunks so the embedding dimension is known.
        Must be called under self._write_lock to avoid a check-then-create
        race between threads.

        Dimension guard: if the table exists but was created with a different
        dimension (e.g. model change from 768d to 4096d), drop and recreate.
        Without this, inserts silently fail or corrupt the index.
        """
        safe = _safe_name(collection)
        import re as _re
        row = self._conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
            (f"vec_{safe}",),
        ).fetchone()
        if row:
            match = _re.search(r"float\[(\d+)\]", row[0] or "")
            if match:
                stored_dim = int(match.group(1))
                if stored_dim != dim:
                    logger.warning(
                        "Dimension mismatch in vec_%s: stored=%d, new=%d. Rebuilding vec table.",
                        safe, stored_dim, dim,
                    )
                    self._conn.execute(f"DROP TABLE vec_{safe}")
                    self._conn.commit()
                else:
                    return  # exists and dimension matches
            else:
                return  # exists, can't parse dim — leave it alone
        self._conn.execute(
            f"CREATE VIRTUAL TABLE vec_{safe} USING vec0("
            f"embedding float[{int(dim)}] distance_metric=cosine)"
        )
        self._conn.commit()
        logger.info("Created vec0 table vec_%s (dim=%d)", safe, dim)

    def collection_exists(self, collection: str) -> bool:
        safe = _safe_name(collection)
        row = self._conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (f"chunks_{safe}",),
        ).fetchone()
        return row is not None

    def delete_collection(self, collection: str) -> bool:
        safe = _safe_name(collection)
        with self._write_lock:
            try:
                self._conn.execute(f"DROP TABLE IF EXISTS vec_{safe}")
                self._conn.execute(f"DROP TABLE IF EXISTS chunks_{safe}")
                self._conn.commit()
                return True
            except Exception as e:
                logger.error("delete_collection(%r) failed: %s", collection, e)
                return False

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------

    def add_chunks(self, collection: str, chunks: list[Chunk]) -> int:
        if not chunks:
            return 0

        safe = _safe_name(collection)
        tbl = f"chunks_{safe}"
        vec = f"vec_{safe}"

        dim = len(chunks[0].embedding)

        with self._write_lock:
            self._ensure_vec_table(collection, dim)

            with self._conn:
                for chunk in chunks:
                    # Upsert: delete existing row with the same chunk_id first.
                    # vec0 does not support ON CONFLICT / INSERT OR REPLACE.
                    existing = self._conn.execute(
                        f"SELECT rowid FROM {tbl} WHERE chunk_id = ?",
                        (chunk.id,),
                    ).fetchone()
                    if existing:
                        rid = existing[0]
                        self._conn.execute(f"DELETE FROM {vec} WHERE rowid = ?", (rid,))
                        self._conn.execute(f"DELETE FROM {tbl} WHERE rowid = ?", (rid,))

                    emb_bytes = _serialize_f32(chunk.embedding)
                    source_file = chunk.metadata.get("source_file", "")

                    self._conn.execute(
                        f"INSERT INTO {tbl} "
                        f"(chunk_id, content, source_file, metadata, embedding) "
                        f"VALUES (?, ?, ?, ?, ?)",
                        (
                            chunk.id,
                            chunk.content,
                            source_file,
                            json.dumps(chunk.metadata),
                            emb_bytes,
                        ),
                    )
                    rid = self._conn.execute("SELECT last_insert_rowid()").fetchone()[0]
                    self._conn.execute(
                        f"INSERT INTO {vec} (rowid, embedding) VALUES (?, ?)",
                        (rid, emb_bytes),
                    )

        return len(chunks)

    def delete_by_source(self, collection: str, source_file: str) -> int:
        safe = _safe_name(collection)
        tbl = f"chunks_{safe}"
        vec = f"vec_{safe}"

        with self._write_lock:
            rows = self._conn.execute(
                f"SELECT rowid FROM {tbl} WHERE source_file = ?",
                (source_file,),
            ).fetchall()
            if not rows:
                return 0

            rowids = [r[0] for r in rows]
            with self._conn:
                vec_exists = self._conn.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                    (vec,),
                ).fetchone()
                if vec_exists:
                    for rid in rowids:
                        self._conn.execute(f"DELETE FROM {vec} WHERE rowid = ?", (rid,))
                self._conn.execute(
                    f"DELETE FROM {tbl} WHERE source_file = ?", (source_file,),
                )
            return len(rowids)

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    def search(
        self,
        collection: str,
        query_embedding: list[float],
        limit: int = 5,
        min_score: float = 0.3,
    ) -> list[SearchResult]:
        safe = _safe_name(collection)
        tbl = f"chunks_{safe}"
        vec = f"vec_{safe}"

        if not self._conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (vec,),
        ).fetchone():
            return []

        # Over-fetch: min_score filtering is post-filter in Python because
        # vec0 does not support WHERE distance < threshold in KNN queries.
        fetch_limit = max(limit * 3, 20)

        try:
            rows = self._conn.execute(
                f"""
                SELECT v.rowid, v.distance, c.content, c.metadata
                FROM {vec} v
                INNER JOIN {tbl} c ON c.rowid = v.rowid
                WHERE v.embedding MATCH ?
                AND k = ?
                ORDER BY v.distance
                """,
                (_serialize_f32(query_embedding), fetch_limit),
            ).fetchall()
        except Exception as e:
            logger.warning("search(%r) failed: %s", collection, e)
            return []

        results = []
        for _rowid, distance, content, metadata_json in rows:
            # Cosine distance in [0, 2] -> similarity score in [0, 1]
            score = 1.0 - (distance / 2.0)
            if score >= min_score:
                meta = json.loads(metadata_json) if isinstance(metadata_json, str) else metadata_json
                results.append(SearchResult(
                    content=content,
                    metadata=meta,
                    score=round(score, 4),
                ))
            if len(results) >= limit:
                break

        return results

    def get_by_source(
        self, collection: str, source_file: str, limit: int = 5,
    ) -> list[SearchResult]:
        """Get chunks for a specific source file (no embedding query needed).

        Used by graph search to fetch content for structurally related files
        discovered via edge traversal.
        """
        safe = _safe_name(collection)
        tbl = f"chunks_{safe}"
        rows = self._conn.execute(
            f"SELECT content, metadata FROM {tbl} WHERE source_file = ? LIMIT ?",
            (source_file, limit),
        ).fetchall()
        return [
            SearchResult(
                content=row[0],
                metadata=json.loads(row[1]) if isinstance(row[1], str) else row[1],
                score=1.0,
            )
            for row in rows
        ]

    def sample_dimension(self, collection: str) -> int | None:
        """Return the embedding dimension from the first stored chunk, or None."""
        safe = _safe_name(collection)
        try:
            row = self._conn.execute(
                f"SELECT embedding FROM chunks_{safe} LIMIT 1"
            ).fetchone()
            if row and row[0]:
                return len(row[0]) // 4  # float32 = 4 bytes each
        except Exception:
            pass
        return None

    def count(self, collection: str) -> int:
        safe = _safe_name(collection)
        try:
            row = self._conn.execute(
                f"SELECT COUNT(*) FROM chunks_{safe}"
            ).fetchone()
            return row[0] if row else 0
        except Exception:
            return 0

    def count_sources(self, collection: str) -> int:
        """Count distinct source files in a collection."""
        safe = _safe_name(collection)
        try:
            row = self._conn.execute(
                f"SELECT COUNT(DISTINCT source_file) FROM chunks_{safe}"
            ).fetchone()
            return row[0] if row else 0
        except Exception:
            return 0

    def list_sources(self, collection: str) -> list[str]:
        safe = _safe_name(collection)
        rows = self._conn.execute(
            f"SELECT DISTINCT source_file FROM chunks_{safe} ORDER BY source_file"
        ).fetchall()
        return [r[0] for r in rows]
