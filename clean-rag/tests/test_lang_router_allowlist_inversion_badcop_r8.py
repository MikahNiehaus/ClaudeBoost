"""A language we cannot route is still real code, and still wins by count.

An allowlist was briefly tried for tier 1: only languages present in
ROUTING_TABLE could win. It looked like it removed the maintenance burden of
SECONDARY_LANGUAGES, and it did, by silently reclassifying every language we
have no model for as a supporting file.

bad-cop measured what that cost: one csharp file beat 500 julia files, so a
99.8% Julia project got Salesforce/SFR-Embedding-Code-400M_R, a model tuned for
C#, Rust and C++. The denylist's answer (julia wins, routes to the generalist
fallback) is strictly better, because a generalist model on Julia beats a
systems-language specialist on Julia.

These tests pin the property that inversion broke: the majority language wins
whether or not we happen to have a model for it. Written by bad-cop to prove
the regression; inverted here to assert it is closed.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server.lang_router import (  # noqa: E402
    MODEL_FALLBACK,
    ROUTING_TABLE,
    detect_dominant_language,
    get_model_for_project,
)


def test_a_tiny_routable_minority_does_not_outvote_real_code():
    """The measured case: 1 csharp file against 500 julia files."""
    counts = {"julia": 500, "csharp": 1}
    assert detect_dominant_language(counts) == "julia"
    assert get_model_for_project(counts) == MODEL_FALLBACK


def test_a_small_routable_minority_does_not_outvote_a_larger_unroutable_majority():
    counts = {"elm": 100, "lua": 5}
    assert detect_dominant_language(counts) == "elm"
    assert get_model_for_project(counts) == MODEL_FALLBACK


def test_a_genuine_routable_majority_still_wins():
    """The guard must not overcorrect: when the routable language really is
    the majority, it must still take the model tuned for it."""
    counts = {"csharp": 500, "julia": 1}
    assert detect_dominant_language(counts) == "csharp"
    assert get_model_for_project(counts) == ROUTING_TABLE["csharp"]


def test_supporting_files_still_lose_to_real_code_routable_or_not():
    """The property the denylist exists for, unchanged by this revert."""
    assert detect_dominant_language({"python": 10, "sql": 100}) == "python"
    assert detect_dominant_language({"julia": 10, "json": 500}) == "julia"


def test_a_pure_unroutable_project_is_unchanged():
    """No routable language anywhere. This behaved identically under both
    schemes and must stay that way."""
    for counts in ({"julia": 500}, {"elm": 300}, {"gdscript": 200}):
        assert detect_dominant_language(counts) == next(iter(counts))
        assert get_model_for_project(counts) == MODEL_FALLBACK


def test_an_unroutable_language_beating_supporting_files_still_routes_to_fallback():
    counts = {"elm": 80, "gdscript": 60, "markdown": 10}
    assert detect_dominant_language(counts) == "elm"
    assert get_model_for_project(counts) == MODEL_FALLBACK
