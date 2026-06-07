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


def _expand_code_tokens(text: str) -> str:
    """Return extra sub-tokens from camelCase and underscore identifiers in text.

    Only returns the NEW tokens (not originals) so they can be appended to content
    before FTS insertion. FTS5 then matches both the full identifier and its parts.

    "getUserById"            -> "by get id user"
    "parse_xml_doc"          -> "doc parse xml"
    "_cancellationTokenSource" -> "cancellation source token"
    Pure prose with no identifiers returns "".
    """
    extra: set[str] = set()
    # _* prefix handles C# private fields like _cancellationTokenSource
    for ident in re.findall(r'_*[a-zA-Z][a-zA-Z0-9_]{3,}', text):
        ident = ident.lstrip('_')
        # Split camelCase boundaries
        split = re.sub(r'([a-z])([A-Z])', r'\1 \2', ident)
        split = re.sub(r'([A-Z]+)([A-Z][a-z])', r'\1 \2', split)
        # Split underscores; keep parts >= 2 chars so "id", "db", "by" are kept
        parts = [p.lower() for p in re.split(r'[_\s]+', split) if len(p) >= 2]
        if len(parts) > 1:
            extra.update(parts)
    return ' '.join(sorted(extra))


class FTSStore:
    """BM25 full-text search over indexed code chunks using SQLite FTS5."""

    def __init__(self, db_path: Path) -> None:
        self._db = Path(db_path)
        self._db.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._db), timeout=30)
        conn.row_factory = sqlite3.Row
        # WAL allows concurrent readers during writes; busy_timeout retries instead of
        # raising "database is locked" immediately.
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=30000")
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
                    (
                        _fts_content(c["content"]),
                        c["source_file"],
                        c.get("section", ""),
                        c.get("line_start", 0),
                    )
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
        except sqlite3.OperationalError as e:
            logger.warning("FTS search failed (returning empty): %s", e)
            return []

    def count(self) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) FROM chunks_fts").fetchone()
            return row[0] if row else 0


def _fts_content(content: str) -> str:
    """Append expanded code tokens to content before FTS insertion.

    Keeps original content intact for display; appends split sub-tokens so
    FTS5 can match both "getUserById" and "get", "user", "by", "id".
    """
    extra = _expand_code_tokens(content)
    if extra:
        return content + " " + extra
    return content


_FTS_STOP_WORDS = frozenset({
    "the", "a", "an", "is", "it", "in", "of", "to", "for", "on", "at",
    "by", "or", "and", "if", "be", "as", "with", "from", "that", "this",
    "are", "was", "were", "has", "have", "not", "no", "do", "can", "will",
    "get", "set", "its", "all", "any", "when", "then", "than", "into",
    "use", "used", "uses", "using", "given", "via", "per", "each",
})


def to_fts5_query(query: str) -> str:
    """Convert a free-text query to a safe FTS5 MATCH expression.

    Short queries (1-3 meaningful terms) use OR for type-signature recall.
    Medium queries (4-6 terms) use implicit AND for precision.
    Long NL queries (>6 terms) return "" — FTS5 AND on docstrings never matches
    code-only content, so skip to dense-only search.
    """
    # Keep only alphanumeric, underscores (code identifiers), and whitespace.
    # FTS5 syntax errors on punctuation like periods, commas, backticks, etc.
    clean = re.sub(r'[^a-zA-Z0-9_\s]', " ", query)
    # Filter: min 2 chars, not a stop word
    terms = [t for t in clean.split() if len(t) >= 2 and t.lower() not in _FTS_STOP_WORDS]
    if not terms:
        return ""
    if len(terms) > 5:
        # Long NL query: FTS5 AND would require all N terms in code — nearly never matches.
        # Defer to dense retrieval only.
        return ""
    if len(terms) == 1:
        return f"{terms[0]}*"
    if len(terms) <= 3:
        # OR gives better recall for short exact-term queries like "str None"
        return " OR ".join(terms)
    # 4-6 meaningful terms: AND (all must appear)
    return " ".join(terms)
