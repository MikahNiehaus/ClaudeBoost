"""
Adversarial tests for walkthrough SKILL.md URL validation logic.
The skill documents allowed URLs in Phase 0 and the Safety section.
These tests prove the documented allow list is complete and consistent,
and that the command .md has an imprecise description vs the full skill.

Run with: python plans/test_walkthrough_url_validation.py
"""

import re
import sys

passed = 0
failed = 0


def test(name, fn):
    global passed, failed
    try:
        fn()
        print(f"  PASS  {name}")
        passed += 1
    except AssertionError as e:
        print(f"  FAIL  {name}")
        print(f"        {e}")
        failed += 1


def assert_true(cond, msg):
    if not cond:
        raise AssertionError(msg)


# This is the allow list as documented in SKILL.md Phase 0 and Safety section.
# The skill says: "localhost, 127.0.0.1, 0.0.0.0, *.local, *.test"
ALLOWED_PATTERNS = [
    r'^https?://localhost(:\d+)?(/.*)?$',
    r'^https?://127\.0\.0\.1(:\d+)?(/.*)?$',
    r'^https?://0\.0\.0\.0(:\d+)?(/.*)?$',
    r'^https?://[^/]+\.local(:\d+)?(/.*)?$',
    r'^https?://[^/]+\.test(:\d+)?(/.*)?$',
]


def is_allowed(url):
    """Check if URL matches the documented allow list."""
    return any(re.match(pat, url) for pat in ALLOWED_PATTERNS)


# The command .md says: "A URL (required, must be localhost)"
# This is LESS specific than the full allow list in SKILL.md.
# An implementation reading only the command .md would refuse 127.0.0.1, 0.0.0.0, *.local, *.test.
def command_md_allows(url):
    """Only allows localhost per the command .md description."""
    return re.match(r'^https?://localhost(:\d+)?(/.*)?$', url) is not None


# Allowed URLs per SKILL.md
ALLOWED_URLS = [
    "http://localhost:3000",
    "http://localhost:3000/dashboard",
    "https://localhost:8443",
    "http://127.0.0.1:5000",
    "http://0.0.0.0:8080",
    "http://myapp.local",
    "http://myapp.local:3000",
    "http://myapp.test",
    "http://myapp.test:5173",
]

# URLs that are not local and must be refused
DISALLOWED_URLS = [
    "https://example.com",
    "https://staging.myapp.com",
    "http://10.0.0.1:3000",    # private IP, not in the documented allow list
    "http://192.168.1.100",    # LAN IP, not in the documented allow list
    "https://localhost.evil.com",  # subdomain lookalike
    "http://notlocalhost",     # no TLD, not localhost
    "https://localhosts",      # typo
    "ftp://localhost:21",      # non-http scheme
]


test("All documented localhost variants are allowed", lambda: (
    [assert_true(is_allowed(u), f"Should allow {u}") for u in ALLOWED_URLS]
))

test("Non-local URLs are refused", lambda: (
    [assert_true(not is_allowed(u), f"Should refuse {u}") for u in DISALLOWED_URLS]
))

# The command .md imprecision finding: it says "must be localhost" but
# 127.0.0.1 and *.local are also allowed per the actual skill
test("FINDING: command.md says 'localhost' only but skill allows 5 patterns", lambda: (
    assert_true(
        not command_md_allows("http://127.0.0.1:5000"),
        "command.md's 'localhost only' description rejects 127.0.0.1 which SKILL.md allows"
    ) or True  # We expect this to NOT allow 127.0.0.1 per the command description
))


def test_command_md_inconsistency():
    # command.md says "A URL (required, must be localhost)"
    # SKILL.md allows: localhost, 127.0.0.1, 0.0.0.0, *.local, *.test
    # These are inconsistent — command.md is too narrow
    assert_true(
        is_allowed("http://127.0.0.1:5000"),
        "SKILL.md allows 127.0.0.1"
    )
    assert_true(
        not command_md_allows("http://127.0.0.1:5000"),
        "command.md's description does not include 127.0.0.1"
    )
    # The inconsistency is real: the two files disagree on what is allowed


test("command.md vs SKILL.md inconsistency: 127.0.0.1 allowed by skill, not by command description",
     test_command_md_inconsistency)

# Edge case: localhost. with trailing dot (rare but valid DNS)
test("localhost with trailing dot - documented allowlist doesn't match (edge case)", lambda: (
    assert_true(
        not is_allowed("http://localhost."),
        "localhost. (trailing dot) should not match the pattern"
    )
))

# Edge case: IPv6 loopback, not in allow list
test("IPv6 loopback ::1 - not in documented allowlist", lambda: (
    assert_true(
        not is_allowed("http://[::1]:3000"),
        "[::1] (IPv6 loopback) is not in the documented allowlist"
    )
))

print()
print(f"Results: {passed} passed, {failed} failed")
if failed > 0:
    sys.exit(1)
