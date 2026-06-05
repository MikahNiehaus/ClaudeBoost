# ClaudeBoost Setup Guide

Complete setup instructions for ClaudeBoost — agents, knowledge bases, RAG search, and slash commands.

## Quick Setup

### Prerequisites

- **Python 3.11+** — https://www.python.org/downloads/ (ensure it's on PATH)
- **Claude Code** — https://docs.anthropic.com/en/docs/claude-code (the CLI tool)
- **Git** — https://git-scm.com/downloads

### 1. Clone ClaudeBoost

```bash
git clone https://github.com/MikahNiehaus/ClaudeBoost.git <install-path>
cd <install-path>
```

### 2. Run the Installer

**Windows:**

```batch
.\install.bat
```

**macOS / Linux:**

```bash
./install.sh
```

Both wrappers delegate to `scripts/setup.py` — the single cross-platform installer. The Unix script symlinks `CLAUDE.md` and `commands/` into `~/.claude/` so any repo edit propagates immediately.

> **TTS scope**: `/speak` is wired for Windows and macOS only. Linux installs everything else but `/speak` is a no-op on that platform.

This does everything in one step:

| Step | What it does | Where it goes |
|------|-------------|---------------|
| 1 | Installs RAG server package | pip (editable install) |
| 2 | Registers RAG MCP server globally | `~/.claude.json` (mcpServers) |
| 3 | Hardlinks CLAUDE.md globally (auto-updates on edit) | `~/.claude/CLAUDE.md` |
| 4 | Links 44 slash commands | `~/.claude/commands/` |
| 5 | Builds RAG vector index | `mcp-rag-server/.rag-index/` |

The installer output should show all steps completing:
```
[1/4] Registering RAG MCP server...        MCP server registered globally.
        CLAUDE.md linked to ~/.claude/CLAUDE.md (auto-updates).
[2/4] Installing slash commands...          Slash commands linked.
[3/4] Building initial RAG index...
Indexed 68 files, 736 chunks
         Index built successfully.
```

**Important**: The installer sets `RAG_PROJECT_ROOT` to your ClaudeBoost directory so the
RAG server can find the index and XML files from any project. If you move ClaudeBoost to
a different location, re-run `install.bat` (Windows) or `./install.sh` (macOS/Linux) to update the path.

### 3. Verify

Open any project in Claude Code and try:
- `/boost` — starts the RAG server and primes the session
- `/list-agents` — should list all 25 agents

Verify the RAG server directly:
```
GET http://127.0.0.1:8612/status
```
Should return `{"status":"ready"}` with collection chunk counts.

That's it. Every Claude Code session now has:
- Semantic search over 106 knowledge files (52 domain, 21 language, 33 framework) and 25 agent XML files
- Global CLAUDE.md telling Claude when and how to use RAG
- 44 slash commands for task management

### How RAG works after install

The RAG MCP server starts automatically when Claude Code opens any project.

- **On startup**: indexes any new or changed files in agents/, knowledge/
- **Auto-watcher**: monitors agents/ and knowledge/ for file changes — re-indexes within 2 seconds
- **No manual action needed**: just work normally, the index stays up to date

### Re-indexing manually

If you need to force a full re-index:
- From Claude Code: call `rag_index` with `force: true`
- From terminal: re-run `install.bat` (rebuilds the index from scratch)

Only changed files get re-indexed normally (incremental via SHA-256 hash comparison).

### What gets indexed

| Scope | Source files | What's in them |
|-------|------------|----------------|
| knowledge | `knowledge/*.xml` (106 files: 52 domain, 21 lang, 33 fw) | Coding standards, security, architecture, debugging, language/framework guides, etc. |
| agents | `agents/*.xml` (25 files) | Agent definitions with capabilities, guidelines, output formats |

## Verification Checklist

```bash
rag_status                    # In Claude Code — shows collection counts
rag_search "SQL injection"    # Should return security.xml results
ls ~/.claude/commands/        # Slash commands
cat ~/.claude/CLAUDE.md       # Global orchestration rules with RAG instructions
```

## Current Tested Versions

As of 2026-06-04:
- **Python**: 3.11+
- **Claude Code**: v2.1.88
- **Model**: Claude Opus 4.8 (1M context)
- **sentence-transformers**: 3.0+ (all-MiniLM-L6-v2, 384 dimensions)
- **ChromaDB**: 0.5+ (embedded SQLite mode)
