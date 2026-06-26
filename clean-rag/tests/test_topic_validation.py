"""Tests for topic name validation across CLI and server."""

import re
import sys
from pathlib import Path

import pytest

_root = str(Path(__file__).resolve().parent.parent)
if _root not in sys.path:
    sys.path.insert(0, _root)

from server.app import _validate_topic_name  # noqa: E402
from cli.topic import _validate_topic_name as cli_validate  # noqa: E402


class TestTopicNameValidation:
    """Both server and CLI must reject the same invalid names."""

    @pytest.mark.parametrize("name", [
        "fastapi",
        "react-hooks",
        "jwt-tokens",
        "python3",
        "a",
        "topic-with-underscores_too",
    ])
    def test_valid_names_accepted(self, name):
        assert _validate_topic_name(name) is None
        assert cli_validate(name) is None

    @pytest.mark.parametrize("name", [
        "",
        "-starts-with-dash",
        "_starts-with-underscore",
        "UPPERCASE",
        "has spaces",
        "../../etc",
        "path/traversal",
        "special!chars",
        "a" * 65,
    ])
    def test_invalid_names_rejected(self, name):
        assert _validate_topic_name(name) is not None
        assert cli_validate(name) is not None

    def test_server_and_cli_agree(self):
        """Both validation functions use the same regex."""
        test_names = [
            "ok", "BAD", "", "a-b-c", "../etc", "good123", "x" * 100,
        ]
        for name in test_names:
            server_result = _validate_topic_name(name)
            cli_result = cli_validate(name)
            # Both should agree on pass/fail
            assert (server_result is None) == (cli_result is None), \
                f"Disagreement on '{name}': server={server_result}, cli={cli_result}"
