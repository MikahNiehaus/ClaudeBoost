"""high_stakes.scan_diff's `test-weakening` category.

Why this category is different from the other five, and why that difference is
the whole test surface:

The other categories (sql, auth, subprocess, concurrency, money) answer "where
would a passing test fail to prove the property". `test-weakening` answers "was
the test made to pass instead of the code". A silenced check is the one defect
that makes every other category's evidence worthless, because the suite reports
green either way.

That difference forces a real behavioral exemption. scan_diff skips comment only
lines, on purpose: a comment that merely names a surface ("handles auth, money,
SQL") is not high stakes code, and matching it is the over trigger that gets a
gate ignored. But for this one category the comment IS the defect.
`# type: ignore`, `# pylint: disable=...` and `// eslint-disable-next-line` are
the silencing mechanism itself, and they are frequently the entire line. So
test-weakening must bypass the comment only skip while the other five keep it.

Two directions both have to hold, and each has a named mutant below:
  - a standalone lint disable comment MUST trip test-weakening (exemption works)
  - a comment naming a surface MUST NOT trip the other categories (skip intact)

Run: python -m pytest tests/test_high_stakes_test_weakening.py -v
"""

import importlib.util
from pathlib import Path

import pytest

HOOKS_DIR = Path(__file__).resolve().parent.parent / "clean-rag" / "hooks"


def _load_high_stakes():
    spec = importlib.util.spec_from_file_location(
        "high_stakes_under_test", HOOKS_DIR / "high_stakes.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def hs():
    return _load_high_stakes()


# ---------------------------------------------------------------------------
# The category fires on real silencing, in the shapes it actually appears in
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "line,path",
    [
        ("@pytest.mark.skip(reason='flaky')", "tests/test_pay.py"),
        ("@pytest.mark.xfail(strict=False)", "tests/test_pay.py"),
        ("    @unittest.skip('later')", "tests/test_a.py"),
        ("    total = a + b  # type: ignore", "src/calc.py"),
        ("    import legacy  # noqa: F401", "src/mod.py"),
        ("    const val = raw as any;", "src/a.ts"),
        ("    doThing(payload as any)", "src/a.ts"),
        ("    const v = raw as unknown as Widget;", "src/a.ts"),
        ("    // @ts-ignore", "src/a.ts"),
        ("    // @ts-expect-error", "src/a.ts"),
        ("    assert True", "tests/test_b.py"),
        ("    #[ignore]", "src/lib.rs"),
    ],
)
def test_real_silencing_trips(hs, line, path):
    hits = hs.scan_diff([line], [path])
    assert "test-weakening" in hits, f"missed: {line!r} -> {hits}"


# ---------------------------------------------------------------------------
# MUTANT 1: remove the comment-only exemption for test-weakening.
# A standalone lint disable is the most common real shape. If the exemption is
# dropped (`cat != "test-weakening"` -> always skip comment lines), these fail.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "line",
    [
        "# pylint: disable=broad-except",
        "# type: ignore",
        "# noqa",
        "// eslint-disable-next-line no-unused-vars",
        "/* eslint-disable */",
    ],
)
def test_standalone_silencing_comment_trips_despite_comment_skip(hs, line):
    """The comment IS the defect here, so the comment-only skip must not apply."""
    hits = hs.scan_diff([line], ["src/util.py"])
    assert "test-weakening" in hits, (
        f"standalone silencing comment was skipped: {line!r} -> {hits}. "
        "The comment-only skip must be exempt for test-weakening."
    )


# ---------------------------------------------------------------------------
# MUTANT 2: broaden the exemption to every category.
# If `cat != "test-weakening"` becomes `True` for all categories, the original
# over-trigger bug comes back: a comment merely naming surfaces starts flagging.
# ---------------------------------------------------------------------------

def test_comment_naming_surfaces_still_skipped_for_other_categories(hs):
    hits = hs.scan_diff(
        ["# handles auth, money, SQL, subprocess, concurrency"], ["src/util.py"]
    )
    assert hits == {}, (
        f"comment-only skip broke for the other categories: {hits}. "
        "Only test-weakening is exempt."
    )


def test_comment_discussing_weakening_does_not_trip(hs):
    """Prose about the rule is not the rule being broken.

    This file and the agent definitions both talk about weakening checks. A diff
    that adds such a sentence must not flag, or the category fires on its own
    documentation.
    """
    hits = hs.scan_diff(
        [
            "# never weaken a failing test to get green",
            "# a silenced check certifies the regression",
        ],
        ["docs/notes.py"],
    )
    assert hits == {}, hits


# ---------------------------------------------------------------------------
# MUTANT 3: add the rejected needles ("skip(", "except exception:").
# Both were considered and rejected because they hit ordinary code. A category
# that fires on every diff gets the whole gate ignored, which is the documented
# over-trigger failure mode. These lines are the reason.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "line,path",
    [
        ("    rows = q.skip(offset).limit(size)", "src/repo.py"),
        ("    items = query.skip(10)", "src/repo.py"),
        ("    except Exception as exc:", "src/util.py"),
        ("    except Exception:", "src/util.py"),
        ("    def skipped_count(self):", "src/report.py"),
        # The reason "as any" carries punctuation in the needle list. Prose and
        # ordinary identifiers containing the phrase must not flag, and this
        # category bypasses the comment-only skip, so a comment counts too.
        ("# apply to as any of the callers that need it", "src/util.py"),
        ("    if len(rows) > 0 or has_any(rows):", "src/util.py"),
        ("    label = 'known as anything else'", "src/util.py"),
    ],
)
def test_ordinary_code_does_not_trip(hs, line, path):
    """The over-trigger guard. These are normal lines, not tampering."""
    hits = hs.scan_diff([line], [path])
    assert "test-weakening" not in hits, (
        f"over-trigger on ordinary code: {line!r} -> {hits}"
    )


# ---------------------------------------------------------------------------
# The category coexists with the others rather than replacing them
# ---------------------------------------------------------------------------

def test_weakening_and_a_real_surface_both_reported(hs):
    hits = hs.scan_diff(
        [
            '    cur.execute("select * from users where id=%s" % uid)',
            "    assert True  # was: assert rows == expected",
        ],
        ["src/db.py"],
    )
    assert "sql" in hits, hits
    assert "test-weakening" in hits, hits


def test_evidence_is_the_real_line(hs):
    """The nudge quotes evidence, so it has to be the actual line, not a label."""
    hits = hs.scan_diff(["    total = a + b  # type: ignore"], ["src/calc.py"])
    assert hits["test-weakening"] == ["total = a + b  # type: ignore"], hits


def test_evidence_capped(hs):
    """_CAP keeps the nudge short. 12 hits must not produce 12 evidence lines."""
    lines = [f"    x{i} = y  # type: ignore" for i in range(12)]
    hits = hs.scan_diff(lines, ["src/a.py"])
    assert len(hits["test-weakening"]) <= hs._CAP, hits


def test_clean_diff_still_clean(hs):
    hits = hs.scan_diff(["def add(a, b):", "    return a + b"], ["src/mathutil.py"])
    assert hits == {}, hits
