"""Search must query each project with the model that built its index.

`lang_router` picks an embedding model per project at index time. The query
side used one global model for everything, so `_provenance_mismatch` refused
every project the router had routed elsewhere: measured, 12,758 files across
5 projects returning zero results against a perfectly good index.

These tests pin the query side to the index's own provenance. Each one fails
on the pre-fix code, which is the point: a test that passes either way would
just be asserting today's behaviour.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server import search as search_mod  # noqa: E402


class FakeEmbedder:
    """Minimal stand in. `model_name` is the only attribute search reads."""

    def __init__(self, model_name):
        self.model_name = model_name
        self.queries = []

    def embed_query(self, text):
        self.queries.append(text)
        return [0.0, 0.0, 0.0]


DEFAULT = "nomic-ai/CodeRankEmbed"
ROUTED = "Salesforce/SFR-Embedding-Code-400M_R"


@pytest.fixture
def provenance(monkeypatch):
    """Control what the manifest reports without writing one."""
    recorded = {}

    def fake_read(project_path):
        return {"model_id": recorded.get(project_path)}

    import server.indexing as indexing
    monkeypatch.setattr(indexing, "read_project_provenance", fake_read)
    return recorded


def _resolve(project_path, default, cache):
    return search_mod._embedder_for_project(
        project_path, default, cache.get if cache is not None else None,
    )


class _Cache:
    def __init__(self, **models):
        self.models = {k: FakeEmbedder(k) for k in models} if models else {}
        self.asked = []

    def get(self, model_id):
        self.asked.append(model_id)
        if model_id not in self.models:
            raise RuntimeError(f"cannot load {model_id}")
        return self.models[model_id]


def test_routed_project_gets_its_own_model(provenance):
    """The whole bug: index on SFR, query with SFR, not the global default."""
    provenance["/p"] = ROUTED
    cache = _Cache(**{ROUTED: 1})
    emb, switched = _resolve("/p", FakeEmbedder(DEFAULT), cache)
    assert switched == ROUTED
    assert emb.model_name == ROUTED
    assert cache.asked == [ROUTED]


def test_routed_project_then_passes_the_provenance_check(provenance):
    """The refusal must actually stop happening, not just the model change."""
    provenance["/p"] = ROUTED
    cache = _Cache(**{ROUTED: 1})
    emb, _ = _resolve("/p", FakeEmbedder(DEFAULT), cache)
    assert search_mod._provenance_mismatch("/p", emb) is None


def test_matching_project_keeps_the_default_instance(provenance):
    """No pointless reload when the recorded model is already the default."""
    provenance["/p"] = DEFAULT
    default = FakeEmbedder(DEFAULT)
    cache = _Cache(**{DEFAULT: 1})
    emb, switched = _resolve("/p", default, cache)
    assert switched is None
    assert emb is default
    assert cache.asked == []


def test_unrecorded_provenance_is_still_refused(provenance):
    """An index with no recorded model stays unverifiable, not auto trusted.

    The temptation is to treat "no model_id" as "whatever we have now". That
    would defeat the check the fix is built on top of.
    """
    provenance["/p"] = None
    default = FakeEmbedder(DEFAULT)
    emb, switched = _resolve("/p", default, _Cache(**{DEFAULT: 1}))
    assert switched is None
    assert emb is default
    assert "no recorded embedding model" in search_mod._provenance_mismatch("/p", emb)


def test_unloadable_model_falls_back_and_stays_refused(provenance):
    """A model that will not load must refuse, never answer from a wrong space.

    Silently querying SFR vectors with a CodeRankEmbed query is the exact
    failure `_provenance_mismatch` exists to prevent, and both models are 768
    wide so no dimension check would catch it.
    """
    provenance["/p"] = ROUTED
    default = FakeEmbedder(DEFAULT)
    emb, switched = _resolve("/p", default, _Cache())  # cache raises
    assert switched is None
    assert emb is default
    assert search_mod._provenance_mismatch("/p", emb) is not None


def test_no_resolver_reproduces_the_old_behaviour(provenance):
    """Absent the resolver, nothing changes. Keeps every existing caller valid."""
    provenance["/p"] = ROUTED
    default = FakeEmbedder(DEFAULT)
    emb, switched = _resolve("/p", default, None)
    assert switched is None
    assert emb is default


def test_two_projects_on_different_models_in_one_search(provenance, monkeypatch):
    """Resolution is per source. One request, two models, both served."""
    provenance["/a"] = DEFAULT
    provenance["/b"] = ROUTED
    cache = _Cache(**{DEFAULT: 1, ROUTED: 1})
    default = cache.models[DEFAULT]

    used = []

    def fake_search_project(query, project_path, embedder, limit, min_score):
        used.append((project_path, embedder.model_name))
        return []

    monkeypatch.setattr(search_mod, "_search_project", fake_search_project)
    monkeypatch.setattr(search_mod, "_check_index_before_search",
                        lambda p, e, m: True)

    search_mod.search(
        query="q",
        sources=["project:/a", "project:/b"],
        code_embedder=default,
        mode="vector",
        embedder_for=cache.get,
    )

    assert used == [("/a", DEFAULT), ("/b", ROUTED)]
