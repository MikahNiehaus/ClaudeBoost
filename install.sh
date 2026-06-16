#!/usr/bin/env bash
#
# ClaudeBoost installer for macOS / Linux.
#
# Symlinks CLAUDE.md and slash commands into ~/.claude/, then delegates to
# scripts/setup.py for everything else (hooks, RAG server, ML deps, MCP tools,
# permissions).
#
# Idempotent — safe to re-run after git pull.

set -e

BOOST_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLAUDE_DIR="$HOME/.claude"

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
echo " ClaudeBoost Installer"
echo " ====================="
echo ""
echo " Source:  $BOOST_DIR"
echo " Target:  $CLAUDE_DIR"
echo " Python:  $($PY --version)"
echo ""

mkdir -p "$CLAUDE_DIR"

# ── 1. Link CLAUDE.md ────────────────────────────────────────────────────────
echo " [1/3] Linking CLAUDE.md..."

if [ -e "$CLAUDE_DIR/CLAUDE.md" ] || [ -L "$CLAUDE_DIR/CLAUDE.md" ]; then
    rm -f "$CLAUDE_DIR/CLAUDE.md"
    if [ -e "$CLAUDE_DIR/CLAUDE.md" ] || [ -L "$CLAUDE_DIR/CLAUDE.md" ]; then
        echo " ERROR: Could not remove existing CLAUDE.md. Check permissions."
        exit 1
    fi
fi
if ln -s "$BOOST_DIR/CLAUDE.md" "$CLAUDE_DIR/CLAUDE.md" 2>/dev/null; then
    echo "        CLAUDE.md linked (auto-updates on git pull)."
else
    cp "$BOOST_DIR/CLAUDE.md" "$CLAUDE_DIR/CLAUDE.md"
    echo "        CLAUDE.md copied (re-run install.sh after git pull to update it)."
fi

# ── 2. Link slash commands ────────────────────────────────────────────────────
echo " [2/3] Linking slash commands..."

if [ -L "$CLAUDE_DIR/commands" ] || [ -d "$CLAUDE_DIR/commands" ]; then
    rm -rf "$CLAUDE_DIR/commands"
    if [ -e "$CLAUDE_DIR/commands" ]; then
        echo " ERROR: Could not remove existing commands directory. Check permissions."
        exit 1
    fi
fi
if ln -s "$BOOST_DIR/.claude/commands" "$CLAUDE_DIR/commands" 2>/dev/null; then
    echo "        Slash commands linked (symlink — auto-updates on git pull)."
else
    echo "        Symlink failed. setup.py will copy commands instead."
fi

# ── 3. Run setup.py ──────────────────────────────────────────────────────────
echo " [3/3] Running setup.py (hooks, RAG server, MCP tools, permissions)..."
echo ""

if ! "$PY" "$BOOST_DIR/scripts/setup.py"; then
    echo ""
    echo " [ERROR] setup.py reported issues. Fix them, then re-run install.sh."
    exit 1
fi

CMD_COUNT=$(find "$BOOST_DIR/.claude/commands" -maxdepth 1 -name '*.md' 2>/dev/null | wc -l | tr -d ' ')

echo ""
echo " ============================================================"
echo "  ClaudeBoost installed!"
echo ""
echo "  $CMD_COUNT slash commands available in every Claude Code session."
echo ""
echo "  Next: open Claude Code and run:"
echo "    /boost"
echo ""
echo "  /boost checks all systems and auto-fixes anything still off."
echo " ============================================================"
echo ""
