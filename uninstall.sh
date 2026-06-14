#!/usr/bin/env bash
#
# ClaudeBoost uninstaller for macOS / Linux.
#
# The mirror image of install.sh. Hands off to scripts/uninstall.py, which
# reverses what setup.py did: hooks, env, statusLine, permissions, the
# ~/.claude symlinks/helpers, the rag-server MCP entry, and the RAG daemon.
#
# Default removes only ClaudeBoost's footprint. Pass --purge for the heavier
# shared bits (pip package, RAG index, PATH edit, mcp-debugger/playwright).
# Pass --dry-run to preview without changing anything.
#
# Usage:
#   ./uninstall.sh                # remove CB footprint (asks first)
#   ./uninstall.sh --dry-run      # show the plan, change nothing
#   ./uninstall.sh --purge --yes  # full removal, no prompt
#
# The repo folder itself is never deleted, remove it yourself afterward.

set -e

BOOST_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

PY=""
if command -v python3 >/dev/null 2>&1; then
    PY="python3"
elif command -v python >/dev/null 2>&1; then
    PY="python"
else
    echo "ERROR: python3 not found on PATH. Install Python 3.9+ first."
    exit 1
fi

exec "$PY" "$BOOST_DIR/scripts/uninstall.py" "$@"
