"""The dominant language vote must be decided by what a project IS written in.

grep-ast resolves ".sql" and ".vue" to real language names. Before the swap
they landed in the "unknown" bucket, which DOC_LANGUAGES already excluded, so
resolving them correctly is what re-opened the hole: they started counting as
code in the vote that picks the embedding model.

Same class of bug as the original Nectar failure, where 3138 unmapped markup
files outvoted 1323 real C# files. Written by bad-cop to prove the gap;
inverted here to assert it is closed.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server.edge_extraction import ext_to_lang  # noqa: E402
from server.lang_router import (  # noqa: E402
    DOC_LANGUAGES,
    MODEL_CSN,
    detect_dominant_language,
    get_model_for_project,
)


def test_sql_still_resolves_but_is_excluded_from_the_vote():
    """Resolving it is right; letting it decide the model is not."""
    assert ext_to_lang("migrations/0001_init.sql") == "sql"
    assert "sql" in DOC_LANGUAGES


def test_vue_still_resolves_but_is_excluded_from_the_vote():
    assert ext_to_lang("components/Widget.vue") == "vue"
    assert "vue" in DOC_LANGUAGES


def test_a_python_app_with_more_migrations_than_code_still_routes_on_python():
    """The measured case: python 10 / sql 100 routed to jina rather than
    CodeRankEmbed. A migrations folder outgrowing the app is ordinary."""
    counts = {"python": 10, "sql": 100, "markdown": 5}
    assert detect_dominant_language(counts) == "python"
    assert get_model_for_project(counts) == MODEL_CSN


def test_a_vue_frontend_routes_on_its_real_code():
    """Vue single file components routinely outnumber .ts in a real app."""
    counts = {"typescript": 20, "vue": 200, "css": 30}
    assert detect_dominant_language(counts) == "typescript"


def test_a_schema_only_repo_routes_on_its_own_language():
    """A migrations repo is a real shape, and for it sql IS the language.

    This asserted None before, which was the regression bad-cop caught: making
    supporting languages lose the vote outright meant a pure sql checkout got
    the generic fallback instead of the model sql actually maps to. They are
    deprioritised, not banned.
    """
    counts = {"sql": 50, "markdown": 10, "vue": 5}
    assert detect_dominant_language(counts) == "sql"
    assert get_model_for_project(counts) == "jinaai/jina-embeddings-v2-base-code"


def test_a_project_of_nothing_nameable_still_falls_back_safely():
    """"unknown" names nothing, so it must not be treated as a language."""
    assert detect_dominant_language({"unknown": 40}) is None
    assert get_model_for_project({"unknown": 40})
    assert detect_dominant_language({}) is None
