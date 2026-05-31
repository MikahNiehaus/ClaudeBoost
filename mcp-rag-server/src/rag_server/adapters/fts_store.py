"""SQLite FTS5 store — BM25 full-text search over project code chunks.

Complements the ChromaDB vector store with exact-term and BM25 retrieval.
Lives at idx_dir/fts.db alongside graph.db.

Short queries (1-3 words, type signatures) often confuse the embedding model
but are handled well by BM25 — exact terms score high even when the vector
similarity is low. The two signals are merged via RRF in search.py.
"""

import logging
import re
import sqlite3
from pathlib import Path

logger = logging.getLogger(__name__)


class FTSStore:
    """BM25 full-text search over indexed code chunks using SQLite FTS5."""

    def __init__(self, db_path: Path) -> None:
        self._db = Path(db_path)
        self._db.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._db))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        try:
            with self._connect() as conn:
                conn.execute("""
                    CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
                        content,
                        source_file UNINDEXED,
                        section     UNINDEXED,
                        line_start  UNINDEXED,
                        tokenize='unicode61 remove_diacritics 1'
                    )
                """)
        except sqlite3.OperationalError as e:
            if "no such module: fts5" in str(e).lower():
                raise RuntimeError(
                    "SQLite FTS5 not available in this Python build — "
                    "BM25 hybrid search disabled."
                ) from e
            raise

    def insert_chunks(self, chunks: list[dict]) -> int:
        """Insert a batch of chunks. Each dict needs content, source_file, section, line_start."""
        if not chunks:
            return 0
        with self._connect() as conn:
            conn.executemany(
                "INSERT INTO chunks_fts(content, source_file, section, line_start) "
                "VALUES (?, ?, ?, ?)",
                [
                    (c["content"], c["source_file"], c.get("section", ""), c.get("line_start", 0))
                    for c in chunks
                ],
            )
        return len(chunks)

    def delete_by_source(self, source_file: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM chunks_fts WHERE source_file = ?", (source_file,))

    def clear(self) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM chunks_fts")

    def search(self, query: str, limit: int = 10) -> list[dict]:
        """BM25 search. Returns list of dicts: source_file, section, line_start, content, score."""
        fts_query = to_fts5_query(query)
        if not fts_query:
            return []
        try:
            with self._connect() as conn:
                rows = conn.execute(
                    """
                    SELECT source_file, section, line_start, content,
                           -bm25(chunks_fts) AS score
                    FROM chunks_fts
                    WHERE chunks_fts MATCH ?
                    ORDER BY score DESC
                    LIMIT ?
                    """,
                    (fts_query, limit),
                ).fetchall()
            return [dict(r) for r in rows]
        except sqlite3.OperationalError:
            return []

    def count(self) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) FROM chunks_fts").fetchone()
            return row[0] if row else 0


def to_fts5_query(query: str) -> str:
    """Convert a free-text query to a safe FTS5 MATCH expression.

    Short queries (1-3 words) use OR to improve recall for type-signature
    lookups like "str None". Longer queries use implicit AND (all terms
    must appear) for precision.
    """
    # Strip FTS5 operator characters
    clean = re.sub(r'["""()\[\]{}\*\^\~\:\-\>\<\+]', " ", query)
    terms = [t for t in clean.split() if len(t) >= 2]
    if not terms:
        return ""
    if len(terms) == 1:
        return f"{terms[0]}*"
    if len(terms) <= 3:
        # OR gives better recall for short exact-term queries
        return " OR ".join(terms)
    # Longer query: all terms must appear
    return " ".join(terms)
