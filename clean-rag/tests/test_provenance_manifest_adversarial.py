"""Adversarial tests for the embedding-provenance change.

Targets:
  - _save_project_manifest carry-over of __pipeline_version__/__model_id__/
    __embedding_dim__ across many successive reindex_file-style calls that
    omit those keys.
  - Corrupt/unreadable manifest on disk.
  - An explicit override beating a carried-over value.
  - Falsy-but-real values (0, "", None) for the carried keys.
  - read_project_provenance / the search provenance gate: absent model_id
    must be treated as a mismatch, not a trivial match, and the gate must
    not depend on embedding_dim alone.
  - ModelCache failure-TTL memoization: cross-model leak, success clearing
    a prior failure, and both routed+fallback dead.

These assert observable behavior (what ends up on disk / what the gate
returns), not internal call sequences, so they survive refactors.
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import server.indexing as indexing
from server.indexing import _save_project_manifest, read_project_provenance


# ---------------------------------------------------------------------------
# _save_project_manifest carry-over
# ---------------------------------------------------------------------------

def test_omitted_keys_are_carried_over(tmp_path):
    """reindex_file calls _save_project_manifest with no pipeline_version/
    model_id/embedding_dim. Those must survive from the prior write, or
    per-file reindex destroys the project's provenance record."""
    manifest_path = tmp_path / "manifest.json"
    _save_project_manifest(
        manifest_path, {"a.py": "hash1"}, "C:/proj",
        pipeline_version=2, model_id="nomic-ai/CodeRankEmbed", embedding_dim=768,
    )
    # Simulate reindex_file: no pipeline_version/model_id/embedding_dim passed.
    _save_project_manifest(manifest_path, {"a.py": "hash1", "b.py": "hash2"}, "C:/proj")

    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert data["__pipeline_version__"] == 2, data
    assert data["__model_id__"] == "nomic-ai/CodeRankEmbed", data
    assert data["__embedding_dim__"] == 768, data
    assert data["a.py"] == "hash1" and data["b.py"] == "hash2"


def test_many_successive_omitted_writes_preserve_provenance(tmp_path):
    """50 successive per-file reindex writes (the real shape of edit-driven
    reindexing) must not lose model_id/pipeline_version at any point."""
    manifest_path = tmp_path / "manifest.json"
    _save_project_manifest(
        manifest_path, {}, "C:/proj",
        pipeline_version=2, model_id="nomic-ai/CodeRankEmbed", embedding_dim=768,
    )
    for i in range(50):
        _save_project_manifest(manifest_path, {f"f{i}.py": f"hash{i}"}, "C:/proj")
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert data["__model_id__"] == "nomic-ai/CodeRankEmbed", f"lost at iteration {i}: {data}"
        assert data["__pipeline_version__"] == 2, f"lost at iteration {i}: {data}"
        assert data["__embedding_dim__"] == 768, f"lost at iteration {i}: {data}"


def test_corrupt_manifest_on_disk_does_not_crash_and_does_not_fabricate(tmp_path):
    """A manifest that is unreadable JSON must not raise, and since nothing
    valid can be carried over, the save must proceed with only what the
    caller actually supplied (no fabricated provenance)."""
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text("{not valid json!!", encoding="utf-8")

    # Must not raise.
    _save_project_manifest(manifest_path, {"a.py": "h"}, "C:/proj")

    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert "__model_id__" not in data, data
    assert "__pipeline_version__" not in data, data


def test_explicit_value_overrides_carried_over_value(tmp_path):
    """A genuine model change (explicit new model_id) must win over
    whatever is already on disk -- the gate must not be trivially
    satisfiable by carry-over clobbering a real change."""
    manifest_path = tmp_path / "manifest.json"
    _save_project_manifest(
        manifest_path, {}, "C:/proj",
        pipeline_version=2, model_id="nomic-ai/CodeRankEmbed", embedding_dim=768,
    )
    _save_project_manifest(
        manifest_path, {}, "C:/proj",
        pipeline_version=3, model_id="Salesforce/SFR-Embedding-Code-400M_R", embedding_dim=1024,
    )
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert data["__model_id__"] == "Salesforce/SFR-Embedding-Code-400M_R", data
    assert data["__pipeline_version__"] == 3, data
    assert data["__embedding_dim__"] == 1024, data


def test_falsy_real_values_are_not_treated_as_omitted(tmp_path):
    """embedding_dim=0 and pipeline_version=0 are real (if unusual) values,
    not "omitted". Only None means omitted. If the carry-over test used
    `if value:` instead of `if value is not None:` this would wrongly fall
    through to the prior value."""
    manifest_path = tmp_path / "manifest.json"
    _save_project_manifest(
        manifest_path, {}, "C:/proj",
        pipeline_version=2, model_id="nomic-ai/CodeRankEmbed", embedding_dim=768,
    )
    _save_project_manifest(
        manifest_path, {}, "C:/proj",
        pipeline_version=0, model_id="", embedding_dim=0,
    )
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert data["__pipeline_version__"] == 0, data
    assert data["__model_id__"] == "", data
    assert data["__embedding_dim__"] == 0, data


def test_none_after_a_real_value_carries_the_real_value_forward(tmp_path):
    """Explicitly passing None (the reindex_file case) after a real value
    must carry the real value forward, not erase it."""
    manifest_path = tmp_path / "manifest.json"
    _save_project_manifest(
        manifest_path, {}, "C:/proj",
        pipeline_version=2, model_id="nomic-ai/CodeRankEmbed", embedding_dim=768,
    )
    _save_project_manifest(
        manifest_path, {}, "C:/proj",
        pipeline_version=None, model_id=None, embedding_dim=None,
    )
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert data["__model_id__"] == "nomic-ai/CodeRankEmbed", data
    assert data["__pipeline_version__"] == 2, data
    assert data["__embedding_dim__"] == 768, data


# ---------------------------------------------------------------------------
# read_project_provenance / the search provenance gate
# ---------------------------------------------------------------------------

def test_read_provenance_missing_manifest_returns_none(tmp_path, monkeypatch):
    monkeypatch.setattr(indexing, "DATABASES_DIR", tmp_path)
    result = read_project_provenance(str(tmp_path / "nonexistent_project"))
    assert result == {"model_id": None, "embedding_dim": None}


def test_read_provenance_corrupt_manifest_returns_none(tmp_path, monkeypatch):
    monkeypatch.setattr(indexing, "DATABASES_DIR", tmp_path)
    project_path = str(tmp_path / "proj")
    _root, _pid, index_dir, _chroma, manifest_path = indexing._project_paths(project_path)
    index_dir.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text("{broken", encoding="utf-8")
    result = read_project_provenance(project_path)
    assert result == {"model_id": None, "embedding_dim": None}


def test_provenance_gate_absent_model_id_is_a_mismatch_not_a_match():
    """Mutant 4: treating an absent __model_id__ as a match instead of a
    mismatch would let every pre-provenance index answer queries as if it
    were confirmed safe. This must not happen."""
    from server.search import _provenance_mismatch

    class FakeEmbedder:
        model_name = "nomic-ai/CodeRankEmbed"

    import server.search as search_mod
    orig = search_mod.read_project_provenance if hasattr(search_mod, "read_project_provenance") else None

    def fake_provenance(project_path):
        return {"model_id": None, "embedding_dim": None}

    import server.indexing as indexing_mod
    real = indexing_mod.read_project_provenance
    indexing_mod.read_project_provenance = fake_provenance
    try:
        reason = _provenance_mismatch("C:/some/project", FakeEmbedder())
    finally:
        indexing_mod.read_project_provenance = real

    assert reason is not None, "absent model_id must be refused, not silently trusted"


def test_provenance_gate_not_trivially_satisfiable_by_a_real_model_change():
    """The reverse of the above: a genuine model change must still be caught,
    not waved through."""
    from server.search import _provenance_mismatch

    class FakeEmbedder:
        model_name = "nomic-ai/CodeRankEmbed"

    def fake_provenance(project_path):
        return {"model_id": "Salesforce/SFR-Embedding-Code-400M_R", "embedding_dim": 1024}

    import server.indexing as indexing_mod
    real = indexing_mod.read_project_provenance
    indexing_mod.read_project_provenance = fake_provenance
    try:
        reason = _provenance_mismatch("C:/some/project", FakeEmbedder())
    finally:
        indexing_mod.read_project_provenance = real

    assert reason is not None
    assert "Salesforce/SFR-Embedding-Code-400M_R" in reason
    assert "nomic-ai/CodeRankEmbed" in reason


def test_provenance_gate_does_not_depend_on_dimension():
    """nomic-ai/CodeRankEmbed and flax-sentence-embeddings/st-codesearch-
    distilroberta-base are both 768-wide. A gate that keyed off dimension
    alone would wave this through as a match. It must not: the recorded
    model_id is what is compared, dimension is never consulted here."""
    from server.search import _provenance_mismatch

    class FakeEmbedder:
        model_name = "nomic-ai/CodeRankEmbed"

    def fake_provenance(project_path):
        return {
            "model_id": "flax-sentence-embeddings/st-codesearch-distilroberta-base",
            "embedding_dim": 768,  # same width as the live embedder on purpose
        }

    import server.indexing as indexing_mod
    real = indexing_mod.read_project_provenance
    indexing_mod.read_project_provenance = fake_provenance
    try:
        reason = _provenance_mismatch("C:/some/project", FakeEmbedder())
    finally:
        indexing_mod.read_project_provenance = real

    assert reason is not None, (
        "same-width different-model must still be refused; a dimension-only "
        "check would pass this"
    )


def test_provenance_gate_matching_model_is_safe():
    from server.search import _provenance_mismatch

    class FakeEmbedder:
        model_name = "nomic-ai/CodeRankEmbed"

    def fake_provenance(project_path):
        return {"model_id": "nomic-ai/CodeRankEmbed", "embedding_dim": 768}

    import server.indexing as indexing_mod
    real = indexing_mod.read_project_provenance
    indexing_mod.read_project_provenance = fake_provenance
    try:
        reason = _provenance_mismatch("C:/some/project", FakeEmbedder())
    finally:
        indexing_mod.read_project_provenance = real

    assert reason is None


# ---------------------------------------------------------------------------
# ModelCache failure TTL memoization (no real model loads -- monkeypatched)
# ---------------------------------------------------------------------------

def _make_cache_with_fake_embedding(monkeypatch, load_results):
    """load_results: dict model_id -> callable() that either returns a fake
    embedder or raises. Patches SentenceTransformerEmbedding construction and
    .embed() so no real model ever loads."""
    from server.lang_router import ModelCache
    import server.lang_router as lang_router_mod

    class FakeEmbedder:
        def __init__(self, model_name):
            self._model_name = model_name

        @property
        def model_name(self):
            return self._model_name

        def embed(self, texts):
            outcome = load_results[self._model_name]
            if callable(outcome):
                return outcome()
            return outcome

    monkeypatch.setattr(
        "server.embedding.SentenceTransformerEmbedding", FakeEmbedder,
    )
    return ModelCache()


def test_failure_for_one_model_does_not_leak_into_another(monkeypatch):
    calls = {"good": 0, "bad": 0, "fallback": 0}

    def bad_embed():
        calls["bad"] += 1
        raise RuntimeError("bad model is deterministically broken")

    def good_embed():
        calls["good"] += 1
        return [[0.1, 0.2]]

    def fallback_embed():
        calls["fallback"] += 1
        return [[0.3, 0.4]]

    cache = _make_cache_with_fake_embedding(
        monkeypatch, {"bad-model": bad_embed, "good-model": good_embed, "fallback-model": fallback_embed},
    )
    monkeypatch.setattr("server.config.CODE_EMBEDDING_MODEL", "fallback-model")

    # bad-model fails and falls back; good-model must be entirely unaffected
    # by bad-model's memoized failure.
    try:
        cache.get("bad-model")
    except Exception:
        pass
    emb = cache.get("good-model")
    assert emb.model_name == "good-model"
    assert calls["good"] == 1, "good-model must load exactly once, not be short-circuited by bad-model's failure"
    assert calls["fallback"] == 1, "fallback-model should have loaded once to serve bad-model's fallback"


def test_success_clears_a_prior_failure(monkeypatch):
    """A model that failed once and then loads successfully (e.g. the cache
    on disk was repaired) must not be memoized as failed forever."""
    state = {"attempt": 0}

    def flaky_embed():
        state["attempt"] += 1
        if state["attempt"] == 1:
            raise RuntimeError("cache corrupt")
        return [[0.1]]

    from server.lang_router import ModelCache

    class FakeEmbedder:
        def __init__(self, model_name):
            self._model_name = model_name

        @property
        def model_name(self):
            return self._model_name

        def embed(self, texts):
            return flaky_embed()

    monkeypatch.setattr("server.embedding.SentenceTransformerEmbedding", FakeEmbedder)
    monkeypatch.setattr("server.config.CODE_EMBEDDING_MODEL", "flaky-model")
    cache = ModelCache()
    cache.FAILURE_TTL_S = 0.01  # tiny TTL so the retry is allowed almost immediately

    # First call: flaky-model fails, and IS the fallback (model_id == fallback),
    # so it takes the `else: raise` branch -- no other model to fall back to.
    try:
        cache.get("flaky-model")
    except RuntimeError:
        pass
    assert "flaky-model" in cache._failures

    time.sleep(0.02)  # let the TTL expire
    emb = cache.get("flaky-model")  # second attempt: flaky_embed succeeds
    assert emb.model_name == "flaky-model"
    assert "flaky-model" not in cache._failures, "a successful reload must clear the memoized failure"


def test_both_routed_and_fallback_dead_memoizes_both(monkeypatch):
    """If the routed model AND the fallback are both broken, both must be
    memoized -- otherwise the next caller pays for both failed loads again
    on every request."""
    calls = {"routed": 0, "fallback": 0}

    def routed_embed():
        calls["routed"] += 1
        raise RuntimeError("routed model dead")

    def fallback_embed():
        calls["fallback"] += 1
        raise RuntimeError("fallback model also dead")

    from server.lang_router import ModelCache

    class FakeEmbedder:
        def __init__(self, model_name):
            self._model_name = model_name

        @property
        def model_name(self):
            return self._model_name

        def embed(self, texts):
            if self._model_name == "routed-model":
                return routed_embed()
            return fallback_embed()

    monkeypatch.setattr("server.embedding.SentenceTransformerEmbedding", FakeEmbedder)
    monkeypatch.setattr("server.config.CODE_EMBEDDING_MODEL", "fallback-model")
    cache = ModelCache()

    try:
        cache.get("routed-model")
        assert False, "expected an exception when both routed and fallback are dead"
    except RuntimeError:
        pass

    assert "routed-model" in cache._failures, "routed model must be memoized as failed"
    assert "fallback-model" in cache._failures, "fallback model must ALSO be memoized as failed"
    assert calls["routed"] == 1
    assert calls["fallback"] == 1

    # A second call within the TTL must not re-attempt either load.
    try:
        cache.get("routed-model")
    except RuntimeError:
        pass
    assert calls["routed"] == 1, "routed model must not be retried within the failure TTL"
    assert calls["fallback"] == 1, "fallback model must not be retried within the failure TTL either"


def test_memoized_exception_type_and_message_preserved(monkeypatch):
    """The exact exception (type and message) raised on the first failed
    load must be what's re-raised on a memoized short-circuit, not a
    generic wrapper that loses the original diagnostic."""
    class WeirdError(ValueError):
        pass

    def bad_embed():
        raise WeirdError("very specific diagnostic message 12345")

    from server.lang_router import ModelCache

    class FakeEmbedder:
        def __init__(self, model_name):
            self._model_name = model_name

        @property
        def model_name(self):
            return self._model_name

        def embed(self, texts):
            return bad_embed()

    monkeypatch.setattr("server.embedding.SentenceTransformerEmbedding", FakeEmbedder)
    monkeypatch.setattr("server.config.CODE_EMBEDDING_MODEL", "bad-model")
    cache = ModelCache()

    try:
        cache.get("bad-model")
        assert False
    except WeirdError as e:
        assert "very specific diagnostic message 12345" in str(e)

    # Memoized short circuit path (still within TTL)
    try:
        cache.get("bad-model")
        assert False
    except WeirdError as e:
        assert "very specific diagnostic message 12345" in str(e), (
            "memoized re-raise lost the original exception type or message"
        )


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
