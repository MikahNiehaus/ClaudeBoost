"""Round 9 adversarial re-check on the allowlist to denylist revert.

Written by bad-cop against the CURRENT state: tier 1 is the denylist again
(``lang not in SECONDARY_LANGUAGES``), tier 2 is the pure-supporting fallback
(``lang != "unknown"``), and SECONDARY_LANGUAGES carries everything added
across rounds six through eight (sql, vue, svelte, proto, starlark, scss,
po, meson, jsonnet, tsv, psv, ...).

This does not re-litigate the six earlier regression tests (those live in
test_lang_router_allowlist_inversion_badcop_r8.py,
test_lang_router_secondary_gap_badcop.py,
test_lang_router_sql_vue_doc_gap_adversarial.py, and
test_badcop_round6_doc_language_reachback.py, and all pass unmodified against
the current code). This file states the two tier structure as three
invariants and sweeps a combinatorial grid against them, so a future change
that keeps every named regression test green but breaks the *interaction*
between the tiers still gets caught.
"""
import itertools
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server.lang_router import (  # noqa: E402
    SECONDARY_LANGUAGES,
    detect_dominant_language,
)

APPLICATION_LANGS = ["python", "csharp", "julia", "elm", "rust", "gdscript"]
SECONDARY_LANGS = ["sql", "vue", "proto", "starlark", "scss", "po", "meson", "json"]


def test_invariant_1_an_application_language_present_always_wins_tier1():
    """If any language outside SECONDARY_LANGUAGES has count > 0, the winner
    must come from that set, never from SECONDARY_LANGUAGES, no matter how
    large the secondary counts are."""
    for app_lang, sec_lang in itertools.product(APPLICATION_LANGS, SECONDARY_LANGS):
        for app_n, sec_n in [(1, 1), (1, 1000), (1000, 1), (5, 5)]:
            counts = {app_lang: app_n, sec_lang: sec_n}
            winner = detect_dominant_language(counts)
            assert winner == app_lang, (
                f"counts={counts!r} produced winner={winner!r}, expected "
                f"the application language {app_lang!r} regardless of the "
                f"secondary count {sec_n}."
            )


def test_invariant_2_multiple_application_languages_still_pick_the_max_by_count():
    """Tier 1, once it has more than one application language, must still
    behave like a normal argmax and ignore secondary noise mixed in."""
    counts = {"python": 5, "csharp": 40, "sql": 9999, "vue": 9999}
    assert detect_dominant_language(counts) == "csharp"


def test_invariant_3_with_no_application_language_the_winner_is_the_max_secondary_excluding_unknown():
    """Tier 2 must be reached, and reached correctly, whenever tier 1 is
    empty: the language with the highest count among the non "unknown"
    secondary languages wins, and "unknown" itself never wins even when it
    has the largest count."""
    for a, b in itertools.combinations(SECONDARY_LANGS, 2):
        counts = {a: 3, b: 30}
        assert detect_dominant_language(counts) == b, (a, b, counts)
        counts2 = {a: 30, b: 3}
        assert detect_dominant_language(counts2) == a, (a, b, counts2)

    # "unknown" must never win tier 2 even as the landslide majority.
    counts3 = {"unknown": 100000, "sql": 1}
    assert detect_dominant_language(counts3) == "sql"


def test_secondary_languages_set_is_internally_consistent_lowercase():
    """Every entry must already be lowercase, since both tiers compare via
    .lower() against this set; a mixed case entry would silently never
    match and the language would leak into tier 1 as application code."""
    for lang in SECONDARY_LANGUAGES:
        assert lang == lang.lower(), f"{lang!r} in SECONDARY_LANGUAGES is not lowercase"
