#!/usr/bin/env bash
# clean-rag uninstaller (Unix/macOS/WSL)
# Usage:
#   ./clean-rag/uninstall.sh            # remove hooks + env, keep data
#   ./clean-rag/uninstall.sh --purge    # also delete databases/ and state/

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

if command -v python3 &>/dev/null; then
    PYTHON=python3
elif command -v python &>/dev/null; then
    PYTHON=python
else
    echo "ERROR: Python not found."
    exit 1
fi

exec "$PYTHON" "$SCRIPT_DIR/uninstall.py" "$@"
