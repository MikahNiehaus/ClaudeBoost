# ClaudeBoost Setup Guide

Complete setup instructions for ClaudeBoost: agents, hooks, local code search, and slash commands.

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

In one run it:

| What it does | Where it goes |
|-------------|---------------|
| Registers the hooks | `~/.claude/settings.json` |
| Links the slash commands | `~/.claude/commands/` |
| Installs agents, skills and `CLAUDE.md` from `clean-rag/portable/` | `~/.claude/` |
| Builds clean-rag its own virtualenv and installs the embedding stack | `clean-rag/clean-rag-venv/` |
| Starts clean-rag, the search server | `http://127.0.0.1:8613` |
| Indexes the ClaudeBoost repo as a project | `POST /index-project` |
| Registers the MCP servers and plugins | `~/.claude.json` |

**Important**: The installer sets `CLAUDEBOOST_HOME` to your ClaudeBoost directory. If you
move ClaudeBoost, re-run `install.bat` (Windows) or `./install.sh` (macOS/Linux).

### 3. Verify

Open any project in Claude Code and run:
- `/clean-rag-server status` to check the search server
- `/boost` to verify all systems

Or check the server directly:
```
GET http://127.0.0.1:8613/status
```
It returns `"status"` plus every registered project under `projects.entries`.

### Indexing a project

Run `/index-project <path>` in Claude Code, or call
`POST http://127.0.0.1:8613/index-project` with `{"project_path": "<abs path>"}`.
Only changed files are re-indexed. After that the index keeps itself fresh: it
reindexes after every edit and sweeps every 10 minutes for outside changes.

There is no topic knowledge base and no agents index. Search runs over your own
indexed projects and the live web. `clean-rag/CLAUDE.md` has the full route table.

## Verification Checklist

```bash
curl -s http://127.0.0.1:8613/status   # Server health and registered projects
ls ~/.claude/agents/                   # Installed agents
ls ~/.claude/commands/                 # Slash commands
cat ~/.claude/CLAUDE.md                # Global orchestration rules
```

## Current Tested Versions

As of 2026-06-04:
- **Python**: 3.11+
- **Claude Code**: v2.1.88
- **Model**: claude-opus-4-6
- **sentence-transformers**: 3.0+ (BAAI/bge-base-en-v1.5, 768 dimensions)
- **sqlite-vec**: 0.1.9+ (vector store)
