"""Adversarial round-7 check: SECONDARY_LANGUAGES completeness.

detect_dominant_language's whole point (per its own docstring and the
Nectar-measured regression that motivated it) is that a supporting file
type must never outvote real application code. SECONDARY_LANGUAGES was
expanded this round to close that hole for markup/config/schema/build
languages -- but grep-ast maps two more realistic, high-volume supporting
file types to language names that were left out: gettext translation
catalogs (``.po``/``.pot`` -> "po") and the Meson build system
(``meson.build`` -> "meson", one file per subdirectory, Meson's normal
real-world layout in GNOME/GTK/systemd-style C projects).

These tests reproduce the exact failure shape the fix was written to
prevent, just with a different supporting-file category.
"""
from server.lang_router import (
    detect_dominant_language,
    get_model_for_project,
    MODEL_SFR,
    MODEL_CSN,
)


def test_po_translation_files_do_not_outvote_real_code():
    """A localized app: 10 real .go files, 50 .po translation catalogs.

    Any real Go project with i18n support easily has more locale files than
    source files. The dominant language must still be "go".
    """
    counts = {"go": 10, "po": 50}
    dominant = detect_dominant_language(counts)
    assert dominant == "go", (
        f"expected 'go' to win over 50 unrouted 'po' translation files, "
        f"got {dominant!r}"
    )
    assert get_model_for_project(counts) == MODEL_CSN


def test_meson_build_files_do_not_outvote_real_c_code():
    """A C project using Meson: 30 real .c files, 40 meson.build files.

    One meson.build per subdirectory is Meson's normal, real-world layout
    (same shape as the cmake/make/bazel build-file category the fix already
    covers) -- so a genuine C project can have more meson.build files than
    .c files. The dominant language must still be "c", routed to SFR, not
    silently demoted to the fallback model.
    """
    counts = {"c": 30, "meson": 40}
    dominant = detect_dominant_language(counts)
    assert dominant == "c", (
        f"expected 'c' to win over 40 unrouted 'meson' build files, "
        f"got {dominant!r}"
    )
    assert get_model_for_project(counts) == MODEL_SFR
