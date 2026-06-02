"""SQLite-backed graph store for code structure edges.

Stored at <project>/workspace/.rag-index/graph.db alongside the ChromaDB index.
ChromaDB metadata is scalar-only, so graph edges live in a separate SQLite file.
"""

import logging
import sqlite3
import sys
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

CREATE TABLE IF NOT EXISTS communities (
    file          TEXT PRIMARY KEY,
    community_id  INTEGER NOT NULL,
    updated_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_community_id ON communities (community_id);

CREATE TABLE IF NOT EXISTS community_summaries (
    community_id  INTEGER PRIMARY KEY,
    summary       TEXT NOT NULL,
    member_hash   TEXT NOT NULL,
    model         TEXT NOT NULL,
    generated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


_EXTERNAL_SENTINEL = "_external_"


# Python stdlib top-level names — fallback for Python < 3.10 or when stdlibs isn't installed.
# sys.stdlib_module_names (3.10+) and the stdlibs package are authoritative; this list
# is a safety net only.
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


def _get_stdlib_names() -> frozenset[str]:
    """Return the complete set of Python stdlib top-level module names.

    Resolution order (best → fallback):
    1. sys.stdlib_module_names — accurate for the running interpreter (Python 3.10+)
    2. stdlibs.module_names — cross-version superset covering all Python 3.x releases
    3. _PYTHON_STDLIB_PREFIXES — hardcoded fallback for environments without stdlibs
    """
    if hasattr(sys, "stdlib_module_names"):
        return frozenset(sys.stdlib_module_names)
    try:
        from stdlibs import module_names  # type: ignore[import-not-found]
        return frozenset(module_names)
    except ImportError:
        return _PYTHON_STDLIB_PREFIXES


# Resolved once at import time — no per-call overhead.
_STDLIB_NAMES: frozenset[str] = _get_stdlib_names()

_CS_EXTERNAL_PREFIXES = frozenset({
    "System", "Microsoft", "Newtonsoft", "AutoMapper",
    "Serilog", "FluentValidation", "MediatR", "Dapper",
    "NUnit", "Xunit", "Moq", "FluentAssertions", "Bogus",
    "Azure", "Amazon", "Google", "Twilio", "SendGrid",
    "Polly", "Hangfire", "Quartz", "MassTransit", "RabbitMQ",
    "StackExchange", "MongoDB", "Npgsql", "MySql", "Oracle",
    "JWT", "IdentityModel", "Humanizer", "CsvHelper",
    "Kendo",  # NuGet: Kendo.Mvc, Kendo.Mvc.UI, Kendo.Mvc.Infrastructure
    "Org",    # NuGet: Org.BouncyCastle.*, Org.Apache.*, etc.
})

# Java stdlib and common third-party top-level packages that are always external.
# Project-internal Java classes use the project's own base package (e.g. io.github.ccxt).
_JAVA_EXTERNAL_PREFIXES = frozenset({
    "java", "javax", "jakarta",       # JDK stdlib
    "sun", "com.sun", "jdk",          # JDK internals
    "org.junit", "org.testng",        # test frameworks
    "org.apache", "org.slf4j",        # Apache / logging
    "org.springframework",            # Spring
    "com.google", "com.fasterxml",    # Guava, Jackson
    "android", "kotlin",              # Android / Kotlin stdlib
})


def _is_external_symbol(
    symbol: str, source_file: str, go_module_prefixes: set[str] | None
) -> bool:
    """Return True if symbol is a stdlib or external-dep import.

    For JS/TS: any non-relative import (no leading dot) is an npm package → external.
    For Python: single-segment names with no slashes or dots are stdlib/third-party.
    For C#: using directives whose first namespace segment is a known BCL/NuGet prefix.
    For Go:
      - No dot in first path segment  → Go stdlib  (os, fmt, net/http, encoding/json)
      - Domain-like first segment that is NOT any project module → external dep
    """
    if not symbol or symbol.startswith("."):
        return False

    if source_file.endswith((".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs")):
        # Path aliases like @/ map to project-internal directories — not npm packages.
        # Standard scoped npm packages use @scope/name (word chars before the first slash).
        # Path aliases use @/ (slash immediately after @) — let resolution handle them.
        if symbol.startswith("@/"):
            return False
        # All other non-relative JS/TS imports are npm packages or node builtins → external.
        # Relative imports (./foo, ../bar) already return False above.
        return True

    if source_file.endswith(".py"):
        # Single-segment names (os, sys, re, chromadb, fastapi, ...) are always external —
        # stdlib or third-party top-level; project-internal modules use dotted or relative paths.
        # Multi-segment names: check whether the first segment is a stdlib package.
        # Third-party dotted names (mcp.server, rich.style, etc.) that pass here are caught
        # by the namespace fallback in resolve_target_files.
        first_segment = symbol.split(".")[0]
        if "/" not in symbol and "." not in symbol:
            return True
        return first_segment in _STDLIB_NAMES

    if source_file.endswith((".cs", ".cshtml")):
        # C# using directives: mark known BCL and NuGet top-level namespaces as external
        # so they don't inflate the unresolved-edge count.
        first_segment = symbol.split(".")[0]
        return first_segment in _CS_EXTERNAL_PREFIXES

    if source_file.endswith(".java"):
        # Java: mark JDK stdlib and common third-party packages as external.
        # Project-internal imports (e.g. io.github.ccxt.*) are NOT in _JAVA_EXTERNAL_PREFIXES
        # and will fall through to the file-map resolver.
        dotted = symbol.split(".")
        # Check single-segment (java, javax) and two-segment (org.junit, com.google) prefixes
        one = dotted[0]
        two = ".".join(dotted[:2]) if len(dotted) >= 2 else ""
        return one in _JAVA_EXTERNAL_PREFIXES or two in _JAVA_EXTERNAL_PREFIXES

    if not source_file.endswith(".go"):
        return False
    parts = symbol.split("/")
    first = parts[0]
    if "." not in first:
        return True  # Go stdlib (os, fmt, net, encoding, ...)
    if go_module_prefixes:
        for prefix in go_module_prefixes:
            if symbol == prefix or symbol.startswith(prefix + "/"):
                return False  # project-internal import that failed to resolve
    return True  # external domain-hosted dep (github.com/other, golang.org/x, etc.)


_JS_EXTENSIONS = (".js", ".jsx", ".ts", ".tsx", ".mjs")
_JS_SOURCE_EXTS = (".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs")


def _resolve_symbol(target_symbol: str, source_file: str, file_map: dict[str, str]) -> str:
    """Try to map *target_symbol* to a project-relative file path.

    Tries keys in priority order:
    1. Exact key match (already in file_map).
    2. Dotted → slash form  (foo.bar → foo/bar).
    3. Slash → dotted form  (foo/bar → foo.bar).
    4. Relative import resolved against source_file directory.
    5. Extension-less JS/TS relative imports (./Foo → Foo.jsx, Foo/index.js).
    6. Path alias @/foo → foo (project root alias common in Expo/Next projects).
    Returns empty string if no match.
    """
    if not target_symbol:
        return ""

    # Strip "as <alias>" suffix — produced by Python "import X as Y" and
    # "from X import Y as Z" statements. The alias is not part of the module path.
    if " as " in target_symbol:
        target_symbol = target_symbol.split(" as ")[0].strip()
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
        # Strip leading dots to count levels up, then strip the path separator.
        # JS-style: "./foo" → lstrip(".") = "/foo" → levels_up=0, stripped="foo"
        #           "../foo" → lstrip(".") = "/foo" → levels_up=1, stripped="foo"
        stripped_with_sep = target_symbol.lstrip(".")
        levels_up = len(target_symbol) - len(stripped_with_sep) - 1  # -1: first dot = same dir
        stripped = stripped_with_sep.lstrip("/")  # remove the path separator after the dots
        parts = source_dir.split("/") if source_dir else []
        if levels_up > 0:
            parts = parts[:-levels_up] if levels_up <= len(parts) else []
        # Only convert dots to slashes for dotted module names (e.g. foo.bar.baz).
        # File paths already contain slashes and may have extensions — applying
        # replace(".", "/") to "src/base/Exchange.js" produces "src/base/Exchange/js",
        # breaking all TS/JS relative imports that include a file extension.
        if "/" in stripped:
            rel_slash = "/".join(parts + [stripped]) if stripped else "/".join(parts)
        else:
            rel_slash = "/".join(parts + [stripped.replace(".", "/")]) if stripped else "/".join(parts)
        if rel_slash in file_map:
            return file_map[rel_slash]
        rel_dot = rel_slash.replace("/", ".")
        if rel_dot in file_map:
            return file_map[rel_dot]
        # 5. Extension-less JS/TS relative imports: ./Foo → Foo.jsx, Foo/index.js, etc.
        if source_file.endswith(_JS_SOURCE_EXTS):
            # TypeScript ESM imports write ./foo.js but the actual file is .ts/.tsx.
            # Try swapping the .js extension before adding more extensions.
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

    # 6. Path alias: @/foo/bar → look up "foo/bar" against file_map.
    #    Common in Expo/Next.js projects where @/ maps to src/ or project root.
    if target_symbol.startswith("@/") and source_file.endswith(_JS_SOURCE_EXTS):
        alias_path = target_symbol[2:]  # strip "@/"
        if alias_path in file_map:
            return file_map[alias_path]
        for ext in _JS_EXTENSIONS:
            if alias_path + ext in file_map:
                return file_map[alias_path + ext]
            if alias_path + "/index" + ext in file_map:
                return file_map[alias_path + "/index" + ext]

    return ""


class SQLiteGraphStore(GraphStorePort):
    """Stores and queries code graph edges in a local SQLite database."""

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._db_path), timeout=30)
        conn.row_factory = sqlite3.Row
        # WAL allows concurrent readers during writes; busy_timeout retries instead of
        # raising "database is locked" immediately.
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=30000")
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(_SCHEMA)
        logger.debug("Graph store initialised at %s", self._db_path)

    def count_edges_by_confidence(self, confidence: str) -> int:
        """Return the number of edges stored with the given confidence tag."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM edges WHERE confidence = ?", (confidence,)
            ).fetchone()
            return row[0]

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

    def count_edges(self) -> int:
        with self._connect() as conn:
            return conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]

    def count_resolved_edges(self) -> int:
        with self._connect() as conn:
            return conn.execute(
                "SELECT COUNT(*) FROM edges WHERE target_file != ''"
            ).fetchone()[0]

    def get_all_edges(self) -> list[GraphEdge]:
        """Return all stored edges. Used by community detection to build the graph."""
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

    def save_communities(self, mapping: dict[str, int]) -> None:
        """Bulk upsert file→community_id. INSERT OR REPLACE per row."""
        if not mapping:
            return
        rows = [(file, cid) for file, cid in mapping.items()]
        with self._connect() as conn:
            conn.executemany(
                "INSERT OR REPLACE INTO communities (file, community_id) VALUES (?, ?)",
                rows,
            )
        logger.debug("Saved %d community assignments", len(rows))

    def get_community_for_file(self, file: str) -> int | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT community_id FROM communities WHERE file = ?", (file,)
            ).fetchone()
        return row["community_id"] if row else None

    def get_community_members(self, community_id: int) -> list[str]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT file FROM communities WHERE community_id = ? ORDER BY file",
                (community_id,),
            ).fetchall()
        return [r["file"] for r in rows]

    def get_all_community_ids(self) -> list[int]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT DISTINCT community_id FROM communities ORDER BY community_id"
            ).fetchall()
        return [r["community_id"] for r in rows]

    def save_community_summary(
        self, community_id: int, summary: str, member_hash: str, model: str
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO community_summaries
                   (community_id, summary, member_hash, model)
                   VALUES (?, ?, ?, ?)""",
                (community_id, summary, member_hash, model),
            )
        logger.debug("Saved summary for community %d", community_id)

    def get_community_summary(self, community_id: int) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT summary, member_hash, model, generated_at "
                "FROM community_summaries WHERE community_id = ?",
                (community_id,),
            ).fetchone()
        if not row:
            return None
        return {
            "summary": row["summary"],
            "member_hash": row["member_hash"],
            "model": row["model"],
            "generated_at": row["generated_at"],
        }

    def delete_ghost_edges(self, current_files: set[str]) -> int:
        """Remove edges whose source_file or resolved target_file is no longer in current_files.

        Uses a temporary table for large sets to avoid excessive IN-clause parameters.
        Returns the number of deleted rows.
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
                      OR (target_file != '' AND target_file != '_external_'
                          AND target_file NOT IN (SELECT path FROM _current_files))
                """
            )
            return result.rowcount

    def count_ghost_edges(self, current_files: set[str]) -> int:
        """Count edges whose source_file or resolved target_file is no longer in current_files.

        Used by the health check — does not delete anything.
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
            row = conn.execute(
                """SELECT COUNT(*) FROM edges
                   WHERE source_file NOT IN (SELECT path FROM _current_files)
                      OR (target_file != '' AND target_file != '_external_'
                          AND target_file NOT IN (SELECT path FROM _current_files))
                """
            ).fetchone()
            return row[0]

    def count_edges(self) -> int:
        """Total edge count."""
        with self._connect() as conn:
            return conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]

    def count_unresolved_edges(self) -> int:
        """Count edges with target_file='' (truly unresolved — excludes _external_)."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM edges WHERE target_file = ''"
            ).fetchone()
            return row[0]

    def resolve_target_files(
        self, file_map: dict[str, str], go_module_prefixes: set[str] | None = None
    ) -> int:
        """Update target_file='' edges whose target_symbol resolves via file_map.

        Unresolvable Go stdlib and external-dep imports are marked '_external_' so
        they don't count as unresolved and don't trigger false health-check warnings.
        Returns the count of edges resolved to real project files (not _external_).
        """
        with self._connect() as conn:
            unresolved = conn.execute(
                "SELECT id, target_symbol, source_file FROM edges WHERE target_file = ''"
            ).fetchall()

        if not unresolved:
            return 0

        # Pre-compute the set of top-level namespace segments that appear inside the
        # project's file_map — used to distinguish unresolved internal imports from
        # unresolved third-party package imports.
        # A segment is "in the project" if any indexed path contains "/<seg>/" or
        # starts with "<seg>/".  This avoids false-positives like "mcp" matching
        # "mcp-rag-server/…" (the dir name contains extra chars after the segment).
        project_namespaces: set[str] = set()
        for k in file_map:
            parts = k.replace("\\", "/").split("/")
            for i, part in enumerate(parts):
                # Record each directory segment that contains a sub-path as a namespace
                project_namespaces.add(part)

        updates: list[tuple[str, int]] = []
        external_count = 0
        for row in unresolved:
            resolved = _resolve_symbol(row["target_symbol"], row["source_file"], file_map)
            if resolved:
                updates.append((resolved, row["id"]))
            elif _is_external_symbol(
                row["target_symbol"], row["source_file"], go_module_prefixes
            ):
                updates.append((_EXTERNAL_SENTINEL, row["id"]))
                external_count += 1
            elif row["source_file"].endswith(".py"):
                # Fallback for Python: dotted third-party imports that aren't caught by
                # _is_external_symbol (e.g. mcp.server, chromadb.config, rich.style).
                # If the first segment of the import is NOT a real project namespace
                # (i.e. no indexed file lives under that directory name), treat as external.
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
                "Marked %d stdlib/external imports as _external_ (not counted as unresolved)",
                external_count,
            )
        return resolved_count
