"""
Tests for scripts/fix-graph-resolution.py — graph edge resolution repair.

This script requires a graph.db and rag_server imports. We test:
- Missing args → exits 1
- Full resolution flow with a minimal temporary graph.db
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

from helpers import run_script, SCRIPTS_DIR

# rag_server must be importable for the full-flow tests
_REPO_ROOT = SCRIPTS_DIR.parent
sys.path.insert(0, str(_REPO_ROOT / "mcp-rag-server" / "src"))
try:
    from rag_server.core.project import project_index_dir
    RAG_SERVER_AVAILABLE = True
except ImportError:
    RAG_SERVER_AVAILABLE = False


def _make_graph_db(path: Path) -> None:
    """Create a minimal graph.db with the schema fix-graph-resolution.py expects."""
    conn = sqlite3.connect(str(path))
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS edges (
            id INTEGER PRIMARY KEY,
            source_file TEXT,
            target_file TEXT,
            edge_type TEXT,
            import_name TEXT
        )
    """)
    cur.execute("INSERT INTO edges (source_file, target_file, edge_type, import_name) VALUES (?, ?, ?, ?)",
                ("src/foo.py", "", "import", "utils"))
    cur.execute("INSERT INTO edges (source_file, target_file, edge_type, import_name) VALUES (?, ?, ?, ?)",
                ("src/bar.py", "_external_", "import", "requests"))
    cur.execute("INSERT INTO edges (source_file, target_file, edge_type, import_name) VALUES (?, ?, ?, ?)",
                ("src/baz.py", "src/utils.py", "import", "utils"))
    conn.commit()
    conn.close()


class TestFixGraphResolution:
    def test_exits_1_without_args(self):
        result = run_script("fix-graph-resolution.py")
        assert result.returncode == 1

    def test_missing_args_prints_usage(self):
        result = run_script("fix-graph-resolution.py")
        output = result.stdout.decode("utf-8", errors="replace") + result.stderr.decode("utf-8", errors="replace")
        assert "Usage" in output or "project_path" in output

    def test_script_is_runnable(self):
        result = run_script("fix-graph-resolution.py")
        assert result.returncode != 127  # not a missing script error

    @pytest.mark.skipif(not RAG_SERVER_AVAILABLE, reason="rag_server not importable")
    def test_full_flow_with_real_graph_db(self, tmp_path):
        """Run with a minimal project dir and pre-built graph.db."""
        # Create project structure
        project = tmp_path / "myproject"
        project.mkdir()
        (project / "src").mkdir()
        (project / "src" / "utils.py").write_text("def helper(): pass", encoding="utf-8")
        (project / "src" / "foo.py").write_text("from src import utils", encoding="utf-8")

        # Create the .rag-index/graph.db that the script reads
        idx_dir = project_index_dir(str(project))
        idx_dir.mkdir(parents=True, exist_ok=True)
        db_path = idx_dir / "graph.db"
        _make_graph_db(db_path)

        result = run_script("fix-graph-resolution.py", args=[str(project)])
        output = result.stdout.decode("utf-8", errors="replace") + result.stderr.decode("utf-8", errors="replace")
        assert result.returncode == 0
        assert "Before:" in output
        assert "After:" in output

    @pytest.mark.skipif(not RAG_SERVER_AVAILABLE, reason="rag_server not importable")
    def test_prints_file_map_count(self, tmp_path):
        project = tmp_path / "proj2"
        project.mkdir()
        (project / "main.py").write_text("pass", encoding="utf-8")

        idx_dir = project_index_dir(str(project))
        idx_dir.mkdir(parents=True, exist_ok=True)
        _make_graph_db(idx_dir / "graph.db")

        result = run_script("fix-graph-resolution.py", args=[str(project)])
        output = result.stdout.decode("utf-8", errors="replace")
        assert "File map:" in output
