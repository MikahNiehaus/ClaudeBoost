"""Adversarial tests for server/metrics.py's radon-backed metrics.

Ported from bad-cop's throwaway scripts so the coverage persists and runs with
the suite. Each test names the correctness property it pins down:

P1  maintainability_index is radon's mi_visit value, not a hand-rolled formula.
P2  the output dict always carries the same seven keys.
P3  a non-Python file, a .py file that does not parse, or a .py file that is
    valid Python the parser or radon still cannot process, all still report
    real lines_of_code and a call_graph and return no "error" key.
P4  complexity_rank is None without radon, A-F with it.
P5  no radon function is ever handed content that is not valid Python.
P6  get_metrics never serves a maintainability_index produced by older code.
P8  format_metrics_for_context renders no None score and does not raise when
    the Python-only fields are missing.
"""
import ast
import hashlib
import json
import logging
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path("C:/Development/ClaudeBoost/clean-rag")))

import server.metrics as metrics_mod
from server.metrics import (
    METRICS_SCHEMA_VERSION,
    _compute_metrics,
    format_metrics_for_context,
    get_metrics,
)

REQUIRED_KEYS = {
    "file",
    "lines_of_code",
    "cyclomatic_complexity",
    "complexity_rank",
    "maintainability_index",
    "call_graph",
    "computed_at",
}

INVALID_PYTHON = "def foo(:\n    this is not python !!!\n   x=== 1\n"


@pytest.fixture
def make_file(tmp_path):
    """Write content to a temp file with the given suffix, return its path."""
    counter = iter(range(1000))

    def _make(suffix, content):
        path = tmp_path / f"sample{next(counter)}{suffix}"
        path.write_text(content, encoding="utf-8")
        return str(path)

    return _make


# === P3 / P2: every file type keeps lines_of_code and call_graph ===

NON_PYTHON_CASES = [
    (".html", "<html>\n<body>\n<h1>Hi</h1>\n</body>\n</html>\n"),
    (".js", "function foo() { if (x) { return 1; } }\n"),
    (".go", "package main\nfunc main() { if true {} }\n"),
    (".md", "# Title\nSome text\n"),
    ("", "def looks_like_python():\n    if True:\n        pass\n"),
]

# Content that looks like Python to the eye but is routed by extension. Kept out
# of the LOC assertions above because a file of nothing but "#" lines has a
# legitimately zero LOC: the counter treats "#" as a comment marker.
LOOKS_LIKE_PYTHON_CASES = [
    (".md", "# if this looks like code: def foo():\n"),
]


@pytest.mark.parametrize("suffix,content", NON_PYTHON_CASES)
def test_non_python_file_reports_loc_and_no_error(make_file, suffix, content):
    """P3: radon cannot run, but LOC and the call graph still come back."""
    result = _compute_metrics(make_file(suffix, content))

    assert "error" not in result, f"P3 violated for {suffix!r}: {result}"
    assert result["lines_of_code"] > 0
    assert result["call_graph"] == {"functions": [], "classes": [], "imports": []}
    assert result["maintainability_index"] is None
    assert result["cyclomatic_complexity"] is None
    assert REQUIRED_KEYS <= set(result), f"P2 violated for {suffix!r}: {result.keys()}"


def test_invalid_python_syntax_keeps_loc_and_call_graph(make_file):
    """P3: a .py file with a syntax error must not hit radon's ast.parse and
    must not produce an 'error' key -- lines_of_code and call_graph survive.

    This is bad-cop's Finding 1 repro. Before the fix it returned only
    {'file', 'error': 'invalid syntax (<unknown>, line 1)'}.
    """
    result = _compute_metrics(make_file(".py", INVALID_PYTHON))

    assert result["lines_of_code"] > 0
    assert "error" not in result, f"P3 VIOLATED: unparseable .py produced {result}"
    assert REQUIRED_KEYS <= set(result)
    # No AST means no Python-only metrics, but the keys are still there.
    assert result["maintainability_index"] is None
    assert result["cyclomatic_complexity"] is None
    assert result["complexity_rank"] is None
    assert result["call_graph"] == {"functions": [], "classes": [], "imports": []}


def test_py_file_with_null_bytes_is_not_an_error(make_file, tmp_path):
    """P3: ast.parse raises ValueError, not SyntaxError, on embedded null bytes.
    That is still a source file that does not parse, not a failure to report."""
    path = tmp_path / "nulls.py"
    path.write_bytes(b"x = 1\n\x00\ndef f(): pass\n")

    result = _compute_metrics(str(path))

    assert "error" not in result, f"P3 violated for null-byte .py: {result}"
    assert result["lines_of_code"] > 0
    assert result["maintainability_index"] is None


@pytest.mark.parametrize("suffix,content", LOOKS_LIKE_PYTHON_CASES)
def test_python_looking_non_python_file_is_not_analysed(make_file, suffix, content):
    """P3/P5: the extension decides, so Python-looking prose in a .md file gets
    no radon metrics and no error either."""
    result = _compute_metrics(make_file(suffix, content))

    assert "error" not in result
    assert REQUIRED_KEYS <= set(result)
    assert result["maintainability_index"] is None
    # Every line is a "#" comment, so zero counted lines is the right answer.
    assert result["lines_of_code"] == 0


def test_unreadable_file_still_reports_error():
    """P2's escape hatch: a genuinely unreadable file is the one case where an
    'error' key is correct, so the fix must not swallow that too."""
    result = _compute_metrics("C:/Development/ClaudeBoost/clean-rag/no-such-file.py")

    assert "error" in result
    assert result["file"].endswith("no-such-file.py")


# === P3/P2: valid Python that a stack limit refuses ===
#
# The ast docs warn that "it is possible to crash the Python interpreter with a
# sufficiently large/complex string due to stack depth limitations in Python's
# AST compiler". CPython surfaces that as whichever stage ran out of stack, and
# there are two distinct stages with two distinct depth thresholds, so a
# pathological file lands in one of two bands. Both must keep the schema.

def _deep_source(depth: int) -> str:
    """Valid Python with a `depth`-deep unary expression, plus a real call graph
    so it is visible whether the graph survived."""
    return (
        "import os\n"
        "\n"
        "class Deep:\n"
        "    pass\n"
        "\n"
        "def go():\n"
        "    return " + "not " * depth + "os\n"
    )


def test_parser_stack_exhaustion_keeps_loc_and_schema(make_file):
    """P3 (bad-cop's re-check finding): at this depth CPython's PEG parser
    itself refuses the source, raising MemoryError("Parser stack overflowed")
    -- syntactically valid Python, but no AST. lines_of_code and the seven keys
    must survive; before the fix this returned only {'file', 'error'}."""
    source = _deep_source(20000)
    with pytest.raises(Exception) as excinfo:
        ast.parse(source)  # precondition: the parse stage is what fails here
    assert not isinstance(excinfo.value, (SyntaxError, ValueError)), (
        "precondition drifted: this input no longer exercises the non-SyntaxError "
        f"refusal path (got {type(excinfo.value).__name__})"
    )

    result = _compute_metrics(make_file(".py", source))

    assert "error" not in result, f"P3 VIOLATED: deeply nested valid .py produced {result}"
    assert REQUIRED_KEYS <= set(result)
    assert result["lines_of_code"] > 0
    # No AST, so no Python-only metrics and no call graph -- but the keys remain.
    assert result["maintainability_index"] is None
    assert result["cyclomatic_complexity"] is None
    assert result["complexity_rank"] is None
    assert result["call_graph"] == {"functions": [], "classes": [], "imports": []}


def test_radon_stack_exhaustion_keeps_call_graph_and_schema(make_file):
    """P3/P2: the narrower band where ast.parse succeeds but radon's recursive
    visitors do not. cc_visit/mi_visit walk the tree recursively and hit
    Python's recursion limit far below the C parser's own limit, so pre-gating
    the parse is not sufficient on its own.

    ast.walk is deque-based, so unlike the parse-stage case the call graph is
    fully recoverable here and must actually come back populated."""
    source = _deep_source(3000)
    ast.parse(source)  # precondition: the parse stage succeeds at this depth

    result = _compute_metrics(make_file(".py", source))

    assert "error" not in result, f"P3 VIOLATED: radon-unmeasurable .py produced {result}"
    assert REQUIRED_KEYS <= set(result)
    assert result["lines_of_code"] > 0
    assert result["maintainability_index"] is None
    assert result["cyclomatic_complexity"] is None
    assert result["complexity_rank"] is None
    # The AST parsed, so the call graph is real -- this is what keeping the two
    # guards separate buys, and a merged guard would discard.
    assert result["call_graph"]["functions"] == ["go"]
    assert result["call_graph"]["classes"] == ["Deep"]
    assert result["call_graph"]["imports"] == ["os"]


def test_stack_exhaustion_survives_the_public_entry_point(tmp_path, make_file):
    """P2 through get_metrics, not just _compute_metrics: the cached round trip
    of a pathological file is still the full schema, and still JSON-round-trips."""
    cache_dir = tmp_path / "metrics-cache"
    cache_dir.mkdir()
    src_path = make_file(".py", _deep_source(3000))

    with patch.object(metrics_mod, "METRICS_CACHE_DIR", cache_dir):
        fresh = get_metrics(src_path)
        cached = get_metrics(src_path)

    assert "error" not in fresh
    assert REQUIRED_KEYS <= set(fresh)
    assert cached == fresh, "a pathological file must cache and replay identically"


def test_unexpected_analyser_failure_is_logged_not_silently_swallowed(make_file, caplog):
    """The stated cost of guarding these steps with `except Exception`: a real
    bug in the analysis step cannot crash the run, so it must be loud instead.
    A TypeError out of radon is not a parse condition and must be logged at
    WARNING naming the class, never downgraded to a quiet INFO."""
    def exploding_cc_visit(source, **kwargs):
        raise TypeError("simulated programming error inside the analyser")

    with patch.object(metrics_mod, "cc_visit", exploding_cc_visit):
        with caplog.at_level(logging.WARNING, logger="server.metrics"):
            result = _compute_metrics(make_file(".py", "def f():\n    return 1\n"))

    assert "error" not in result
    assert REQUIRED_KEYS <= set(result)
    assert result["maintainability_index"] is None
    warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert warnings, "an unrecognised analyser failure was swallowed without a warning"
    assert "TypeError" in warnings[0].getMessage()


# === P5: radon is never invoked with content that is not valid Python ===

ALL_CASES = (
    NON_PYTHON_CASES
    + LOOKS_LIKE_PYTHON_CASES
    + [(".py", INVALID_PYTHON), (".py", "def ok():\n    return 1\n")]
)


@pytest.mark.parametrize("suffix,content", ALL_CASES)
def test_radon_only_ever_sees_parseable_python(monkeypatch, make_file, suffix, content):
    """P5: record the source handed to each radon entry point and assert every
    one of them is valid Python. An unparseable .py reaching cc_visit/mi_visit
    is what Finding 1 was."""
    seen: list[tuple[str, str]] = []
    real_cc_visit, real_mi_visit = metrics_mod.cc_visit, metrics_mod.mi_visit

    def spy_cc_visit(source, **kwargs):
        seen.append(("cc_visit", source))
        return real_cc_visit(source, **kwargs)

    def spy_mi_visit(source, multi):
        seen.append(("mi_visit", source))
        return real_mi_visit(source, multi)

    monkeypatch.setattr(metrics_mod, "cc_visit", spy_cc_visit)
    monkeypatch.setattr(metrics_mod, "mi_visit", spy_mi_visit)

    result = _compute_metrics(make_file(suffix, content))

    assert "error" not in result, f"P3 violated for {suffix!r}: {result}"
    for name, source in seen:
        ast.parse(source)  # raises if P5 is violated
    if content == INVALID_PYTHON:
        assert seen == [], f"P5 VIOLATED: radon called on unparseable source: {seen}"


# === P1 / P4: the value is radon's, and the rank tracks radon's availability ===

def test_maintainability_index_is_radons_mi_visit(make_file):
    """P1: the reported value equals radon.metrics.mi_visit for that source,
    never the old 171 - 5.2*(cc**0.4) - 0.23*loc + 50*loc**-0.5 formula."""
    from radon.metrics import mi_visit

    source = (
        "import os\n"
        "\n"
        "def walk(root):\n"
        "    total = 0\n"
        "    for dirpath, dirnames, filenames in os.walk(root):\n"
        "        for name in filenames:\n"
        "            if name.endswith('.py'):\n"
        "                total += len(name)\n"
        "            elif name.endswith('.md'):\n"
        "                total -= 1\n"
        "    return total\n"
    )
    result = _compute_metrics(make_file(".py", source))

    assert result["maintainability_index"] == round(mi_visit(source, True), 1)

    loc = result["lines_of_code"]
    cc = result["cyclomatic_complexity"]
    old_formula = round(
        max(0, min(100, 171 - 5.2 * (cc ** 0.4) - 0.23 * loc + 50 * (loc ** -0.5))), 1
    )
    assert result["maintainability_index"] != old_formula, (
        "maintainability_index still matches the old Halstead-less formula"
    )


def test_complexity_rank_is_a_letter_with_radon(make_file):
    """P4: radon computed a result, so the rank is one of A-F."""
    result = _compute_metrics(make_file(".py", "def foo():\n    return 1\n"))

    assert result["complexity_rank"] in ("A", "B", "C", "D", "E", "F")
    assert result["maintainability_index"] is not None


def test_complexity_rank_is_none_without_radon(make_file):
    """P4/P2: no radon means no rank and no MI, but the same seven keys."""
    path = make_file(".py", "x = 1\nif True:\n    y = 2\n")

    with patch.object(metrics_mod, "_HAS_RADON", False):
        result = _compute_metrics(path)

    assert REQUIRED_KEYS <= set(result)
    assert result["complexity_rank"] is None
    assert result["maintainability_index"] is None
    # The line-scan fallback still estimates complexity for a Python file.
    assert result["cyclomatic_complexity"] == 2


def test_call_graph_populated_for_valid_python(make_file):
    """The AST is parsed once and reused, so the call graph must still fill in."""
    result = _compute_metrics(
        make_file(".py", "import os\n\nclass Thing:\n    pass\n\ndef go():\n    return os\n")
    )

    assert result["call_graph"]["functions"] == ["go"]
    assert result["call_graph"]["classes"] == ["Thing"]
    assert result["call_graph"]["imports"] == ["os"]


# === P6: the cache never serves a value computed by older code ===

def test_stale_pre_change_cache_entry_is_not_served(tmp_path, make_file):
    """P6 / bad-cop Finding 2: an entry cached before this change (old formula's
    maintainability_index, no version stamp) must not be returned as if the
    current code produced it, even though the file content -- and so the file
    hash -- has not changed and the TTL has not expired."""
    cache_dir = tmp_path / "metrics-cache"
    cache_dir.mkdir()
    src_path = make_file(".py", "def bar():\n    return 42\n")

    with patch.object(metrics_mod, "METRICS_CACHE_DIR", cache_dir):
        file_hash = metrics_mod._get_file_hash(src_path)
        cache_file = cache_dir / f"{hashlib.sha256(src_path.encode()).hexdigest()[:8]}.json"
        cache_file.write_text(
            json.dumps(
                {
                    "file": src_path,
                    "file_hash": file_hash,  # matches: content never changed
                    "cached_at": datetime.now().isoformat(),  # inside the TTL
                    "metrics": {
                        "file": src_path,
                        "lines_of_code": 2,
                        "cyclomatic_complexity": 1,
                        "complexity_rank": "A",
                        "maintainability_index": 55.5,  # old formula's value
                        "call_graph": {"functions": ["bar"], "classes": [], "imports": []},
                        "computed_at": "2020-01-01T00:00:00",
                    },
                }
            ),
            encoding="utf-8",
        )

        result = get_metrics(src_path, force_recompute=False)
        real_mi = _compute_metrics(src_path)["maintainability_index"]

        assert result["maintainability_index"] != 55.5, (
            "P6 VIOLATED: stale pre-change cache entry served as-is"
        )
        assert result["maintainability_index"] == real_mi
        # The stale entry is replaced by a stamped one, so the next read hits.
        rewritten = json.loads(cache_file.read_text(encoding="utf-8"))
        assert rewritten["__metrics_version__"] == METRICS_SCHEMA_VERSION


def test_cache_entry_from_a_different_version_is_not_served(tmp_path, make_file):
    """P6: the stamp is compared, not merely present -- a future or older
    version number is just as invalid as a missing one."""
    cache_dir = tmp_path / "metrics-cache"
    cache_dir.mkdir()
    src_path = make_file(".py", "def baz():\n    return 7\n")

    with patch.object(metrics_mod, "METRICS_CACHE_DIR", cache_dir):
        cache_file = cache_dir / f"{hashlib.sha256(src_path.encode()).hexdigest()[:8]}.json"
        cache_file.write_text(
            json.dumps(
                {
                    "file": src_path,
                    "__metrics_version__": METRICS_SCHEMA_VERSION + 1,
                    "file_hash": metrics_mod._get_file_hash(src_path),
                    "cached_at": datetime.now().isoformat(),
                    "metrics": {"maintainability_index": 12.3},
                }
            ),
            encoding="utf-8",
        )

        result = get_metrics(src_path, force_recompute=False)

    assert result["maintainability_index"] != 12.3
    assert REQUIRED_KEYS <= set(result)


def test_current_cache_entry_is_served(tmp_path, make_file):
    """The version stamp must not defeat caching altogether: a stamped entry
    with a matching hash inside the TTL is still a hit."""
    cache_dir = tmp_path / "metrics-cache"
    cache_dir.mkdir()
    src_path = make_file(".py", "def qux():\n    return 1\n")

    with patch.object(metrics_mod, "METRICS_CACHE_DIR", cache_dir):
        first = get_metrics(src_path)
        # A sentinel only a cache hit could return.
        cache_file = cache_dir / f"{hashlib.sha256(src_path.encode()).hexdigest()[:8]}.json"
        entry = json.loads(cache_file.read_text(encoding="utf-8"))
        entry["metrics"]["computed_at"] = "1999-12-31T00:00:00"
        cache_file.write_text(json.dumps(entry), encoding="utf-8")

        second = get_metrics(src_path)

    assert first["maintainability_index"] == second["maintainability_index"]
    assert second["computed_at"] == "1999-12-31T00:00:00", "stamped entry was not reused"


def test_expired_cache_entry_is_recomputed(tmp_path, make_file):
    """The TTL still applies on top of the version stamp."""
    cache_dir = tmp_path / "metrics-cache"
    cache_dir.mkdir()
    src_path = make_file(".py", "def old():\n    return 1\n")

    with patch.object(metrics_mod, "METRICS_CACHE_DIR", cache_dir):
        get_metrics(src_path)
        cache_file = cache_dir / f"{hashlib.sha256(src_path.encode()).hexdigest()[:8]}.json"
        entry = json.loads(cache_file.read_text(encoding="utf-8"))
        stale = datetime.now() - timedelta(seconds=metrics_mod.CACHE_TTL_SECONDS + 60)
        entry["cached_at"] = stale.isoformat()
        entry["metrics"]["computed_at"] = "1999-12-31T00:00:00"
        cache_file.write_text(json.dumps(entry), encoding="utf-8")

        result = get_metrics(src_path)

    assert result["computed_at"] != "1999-12-31T00:00:00"


# === P8: formatting never renders a None score and never raises ===

def test_format_renders_no_none_for_non_python_metrics():
    out = format_metrics_for_context(
        [
            {
                "file": "foo.html",
                "lines_of_code": 5,
                "cyclomatic_complexity": None,
                "complexity_rank": None,
                "maintainability_index": None,
                "call_graph": {"functions": [], "classes": [], "imports": []},
                "computed_at": "2026-01-01T00:00:00",
            }
        ]
    )

    assert "None" not in out, f"format_metrics_for_context rendered a None: {out}"
    assert "LOC=5" in out


def test_format_does_not_raise_when_python_fields_absent():
    """P8: the Python-only keys missing entirely, not merely None."""
    out = format_metrics_for_context(
        [
            {
                "file": "bar.html",
                "lines_of_code": 3,
                "call_graph": {"functions": [], "classes": [], "imports": []},
                "computed_at": "2026-01-01T00:00:00",
            }
        ]
    )

    assert "None" not in out
    assert "- **bar.html**: LOC=3" in out


def test_format_renders_python_metrics_and_warning():
    out = format_metrics_for_context(
        [
            {
                "file": "app.py",
                "lines_of_code": 120,
                "cyclomatic_complexity": 25,
                "complexity_rank": "D",
                "maintainability_index": 41.7,
                "call_graph": {"functions": [], "classes": [], "imports": []},
                "computed_at": "2026-01-01T00:00:00",
                "complexity_warning": "Function big has complexity 25 (rank D), consider refactoring",
            }
        ]
    )

    assert "LOC=120, Complexity=25 (D), Maintainability=41.7" in out
    assert "Warning: Function big has complexity 25" in out


def test_format_skips_errored_entries():
    out = format_metrics_for_context([{"file": "gone.py", "error": "No such file"}])

    assert "gone.py" not in out
    assert "No such file" not in out


# === P7: the tree-sitter grammars declared in requirements are importable ===


# ---------------------------------------------------------------------------
# Tree-sitter grammar coverage.
#
# These used to assert against _LANG_MODULE_MAP, a hand kept table naming one
# pip package and one accessor function per language. That table is gone:
# edge_extraction now calls tree_sitter_language_pack.get_parser(), which ships
# 71 grammars as prebuilt wheels.
#
# The old table is also why one of these was an xfail. It mapped php to the
# attribute "language", but tree_sitter_php only ever exposed language_php, so
# .php files silently contributed zero graph edges. Swapping to the pack fixed
# that, which is why the marker is gone rather than moved.
# ---------------------------------------------------------------------------

#: Languages this project actually routes files to. If the pack cannot parse
#: one of these, that language contributes no edges and the loss is silent.
_REQUIRED_LANGUAGES = [
    "python", "javascript", "typescript", "tsx", "go", "rust", "java",
    "c", "cpp", "ruby", "bash", "lua", "kotlin", "swift", "php", "csharp",
]


def test_every_required_language_actually_parses():
    """Every language we route to must produce a working parser.

    A missing grammar does not raise anywhere: _get_parser caches None and that
    language quietly contributes zero edges to the import graph forever.
    """
    from server.edge_extraction import _get_parser

    missing = [lang for lang in _REQUIRED_LANGUAGES if _get_parser(lang) is None]
    assert not missing, f"no grammar available for: {missing}"


def test_php_parses():
    """Regression: the hand kept map named the wrong accessor for php, so php
    files contributed zero edges and nothing reported it."""
    from server.edge_extraction import _get_parser

    assert _get_parser("php") is not None


def test_the_hand_kept_grammar_table_is_gone():
    """Its per language pip pins and accessor names were maintained by hand and
    drifted; the pack replaces both."""
    import server.edge_extraction as ee

    assert not hasattr(ee, "_LANG_MODULE_MAP")


def test_requirements_declares_the_pack_not_individual_grammars():
    """One dependency, not one per language."""
    from pathlib import Path

    req = (Path(__file__).resolve().parent.parent / "requirements.txt").read_text(
        encoding="utf-8"
    )
    assert "tree-sitter-language-pack" in req
    assert "grep-ast" in req
    per_language = [
        line.strip() for line in req.splitlines()
        if line.strip().startswith("tree-sitter-")
        and "language-pack" not in line
    ]
    assert not per_language, (
        f"individual grammar pins should be gone, still present: {per_language}"
    )


def test_unknown_language_degrades_instead_of_raising():
    from server.edge_extraction import _get_parser

    assert _get_parser("definitely-not-a-language") is None
