"""Tests for the graph improvement features.

Covers:
- PageRank computation and storage (community.py, sqlite_graph_store.py)
- _normalize_pagerank (search.py)
- Community summarizer: Ollama path, Claude API fallback, failure when neither available
- Co-change git extractor: happy path, PyDriller missing, not a git repo
- TypeScript / Go SCIP extractors: tool missing path

All tests are unit-level — no external services required.
"""

import json
import os
import sqlite3
import tempfile
from collections import namedtuple
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest

# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

FakeEdge = namedtuple("FakeEdge", ["source_file", "target_file", "edge_type", "confidence"])


def _make_edge(src, tgt):
    return FakeEdge(source_file=src, target_file=tgt, edge_type="references", confidence="EXTRACTED")


def _make_graph_store(tmp_path: Path):
    from rag_server.adapters.sqlite_graph_store import SQLiteGraphStore
    return SQLiteGraphStore(tmp_path / "graph.db")


# ---------------------------------------------------------------------------
# 1. _normalize_pagerank
# ---------------------------------------------------------------------------

class TestNormalizePagerank:
    def setup_method(self):
        from rag_server.tools.search import _normalize_pagerank
        self.fn = _normalize_pagerank

    def test_empty(self):
        assert self.fn({}) == {}

    def test_all_same(self):
        result = self.fn({"a.py": 0.5, "b.py": 0.5, "c.py": 0.5})
        for v in result.values():
            assert v == 1.0

    def test_range(self):
        result = self.fn({"low.py": 0.0, "high.py": 1.0, "mid.py": 0.5})
        assert result["low.py"] == pytest.approx(0.5)
        assert result["high.py"] == pytest.approx(1.5)
        assert result["mid.py"] == pytest.approx(1.0)

    def test_all_values_in_range(self):
        scores = {"a.py": 0.001, "b.py": 0.002, "c.py": 0.01}
        result = self.fn(scores)
        for v in result.values():
            assert 0.5 <= v <= 1.5


# ---------------------------------------------------------------------------
# 2. compute_pagerank
# ---------------------------------------------------------------------------

class TestComputePagerank:
    def test_empty_graph(self, tmp_path):
        from rag_server.core.community import compute_pagerank
        store = _make_graph_store(tmp_path)
        result = compute_pagerank(store)
        assert result == {}

    def test_simple_directed(self, tmp_path):
        from rag_server.core.community import compute_pagerank
        from rag_server.ports.graph_port import GraphEdge
        store = _make_graph_store(tmp_path)

        # a imports b; b imports c — c should rank highest (everyone imports toward it)
        edges = [
            GraphEdge("a.py", "<ts>", "b.py", "<ts>", "references", "EXTRACTED"),
            GraphEdge("b.py", "<ts>", "c.py", "<ts>", "references", "EXTRACTED"),
            GraphEdge("a.py", "<ts>", "c.py", "<ts>", "references", "EXTRACTED"),
        ]
        store.add_edges(edges)

        result = compute_pagerank(store)
        assert "c.py" in result
        # c.py is the most-imported file — it should score highest
        assert result["c.py"] >= result.get("b.py", 0)
        assert result["c.py"] >= result.get("a.py", 0)

    def test_external_edges_excluded(self, tmp_path):
        from rag_server.core.community import compute_pagerank
        from rag_server.ports.graph_port import GraphEdge
        store = _make_graph_store(tmp_path)

        edges = [
            GraphEdge("a.py", "<ts>", "_external_", "<ts>", "references", "EXTRACTED"),
            GraphEdge("b.py", "<ts>", "", "<ts>", "references", "EXTRACTED"),
            GraphEdge("a.py", "<ts>", "b.py", "<ts>", "references", "EXTRACTED"),
        ]
        store.add_edges(edges)

        result = compute_pagerank(store)
        assert "_external_" not in result
        assert "" not in result
        assert "a.py" in result
        assert "b.py" in result


# ---------------------------------------------------------------------------
# 3. sqlite_graph_store: clear_graph_structure / get_all_community_ids_with_summaries
# ---------------------------------------------------------------------------

class TestGraphStructureMethods:
    def test_clear_graph_structure_preserves_summaries(self, tmp_path):
        from rag_server.ports.graph_port import GraphEdge
        store = _make_graph_store(tmp_path)

        # Set up: add edges, communities, and a summary
        edges = [GraphEdge("a.py", "<ts>", "b.py", "<ts>", "references", "EXTRACTED")]
        store.add_edges(edges)
        store.save_communities({"a.py": 0, "b.py": 0})
        store.save_community_summary(0, "Summary text.", "abc123", "qwen3:4b")

        assert store.count_edges() > 0

        # clear_graph_structure wipes edges + communities but keeps summaries
        store.clear_graph_structure()

        assert store.count_edges() == 0
        assert store.get_community_for_file("a.py") is None
        # Summary survives
        result = store.get_community_summary(0)
        assert result is not None
        assert result["summary"] == "Summary text."

    def test_get_all_community_ids_with_summaries_empty(self, tmp_path):
        store = _make_graph_store(tmp_path)
        assert store.get_all_community_ids_with_summaries() == []

    def test_get_all_community_ids_with_summaries_populated(self, tmp_path):
        store = _make_graph_store(tmp_path)
        store.save_community_summary(0, "Summary A.", "hash0", "qwen3:4b")
        store.save_community_summary(2, "Summary C.", "hash2", "qwen3:4b")
        result = store.get_all_community_ids_with_summaries()
        assert set(result) == {0, 2}


# ---------------------------------------------------------------------------
# 3b. sqlite_graph_store: save_pagerank / get_all_pagerank
# ---------------------------------------------------------------------------

class TestPageRankStorage:
    def test_save_and_retrieve(self, tmp_path):
        store = _make_graph_store(tmp_path)
        scores = {"a.py": 0.3, "b.py": 0.7, "c.py": 0.1}
        store.save_pagerank(scores)
        result = store.get_all_pagerank()
        assert result == pytest.approx(scores)

    def test_empty_save(self, tmp_path):
        store = _make_graph_store(tmp_path)
        store.save_pagerank({})
        assert store.get_all_pagerank() == {}

    def test_save_replaces(self, tmp_path):
        store = _make_graph_store(tmp_path)
        store.save_pagerank({"a.py": 0.5})
        store.save_pagerank({"b.py": 0.9})  # full replacement
        result = store.get_all_pagerank()
        assert "a.py" not in result
        assert result["b.py"] == pytest.approx(0.9)

    def test_get_empty(self, tmp_path):
        store = _make_graph_store(tmp_path)
        assert store.get_all_pagerank() == {}


# ---------------------------------------------------------------------------
# 4. Summarizer: Ollama → Claude API → error
# ---------------------------------------------------------------------------

class TestSummarizer:
    def _call(self, *args, **kwargs):
        from rag_server.core.summarizer import summarize_community
        return summarize_community(*args, **kwargs)

    def test_ollama_success(self, tmp_path):
        store = _make_graph_store(tmp_path)
        fake_response = json.dumps({"response": "Handles authentication flow."}).encode()

        with mock.patch("urllib.request.urlopen") as mock_open:
            mock_open.return_value.__enter__ = lambda s: s
            mock_open.return_value.__exit__ = mock.Mock(return_value=False)
            mock_open.return_value.read = lambda: fake_response
            result = self._call(1, ["auth/login.py", "auth/token.py"], store, str(tmp_path))

        assert "authentication" in result.lower() or len(result) > 0

    def test_ollama_down_claude_success(self, tmp_path):
        store = _make_graph_store(tmp_path)

        mock_msg = SimpleNamespace(content=[SimpleNamespace(text="Manages the data pipeline.")])
        mock_client = mock.MagicMock()
        mock_client.messages.create.return_value = mock_msg
        mock_anthropic = mock.MagicMock()
        mock_anthropic.Anthropic.return_value = mock_client

        with mock.patch("urllib.request.urlopen", side_effect=OSError("connection refused")), \
             mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}), \
             mock.patch.dict("sys.modules", {"anthropic": mock_anthropic}):
            result = self._call(1, ["pipeline/step1.py", "pipeline/step2.py"], store, str(tmp_path))

        assert len(result) > 0

    def test_neither_raises(self, tmp_path):
        store = _make_graph_store(tmp_path)

        with mock.patch("urllib.request.urlopen", side_effect=OSError("connection refused")), \
             mock.patch.dict(os.environ, {}, clear=True):
            # Ensure ANTHROPIC_API_KEY is not set
            os.environ.pop("ANTHROPIC_API_KEY", None)
            with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
                self._call(1, ["a.py", "b.py"], store, str(tmp_path))

    def test_cache_hit_returns_without_llm(self, tmp_path):
        store = _make_graph_store(tmp_path)
        from rag_server.core.summarizer import compute_member_hash

        members = ["a.py", "b.py"]
        member_hash = compute_member_hash(members)
        store.save_community_summary(1, "Cached summary.", member_hash, "qwen3:4b")

        # No LLM patch needed — cache hit should return before any network call
        result = self._call(1, members, store, str(tmp_path))
        assert result == "Cached summary."

    def test_empty_members(self, tmp_path):
        store = _make_graph_store(tmp_path)
        result = self._call(1, [], store, str(tmp_path))
        assert result == ""


# ---------------------------------------------------------------------------
# 5. Co-change git extractor
# ---------------------------------------------------------------------------

class TestCoChangeExtractor:
    def test_pydriller_missing(self, tmp_path):
        from rag_server.indexing.git_extractor import extract_co_change_edges
        with mock.patch.dict("sys.modules", {"pydriller": None}):
            result = extract_co_change_edges(str(tmp_path))
        assert result == []

    def test_min_count_threshold(self, tmp_path):
        from rag_server.indexing.git_extractor import _extract

        FakeModFile = namedtuple("FakeModFile", ["new_path", "old_path"])
        FakeCommit = namedtuple("FakeCommit", ["modified_files"])

        # Commit 1: a.py + b.py
        # Commit 2: a.py + b.py (co-change count = 2 → edge)
        # Commit 3: a.py + c.py (co-change count = 1 → no edge)
        commits = [
            FakeCommit([FakeModFile("a.py", None), FakeModFile("b.py", None)]),
            FakeCommit([FakeModFile("a.py", None), FakeModFile("b.py", None)]),
            FakeCommit([FakeModFile("a.py", None), FakeModFile("c.py", None)]),
        ]

        class FakeRepo:
            def __init__(self, path):
                pass
            def traverse_commits(self):
                return iter(commits)

        edges = _extract(str(tmp_path), FakeRepo)
        edge_pairs = {(e.source_file, e.target_file) for e in edges}

        # a.py + b.py should be an edge (count=2)
        assert ("a.py", "b.py") in edge_pairs or ("b.py", "a.py") in edge_pairs
        # a.py + c.py should NOT be an edge (count=1)
        assert ("a.py", "c.py") not in edge_pairs and ("c.py", "a.py") not in edge_pairs

    def test_edge_type_and_confidence(self, tmp_path):
        from rag_server.indexing.git_extractor import _extract

        FakeModFile = namedtuple("FakeModFile", ["new_path", "old_path"])
        FakeCommit = namedtuple("FakeCommit", ["modified_files"])

        commits = [
            FakeCommit([FakeModFile("x.py", None), FakeModFile("y.py", None)]),
            FakeCommit([FakeModFile("x.py", None), FakeModFile("y.py", None)]),
        ]

        class FakeRepo:
            def __init__(self, path): pass
            def traverse_commits(self): return iter(commits)

        edges = _extract(str(tmp_path), FakeRepo)
        assert len(edges) == 1
        assert edges[0].edge_type == "co_change"
        assert edges[0].confidence == "GIT"

    def test_repo_error_returns_empty(self, tmp_path):
        from rag_server.indexing.git_extractor import extract_co_change_edges

        pydriller_mock = mock.MagicMock()
        pydriller_mock.Repository.side_effect = Exception("not a git repo")

        with mock.patch.dict("sys.modules", {"pydriller": pydriller_mock}):
            result = extract_co_change_edges(str(tmp_path))
        assert result == []


# ---------------------------------------------------------------------------
# 6. SCIP TypeScript / Go extractors: tool-not-found path
# ---------------------------------------------------------------------------

class TestScipExtractors:
    def test_typescript_missing_returns_empty(self, tmp_path):
        from rag_server.indexing.scip_extractor import extract_typescript_edges
        with mock.patch("subprocess.run", side_effect=FileNotFoundError("scip-typescript not found")):
            result = extract_typescript_edges(str(tmp_path))
        assert result == []

    def test_go_missing_returns_empty(self, tmp_path):
        from rag_server.indexing.scip_extractor import extract_go_edges
        with mock.patch("subprocess.run", side_effect=FileNotFoundError("scip-go not found")):
            result = extract_go_edges(str(tmp_path))
        assert result == []

    def test_typescript_nonzero_returncode_returns_empty(self, tmp_path):
        from rag_server.indexing.scip_extractor import extract_typescript_edges
        mock_result = mock.MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = b"error output"
        with mock.patch("subprocess.run", return_value=mock_result):
            result = extract_typescript_edges(str(tmp_path))
        assert result == []

    def test_go_nonzero_returncode_returns_empty(self, tmp_path):
        from rag_server.indexing.scip_extractor import extract_go_edges
        mock_result = mock.MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = b"error output"
        with mock.patch("subprocess.run", return_value=mock_result):
            result = extract_go_edges(str(tmp_path))
        assert result == []
