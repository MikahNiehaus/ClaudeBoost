#!/usr/bin/env bash
# clean-rag OpenCode integration uninstaller (Unix/macOS/WSL)
#
# KEEP IN SYNC WITH uninstall.bat. Both just find Python and exec uninstall.py.
#
# Usage:
#   ./clean-rag/opencode/uninstall.sh

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
