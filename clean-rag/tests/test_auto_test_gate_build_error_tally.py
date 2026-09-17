"""A build tool's own error count read as a test runner's tally.

_runner_reported_results decides whether the tests actually ran, and the answer
gates the one hook in this family that genuinely blocks. Its pytest pattern
counted `\\d+ (error|errors)`, which no test runner owns: webpack prints
"compiled with 1 error" on its own launch banner, MSBuild prints "1 Error(s)",
cargo prints "2 errors emitted". Each of those is a launch that never reached a
test.

The cost landed on the case the hook's docstring names as the failure mode to
avoid. jest was not installed, nothing ran, and the gate blocked the stop and
handed the model "Tests are failing. Fix from the actual output above" over
output naming no test failure at all.

"passed", "failed" and "skipped" are counted instead, because only a runner
counts those. pytest's tally of errors alone still counts where it is its own
summary line ending in the run duration, which is the shape pytest really
prints; the fixtures below were captured from pytest 9.0.3 rather than written
from memory.
"""

from __future__ import annotations

import importlib.util
import io
import json
import sys
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parents[1] / "hooks" / "auto-test-gate.py"


def _load():
    spec = importlib.util.spec_from_file_location("auto_test_gate_tally", HOOK)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


atg = _load()

BLOCKS, ALLOWS = 2, 0


def _gate_verdict(failures: str, monkeypatch, tmp_path) -> int:
    """main()'s real exit code for a failing run with this output.

    Everything main() reaches for outside itself is declared, not inherited:
    the repo it would detect, the runner result, and the block budget.
    """
    monkeypatch.setattr(atg, "_git_root", lambda cwd: str(tmp_path))
    monkeypatch.setattr(atg, "_code_changed", lambda root: True)
    monkeypatch.setattr(atg, "BLOCK_DIR", tmp_path / "budget")
    monkeypatch.setattr(
        atg,
        "_run_tests",
        lambda root: {
            "has_tests": True,
            "passed": False,
            "exit_code": 1,
            "failures": failures,
        },
    )
    payload = {"cwd": str(tmp_path), "session_id": "build-error-tally"}
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
    return atg.main()


# Launch failures from three build tools, each carrying its own error count and
# an ENV_MARKER. Nothing ran in any of them.
BUILD_TOOL_TALLIES = {
    "webpack counts its own compile error": (
        "webpack 5.88.0 compiled with 1 error in 342ms\n"
        "\n"
        "ERROR in ./src/index.test.js\n"
        "Module not found: Error: Can't resolve 'jest' in '/app/src'\n"
        "  Error: Cannot find module 'jest'\n"
    ),
    "msbuild counts errors in its build summary": (
        "MSB3644: The reference assemblies for .NETFramework were not found.\n"
        "\n"
        "Build FAILED.\n"
        "    0 Warning(s)\n"
        "    1 Error(s)\n"
        "'dotnet' is not recognized as an internal or external command\n"
    ),
    "cargo counts emitted errors": (
        "error[E0433]: failed to resolve: use of undeclared crate\n"
        "error: could not compile `app` (test \"integration\") due to 1 previous error\n"
        "note: 2 errors emitted\n"
        "Error: Cannot find module 'wasm-pack'\n"
    ),
}

# Captured from pytest 9.0.3 on a module whose import fails. pytest launched,
# so a real collection error is a real failure to report.
PYTEST_ERROR_ONLY = {
    "quiet mode, bare summary line": (
        "=================================== ERRORS ====================================\n"
        "____________________ ERROR collecting test_collect_fail.py ____________________\n"
        "test_collect_fail.py:1: in <module>\n"
        "    import definitely_not_installed_xyz\n"
        "E   ModuleNotFoundError: No module named 'definitely_not_installed_xyz'\n"
        "=========================== short test summary info ===========================\n"
        "ERROR test_collect_fail.py\n"
        "!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!\n"
        "1 error in 0.27s\n"
    ),
    "default verbosity, summary line in a banner": (
        "collected 0 items / 1 error\n"
        "E   ModuleNotFoundError: No module named 'definitely_not_installed_xyz'\n"
        "ERROR test_collect_fail.py\n"
        "!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!\n"
        "============================== 1 error in 0.14s ===============================\n"
    ),
}


@pytest.mark.parametrize("label", sorted(BUILD_TOOL_TALLIES))
def test_a_build_tools_error_count_is_not_a_test_tally(label):
    assert not atg._runner_reported_results(BUILD_TOOL_TALLIES[label]), (
        f"a build tool's own error count read as tests having run: {label}"
    )


@pytest.mark.parametrize("label", sorted(BUILD_TOOL_TALLIES))
def test_a_launch_failure_behind_a_build_tool_still_allows(label, monkeypatch, tmp_path):
    """The hook's documented contract. Nothing ran, the output names a missing
    module, and the model cannot fix it by editing code."""
    failures = BUILD_TOOL_TALLIES[label]
    assert any(m in failures.lower() for m in atg.ENV_MARKERS), (
        "fixture no longer exercises the bug: it contains no ENV_MARKER"
    )
    assert _gate_verdict(failures, monkeypatch, tmp_path) == ALLOWS, (
        f"a launch failure was blocked instead of allowed: {label}"
    )


@pytest.mark.parametrize("label", sorted(PYTEST_ERROR_ONLY))
def test_pytests_own_error_summary_still_counts_as_a_run(label):
    assert atg._runner_reported_results(PYTEST_ERROR_ONLY[label]), (
        f"pytest's own summary line stopped counting as a run: {label}"
    )


def test_a_failure_tally_still_counts_when_the_words_are_a_runners_own():
    for tally in ("1 failed, 1 passed, 1 error in 0.07s",
                  "Tests:       1 failed, 7 passed, 8 total",
                  "Ran 4 tests in 0.03s",
                  "3 skipped, 2 passed in 0.11s"):
        assert atg._runner_reported_results(tally), tally


def test_a_real_failure_carrying_env_wording_still_blocks(monkeypatch, tmp_path):
    """A test that asserts about a missing module is a real failure, not an
    environment problem. Narrowing the tally must not reopen that."""
    failures = (
        "E       AssertionError: assert 'No module named torch' in 'ImportError'\n"
        "========================= 1 failed, 9 passed in 1.10s ==========================\n"
    )
    assert _gate_verdict(failures, monkeypatch, tmp_path) == BLOCKS
