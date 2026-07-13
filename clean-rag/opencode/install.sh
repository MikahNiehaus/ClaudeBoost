#!/usr/bin/env bash
# clean-rag OpenCode integration installer (Unix/macOS/WSL)
#
# KEEP IN SYNC WITH install.bat. Both just find a Python interpreter and exec
# install.py, so the real logic lives in install.py. Change one, change the other.
#
# Usage:
#   ./clean-rag/opencode/install.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

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
