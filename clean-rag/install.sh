#!/usr/bin/env bash
# clean-rag installer (Unix/macOS/WSL)
# Usage:
#   ./clean-rag/install.sh                     # full install with pre-seeding
#   ./clean-rag/install.sh --no-seed           # skip pre-seeding (fast)
#   ./clean-rag/install.sh --seed react,fastapi # seed specific topics
#   ./clean-rag/install.sh --skip-deps         # skip pip install

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
