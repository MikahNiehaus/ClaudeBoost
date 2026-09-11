"""Whether the _KEY_NAME widening (dots and hyphens) is really the zero cost
change file_scan.py's own comment claims.

The comment above _KEY_NAME reports the widening as "zero additional files
dropped, and none lost" across six real projects, and now says in the same
breath that this is what one corpus contained rather than what the class
costs. These three shapes are the cost it names; this file is what keeps
that paragraph honest, since a comment cannot fail.

These three cases are real dotted or hyphenated Spring/Java/.NET style
config keys, independently constructed rather than copied from the module's
own examples, that contain a credential keyword as a SUBSTRING of a longer,
non credential key name. _SECRET_NAME_RE does a bare re.search and
_NOT_THE_SECRET_NAME_RE only excludes a fixed suffix list (name, message,
label, policy, error, hint, prompt, title, description, regex, pattern,
length, enabled, required, placeholder, visible), which none of these three
end with, so all three pass every guard after the name match and get
flagged as though they held a live credential.

None of them use ``[`` or ``"`` next to the operator, so this is
attributable to the widened _KEY_NAME character class specifically
(dots and hyphens now allowed throughout the name), not to _CLOSING, which
this rule (_ENV_SECRET_ASSIGNMENT_RE) does not use at all.

Pinned rather than fixed, the same way the sibling _CLOSING tradeoff file
pins its two shapes: over-suppression is this module's accepted direction.
Narrowing the rule to spare them would mean extending
_NOT_THE_SECRET_NAME_RE's suffix list by guesswork, and a guess in that
direction loses a real credential rather than a search hit.
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server.file_scan import looks_like_secret  # noqa: E402


def _scan(text: str, suffix: str = ".txt") -> bool:
    d = Path(tempfile.mkdtemp())
    p = d / f"probe{suffix}"
    p.write_text(text, encoding="utf-8")
    return looks_like_secret(p)


class TestKeyNameWideningHasARealFalsePositiveClass:
    def test_a_rotation_schedule_key_is_wrongly_flagged(self):
        """The key names WHEN a key rotates, not the key itself."""
        text = "app.api-key-rotation-schedule=EVERY_30_DAYS_AT_MIDNIGHT_UTC"
        assert _scan(text) is True, (
            "the accepted over-suppression from the widened _KEY_NAME "
            "stopped happening for a dotted/hyphenated rotation schedule "
            "key; re-check whether that widening is still cost free before "
            "trusting the comment's zero"
        )

    def test_a_refresh_interval_key_is_wrongly_flagged(self):
        """A numeric interval config value, not a token."""
        text = "com.example.auth-token-refresh-interval-ms=1800000000000000"
        assert _scan(text) is True, (
            "the accepted over-suppression from the widened _KEY_NAME "
            "stopped happening for a dotted refresh interval key; "
            "re-check the zero-cost claim before trusting it"
        )

    def test_a_secret_file_path_key_is_wrongly_flagged(self):
        """A filesystem path to where a secret lives, not the secret."""
        text = "service.client-secret-file-path=/etc/secrets/client.pem"
        assert _scan(text) is True, (
            "the accepted over-suppression from the widened _KEY_NAME "
            "stopped happening for a dotted secret-file-path key; "
            "re-check the zero-cost claim before trusting it"
        )

    def test_none_of_the_three_shapes_matched_before_widening(self):
        """Confirms these are new cost from _KEY_NAME, not preexisting
        behaviour, the same proof style the _CLOSING pin file uses."""
        import re

        old_key_name = r"[A-Za-z_][A-Za-z0-9_]*"
        old_env_re = re.compile(
            r"^[ \t]*(?:export[ \t]+)?(?P<name>" + old_key_name + r")="
            r"(?P<value>[^\s#]+)[ \t]*$",
            re.MULTILINE,
        )
        shapes = [
            "app.api-key-rotation-schedule=EVERY_30_DAYS_AT_MIDNIGHT_UTC",
            "com.example.auth-token-refresh-interval-ms=1800000000000000",
            "service.client-secret-file-path=/etc/secrets/client.pem",
        ]
        for text in shapes:
            assert not list(old_env_re.finditer(text)), (
                f"{text!r} already matched the undotted key name, so it is "
                f"not cost the widening introduced"
            )


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v", "-s"]))
