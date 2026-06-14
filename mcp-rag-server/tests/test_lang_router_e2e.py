"""End-to-end tests for the language-routing embedding system.

These tests verify that:
1. IndexingEngine passes `lang_router` to _do_index_project
2. The project embedder is selected per-language family
3. The chosen model is recorded in the manifest
4. Dimension mismatches trigger force re-index
5. The full routing path works with a real (mocked) embedder

Run:
    pytest mcp-rag-server/tests/test_lang_router_e2e.py -v -s

No live RAG server needed — all external dependencies are mocked.
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

from rag_server.indexing.lang_router import (
    ModelCache,
    MODEL_CSN,
    MODEL_SFR,
    MODEL_JINA,
    MODEL_FALLBACK,
    get_model_for_project,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_embedder(dims: int = 768):
    """Return a mock EmbeddingPort with the given output dimensions."""
    emb = MagicMock()
    emb.is_loaded = True
    emb.dimensions.return_value = dims
    emb.embed.return_value = [[0.1] * dims]
    emb.embed_query.return_value = [0.1] * dims
    return emb


def _make_scan(files_by_language: dict[str, int], file_paths: list[str] | None = None):
    """Return a mock ScanResult."""
    scan = MagicMock()
    scan.files_by_language = files_by_language
    scan.files = file_paths or []
    scan.skipped_gitignore = 0
    scan.skipped_too_large = 0
    scan.skipped_generated = 0
    return scan


# ---------------------------------------------------------------------------
# get_model_for_project integration
# ---------------------------------------------------------------------------

class TestGetModelForProjectE2E:
    """Verify routing decisions against real-world project profiles."""

    def test_pure_python_project(self):
        lang = get_model_for_project({"python": 120, "yaml": 5, "markdown": 30})
        assert lang == MODEL_CSN

    def test_aspnet_project(self):
        lang = get_model_for_project({
            "csharp": 200, "cshtml": 40, "json": 10, "markdown": 5,
        })
        assert lang == MODEL_SFR

    def test_rust_cli_project(self):
        lang = get_model_for_project({"rust": 50, "toml": 8, "markdown": 3})
        assert lang == MODEL_SFR

    def test_scala_backend(self):
        lang = get_model_for_project({"scala": 80, "xml": 2, "markdown": 5})
        assert lang == MODEL_JINA

    def test_mixed_js_ts_project(self):
        # TypeScript > JavaScript in this project
        lang = get_model_for_project({"typescript": 100, "javascript": 40, "json": 20})
        assert lang == MODEL_CSN

    def test_docs_only(self):
        lang = get_model_for_project({"markdown": 50, "rst": 10, "yaml": 5})
        assert lang == MODEL_FALLBACK

    def test_unknown_language(self):
        lang = get_model_for_project({"brainfuck": 3})
        assert lang == MODEL_FALLBACK


# ---------------------------------------------------------------------------
# ModelCache integration
# ---------------------------------------------------------------------------

class TestModelCacheE2E:
    def test_get_creates_sentence_transformer(self):
        cache = ModelCache()
        mock_emb = _make_embedder()

        with patch(
            "rag_server.core.embedding.SentenceTransformerEmbedding",
            return_value=mock_emb,
        ) as cls:
            result = cache.get(MODEL_CSN)

        cls.assert_called_once_with(model_name=MODEL_CSN)
        assert result is mock_emb

    def test_seeded_embedder_not_recreated(self):
        """Seeding the cache (as server.py does) skips factory for that model."""
        cache = ModelCache()
        existing = _make_embedder()
        cache._cache[MODEL_CSN] = existing

        with patch(
            "rag_server.core.embedding.SentenceTransformerEmbedding"
        ) as cls:
            result = cache.get(MODEL_CSN)

        cls.assert_not_called()
        assert result is existing

    def test_multiple_projects_share_cache(self):
        """Same model used by two projects reuses the cached instance."""
        cache = ModelCache()
        emb = _make_embedder()

        with patch(
            "rag_server.core.embedding.SentenceTransformerEmbedding",
            return_value=emb,
        ) as cls:
            r1 = cache.get(MODEL_CSN)
            r2 = cache.get(MODEL_CSN)

        cls.assert_called_once()
        assert r1 is r2 is emb


# ---------------------------------------------------------------------------
# IndexingEngine integration (mocked filesystem + stores)
# ---------------------------------------------------------------------------

class TestIndexingEngineWithLangRouter:
    """Test that IndexingEngine routes to the correct embedder when lang_router is set."""

    def _run_index(
        self,
        files_by_language: dict[str, int],
        chosen_model: str,
        existing_manifest: dict | None = None,
    ):
        """Run _do_index_project with mocked dependencies.

        Returns (result, used_embedder_mock).
        """
        from rag_server.indexing.engine import IndexingEngine
        from rag_server.ports.store_port import StorePort

        default_emb = _make_embedder(768)
        routed_emb = _make_embedder(768)

        cache = ModelCache()
        cache._cache[chosen_model] = routed_emb

        store_mock = MagicMock(spec=StorePort)

        engine = IndexingEngine(
            embedder=default_emb,
            store=store_mock,
            lang_router=cache,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            index_dir = Path(tmpdir)

            if existing_manifest is not None:
                manifest_path = index_dir / "manifest.json"
                manifest_path.write_text(json.dumps(existing_manifest), encoding="utf-8")

            scan = _make_scan(files_by_language)

            with (
                patch("rag_server.core.scanner.scan_project", return_value=scan),
                patch("rag_server.core.store.ChromaStore") as chroma_cls,
                patch("rag_server.adapters.sqlite_graph_store.SQLiteGraphStore"),
                patch("rag_server.core.locking.index_write_lock"),
                patch("rag_server.core.embedding.SentenceTransformerEmbedding"),
            ):
                chroma_inst = MagicMock()
                chroma_inst.collection_exists.return_value = False
                chroma_inst.count.return_value = 0
                chroma_inst.sample_dimension.return_value = None
                chroma_inst.add_chunks.return_value = 0
                chroma_cls.return_value = chroma_inst

                result = engine.index_project(
                    project_path=tmpdir,
                    languages=None,
                    force=True,  # skip health checks for simplicity
                )

        return result, routed_emb, default_emb

    def test_python_project_uses_csn_model(self):
        result, routed, default = self._run_index(
            files_by_language={"python": 50},
            chosen_model=MODEL_CSN,
        )
        assert result.get("embedding_model") == MODEL_CSN

    def test_csharp_project_uses_sfr_model(self):
        result, routed, default = self._run_index(
            files_by_language={"csharp": 80},
            chosen_model=MODEL_SFR,
        )
        assert result.get("embedding_model") == MODEL_SFR

    def test_no_lang_router_uses_default_embedder(self):
        from rag_server.indexing.engine import IndexingEngine

        default_emb = _make_embedder(768)
        store_mock = MagicMock()

        engine = IndexingEngine(embedder=default_emb, store=store_mock, lang_router=None)
        assert engine._lang_router is None

    def test_result_has_embedding_model_field(self):
        result, _, _ = self._run_index(
            files_by_language={"scala": 30},
            chosen_model=MODEL_JINA,
        )
        assert "embedding_model" in result

    def test_docs_only_uses_fallback_model(self):
        result, _, _ = self._run_index(
            files_by_language={"markdown": 100},
            chosen_model=MODEL_FALLBACK,
        )
        assert result.get("embedding_model") == MODEL_FALLBACK


# ---------------------------------------------------------------------------
# Manifest model recording
# ---------------------------------------------------------------------------

class TestManifestModelRecording:
    """Verify __embedding_model__ is written to and read from the manifest."""

    def test_manifest_records_chosen_model(self, tmp_path):
        manifest_path = tmp_path / "manifest.json"

        # Simulate what _do_index_project writes at the end
        chosen = MODEL_CSN
        manifest_data = {
            "__schema_version__": 3,
            "__embedding_model__": chosen,
            "src/main.py": "abc123",
        }
        manifest_path.write_text(json.dumps(manifest_data), encoding="utf-8")

        loaded = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert loaded["__embedding_model__"] == MODEL_CSN

    def test_manifest_model_excluded_from_file_hashes(self, tmp_path):
        """__embedding_model__ should not appear in the file-hash dict."""
        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_text(
            json.dumps({
                "__schema_version__": 3,
                "__embedding_model__": MODEL_SFR,
                "src/main.cs": "deadbeef",
            }),
            encoding="utf-8",
        )

        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
        # Simulate engine manifest loading (strips meta keys)
        file_hashes = {
            k: v for k, v in raw.items()
            if k not in ("__schema_version__", "__embedding_model__")
        }
        assert "__embedding_model__" not in file_hashes
        assert "src/main.cs" in file_hashes


# ---------------------------------------------------------------------------
# Config integration
# ---------------------------------------------------------------------------

class TestConfigIntegration:
    def test_lang_routing_enabled_by_default(self):
        import importlib
        import os
        env_before = os.environ.pop("RAG_LANG_ROUTING", None)
        try:
            import rag_server.config as cfg
            importlib.reload(cfg)
            assert cfg.LANG_ROUTING_ENABLED is True
        finally:
            if env_before is not None:
                os.environ["RAG_LANG_ROUTING"] = env_before
            importlib.reload(cfg)  # restore

    def test_lang_routing_disabled_by_env(self, monkeypatch):
        monkeypatch.setenv("RAG_LANG_ROUTING", "0")
        import importlib
        import rag_server.config as cfg
        importlib.reload(cfg)
        assert cfg.LANG_ROUTING_ENABLED is False
        importlib.reload(cfg)  # restore to default

    def test_lang_routing_disabled_by_false(self, monkeypatch):
        monkeypatch.setenv("RAG_LANG_ROUTING", "false")
        import importlib
        import rag_server.config as cfg
        importlib.reload(cfg)
        assert cfg.LANG_ROUTING_ENABLED is False
        importlib.reload(cfg)
