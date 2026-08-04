"""The leaf must survive truncation, or the parent prefix defeats itself.

project_id.py adds the parent folder to the slug so two projects sharing a leaf
name are tellable apart by eye. Slicing the JOINED string trims from the right,
so a long parent ate the leaf entirely and both projects got the same readable
slug again, differing only by hash. Measured: a 59 character parent left zero
characters of "Nectar" or "AscendMobile".

Written by bad-cop to prove the gap; inverted here to assert it is closed.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server.project_id import MAX_SLUG, project_dir_name  # noqa: E402

LONG_PARENT = "a-very-long-shared-workspace-directory-name-for-this-team"


def _slug_part(dir_name: str) -> str:
    """Everything before the trailing -<hash> suffix."""
    return dir_name.rsplit("-", 1)[0]


def test_a_long_parent_does_not_swallow_the_leaf():
    assert len(LONG_PARENT) > MAX_SLUG

    a = project_dir_name(str(Path("C:/") / LONG_PARENT / "Nectar"))
    b = project_dir_name(str(Path("C:/") / LONG_PARENT / "AscendMobile"))

    assert a != b
    assert _slug_part(a) != _slug_part(b), f"slugs still identical: {_slug_part(a)!r}"
    assert "nectar" in a
    assert "ascendmobile" in b


def test_the_name_still_respects_the_length_budget():
    """A slug that outgrows MAX_SLUG defeats the reason the cap exists."""
    name = project_dir_name(str(Path("C:/") / LONG_PARENT / "Nectar"))
    assert len(_slug_part(name)) <= MAX_SLUG, name


def test_a_leaf_longer_than_the_budget_still_produces_a_usable_name():
    """No room for a parent at all. The leaf alone plus the hash is correct; a
    truncated parent fragment with no leaf would not be."""
    leaf = "an-extremely-long-project-directory-name-that-exceeds-the-budget"
    name = project_dir_name(str(Path("C:/") / LONG_PARENT / leaf))
    assert _slug_part(name)
    assert len(_slug_part(name)) <= MAX_SLUG


def test_the_ordinary_case_is_unchanged():
    """The two real projects this feature was added for."""
    a = project_dir_name(str(Path("C:/Development/F and B PWA/Nectar")))
    b = project_dir_name(str(Path("C:/Development/F and B PWA2/Nectar")))
    assert a != b
    assert "f-and-b-pwa-nectar" in a
    assert "f-and-b-pwa2-nectar" in b
