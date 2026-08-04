"""Round 6 adversarial pass on the MAX_SLUG parent truncation fix.

_MIN_PARENT_CHARS exists so a parent fragment too short to read is dropped
entirely: "Below this, a parent fragment is noise rather than a hint, so the
leaf gets the whole budget instead." The gate that enforces this checks
`room`, the budget before parent[:room].strip('-') runs. Stripping happens
after the gate, so a parent with an internal hyphen that lands right at the
truncation boundary can lose a character to strip() after already passing
the room check, and the actual embedded fragment can end up shorter than
_MIN_PARENT_CHARS says is worth keeping.

Written by bad-cop. Not inverted; this asserts the gap is still open.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server.project_id import (  # noqa: E402
    MAX_SLUG,
    _MIN_PARENT_CHARS,
    project_dir_name,
    slugify_name,
)


def _embedded_parent_fragment(dir_name: str, leaf_len: int) -> str:
    """Recover the parent fragment actually written into the slug, given the
    known leaf length. Empty string when no parent fragment is present.
    """
    slug_part = dir_name.rsplit("-", 1)[0]
    if len(slug_part) <= leaf_len:
        return ""
    return slug_part[: len(slug_part) - leaf_len - 1]


def test_a_parent_hyphen_at_the_truncation_boundary_keeps_the_min_char_guarantee():
    """room lands exactly on _MIN_PARENT_CHARS (4), with a real word boundary
    hyphen sitting right where the slice cuts. parent[:room] keeps a
    trailing hyphen that strip('-') then removes, so the parent fragment
    that actually reaches the final slug is 3 characters, one below the
    minimum the room check was supposed to guarantee.
    """
    parent_raw = "abc-defghijklmnopqrstuvwxyz0123456789ABCDEFGH"
    parent_slug = slugify_name(parent_raw)
    assert parent_slug[:4] == "abc-", "the hyphen must land at index 3"

    leaf = "z" * 35  # room = MAX_SLUG - 35 - 1 = 4, the exact boundary
    dir_name = project_dir_name(f"C:/{parent_raw}/{leaf}")
    fragment = _embedded_parent_fragment(dir_name, len(leaf))

    assert not (0 < len(fragment) < _MIN_PARENT_CHARS), (
        f"parent fragment {fragment!r} (len {len(fragment)}) reached the "
        f"slug despite being below _MIN_PARENT_CHARS ({_MIN_PARENT_CHARS}); "
        f"full dir_name={dir_name!r}"
    )


def test_slug_part_length_is_always_bounded_including_after_strip_side_effects():
    """Sanity companion: whatever the parent/leaf combination, the readable
    slug part must never exceed MAX_SLUG. Covered here across a boundary
    sweep with an internal hyphen present, which is the shape that produces
    the shrink above.
    """
    for leaf_len in (33, 34, 35, 36, 37):
        parent_raw = "abc-defghijklmnopqrstuvwxyz0123456789ABCDEFGH"
        leaf = "z" * leaf_len
        dir_name = project_dir_name(f"C:/{parent_raw}/{leaf}")
        slug_part = dir_name.rsplit("-", 1)[0]
        assert len(slug_part) <= MAX_SLUG, (leaf_len, dir_name)
