"""Pins both sides of the trade file_scan.py's assignment regexes make.

The cost side: _CLOSING lets the quoted rule reach JSON, and in doing so it
also matches any bracket indexed name that merely contains a credential
keyword. Two such shapes are pinned below. Both are false positives, both are
kept on purpose, and pinning them means the module's stated cost stays honest
if anyone widens the class further. The measurement behind the figure in
file_scan.py is six real projects and 7846 files: 14 files dropped before
_CLOSING, 16 after.

The benefit side: a dotted Spring or Java style key with an unquoted value.
The two assignment regexes used to disagree about whether a key may contain a
dot, so ``spring.datasource.password=<live value>`` matched neither and was
indexed verbatim out of any extension CODE_EXTENSIONS accepts, .md and .txt
included. They share one name class now.
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server.file_scan import looks_like_secret, exclusion_reason  # noqa: E402


def _scan(text: str, suffix: str = ".txt") -> bool:
    d = Path(tempfile.mkdtemp())
    p = d / f"probe{suffix}"
    p.write_text(text, encoding="utf-8")
    return looks_like_secret(p)


class TestClosingBracketIntroducesMoreThanTheOneMeasuredShape:
    """Two realistic shapes the _CLOSING class matches beyond the .NET header
    case file_scan.py names. Neither holds a credential, both are dropped from
    the index anyway, and that is the accepted direction of the trade.

    Pinned rather than fixed: over-suppression is what this module chose, so
    these assert the current behaviour so the stated cost cannot drift without
    a red test."""

    def test_a_bracketed_error_code_map_is_wrongly_flagged(self):
        """An error catalogue keyed by a name that merely contains a credential
        keyword. 'api_key' names the field the error is about, not a secret."""
        text = 'errors["api_key"] = "missing-value-code"'
        assert looks_like_secret_from_text(text) is True, (
            "the accepted over-suppression stopped happening; re-measure the "
            "figure in file_scan.py before assuming that is an improvement"
        )

    def test_a_descriptive_identifier_containing_the_keyword_as_a_substring(self):
        """apiKey is a substring of the identifier, not the identifier itself.
        _SECRET_NAME_RE does a bare re.search, so a name containing a keyword
        anywhere qualifies, and _CLOSING is what lets a bracket indexed access
        reach that check. A fixture table is where this fires."""
        text = 'testCases["apiKeyValidationScenario"] = "abcd1234efgh5678"'
        assert looks_like_secret_from_text(text) is True, (
            "the accepted over-suppression stopped happening; re-measure the "
            "figure in file_scan.py before assuming that is an improvement"
        )

    def test_both_shapes_are_new_cost_from_the_closing_class(self):
        """Rebuilds the regex with CLOSING empty and proves neither shape above
        matched then, so both are cost the class introduced rather than
        behaviour that predates it."""
        import re
        from server import file_scan as fs

        pre_fix_re = re.compile(
            r"(?P<name>[A-Za-z_][A-Za-z0-9_.\-]*)"
            r"\s*[:=]\s*"
            r"(?P<quote>[\"'])(?P<value>[^\"'\n]+)(?P=quote)",
        )
        new_only_shapes = [
            'errors["api_key"] = "missing-value-code"',
            'testCases["apiKeyValidationScenario"] = "abcd1234efgh5678"',
        ]
        for text in new_only_shapes:
            assert not list(pre_fix_re.finditer(text)), (
                f"{text!r} already matched before _CLOSING was added, so it "
                f"is not cost the class introduced"
            )
            assert list(fs._QUOTED_SECRET_ASSIGNMENT_RE.finditer(text)), (
                f"{text!r} was expected to newly match after _CLOSING"
            )


def looks_like_secret_from_text(text: str) -> bool:
    return _scan(text)


class TestDottedKeyIsDetected:
    """A Spring or Java style dotted property key with an unquoted value.

    This used to escape both rules. The quoted rule allowed a dot in a key and
    the environment rule did not, so a key like ``spring.datasource.password``
    matched neither and its value was indexed verbatim. Both now build their
    name group from file_scan._KEY_NAME, which is what stops the two from
    disagreeing again.

    The exposure was never the .properties file, which is not in
    CODE_EXTENSIONS and never reaches this function. It is the same block
    pasted into an extension that is indexed: a README, a runbook, a .md
    troubleshooting note. That is the "jotted it into notes.md for now" case
    looks_like_secret says it exists to catch.
    """

    def test_a_dotted_key_with_an_unquoted_value_is_detected(self):
        text = "spring.datasource.password=SuperSecretDbPass123"
        assert looks_like_secret_from_text(text) is True

    def test_an_undotted_environment_key_is_still_detected(self):
        """The widened name class must not cost the shape it already had."""
        assert looks_like_secret_from_text("DB_PASSWORD=hunter2hunter2") is True

    def test_a_credential_in_an_indexed_markdown_runbook_is_excluded(
        self, tmp_path,
    ):
        """End to end at the layer that decides: is the file kept out of the
        index, the same way test_secret_content_in_text_docs.py's TODO.md case
        is, or does it pass every filter and get embedded?
        """
        runbook = tmp_path / "TROUBLESHOOTING.md"
        runbook.write_text(
            "# Troubleshooting the staging datasource\n\n"
            "Paste of the working application.properties for reference:\n\n"
            "spring.datasource.url=jdbc:postgresql://db.internal:5432/app\n"
            "spring.datasource.username=app_user\n"
            "spring.datasource.password=Tr0ub4dor&3Real2024\n",
            encoding="utf-8",
        )

        assert looks_like_secret(runbook) is True, (
            "a real looking database password in an indexed markdown file "
            "with a dotted key was not recognised, so it would be chunked, "
            "embedded, and returned verbatim by a /search hit"
        )
        assert exclusion_reason(runbook) == (
            "TROUBLESHOOTING.md contains what looks like a live credential"
        ), (
            "looks_like_secret sees it but exclusion_reason does not refuse "
            "the file, so nothing actually keeps it out of the index"
        )


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v", "-s"]))
