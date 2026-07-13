#!/usr/bin/env bash
# clean-rag installer (Unix/macOS/WSL)
#
# KEEP IN SYNC WITH install.bat: this is the Linux/macOS twin of the
# Windows installer. Both just find a Python interpreter and exec
# install.py with the same args, so the real logic lives in install.py --
# but if you change flag handling, usage text, or the Python-detection
# fallback order here, make the matching change in install.bat too (and
# vice versa), or the two platforms will drift out of sync silently.
#
# Usage:
#   ./clean-rag/install.sh                # full install (idempotent, safe to re-run)
#   ./clean-rag/install.sh --skip-deps    # skip pip install

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Find Python: prefer python3, fall back to python
if command -v python3 &>/dev/null; then
    PYTHON=python3
elif command -v python &>/dev/null; then
    PYTHON=python
else
    echo "ERROR: Python not found. Install Python 3.10+ and try again."
    exit 1
fi

echo "Using Python: $("$PYTHON" --version)"
exec "$PYTHON" "$SCRIPT_DIR/install.py" "$@"
