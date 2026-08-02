"""Round 6 adversarial pass on the sql/vue/svelte fix.

Excluding sql/vue/svelte from the vote fixes the "supporting cast outvotes
the real language" case. It does not check the opposite: a project where one
of those three genuinely IS the whole codebase (a migrations only repo, a
Vue component library with no other source), and it does not check whether
other markup/config/template extensions grep-ast now resolves have the same
vote distorting shape sql/vue/svelte did.

Written by bad-cop. Not inverted; these assert the gap is still open.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server.lang_router import (  # noqa: E402
    JINA_FAMILY,
    MODEL_JINA,
    MODEL_SFR,
    detect_dominant_language,
    get_model_for_language,
    get_model_for_project,
)


def test_a_pure_sql_migrations_repo_still_gets_the_sql_model():
    """sql is listed in JINA_FAMILY as the right model for sql content. A repo
    that is genuinely nothing but .sql (a schema/migrations only checkout)
    should still get that model, the same way it did before sql was added to
    DOC_LANGUAGES. Excluding sql from the vote entirely, with no code left
    over, must not silently downgrade it to the generic fallback.
    """
    counts = {"sql": 500}
    assert get_model_for_language("sql") == MODEL_JINA, "sql is in JINA_FAMILY"
    model = get_model_for_project(counts)
    assert model == MODEL_JINA, (
        f"pure-SQL project routed to {model!r} instead of the sql model "
        f"{MODEL_JINA!r} that JINA_FAMILY says sql should get. "
        "detect_dominant_language() returns None here because sql is now in "
        "DOC_LANGUAGES, so JINA_FAMILY's sql entry is dead code: it can "
        "never be reached through the normal per-project routing path."
    )


def test_a_grpc_service_with_more_proto_than_csharp_still_routes_on_csharp():
    """.proto contract files are the sql/vue problem again: a gRPC service can
    easily carry more .proto than .cs, the same way a migrations folder
    outgrows the app or a Vue app's SFCs outnumber its .ts. proto is not in
    DOC_LANGUAGES and not in any family, so it is not excluded from the vote
    and it does not map to MODEL_SFR either.
    """
    counts = {"csharp": 50, "proto": 200}
    dominant = detect_dominant_language(counts)
    assert dominant == "csharp", (
        f"proto (200) outvoted csharp (50): dominant={dominant!r}. "
        "This is the exact Nectar failure shape (unvoted extension outvotes "
        "the real language), just for .proto instead of .html/.yml."
    )
    assert get_model_for_project(counts) == MODEL_SFR


def test_a_rust_repo_with_bazel_build_files_still_routes_on_rust():
    """BUILD/WORKSPACE (starlark) files are build config, not code, the same
    category as the cmake/toml/yaml files already excluded. A bazel
    monorepo can have far more BUILD files than actual .rs sources.
    """
    counts = {"rust": 30, "starlark": 150}
    dominant = detect_dominant_language(counts)
    assert dominant == "rust", (
        f"starlark (150) outvoted rust (30): dominant={dominant!r}."
    )
    assert get_model_for_project(counts) == MODEL_SFR


def test_scss_partials_do_not_outvote_the_apps_real_language():
    """.css is already excluded as a doc/markup language. .scss is the exact
    same category (a stylesheet, compiled away, not the app), and a design
    system heavy frontend can hold hundreds of .scss partials against a
    modest handful of real source files.
    """
    counts = {"csharp": 20, "scss": 300}
    dominant = detect_dominant_language(counts)
    assert dominant == "csharp", (
        f"scss (300) outvoted csharp (20): dominant={dominant!r}. "
        ".css is in DOC_LANGUAGES; .scss, the same kind of file, is not."
    )
    assert get_model_for_project(counts) == MODEL_SFR
