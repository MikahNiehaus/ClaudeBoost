"""Tests for lang_router.py — targets 100% branch and line coverage.

Run:
    pytest mcp-rag-server/tests/test_lang_router.py -v
"""
from __future__ import annotations

import threading
from unittest.mock import MagicMock, patch

import pytest

from rag_server.indexing.lang_router import (
    CSN_FAMILY,
    DOC_LANGUAGES,
    JINA_FAMILY,
    MODEL_CSN,
    MODEL_FALLBACK,
    MODEL_JINA,
    MODEL_SFR,
    ROUTING_TABLE,
    SFR_FAMILY,
    ModelCache,
    detect_dominant_language,
    get_model_for_language,
    get_model_for_project,
)

# Alias for clarity in tests
FALLBACK_MODEL = MODEL_FALLBACK


# ---------------------------------------------------------------------------
# Constants / table sanity
# ---------------------------------------------------------------------------

class TestConstants:
    def test_csn_family_is_nonempty(self):
        assert len(CSN_FAMILY) > 0

    def test_sfr_family_is_nonempty(self):
        assert len(SFR_FAMILY) > 0

    def test_jina_family_is_nonempty(self):
        assert len(JINA_FAMILY) > 0

    def test_doc_languages_is_nonempty(self):
        assert len(DOC_LANGUAGES) > 0

    def test_families_are_disjoint(self):
        assert CSN_FAMILY.isdisjoint(SFR_FAMILY)
        assert CSN_FAMILY.isdisjoint(JINA_FAMILY)
        assert SFR_FAMILY.isdisjoint(JINA_FAMILY)

    def test_families_dont_overlap_doc_languages(self):
        assert CSN_FAMILY.isdisjoint(DOC_LANGUAGES)
        assert SFR_FAMILY.isdisjoint(DOC_LANGUAGES)
        assert JINA_FAMILY.isdisjoint(DOC_LANGUAGES)

    def test_routing_table_covers_all_families(self):
        for lang in CSN_FAMILY:
            assert lang in ROUTING_TABLE, f"{lang} missing from ROUTING_TABLE"
        for lang in SFR_FAMILY:
            assert lang in ROUTING_TABLE, f"{lang} missing from ROUTING_TABLE"
        for lang in JINA_FAMILY:
            assert lang in ROUTING_TABLE, f"{lang} missing from ROUTING_TABLE"

    def test_routing_table_correct_models(self):
        for lang in CSN_FAMILY:
            assert ROUTING_TABLE[lang] == MODEL_CSN
        for lang in SFR_FAMILY:
            assert ROUTING_TABLE[lang] == MODEL_SFR
        for lang in JINA_FAMILY:
            assert ROUTING_TABLE[lang] == MODEL_JINA

    def test_fallback_model_is_string(self):
        assert isinstance(FALLBACK_MODEL, str) and FALLBACK_MODEL


# ---------------------------------------------------------------------------
# get_model_for_language
# ---------------------------------------------------------------------------

class TestGetModelForLanguage:
    def test_python_routes_to_csn(self):
        assert get_model_for_language("python") == MODEL_CSN

    def test_javascript_routes_to_csn(self):
        assert get_model_for_language("javascript") == MODEL_CSN

    def test_typescript_routes_to_csn(self):
        assert get_model_for_language("typescript") == MODEL_CSN

    def test_java_routes_to_csn(self):
        assert get_model_for_language("java") == MODEL_CSN

    def test_go_routes_to_csn(self):
        assert get_model_for_language("go") == MODEL_CSN

    def test_php_routes_to_csn(self):
        assert get_model_for_language("php") == MODEL_CSN

    def test_ruby_routes_to_csn(self):
        assert get_model_for_language("ruby") == MODEL_CSN

    def test_csharp_routes_to_sfr(self):
        assert get_model_for_language("csharp") == MODEL_SFR

    def test_rust_routes_to_sfr(self):
        assert get_model_for_language("rust") == MODEL_SFR

    def test_kotlin_routes_to_sfr(self):
        assert get_model_for_language("kotlin") == MODEL_SFR

    def test_swift_routes_to_sfr(self):
        assert get_model_for_language("swift") == MODEL_SFR

    def test_c_routes_to_sfr(self):
        assert get_model_for_language("c") == MODEL_SFR

    def test_cpp_routes_to_sfr(self):
        assert get_model_for_language("cpp") == MODEL_SFR

    def test_scala_routes_to_jina(self):
        assert get_model_for_language("scala") == MODEL_JINA

    def test_lua_routes_to_jina(self):
        assert get_model_for_language("lua") == MODEL_JINA

    def test_bash_routes_to_jina(self):
        assert get_model_for_language("bash") == MODEL_JINA

    def test_sql_routes_to_jina(self):
        assert get_model_for_language("sql") == MODEL_JINA

    def test_unknown_language_falls_back(self):
        assert get_model_for_language("brainfuck") == MODEL_FALLBACK

    def test_empty_string_falls_back(self):
        assert get_model_for_language("") == MODEL_FALLBACK

    def test_case_insensitive_python(self):
        assert get_model_for_language("Python") == MODEL_CSN

    def test_case_insensitive_csharp(self):
        assert get_model_for_language("CSharp") == MODEL_SFR

    def test_case_insensitive_scala(self):
        assert get_model_for_language("SCALA") == MODEL_JINA

    def test_all_csn_family_members(self):
        for lang in CSN_FAMILY:
            assert get_model_for_language(lang) == MODEL_CSN

    def test_all_sfr_family_members(self):
        for lang in SFR_FAMILY:
            assert get_model_for_language(lang) == MODEL_SFR

    def test_all_jina_family_members(self):
        for lang in JINA_FAMILY:
            assert get_model_for_language(lang) == MODEL_JINA


# ---------------------------------------------------------------------------
# detect_dominant_language
# ---------------------------------------------------------------------------

class TestDetectDominantLanguage:
    def test_python_project(self):
        assert detect_dominant_language({"python": 100, "markdown": 20}) == "python"

    def test_csharp_project(self):
        assert detect_dominant_language({"csharp": 80, "json": 10}) == "csharp"

    def test_mixed_code_picks_dominant(self):
        # TypeScript > Python > Go
        result = detect_dominant_language({"typescript": 50, "python": 30, "go": 10})
        assert result == "typescript"

    def test_docs_only_returns_none(self):
        assert detect_dominant_language({"markdown": 100, "json": 20, "yaml": 5}) is None

    def test_empty_dict_returns_none(self):
        assert detect_dominant_language({}) is None

    def test_docs_dont_influence_selection(self):
        # Even with many more markdown files, python should win for code
        result = detect_dominant_language({"python": 5, "markdown": 500})
        assert result == "python"

    def test_single_code_language(self):
        assert detect_dominant_language({"rust": 42}) == "rust"

    def test_ties_returns_one_of_them(self):
        # When counts are equal, any one of them is acceptable
        result = detect_dominant_language({"python": 10, "java": 10})
        assert result in {"python", "java"}

    def test_case_insensitive_doc_exclusion(self):
        # "Markdown" (capitalised) should still be excluded
        result = detect_dominant_language({"Markdown": 1000, "python": 5})
        assert result == "python"

    def test_all_doc_types_excluded(self):
        doc_only = {lang: 10 for lang in DOC_LANGUAGES}
        assert detect_dominant_language(doc_only) is None

    def test_zero_count_code_file(self):
        # A code language with 0 files and docs should return the code language
        # (max of {} = no code files → None if 0 is excluded? Actually 0 is falsy
        # but the dict still has the key; max picks it over nothing)
        result = detect_dominant_language({"python": 1, "markdown": 0})
        assert result == "python"


# ---------------------------------------------------------------------------
# get_model_for_project
# ---------------------------------------------------------------------------

class TestGetModelForProject:
    def test_python_project(self):
        assert get_model_for_project({"python": 100}) == MODEL_CSN

    def test_csharp_project(self):
        assert get_model_for_project({"csharp": 50}) == MODEL_SFR

    def test_scala_project(self):
        assert get_model_for_project({"scala": 20}) == MODEL_JINA

    def test_docs_only_fallback(self):
        assert get_model_for_project({"markdown": 100}) == MODEL_FALLBACK

    def test_empty_fallback(self):
        assert get_model_for_project({}) == MODEL_FALLBACK

    def test_mixed_project_picks_dominant(self):
        # C# dominates → SFR
        result = get_model_for_project({"csharp": 200, "python": 10})
        assert result == MODEL_SFR

    def test_unknown_language_fallback(self):
        assert get_model_for_project({"cobol": 5}) == MODEL_FALLBACK

    def test_logging_called(self, caplog):
        import logging
        with caplog.at_level(logging.INFO, logger="rag_server.indexing.lang_router"):
            get_model_for_project({"python": 10})
        assert any("python" in r.message for r in caplog.records)

    def test_fallback_logging(self, caplog):
        import logging
        with caplog.at_level(logging.DEBUG, logger="rag_server.indexing.lang_router"):
            get_model_for_project({})
        assert any("fallback" in r.message.lower() for r in caplog.records)


# ---------------------------------------------------------------------------
# ModelCache
# ---------------------------------------------------------------------------

class TestModelCache:
    def _make_cache(self):
        return ModelCache()

    def test_get_returns_embedder(self):
        cache = self._make_cache()
        mock_emb = MagicMock()
        mock_emb.is_loaded = False

        with patch(
            "rag_server.core.embedding.SentenceTransformerEmbedding",
            return_value=mock_emb,
        ):
            result = cache.get("some/model")

        assert result is mock_emb

    def test_get_caches_second_call(self):
        cache = self._make_cache()
        mock_emb = MagicMock()

        with patch(
            "rag_server.core.embedding.SentenceTransformerEmbedding",
            return_value=mock_emb,
        ) as mock_cls:
            first = cache.get("some/model")
            second = cache.get("some/model")

        # SentenceTransformerEmbedding should only be instantiated once
        assert mock_cls.call_count == 1
        assert first is second

    def test_get_different_models_independent(self):
        cache = self._make_cache()
        emb_a = MagicMock()
        emb_b = MagicMock()

        with patch(
            "rag_server.core.embedding.SentenceTransformerEmbedding",
            side_effect=[emb_a, emb_b],
        ):
            a = cache.get("model/a")
            b = cache.get("model/b")

        assert a is emb_a
        assert b is emb_b

    def test_loaded_models_empty_initially(self):
        cache = self._make_cache()
        assert cache.loaded_models() == []

    def test_loaded_models_after_get(self):
        cache = self._make_cache()
        mock_emb = MagicMock()

        with patch(
            "rag_server.core.embedding.SentenceTransformerEmbedding",
            return_value=mock_emb,
        ):
            cache.get("my/model")

        assert "my/model" in cache.loaded_models()

    def test_warmed_models_empty_when_not_loaded(self):
        cache = self._make_cache()
        mock_emb = MagicMock()
        mock_emb.is_loaded = False

        with patch(
            "rag_server.core.embedding.SentenceTransformerEmbedding",
            return_value=mock_emb,
        ):
            cache.get("my/model")

        assert cache.warmed_models() == []

    def test_warmed_models_includes_loaded(self):
        cache = self._make_cache()
        mock_emb = MagicMock()
        mock_emb.is_loaded = True

        with patch(
            "rag_server.core.embedding.SentenceTransformerEmbedding",
            return_value=mock_emb,
        ):
            cache.get("my/model")

        assert "my/model" in cache.warmed_models()

    def test_len_empty(self):
        assert len(self._make_cache()) == 0

    def test_len_after_get(self):
        cache = self._make_cache()
        mock_emb = MagicMock()

        with patch(
            "rag_server.core.embedding.SentenceTransformerEmbedding",
            return_value=mock_emb,
        ):
            cache.get("model/x")

        assert len(cache) == 1

    def test_contains_false_before_get(self):
        cache = self._make_cache()
        assert "model/x" not in cache

    def test_contains_true_after_get(self):
        cache = self._make_cache()
        mock_emb = MagicMock()

        with patch(
            "rag_server.core.embedding.SentenceTransformerEmbedding",
            return_value=mock_emb,
        ):
            cache.get("model/x")

        assert "model/x" in cache

    def test_seeding_cache_directly(self):
        """Server seeds cache with existing code_embedder to avoid double load."""
        cache = self._make_cache()
        existing_emb = MagicMock()
        cache._cache["nomic-ai/CodeRankEmbed"] = existing_emb

        # get() should return the seeded embedder without creating a new one
        with patch(
            "rag_server.core.embedding.SentenceTransformerEmbedding"
        ) as mock_cls:
            result = cache.get("nomic-ai/CodeRankEmbed")

        mock_cls.assert_not_called()
        assert result is existing_emb

    def test_thread_safety_concurrent_get_same_model(self):
        """Concurrent get() calls for the same model should only load once.

        The slot lock ensures only the first thread through calls the factory;
        the rest see the cached result on the inner double-check.
        """
        cache = self._make_cache()
        load_count = {"n": 0}
        count_lock = threading.Lock()
        results = []
        results_lock = threading.Lock()

        def counting_factory(model_name):
            with count_lock:
                load_count["n"] += 1
            emb = MagicMock()
            emb.is_loaded = False
            return emb

        # Single shared patch so all threads use the same factory function.
        with patch(
            "rag_server.core.embedding.SentenceTransformerEmbedding",
            side_effect=counting_factory,
        ):
            def _worker():
                r = cache.get("concurrent/model")
                with results_lock:
                    results.append(r)

            threads = [threading.Thread(target=_worker) for _ in range(4)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

        # Slot lock: factory called exactly once.
        assert load_count["n"] == 1
        # All threads got the same cached object.
        assert all(r is results[0] for r in results)
        assert "concurrent/model" in cache

    def test_slot_lock_reused_across_calls(self):
        cache = self._make_cache()
        lock1 = cache._slot_lock("model/a")
        lock2 = cache._slot_lock("model/a")
        assert lock1 is lock2

    def test_slot_lock_different_models_different_locks(self):
        cache = self._make_cache()
        lock_a = cache._slot_lock("model/a")
        lock_b = cache._slot_lock("model/b")
        assert lock_a is not lock_b
