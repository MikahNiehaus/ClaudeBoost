"""Tests for search source parsing and topic validation."""

import sys
from pathlib import Path

import pytest

_root = str(Path(__file__).resolve().parent.parent)
if _root not in sys.path:
    sys.path.insert(0, _root)

from server.search import _TOPIC_NAME_RE  # noqa: E402


class TestSearchTopicValidation:
    """Topic names in search source specifiers must pass validation."""

    @pytest.mark.parametrize("name,valid", [
        ("fastapi", True),
        ("react-hooks", True),
        ("a1b2", True),
        ("../../etc", False),
        ("BAD_NAME", False),
        ("-dash-start", False),
        ("has space", False),
        ("", False),
    ])
    def test_topic_regex(self, name, valid):
        result = bool(_TOPIC_NAME_RE.match(name)) if name else False
        assert result == valid, f"'{name}' should be {'valid' if valid else 'invalid'}"
