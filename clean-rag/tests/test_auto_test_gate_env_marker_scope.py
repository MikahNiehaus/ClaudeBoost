"""A real test failure must not be excused as an environment problem.

ENV_MARKERS is a substring scan over the whole failure text, and every string
in it is also something a test may legitimately assert about: a retry test
asserts on "connection refused", a CLI wrapper on "command not found", an
import guard on "No module named". Any such failure was reclassified as
unfixable and the stop was allowed, silently, on the one hook in this family
that genuinely blocks.

The separator is the runner's own tally. A launch failure never prints one,
because nothing ran. The documented contract is unchanged: a genuine
environment problem still allows.
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
    spec = importlib.util.spec_from_file_location("auto_test_gate_under_test", HOOK)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


atg = _load()

BLOCKS, ALLOWS = 2, 0


def _gate_verdict(failures: str, monkeypatch, tmp_path) -> int:
    """main()'s real exit code for a failing run with this output.

    Drives the shipped decision rather than re-spelling it here: a test that
    restates the condition it is checking passes just as happily when the
    condition ships inverted.

    Everything main() reaches for outside itself is declared, not inherited:
    the repo it would detect, the runner result, and the block-budget directory.
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
    payload = {"cwd": str(tmp_path), "session_id": "env-marker-scope"}
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
    return atg.main()


REAL_FAILURES = {
    "pytest, assertion names a refused connection": """\
=================================== FAILURES ===================================
____________________ test_retries_on_connection_refused ________________________
>       assert client.attempts == 3
E       AssertionError: expected 3 retry attempts after ConnectionRefusedError, got 1.
E       requests.exceptions.ConnectionError: [Errno 111] Connection refused
=========================== short test summary info ============================
FAILED tests/test_http_client.py::test_retries_on_connection_refused
========================= 1 failed, 2 passed in 0.42s ==========================
""",
    "unittest, assertion names a missing binary": """\
Ran 4 tests in 0.03s

FAILED (failures=1)
FAIL: test_reports_missing_binary (tests.test_cli.CliTest)
AssertionError: 'ffmpeg: command not found' != 'ffmpeg is not installed'
""",
    "jest, assertion names a missing module": """\
  ● loader › reports a missing optional dependency

    expect(received).toBe(expected)
    Received: "Cannot find module 'sharp'"
Tests:       1 failed, 7 passed, 8 total
""",
    "pytest, import guard asserts on the import error text": """\
E       AssertionError: assert 'No module named torch' in 'ImportError'
========================= 1 failed, 9 passed in 1.10s ==========================
""",
}

GENUINE_ENV = {
    "npm missing on windows": (
        "'npm' is not recognized as an internal or external command,\n"
        "operable program or batch file.\n"
    ),
    "npm missing on posix": "/bin/sh: 1: npm: command not found\n",
    "pytest not installed": "C:\\Python312\\python.exe: No module named pytest\n",
    "jest not installed": (
        "Error: Cannot find module 'jest'\n"
        "    at Function.Module._resolveFilename (node:internal/modules/cjs/loader:1077:15)\n"
    ),
    "npx cannot resolve the package": (
        "npm ERR! could not determine executable to run\n"
    ),
}


@pytest.mark.parametrize("label", sorted(REAL_FAILURES))
def test_a_real_failure_is_not_excused(label, monkeypatch, tmp_path):
    failures = REAL_FAILURES[label]
    assert any(m in failures.lower() for m in atg.ENV_MARKERS), (
        "fixture no longer exercises the bug: it contains no ENV_MARKER"
    )
    assert _gate_verdict(failures, monkeypatch, tmp_path) == BLOCKS, (
        f"a real test failure was excused as an environment problem: {label}"
    )


@pytest.mark.parametrize("label", sorted(GENUINE_ENV))
def test_a_genuine_environment_problem_still_allows(label, monkeypatch, tmp_path):
    """The hook's documented contract, unchanged: when the runner never
    launched, allow rather than block on something the model cannot fix."""
    assert _gate_verdict(GENUINE_ENV[label], monkeypatch, tmp_path) == ALLOWS, (
        f"a genuine environment problem would now block the stop: {label}"
    )


def test_an_ordinary_failure_with_no_env_wording_still_blocks(monkeypatch, tmp_path):
    failures = (
        "E       AssertionError: assert 4 == 5\n"
        "========================= 1 failed in 0.02s ==========================\n"
    )
    assert _gate_verdict(failures, monkeypatch, tmp_path) == BLOCKS


def test_the_real_failure_text_reaches_the_model(monkeypatch, tmp_path, capsys):
    """Blocking is only useful if the assertion diff comes back with it."""
    failures = REAL_FAILURES["pytest, assertion names a refused connection"]
    assert _gate_verdict(failures, monkeypatch, tmp_path) == BLOCKS
    assert "expected 3 retry attempts" in capsys.readouterr().err
