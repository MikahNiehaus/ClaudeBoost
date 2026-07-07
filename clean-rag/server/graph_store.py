"""SQLite-backed graph store for code structure edges.

Stored at databases/_projects/<hash>/graph.db alongside the ChromaDB index.
Tracks import/export/inheritance relationships between files for structural
code search (mode=graph).

Ported from ClaudeBoost mcp-rag-server. Fully self-contained, no external imports.
"""

import logging
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# GraphEdge dataclass (inline, no port dependency)
# ---------------------------------------------------------------------------

@dataclass
class GraphEdge:
    """A directed edge in the code graph.

    source_file / source_symbol -> target_file / target_symbol
    edge_type:  "calls" | "imports" | "inherits" | "implements"
    confidence: "EXTRACTED" (direct AST read) | "INFERRED" (name match heuristic)
    """
    source_file: str
    source_symbol: str
    target_file: str
    target_symbol: str
    edge_type: str
    confidence: str


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

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

CREATE TABLE IF NOT EXISTS node_pagerank (
    file        TEXT PRIMARY KEY,
    score       REAL NOT NULL,
    computed_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

_EXTERNAL_SENTINEL = "_external_"


# ---------------------------------------------------------------------------
# External symbol detection
# ---------------------------------------------------------------------------

# Python stdlib top level names (fallback for Python < 3.10)
_PYTHON_STDLIB_PREFIXES = frozenset({
    "abc", "ast", "asyncio", "base64", "binascii", "bisect", "builtins",
    "codecs", "collections", "concurrent", "configparser", "contextlib",
    "copy", "csv", "ctypes", "dataclasses", "datetime", "dbm", "decimal",
    "email", "enum", "fnmatch", "fractions", "ftplib", "functools", "gc",
    "getopt", "getpass", "glob", "gzip", "hashlib", "heapq", "html",
    "http", "imaplib", "inspect", "io", "itertools", "json", "logging",
    "lzma", "marshal", "math", "mmap", "multiprocessing", "operator",
    "os", "pathlib", "pickle", "platform", "poplib", "pprint", "queue",
    "random", "re", "readline", "reprlib", "rlcompleter", "selectors",
    "shelve", "shutil", "signal", "smtplib", "socket", "sqlite3",
    "ssl", "stat", "statistics", "string", "struct", "subprocess",
    "sys", "tarfile", "tempfile", "textwrap", "threading", "time",
    "token", "tokenize", "traceback", "types", "typing", "unittest",
    "urllib", "uuid", "warnings", "weakref", "xml", "xmlrpc", "zipfile",
    "zlib", "bz2", "array", "cmath", "grp", "pwd", "termios", "tty",
})


def _get_stdlib_names() -> frozenset:
    """Return Python stdlib top level module names.

    Resolution: sys.stdlib_module_names (3.10+) > stdlibs package > hardcoded fallback.
    """
    if hasattr(sys, "stdlib_module_names"):
        return frozenset(sys.stdlib_module_names)
    try:
        from stdlibs import module_names
        return frozenset(module_names)
    except ImportError:
        return _PYTHON_STDLIB_PREFIXES


_STDLIB_NAMES: frozenset = _get_stdlib_names()

# C# BCL and common NuGet top level namespaces
_CS_EXTERNAL_PREFIXES = frozenset({
    "System", "Microsoft", "Newtonsoft", "AutoMapper",
    "Serilog", "FluentValidation", "MediatR", "Dapper",
    "NUnit", "Xunit", "Moq", "FluentAssertions", "Bogus",
    "Azure", "Amazon", "Google", "Twilio", "SendGrid",
    "Polly", "Hangfire", "Quartz", "MassTransit", "RabbitMQ",
    "StackExchange", "MongoDB", "Npgsql", "MySql", "Oracle",
    "JWT", "IdentityModel", "Humanizer", "CsvHelper",
    "Kendo", "Org",
})

# Java stdlib and common third party top level packages
_JAVA_EXTERNAL_PREFIXES = frozenset({
    "java", "javax", "jakarta",
    "sun", "com.sun", "jdk",
    "org.junit", "org.testng",
    "org.apache", "org.slf4j",
    "org.springframework",
    "com.google", "com.fasterxml",
    "android", "kotlin",
})


def _is_external_symbol(
    symbol: str, source_file: str, go_module_prefixes: set | None,
) -> bool:
    """Return True if symbol is a stdlib or external dep import.

    JS/TS: non relative import (no leading dot) = npm package.
    Python: single segment names = stdlib/third party.
    C#: known BCL/NuGet top level namespace.
    Go: no dot in first path segment = stdlib; domain not in project modules = external.
    """
    if not symbol or symbol.startswith("."):
        return False

    if source_file.endswith((".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs")):
        if symbol.startswith("@/"):
            return False
        return True

    if source_file.endswith(".py"):
        first_segment = symbol.split(".")[0]
        if "/" not in symbol and "." not in symbol:
            return True
        return first_segment in _STDLIB_NAMES

    if source_file.endswith((".cs", ".cshtml")):
        first_segment = symbol.split(".")[0]
        return first_segment in _CS_EXTERNAL_PREFIXES

    if source_file.endswith(".java"):
        dotted = symbol.split(".")
        one = dotted[0]
        two = ".".join(dotted[:2]) if len(dotted) >= 2 else ""
        return one in _JAVA_EXTERNAL_PREFIXES or two in _JAVA_EXTERNAL_PREFIXES

    if not source_file.endswith(".go"):
        return False
    parts = symbol.split("/")
    first = parts[0]
    if "." not in first:
        return True
    if go_module_prefixes:
        for prefix in go_module_prefixes:
            if symbol == prefix or symbol.startswith(prefix + "/"):
                return False
    return True


# ---------------------------------------------------------------------------
# Symbol resolution
# ---------------------------------------------------------------------------

_JS_EXTENSIONS = (".js", ".jsx", ".ts", ".tsx", ".mjs")
_JS_SOURCE_EXTS = (".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs")


def _resolve_symbol(
    target_symbol: str, source_file: str, file_map: dict[str, str],
) -> str:
    """Try to map target_symbol to a project relative file path.

    Tries keys in priority order:
    1. Exact match
    2. Dotted to slash (foo.bar -> foo/bar)
    3. Slash to dotted (foo/bar -> foo.bar)
    4. Relative import resolved against source_file directory
    5. Extension less JS/TS relative imports (./Foo -> Foo.jsx, Foo/index.js)
    6. Path alias @/foo -> foo (project root alias)
    Returns empty string if no match.
    """
    if not target_symbol:
        return ""

    # Strip "as <alias>" suffix from Python imports
    if " as " in target_symbol:
        target_symbol = target_symbol.split(" as ")[0].strip()
    if not target_symbol:
        return ""

    # 1. Exact match
    if target_symbol in file_map:
        return file_map[target_symbol]

    # 2. Dotted to slash
    slash_form = target_symbol.replace(".", "/")
    if slash_form in file_map:
        return file_map[slash_form]

    # 3. Slash to dotted
    dot_form = target_symbol.replace("/", ".")
    if dot_form in file_map:
        return file_map[dot_form]

    # 4. Relative import (starts with . or ..)
    if target_symbol.startswith("."):
        source_dir = "/".join(source_file.split("/")[:-1])
        stripped_with_sep = target_symbol.lstrip(".")
        levels_up = len(target_symbol) - len(stripped_with_sep) - 1
        stripped = stripped_with_sep.lstrip("/")
        parts = source_dir.split("/") if source_dir else []
        if levels_up > 0:
            parts = parts[:-levels_up] if levels_up <= len(parts) else []
        if "/" in stripped:
            rel_slash = "/".join(parts + [stripped]) if stripped else "/".join(parts)
        else:
            rel_slash = "/".join(parts + [stripped.replace(".", "/")]) if stripped else "/".join(parts)
        if rel_slash in file_map:
            return file_map[rel_slash]
        rel_dot = rel_slash.replace("/", ".")
        if rel_dot in file_map:
            return file_map[rel_dot]
        # 5. Extension less JS/TS relative imports
        if source_file.endswith(_JS_SOURCE_EXTS):
            if rel_slash.endswith(".js") and source_file.endswith((".ts", ".tsx")):
                stem = rel_slash[:-3]
                for ts_ext in (".ts", ".tsx"):
                    if stem + ts_ext in file_map:
                        return file_map[stem + ts_ext]
            for ext in _JS_EXTENSIONS:
                if rel_slash + ext in file_map:
                    return file_map[rel_slash + ext]
                if rel_slash + "/index" + ext in file_map:
                    return file_map[rel_slash + "/index" + ext]

    # 6. Path alias: @/foo/bar -> look up "foo/bar"
    if target_symbol.startswith("@/") and source_file.endswith(_JS_SOURCE_EXTS):
        alias_path = target_symbol[2:]
        if alias_path in file_map:
            return file_map[alias_path]
        for ext in _JS_EXTENSIONS:
            if alias_path + ext in file_map:
                return file_map[alias_path + ext]
            if alias_path + "/index" + ext in file_map:
                return file_map[alias_path + "/index" + ext]

    return ""


# ---------------------------------------------------------------------------
# SQLiteGraphStore
# ---------------------------------------------------------------------------

class SQLiteGraphStore:
    """Stores and queries code graph edges in a local SQLite database."""

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._db_path), timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=30000")
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(_SCHEMA)
        logger.debug("Graph store initialised at %s", self._db_path)

    def add_edges(self, edges: Sequence[GraphEdge]) -> None:
        """Persist a batch of edges (duplicates ignored via INSERT OR IGNORE)."""
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
        direction: str = "both",
        max_nodes: int = 200,
    ) -> list[GraphEdge]:
        """Return edges incident on file, expanded transitively out to `depth` hops.

        depth: number of hops, clamped to 1-5 (was hardcoded to a max of 2).
        direction: "both" (default, original behavior -- file may be either
            source_file or target_file of a matching edge), "callers" (only
            follow edges where the frontier is target_file -- i.e. the other
            side has an edge pointing INTO the frontier, meaning it depends
            on/calls/imports it -- this is the "blast radius" direction),
            or "dependencies" (only follow edges where the frontier is
            source_file -- what the frontier itself points at).
        max_nodes: if a hop's frontier would exceed this, prune to the top
            max_nodes by PageRank (get_all_pagerank()) before expanding
            further -- keeps deep traversals from exploding on hub files.
            Falls back to deterministic (sorted) truncation if no PageRank
            data exists yet (e.g. a project indexed before compute_pagerank
            was wired into indexing.py).
        """
        depth = min(max(depth, 1), 5)
        if direction not in ("both", "callers", "dependencies"):
            direction = "both"

        def _rows_for_frontier(conn, files: list[str]) -> list:
            if not files:
                return []
            ph = ",".join("?" * len(files))
            if direction == "callers":
                return conn.execute(
                    f"SELECT * FROM edges WHERE target_file IN ({ph})", files,
                ).fetchall()
            elif direction == "dependencies":
                return conn.execute(
                    f"SELECT * FROM edges WHERE source_file IN ({ph})", files,
                ).fetchall()
            else:
                return conn.execute(
                    f"SELECT * FROM edges WHERE source_file IN ({ph}) OR target_file IN ({ph})",
                    files + files,
                ).fetchall()

        def _next_hop_neighbor(row) -> str | None:
            """The newly-discovered node on the far side of an edge, respecting direction."""
            sf, tf = row["source_file"], row["target_file"]
            if direction == "callers":
                candidate = sf  # matched because tf was in the frontier
            elif direction == "dependencies":
                candidate = tf  # matched because sf was in the frontier
            else:
                candidate = tf if sf in visited else sf
            if not candidate or candidate == _EXTERNAL_SENTINEL:
                return None
            return candidate

        def _prune(frontier: set[str]) -> set[str]:
            if len(frontier) <= max_nodes:
                return frontier
            pagerank = self.get_all_pagerank()
            if pagerank:
                ranked = sorted(frontier, key=lambda f: pagerank.get(f, 0.0), reverse=True)
            else:
                ranked = sorted(frontier)  # deterministic fallback, no pagerank data yet
            return set(ranked[:max_nodes])

        with self._connect() as conn:
            if symbol:
                depth1_rows = conn.execute(
                    """SELECT * FROM edges
                       WHERE (source_file = ? AND source_symbol = ?)
                          OR (target_file = ? AND target_symbol = ?)""",
                    (file, symbol, file, symbol),
                ).fetchall()
            else:
                depth1_rows = conn.execute(
                    """SELECT * FROM edges
                       WHERE source_file = ? OR target_file = ?""",
                    (file, file),
                ).fetchall()
                if direction == "callers":
                    depth1_rows = [r for r in depth1_rows if r["target_file"] == file]
                elif direction == "dependencies":
                    depth1_rows = [r for r in depth1_rows if r["source_file"] == file]

            all_rows = list(depth1_rows)
            seen_edges = {(r["source_file"], r["target_file"], r["edge_type"]) for r in all_rows}
            visited = {file}

            frontier: set[str] = set()
            for r in depth1_rows:
                sf, tf = r["source_file"], r["target_file"]
                if sf != file and sf and sf != _EXTERNAL_SENTINEL:
                    frontier.add(sf)
                if tf != file and tf and tf != _EXTERNAL_SENTINEL:
                    frontier.add(tf)
            visited |= frontier

            hop = 2
            while hop <= depth and frontier:
                frontier = _prune(frontier)
                hop_rows = _rows_for_frontier(conn, list(frontier))
                next_frontier: set[str] = set()
                for r in hop_rows:
                    key = (r["source_file"], r["target_file"], r["edge_type"])
                    if key not in seen_edges:
                        seen_edges.add(key)
                        all_rows.append(r)
                    neighbor = _next_hop_neighbor(r)
                    if neighbor and neighbor not in visited:
                        next_frontier.add(neighbor)
                visited |= next_frontier
                frontier = next_frontier
                hop += 1

        return [
            GraphEdge(
                source_file=r["source_file"],
                source_symbol=r["source_symbol"],
                target_file=r["target_file"],
                target_symbol=r["target_symbol"],
                edge_type=r["edge_type"],
                confidence=r["confidence"],
            )
            for r in all_rows
        ]

    def delete_edges_for_file(self, file: str) -> None:
        """Remove all edges where source_file == file (used on incremental reindex)."""
        with self._connect() as conn:
            conn.execute("DELETE FROM edges WHERE source_file = ?", (file,))

    def has_graph(self) -> bool:
        """Return True if at least one edge has been stored."""
        with self._connect() as conn:
            count = conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
        return count > 0

    def count_edges(self) -> int:
        """Total edge count."""
        with self._connect() as conn:
            return conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]

    def get_all_edges(self) -> list[GraphEdge]:
        """Return every stored edge. Used for whole-graph analysis (PageRank)."""
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM edges").fetchall()
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

    def count_resolved_edges(self) -> int:
        """Count edges with a resolved target_file (not empty, not external)."""
        with self._connect() as conn:
            return conn.execute(
                "SELECT COUNT(*) FROM edges WHERE target_file != '' AND target_file != ?",
                (_EXTERNAL_SENTINEL,),
            ).fetchone()[0]

    def count_unresolved_edges(self) -> int:
        """Count edges with target_file='' (truly unresolved, excludes external)."""
        with self._connect() as conn:
            return conn.execute(
                "SELECT COUNT(*) FROM edges WHERE target_file = ''"
            ).fetchone()[0]

    def delete_ghost_edges(self, current_files: set[str]) -> int:
        """Remove edges whose source_file or resolved target_file is no longer indexed.

        Uses a temporary table for large sets. Returns deleted row count.
        """
        files = list(current_files)
        with self._connect() as conn:
            conn.execute(
                "CREATE TEMPORARY TABLE IF NOT EXISTS _current_files (path TEXT PRIMARY KEY)"
            )
            conn.execute("DELETE FROM _current_files")
            conn.executemany(
                "INSERT OR IGNORE INTO _current_files VALUES (?)", [(f,) for f in files]
            )
            result = conn.execute(
                """DELETE FROM edges
                   WHERE source_file NOT IN (SELECT path FROM _current_files)
                      OR (target_file != '' AND target_file != ?
                          AND target_file NOT IN (SELECT path FROM _current_files))
                """,
                (_EXTERNAL_SENTINEL,),
            )
            return result.rowcount

    def resolve_target_files(
        self, file_map: dict[str, str], go_module_prefixes: set[str] | None = None,
    ) -> int:
        """Update target_file='' edges whose target_symbol resolves via file_map.

        External/stdlib imports are marked '_external_' so they don't count as unresolved.
        Returns the count of edges resolved to real project files (not external).
        """
        with self._connect() as conn:
            unresolved = conn.execute(
                "SELECT id, target_symbol, source_file FROM edges WHERE target_file = ''"
            ).fetchall()

        if not unresolved:
            return 0

        # Build set of project namespace segments for fallback detection
        project_namespaces: set[str] = set()
        for k in file_map:
            parts = k.replace("\\", "/").split("/")
            for part in parts:
                project_namespaces.add(part)

        updates: list[tuple[str, int]] = []
        external_count = 0
        for row in unresolved:
            resolved = _resolve_symbol(row["target_symbol"], row["source_file"], file_map)
            if resolved:
                updates.append((resolved, row["id"]))
            elif _is_external_symbol(
                row["target_symbol"], row["source_file"], go_module_prefixes,
            ):
                updates.append((_EXTERNAL_SENTINEL, row["id"]))
                external_count += 1
            elif row["source_file"].endswith(".py"):
                # Fallback for Python: dotted third party imports not caught above
                symbol = row["target_symbol"]
                if " as " in symbol:
                    symbol = symbol.split(" as ")[0].strip()
                first_seg = symbol.split(".")[0]
                if first_seg and first_seg not in project_namespaces:
                    updates.append((_EXTERNAL_SENTINEL, row["id"]))
                    external_count += 1

        if updates:
            with self._connect() as conn:
                conn.executemany(
                    "UPDATE edges SET target_file = ? WHERE id = ?",
                    updates,
                )

        resolved_count = len(updates) - external_count
        if external_count:
            logger.debug(
                "Marked %d stdlib/external imports as _external_", external_count,
            )
        return resolved_count

    def save_pagerank(self, scores: dict[str, float]) -> None:
        """Replace all PageRank scores with a fresh set."""
        if not scores:
            return
        rows = list(scores.items())
        with self._connect() as conn:
            conn.execute("DELETE FROM node_pagerank")
            conn.executemany(
                "INSERT INTO node_pagerank (file, score) VALUES (?, ?)",
                rows,
            )
        logger.debug("Saved PageRank scores for %d nodes", len(rows))

    def get_all_pagerank(self) -> dict[str, float]:
        """Return all stored PageRank scores keyed by file path."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT file, score FROM node_pagerank"
            ).fetchall()
        return {r["file"]: r["score"] for r in rows}


def compute_pagerank(graph_store: "SQLiteGraphStore") -> dict[str, float]:
    """Score each file by how many other files import or reference it.

    Ported from ClaudeBoost mcp-rag-server (core/community.py) -- the
    save_pagerank()/get_all_pagerank() storage methods above were already
    ported, but this computation function (the only thing that actually
    populates node_pagerank) never was, so the table has been empty since
    this store was introduced. Uses PageRank on a directed graph where
    A->B means A imports/references B, so widely-imported files (core
    modules, shared utilities) get high scores. Returns {} on any failure
    or if NetworkX is not available.
    """
    try:
        import networkx as nx
    except ImportError:
        logger.debug("PageRank skipped: networkx not installed")
        return {}

    edges = graph_store.get_all_edges()
    if not edges:
        return {}

    try:
        graph: "nx.DiGraph" = nx.DiGraph()
        for e in edges:
            graph.add_node(e.source_file)
            if e.target_file and e.target_file != _EXTERNAL_SENTINEL:
                graph.add_node(e.target_file)
                graph.add_edge(e.source_file, e.target_file)
        if graph.number_of_nodes() == 0:
            return {}
        scores = nx.pagerank(graph, alpha=0.85, max_iter=100)
        logger.info("PageRank computed for %d nodes", len(scores))
        return scores
    except Exception:
        logger.exception("PageRank computation failed")
        return {}
