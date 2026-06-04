"""
ClaudeBoost hook test runner.

Discovers all test_*.py files in scripts/tests/ and runs them via pytest.
Usage:
  python scripts/test-hooks.py           # run all hook tests
  python scripts/test-hooks.py -v        # verbose output
  python scripts/test-hooks.py -k gate   # filter by keyword
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent / "tests"


def main() -> int:
    if not TESTS_DIR.exists():
        print(f"ERROR: tests directory not found at {TESTS_DIR}", file=sys.stderr)
        return 1

    test_files = sorted(TESTS_DIR.glob("test_*.py"))
    if not test_files:
        print("No test files found in scripts/tests/", file=sys.stderr)
        return 1

    print(f"Running {len(test_files)} hook test file(s) from {TESTS_DIR}\n")

    # Forward any extra args (e.g. -v, -k) to pytest
    extra_args = sys.argv[1:]

    result = subprocess.run(
        [sys.executable, "-m", "pytest", str(TESTS_DIR), *extra_args],
        cwd=str(TESTS_DIR),
    )
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
