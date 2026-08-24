"""clean-rag's suite must never fail purely because a test dependency is absent.

27 of its tests are async and carry @pytest.mark.asyncio. Without pytest-asyncio
pytest does not skip them, it fails them, and the only clue is a warning that
reads like a typo in the test file rather than a missing package:

    PytestUnknownMarkWarning: Unknown pytest.mark.asyncio, is this a typo?

So a correct checkout reported 27 failures. Combined with 21 Windows only tests
that also failed on macOS, the suite sat at 48 red for long enough that the red
became the expected state, which is how a suite stops being read at all.

The fix is clean-rag/tests/conftest.py, which converts those into skips naming
the install command, plus clean-rag/requirements-dev.txt declaring the
dependency that was never declared anywhere.

This guards both. It runs pytest in a subprocess with the plugin forced off,
which reproduces a machine that has not installed it, and asserts the result is
skips rather than failures.

Run: python -m pytest tests/test_clean_rag_suite_reports_honestly.py -v
"""

import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
CLEAN_RAG_TESTS = REPO / "clean-rag" / "tests"
CONFTEST = CLEAN_RAG_TESTS / "conftest.py"
DEV_REQS = REPO / "clean-rag" / "requirements-dev.txt"

#: A file known to be mostly async. Named explicitly so the test fails loudly if
#: it is renamed, rather than quietly asserting nothing.
ASYNC_FILE = CLEAN_RAG_TESTS / "test_sweep_model_eviction_gating.py"


def test_the_async_test_file_still_exists():
    assert ASYNC_FILE.is_file(), (
        f"{ASYNC_FILE.name} is gone; point this test at another async file or "
        "drop it, but do not leave it asserting nothing"
    )
    assert "@pytest.mark.asyncio" in ASYNC_FILE.read_text(encoding="utf-8")


def test_missing_pytest_asyncio_produces_skips_not_failures():
    """The regression itself, reproduced by disabling the plugin."""
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", str(ASYNC_FILE), "-q", "-p", "no:asyncio"],
        capture_output=True, text=True, cwd=str(REPO), timeout=300,
    )
    out = proc.stdout + proc.stderr

    assert " failed" not in out, (
        "async tests FAILED with pytest-asyncio absent. They must skip with an "
        "actionable reason instead, or a missing test dependency looks "
        f"identical to real bugs.\n{out[-800:]}"
    )
    assert "skipped" in out, f"expected skips, got:\n{out[-500:]}"


def test_the_skip_reason_names_the_install_command():
    """A skip nobody can act on is only marginally better than a failure."""
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", str(ASYNC_FILE), "-q", "-p", "no:asyncio"],
        capture_output=True, text=True, cwd=str(REPO), timeout=300,
    )
    out = proc.stdout + proc.stderr
    assert "pytest-asyncio" in out, "the skip should name the missing package"
    assert "requirements-dev.txt" in out, (
        "the skip should name the file that declares it"
    )


def test_the_dependency_is_declared():
    assert DEV_REQS.is_file(), (
        "clean-rag/requirements-dev.txt is missing. Test dependencies being "
        "undeclared is the root cause here, not the symptom."
    )
    text = DEV_REQS.read_text(encoding="utf-8")
    assert re.search(r"^pytest-asyncio", text, re.M), (
        "pytest-asyncio must be declared in requirements-dev.txt"
    )


def test_the_conftest_registers_the_marker():
    """
    Registering it removes the "unknown mark, is this a typo" warning, which
    pointed at the test file instead of at the absent package.
    """
    assert CONFTEST.is_file(), "clean-rag/tests/conftest.py is missing"
    text = CONFTEST.read_text(encoding="utf-8")
    assert "markers" in text and "asyncio" in text


def test_windows_only_tests_are_marked_not_failing():
    """
    The other half of the 48: tests asserting Windows filesystem spelling
    (trailing dots, drive roots, UNC, 8.3 aliases) ran unguarded on macOS.
    """
    resolution = CLEAN_RAG_TESTS / "test_project_root_resolution.py"
    if not resolution.is_file():
        pytest.skip("test_project_root_resolution.py not present")
    text = resolution.read_text(encoding="utf-8")
    assert "windows_only" in text, (
        "the Windows specific cases must carry a skip marker, not fail on POSIX"
    )
    assert 'os.name != "nt"' in text
