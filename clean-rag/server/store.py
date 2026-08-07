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


@dataclass
class _CachedConnection:
    """One shared sqlite handle plus the state a deferred close needs.

    Shaped after SQLAlchemy's pool record (lib/sqlalchemy/pool/base.py):
    invalidating a record only marks it, the record itself stays in the pool, and
    the underlying DBAPI connection is closed at check in once the last holder
    gives it back (``_ConnectionRecord.checkin`` and ``invalidate``). Closing it
    while a holder is still using it is not survivable here: a reader mid
    execute() when the handle closes takes the whole process down with an access
    violation on Windows, and a writer between statements dies with "Cannot
    operate on a closed database".

    The record staying in the cache while its close is deferred is the load
    bearing half, not a detail. Popping it and deferring the close let the next
    ChromaStore for the same path build a SECOND record, so one db file had two
    open handles and, worse, two different write_locks. Two writers then each
    held their own lock and raced _ensure_vec_table's check then create, and the
    loser's whole add_chunks call failed with "table vec_codebase already
    exists". So: one record, one connection and one write_lock per db path, and
    the record is dropped from the cache only in the same critical section that
    actually closes its handle.

    holders counts live ChromaStore instances rather than individual calls,
    because index_project keeps one store for a run that lasts hours and uses it
    between statements the whole time.
    """

    conn: sqlite3.Connection
    #: Serializes writes on this handle so last_insert_rowid() cannot return
    #: another thread's rowid, and so _ensure_vec_table cannot race between
    #: checking for its table and creating it. It lives in the same record as
    #: the connection it guards, which is what stops the lock and the handle
    #: from ever being paired with two different underlying connections.
    write_lock: threading.Lock
    #: Live ChromaStore instances still holding this handle.
    holders: int = 0
    #: An eviction has asked for this handle. The last holder out closes it.
    close_when_idle: bool = False
    #: True once the close has actually run, so it can never run twice.
    closed: bool = False


# Process-wide connection cache keyed by canonical db file path.
#
# Reentrant, not a plain Lock: a store that a caller never closed checks itself
# in from ChromaStore.__del__, and the cyclic collector can run that destructor
# at any allocation point, including inside one of the sections below on this
# same thread. A plain Lock deadlocks the server there. Every section under this
# lock is a short bookkeeping update that stays correct if a check in interleaves
# with it, since the only shared state is a counter and a pair of flags.
_conn_cache: dict[str, _CachedConnection] = {}
_conn_cache_lock = threading.RLock()


def _forget(db_path: str, entry: _CachedConnection) -> None:
    """Drop a closed record from the cache.

    Call with ``_conn_cache_lock`` held. Identity checked, so a record that was
    already replaced by a newer one for the same path is left alone.
    """
    if _conn_cache.get(db_path) is entry:
        del _conn_cache[db_path]


def _mark_for_close(db_path: str, entry: _CachedConnection) -> sqlite3.Connection | None:
    """Mark an evicted record, returning its handle only if it is idle now.

    Call with ``_conn_cache_lock`` held. None means a live holder still has the
    handle, in which case the record stays cached, so any later ChromaStore for
    this path is handed this same connection and this same write lock instead of
    opening a second one, and that holder's :meth:`ChromaStore.close` performs
    the close.
    """
    entry.close_when_idle = True
    if entry.closed:
        _forget(db_path, entry)
        return None
    if entry.holders > 0:
        return None
    entry.closed = True
    _forget(db_path, entry)
    return entry.conn


def _close_quietly(conn: sqlite3.Connection, db_path: str) -> None:
    """Close a handle no one holds. Failing to close must not abort a sweep.

    Called with ``_conn_cache_lock`` released, the same way SQLAlchemy's pool
    closes outside its own mutex, because the last connection out of a WAL
    database checkpoints on close and that is not a wait to impose on every other
    database's opens. What that costs is a moment where this handle is closing
    while a store for the same path opens a fresh one. Harmless: by the time a
    handle reaches here it has been unlinked from the cache and marked closed
    under the lock, so it has no holders and nothing can reach it to write
    through it. The invariant that matters, one usable connection and one write
    lock per path, holds throughout.
    """
    try:
        conn.close()
    except Exception as e:
        logger.debug("Connection close for %s (non-fatal): %s", db_path, e)


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
        """Stop serving this directory's connection, and close it once idle.

        The close waits for the last live holder to call :meth:`close`, because a
        sweep evicting a project while an index run or a search still held that
        handle used to close the database underneath it. With no holder it closes
        here and now, which is the sweep's normal case.

        A deferred close leaves the record cached, marked. That is what keeps the
        eviction from producing a second connection to the same file: the next
        ChromaStore for this path joins the marked record rather than opening its
        own, and the close still happens the moment the last holder leaves.
        """
        db_path = str((Path(persist_dir).resolve() / "vectors.db"))
        with _conn_cache_lock:
            entry = _conn_cache.get(db_path)
            conn = _mark_for_close(db_path, entry) if entry is not None else None
            holders = entry.holders if entry is not None else 0
        if conn is not None:
            _close_quietly(conn, db_path)
        elif entry is not None:
            logger.info(
                "Close of %s deferred, %d holder(s) still using it", db_path, holders,
            )

    @staticmethod
    def clear_cache() -> None:
        """Evict every cached connection. Called during graceful shutdown.

        Deferred the same way as :meth:`evict_cache`, and for the same two
        reasons. Shutdown is not a reason to close a handle a worker thread is
        still writing through, and the process exit that follows releases the
        file anyway. A record whose close is deferred stays cached, so nothing
        that opens a store during shutdown gets a second handle on a file another
        thread is still writing.
        """
        with _conn_cache_lock:
            marked = [
                (key, _mark_for_close(key, entry))
                for key, entry in list(_conn_cache.items())
            ]
        for key, conn in marked:
            if conn is not None:
                _close_quietly(conn, key)
            else:
                logger.info("Close of %s deferred at shutdown, still in use", key)

    def __init__(self, persist_dir: str):
        # Set before anything that can raise, so the __del__ backstop below has
        # something defined to look at if the open fails.
        self._entry: _CachedConnection | None = None
        self._persist_dir = Path(persist_dir).resolve()
        self._persist_dir.mkdir(parents=True, exist_ok=True)
        self._db_path = str(self._persist_dir / "vectors.db")

        with _conn_cache_lock:
            # Any cached record is reused, including one an eviction has already
            # marked: a marked record still has a live, working handle, and
            # opening a second one beside it is the thing that breaks the write
            # lock. The mark is deliberately not cleared here, so the eviction
            # still takes effect at the next moment nothing holds the handle.
            entry = _conn_cache.get(self._db_path)
            if entry is None:
                entry = _CachedConnection(
                    conn=_open_connection(self._db_path),
                    write_lock=threading.Lock(),
                )
                _conn_cache[self._db_path] = entry
                logger.info("sqlite-vec store opened at %s", self._db_path)
            else:
                logger.debug("sqlite-vec connection reused for %s", self._db_path)
            entry.holders += 1
            self._entry = entry
            self._conn = entry.conn
            self._write_lock = entry.write_lock

    def close(self) -> None:
        """Give the shared connection back.

        Drops this store's reference, and closes the underlying handle only when
        this was the last holder of a handle an eviction already asked for.
        Running that deferred close here is what keeps deferring one from
        turning into a leak: the memory the sweep evicts for is released as soon
        as the last user is done with it. Safe to call more than once.
        """
        entry, self._entry, self._conn = self._entry, None, None
        if entry is None:
            return
        with _conn_cache_lock:
            entry.holders -= 1
            close_now = (
                entry.close_when_idle and entry.holders <= 0 and not entry.closed
            )
            if close_now:
                entry.closed = True
                # Dropped from the cache in the same critical section that owns
                # the close, so nothing can be handed a record whose handle is
                # about to stop working.
                _forget(self._db_path, entry)
        if close_now:
            _close_quietly(entry.conn, self._db_path)

    def __enter__(self) -> "ChromaStore":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    def __del__(self) -> None:
        # Backstop only. Every caller in server/ opens its store in a `with`,
        # and new ones should too, because a
        # destructor is not a release mechanism you can rely on: an exception
        # raised while a store was a local in the frame keeps that frame, and so
        # the store, alive for as long as anything holds the traceback, and a
        # connection an eviction asked to close then stays open indefinitely.
        # __exit__ runs on the way out of the block whether the block returned
        # or raised, which is what makes the check in deterministic. SQLAlchemy
        # keeps the same shape: a weakref finalizer behind an explicit close, not
        # instead of one.
        #
        # Caught because a destructor cannot usefully raise: an exception here
        # would only be printed and ignored, and the two ways this can fail are
        # an __init__ that raised before _entry existed (whose real error the
        # caller already has) and interpreter shutdown.
        try:
            self.close()
        except Exception:
            logger.debug("Connection check in from __del__ failed", exc_info=True)

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
