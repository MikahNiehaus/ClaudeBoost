#!/usr/bin/env bash
#
# ClaudeBoost installer for macOS / Linux.
#
# Symlinks CLAUDE.md and slash commands into ~/.claude/, registers the RAG
# MCP server with the Claude CLI, then hands off to scripts/setup.py for the
# heavy lifting (hooks, state, ML deps).
#
# Idempotent — safe to re-run after `git pull`.

set -e

BOOST_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLAUDE_DIR="$HOME/.claude"

# Pick a Python — prefer python3, fall back to python (some macOS setups).
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

# ── 1. Register RAG MCP server globally ──────────────────────────────────────
echo " [1/3] Registering RAG MCP server..."

if $PY -c "import rag_server" >/dev/null 2>&1; then
    echo "        rag-server already installed."
else
    echo "        Installing rag-server package..."
    if $PY -m pip install -e "$BOOST_DIR/mcp-rag-server" >/dev/null 2>&1; then
        echo "        rag-server package installed."
    else
        echo "        WARNING: Could not install rag-server. Install manually:"
        echo "          $PY -m pip install -e \"$BOOST_DIR/mcp-rag-server\""
    fi
fi

if command -v claude >/dev/null 2>&1; then
    claude mcp remove rag-server --scope user >/dev/null 2>&1 || true
    claude mcp add rag-server --scope user \
        -e RAG_PROJECT_ROOT="$BOOST_DIR" \
        -- python -m rag_server >/dev/null 2>&1 || true
    echo "        MCP server registered globally (RAG_PROJECT_ROOT=$BOOST_DIR)."
else
    echo "        Claude CLI not found. Add manually to ~/.claude.json."
fi

# ── 2. Symlink CLAUDE.md and slash commands ──────────────────────────────────
echo " [2/3] Installing CLAUDE.md and slash commands..."

# CLAUDE.md — symlink so edits in the repo propagate.
if [ -e "$CLAUDE_DIR/CLAUDE.md" ] || [ -L "$CLAUDE_DIR/CLAUDE.md" ]; then
    rm -f "$CLAUDE_DIR/CLAUDE.md"
fi
ln -s "$BOOST_DIR/CLAUDE.md" "$CLAUDE_DIR/CLAUDE.md"
echo "        CLAUDE.md linked to $CLAUDE_DIR/CLAUDE.md (auto-updates)."

# commands/ — symlink the whole dir. setup.py detects the symlink and skips
# the file-by-file mirror, so the repo stays the source of truth.
if [ -L "$CLAUDE_DIR/commands" ] || [ -d "$CLAUDE_DIR/commands" ]; then
    rm -rf "$CLAUDE_DIR/commands"
fi
ln -s "$BOOST_DIR/.claude/commands" "$CLAUDE_DIR/commands"
echo "        Slash commands linked."

# ── 3. Hand off to setup.py for hooks, state, ML deps ────────────────────────
echo " [3/3] Running setup.py..."
echo ""
"$PY" "$BOOST_DIR/scripts/setup.py"

CMD_COUNT=$(find "$BOOST_DIR/.claude/commands" -maxdepth 1 -name '*.md' 2>/dev/null | wc -l | tr -d ' ')

echo ""
echo " ============================================================"
echo "  ClaudeBoost installed!"
echo ""
echo "  What's available now:"
echo "    - RAG search in every Claude Code session"
echo "    - $CMD_COUNT slash commands (global)"
echo ""
echo "  To verify: open any project in Claude Code and try:"
echo "    rag_status"
echo " ============================================================"
echo ""
