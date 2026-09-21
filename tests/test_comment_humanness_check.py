"""comment-humanness-check.py had no length check and no narration check, so a
three sentence comment that restated the line under it passed clean as long as
it avoided the banned word list. These cover the two checks that close that gap.

The narration rule is ported from no-redundant-comments in
pertrai1/eslint-plugin-llm-core (MIT): compare the comment's opening verb
against the statement it sits on, and exempt any comment that says why.

Run: python -m pytest tests/test_comment_humanness_check.py -v
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parent.parent / "scripts" / "comment-humanness-check.py"


def run_hook(content: str):
    """Invoke the real script the way Claude Code's PostToolUse dispatch does."""
    payload = json.dumps({"tool_input": {"content": content}})
    proc = subprocess.run(
        [sys.executable, str(HOOK)],
        input=payload.encode("utf-8"),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
    )
    return proc.returncode, proc.stderr.decode("utf-8", errors="replace")


NARRATION_CASES = [
    ("return statement", "function f(a) {\n  // Return the total\n  return a.total;\n}"),
    ("named call", "const x = 1;\n// Save the record to the database\nsaveRecord(x);"),
    ("assignment", "// Get the active user\nconst user = store.activeUser;"),
    ("loop", "// Process each row\nfor (const row of rows) { work(row); }"),
    ("conditional", "// Check that the id is present\nif (!id) return;"),
    ("inline", "validateInput(x); // Validate the input"),
    ("python hash comment", "# Load the config\nconfig = read_config()"),
]


@pytest.mark.parametrize("label,src", NARRATION_CASES, ids=[c[0] for c in NARRATION_CASES])
def test_narration_is_flagged(label, src):
    rc, err = run_hook(src)
    assert rc == 0, "narration is a nudge, never a block"
    assert "[comment-narration]" in err, f"{label} went unflagged:\n{err}"


def test_comment_over_the_word_cap_is_flagged():
    src = (
        "// this comment goes on well past the point of usefulness and keeps adding "
        "words that nobody reading the code will ever actually need to see here\n"
        "const y = 2;"
    )
    rc, err = run_hook(src)
    assert rc == 0
    assert "[comment-length]" in err


EXEMPT_CASES = [
    # A comment carrying a reason has earned its words, however it opens.
    ("because", "// Return early because a null id means the row was deleted mid flight\nreturn null;"),
    ("race", "// Set the flag before the call, a race here leaks the token\nsetFlag(true);"),
    (
        "long but explains why",
        "// kept at ten because the upstream API rate limits past that and the retry "
        "storm takes the whole queue down with it every time we tried more\n"
        "const LIMIT = 10;",
    ),
]


@pytest.mark.parametrize("label,src", EXEMPT_CASES, ids=[c[0] for c in EXEMPT_CASES])
def test_explanatory_comments_are_left_alone(label, src):
    rc, err = run_hook(src)
    assert rc == 0
    assert "[comment-narration]" not in err, f"{label} was wrongly flagged:\n{err}"
    assert "[comment-length]" not in err, f"{label} was wrongly flagged:\n{err}"


def test_short_comment_that_does_not_restate_is_silent():
    rc, err = run_hook("// callers rely on the sort order\nrows.sort(byName);")
    assert rc == 0
    assert err.strip() == ""


def test_docstring_content_is_not_treated_as_a_comment():
    src = 'def f():\n    """\n    # Get the thing\n    """\n    return 1'
    rc, err = run_hook(src)
    assert rc == 0
    assert "[comment-narration]" not in err


def test_single_comment_still_reaches_the_new_checks():
    """The older nudges need three comments before they run. A file with one
    bad comment used to escape entirely, which is the hole these two fill."""
    rc, err = run_hook("// Fetch the rows\nconst rows = db.query(sql);")
    assert rc == 0
    assert "[comment-narration]" in err


def test_dash_block_still_wins_over_the_new_nudges():
    """Regression: a dash exits 2 before any nudge is printed."""
    rc, err = run_hook("// Get the non-blocking handle\nconst h = getHandle();")
    assert rc == 2
    assert "BLOCKED" in err
    assert "[comment-narration]" not in err


# --- adversarial: bad-cop findings below this line -------------------------


MALFORMED_PAYLOADS = [
    ("content is an int", '{"tool_input": {"content": 123}}'),
    ("content is a list", '{"tool_input": {"content": ["// Get the thing", "x=1"]}}'),
    ("tool_input is a list", '{"tool_input": ["new_string", "// Get the thing\\nx=1"]}'),
    ("tool_input is an int", '{"tool_input": 5}'),
    ("payload is a bare list", "[1,2,3]"),
    ("edits new_string is an int", '{"tool_input": {"edits": [{"new_string": 42}]}}'),
]


@pytest.mark.parametrize("label,raw_json", MALFORMED_PAYLOADS, ids=[c[0] for c in MALFORMED_PAYLOADS])
def test_malformed_payload_shapes_never_raise(label, raw_json):
    """The hook must never raise (only json.loads is guarded today).

    A payload where tool_input, or one of its fields, is not the plain
    string/dict shape Claude Code normally sends currently crashes with an
    uncaught traceback and exit code 1 instead of degrading to a no-op.
    """
    proc = subprocess.run(
        [sys.executable, str(HOOK)],
        input=raw_json.encode("utf-8"),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
    )
    assert proc.returncode in (0, 2), (
        f"{label} crashed instead of degrading to a no-op:\n"
        f"{proc.stderr.decode('utf-8', errors='replace')}"
    )


def test_regex_literal_with_escaped_slashes_does_not_corrupt_a_trailing_comment():
    """A same-line regex literal containing an escaped // must not be read
    as the comment marker. It currently is: extract_comment_code_pairs finds
    the FIRST "//" on the line, which lands inside the regex, and glues the
    regex tail onto the front of the real trailing comment. A legitimate
    19 word comment (one under the cap) is reported as 21 words because of
    the glued on regex tail, and the quoted "Original" text shown to the
    user is not the comment that was actually written.
    """
    real_comment = (
        "kept intentionally general so callers on either windows or posix paths "
        "get the same normalized result every single time"
    )
    assert len(real_comment.split()) == 19
    src = f'const stripSlashes = /\\/\\//g; // {real_comment}\nreturn stripSlashes;'
    rc, err = run_hook(src)
    assert rc == 0
    assert "[comment-length]" not in err, f"legit under-cap comment was flagged:\n{err}"


def test_arrow_function_callback_is_not_read_as_an_assignment():
    """check_narration's assignment branch matches any bare '=' not next to
    a comparison operator. '=>' satisfies that (the char after '=' is '>',
    which passes the negative lookahead), so a callback registration like
    beforeEach(() => {...}) is misread as a variable assignment and a
    genuinely explanatory setup comment gets flagged as narration.
    """
    src = "// Set up before each test\nbeforeEach(() => {\n  db.reset();\n});"
    rc, err = run_hook(src)
    assert rc == 0
    assert "[comment-narration]" not in err, f"callback registration misread as assignment:\n{err}"


def test_default_parameter_call_is_not_read_as_an_assignment():
    """Same root cause as the arrow function case: a named/default argument
    'size = 20' inside a call's parens trips the same bare '=' heuristic.
    """
    src = "// Load the default page size\nfetchPage(size = 20);"
    rc, err = run_hook(src)
    assert rc == 0
    assert "[comment-narration]" not in err, f"call with a default arg misread as assignment:\n{err}"


# --- re-check: fix 1/2/3 regression pass below this line -------------------


def test_comment_marker_directly_after_a_backslash_still_blocks_a_dash():
    """_inline_comment_index skips ANY "//" preceded by a backslash, on the
    theory that it is an escaped slash inside a regex literal. That heuristic
    only checks the single character right before the match, so a line where
    a backslash happens to sit directly against the comment marker, e.g. a
    regex ending in an escaped backslash with no space before the trailing
    comment, loses the comment entirely: extract_comment_texts returns [],
    and every check downstream, including the hard dash block, never sees it.

    Before this fix (plain stripped.find("//")) this same line correctly
    found the marker and blocked. This proves the fix regressed it: the
    non-blocking compound word in the trailing comment now sails through
    silently at exit 0 instead of blocking at exit 2.
    """
    src = "const re = /\\\\// non-blocking value here\nreturn re;"
    rc, err = run_hook(src)
    assert rc == 2, (
        "a dash-violating comment right after a backslash-adjacent // marker "
        f"was silently let through (rc={rc}, stderr={err!r})"
    )
    assert "BLOCKED" in err
