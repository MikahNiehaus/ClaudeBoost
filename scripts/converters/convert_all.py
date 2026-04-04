"""
Run all reference-to-knowledge converters.

Usage: python scripts/converters/convert_all.py
"""

import subprocess
import sys
from pathlib import Path

CONVERTERS_DIR = Path(__file__).resolve().parent

CONVERTERS = [
    "nodebestpractices.py",
    "system_design_primer.py",
    "java_design_patterns.py",
]


def main():
    for script in CONVERTERS:
        path = CONVERTERS_DIR / script
        if not path.exists():
            print(f"  SKIP {script}: not found")
            continue

        print(f"\n{'='*60}")
        print(f"  Running {script}")
        print(f"{'='*60}")

        result = subprocess.run(
            [sys.executable, str(path)],
            capture_output=False,
        )

        if result.returncode != 0:
            print(f"  FAILED: {script} (exit code {result.returncode})")

    print(f"\n{'='*60}")
    print("  All converters complete")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
