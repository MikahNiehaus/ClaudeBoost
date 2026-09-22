"""The leaf must survive truncation, or the parent prefix defeats itself.

project_id.py adds the parent folder to the slug so two projects sharing a leaf
name are tellable apart by eye. Slicing the JOINED string trims from the right,
so a long parent ate the leaf entirely and both projects got the same readable
slug again, differing only by hash. Measured: a 59 character parent left zero
characters of "Litware" or "ContosoMobile".

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

    a = project_dir_name(str(Path("C:/") / LONG_PARENT / "Litware"))
    b = project_dir_name(str(Path("C:/") / LONG_PARENT / "ContosoMobile"))

    assert a != b
    assert _slug_part(a) != _slug_part(b), f"slugs still identical: {_slug_part(a)!r}"
    assert "litware" in a
    assert "contosomobile" in b


def test_the_name_still_respects_the_length_budget():
    """A slug that outgrows MAX_SLUG defeats the reason the cap exists."""
    name = project_dir_name(str(Path("C:/") / LONG_PARENT / "Litware"))
    assert len(_slug_part(name)) <= MAX_SLUG, name


def test_a_leaf_longer_than_the_budget_still_produces_a_usable_name():
    """No room for a parent at all. The leaf alone plus the hash is correct; a
    truncated parent fragment with no leaf would not be."""
    leaf = "an-extremely-long-project-directory-name-that-exceeds-the-budget"
    name = project_dir_name(str(Path("C:/") / LONG_PARENT / leaf))
    assert _slug_part(name)
    assert len(_slug_part(name)) <= MAX_SLUG


def test_the_documented_example_is_the_name_the_code_produces():
    """The module docstring names a path and the directory it becomes. Renaming
    the example project without recomputing the digest left a hash that belongs
    to a path nobody can reach.
    """
    import server.project_id as project_id

    assert "myproject-2d7cff12" in project_id.__doc__
    assert project_dir_name(r"C:\Development\myproject") == "myproject-2d7cff12"


def test_the_ordinary_case_is_unchanged():
    """The sibling-parent collision this feature was added for."""
    a = project_dir_name(str(Path("C:/Development/X and Y PWA/Litware")))
    b = project_dir_name(str(Path("C:/Development/X and Y PWA2/Litware")))
    assert a != b
    assert "x-and-y-pwa-litware" in a
    assert "x-and-y-pwa2-litware" in b
