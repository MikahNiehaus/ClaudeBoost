"""
ClaudeBoost hook test runner.

Runs both hook test trees:
  scripts/tests/      the scripts/ hooks (bash-guard, tdd-guard, consult-gate, ...)
  clean-rag/tests/    the clean-rag hooks (research-gate, auto-test-gate, verifier-gate, ...)

The clean-rag tree used to be left out, so the three hooks with the sharpest
correctness properties had no coverage from the "run all hook tests" entry
point.

Each tree gets its own pytest process. One invocation over both paths does not
work: both directories are named `tests` and both carry an `__init__.py`, so
they claim the same top level package name and the second one to be collected
fails every import with ModuleNotFoundError. Separate processes also keep each
tree's working directory the way its tests already expect.

The exit code is nonzero if either tree fails.

Usage:
  python scripts/test-hooks.py           # run all hook tests
  python scripts/test-hooks.py -v        # verbose output
  python scripts/test-hooks.py -k gate   # filter by keyword
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
TEST_DIRS = (
    REPO_ROOT / "scripts" / "tests",
    REPO_ROOT / "clean-rag" / "tests",
)


def main() -> int:
    present = [d for d in TEST_DIRS if d.exists()]
    if not present:
        print(
            "ERROR: no test directory found. Looked for:\n  "
            + "\n  ".join(str(d) for d in TEST_DIRS),
            file=sys.stderr,
        )
        return 1

    for missing in (d for d in TEST_DIRS if not d.exists()):
        print(f"WARNING: {missing} not found, skipping it.", file=sys.stderr)

    counts = {d: len(sorted(d.glob("test_*.py"))) for d in present}
    if not sum(counts.values()):
        print("No test files found in any hook test directory.", file=sys.stderr)
        return 1

    # Forward any extra args (e.g. -v, -k) to pytest
    extra_args = sys.argv[1:]

    failed = []
    for d in present:
        print(f"\n=== {counts[d]} test file(s) from {d} ===\n", flush=True)
        result = subprocess.run(
            [sys.executable, "-m", "pytest", str(d), *extra_args],
            cwd=str(d),
        )
        if result.returncode != 0:
            failed.append((d, result.returncode))

    if failed:
        print("\nFAILED test trees:", file=sys.stderr)
        for d, code in failed:
            print(f"  {d} (pytest exit {code})", file=sys.stderr)
        return 1

    print(f"\nAll {sum(counts.values())} hook test file(s) passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
