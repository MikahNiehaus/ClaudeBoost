#!/usr/bin/env bash
#
# ClaudeBoost — run this once after cloning to get fully set up on macOS/Linux.
#
# What this does:
#   1. Clears any stale hooks from a previous install (safe on fresh install)
#   2. Runs Python setup (installs RAG server, hooks, MCP config)
#   3. Opens Claude Code and runs /setup to verify everything

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

echo ""
echo " ClaudeBoost"
echo " ==========="
echo " Run this once after cloning to get fully set up."
echo ""
echo " What this does:"
echo "   1. Clears any stale hooks from a previous install (safe on fresh install)"
echo "   2. Runs setup.py (installs RAG server, hooks, MCP config)"
echo "   3. Opens Claude Code and runs /setup to verify everything"
echo ""
read -rp "Press Enter to continue (or Ctrl-C to abort)..." _

# ── Step 1: Clear stale hooks ────────────────────────────────────────────────
echo ""
echo "[1/3] Clearing stale hooks..."
echo ""
"$PY" "$BOOST_DIR/scripts/fix_hooks.py"

# ── Step 2: Setup ────────────────────────────────────────────────────────────
echo ""
echo "[2/3] Running setup..."
echo ""
if ! "$PY" "$BOOST_DIR/scripts/setup.py"; then
    echo ""
    echo " [ERROR] Setup failed. Fix the issues shown above, then re-run this file."
    exit 1
fi

# ── Step 3: Open Claude Code with /setup to verify ───────────────────────────
echo ""
echo "[3/3] Opening Claude Code..."
echo "      Claude will run /setup automatically to verify all systems."
echo ""
cd "$BOOST_DIR"
if command -v claude >/dev/null 2>&1; then
    claude "/setup"
else
    echo "Claude CLI not found on PATH. Install it, then run: claude /setup"
fi
