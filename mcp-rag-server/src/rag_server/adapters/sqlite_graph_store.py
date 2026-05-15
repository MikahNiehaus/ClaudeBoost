"""SQLite-backed graph store for code structure edges.

Stored at <project>/workspace/.rag-index/graph.db alongside the ChromaDB index.
ChromaDB metadata is scalar-only, so graph edges live in a separate SQLite file.
"""

import logging
import sqlite3
from pathlib import Path
from typing import Sequence

from rag_server.ports.graph_port import GraphEdge, GraphStorePort

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS edges (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    source_file   TEXT NOT NULL,
    source_symbol TEXT NOT NULL,
    target_file   TEXT NOT NULL,
    target_symbol TEXT NOT NULL,
    edge_type     TEXT NOT NULL,
    confidence    TEXT NOT NULL,
    UNIQUE(source_file, source_symbol, target_file, target_symbol, edge_type)
);

CREATE INDEX IF NOT EXISTS idx_source_file ON edges (source_file);
CREATE INDEX IF NOT EXISTS idx_target_file ON edges (target_file);
"""


def _resolve_symbol(target_symbol: str, source_file: str, file_map: dict[str, str]) -> str:
    """Try to map *target_symbol* to a project-relative file path.

    Tries keys in priority order:
    1. Exact key match (already in file_map).
    2. Dotted → slash form  (foo.bar → foo/bar).
    3. Slash → dotted form  (foo/bar → foo.bar).
    4. Relative import resolved against source_file directory.
    Returns empty string if no match.
    """
    if not target_symbol:
        return ""

    # 1. Exact match
    if target_symbol in file_map:
        return file_map[target_symbol]

    # 2. Dotted → slash
    slash_form = target_symbol.replace(".", "/")
    if slash_form in file_map:
        return file_map[slash_form]

    # 3. Slash → dotted
    dot_form = target_symbol.replace("/", ".")
    if dot_form in file_map:
        return file_map[dot_form]

    # 4. Relative import (starts with . or ..)
    if target_symbol.startswith("."):
        source_dir = "/".join(source_file.split("/")[:-1])
        # Strip leading dots to count levels up
        stripped = target_symbol.lstrip(".")
        levels_up = len(target_symbol) - len(stripped) - 1  # -1 for the first dot = same dir
        parts = source_dir.split("/") if source_dir else []
        if levels_up > 0:
            parts = parts[:-levels_up] if levels_up <= len(parts) else []
        rel_slash = "/".join(parts + [stripped.replace(".", "/")]) if stripped else "/".join(parts)
        if rel_slash in file_map:
            return file_map[rel_slash]
        rel_dot = rel_slash.replace("/", ".")
        if rel_dot in file_map:
            return file_map[rel_dot]

    return ""


class SQLiteGraphStore(GraphStorePort):
    """Stores and queries code graph edges in a local SQLite database."""

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(_SCHEMA)
        logger.debug("Graph store initialised at %s", self._db_path)

    def add_edges(self, edges: Sequence[GraphEdge]) -> None:
        if not edges:
            return
        rows = [
            (e.source_file, e.source_symbol, e.target_file, e.target_symbol,
             e.edge_type, e.confidence)
            for e in edges
        ]
        with self._connect() as conn:
            conn.executemany(
                """INSERT OR IGNORE INTO edges
                   (source_file, source_symbol, target_file, target_symbol, edge_type, confidence)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                rows,
            )
        logger.debug("Stored %d edges", len(rows))

    def get_neighbours(
        self,
        file: str,
        symbol: str | None = None,
        depth: int = 1,
    ) -> list[GraphEdge]:
        """Return all edges incident on *file* (as source or target).

        depth > 1 is reserved; only depth=1 is implemented.
        """
        with self._connect() as conn:
            if symbol:
                rows = conn.execute(
                    """SELECT * FROM edges
                       WHERE (source_file = ? AND source_symbol = ?)
                          OR (target_file = ? AND target_symbol = ?)""",
                    (file, symbol, file, symbol),
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT * FROM edges
                       WHERE source_file = ? OR target_file = ?""",
                    (file, file),
                ).fetchall()

        return [
            GraphEdge(
                source_file=r["source_file"],
                source_symbol=r["source_symbol"],
                target_file=r["target_file"],
                target_symbol=r["target_symbol"],
                edge_type=r["edge_type"],
                confidence=r["confidence"],
            )
            for r in rows
        ]

    def delete_edges_for_file(self, file: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM edges WHERE source_file = ?", (file,))

    def has_graph(self) -> bool:
        with self._connect() as conn:
            count = conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
        return count > 0

    def resolve_target_files(self, file_map: dict[str, str]) -> int:
        """Update target_file='' edges whose target_symbol resolves via file_map.

        file_map keys are module-name variants (dotted, slash-separated, with/without
        extension). For each unresolved edge, we try several normalisation strategies
        before giving up and leaving target_file empty.
        """
        with self._connect() as conn:
            unresolved = conn.execute(
                "SELECT id, target_symbol, source_file FROM edges WHERE target_file = ''"
            ).fetchall()

        if not unresolved:
            return 0

        updates: list[tuple[str, int]] = []
        for row in unresolved:
            resolved = _resolve_symbol(row["target_symbol"], row["source_file"], file_map)
            if resolved:
                updates.append((resolved, row["id"]))

        if updates:
            with self._connect() as conn:
                conn.executemany(
                    "UPDATE edges SET target_file = ? WHERE id = ?",
                    updates,
                )
        return len(updates)
