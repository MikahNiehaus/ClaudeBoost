# ClaudeBoost Setup Guide

Complete setup instructions. ClaudeBoost works standalone (agents + knowledge + RAG search)
or with Gas Town (adds multi-agent coordination, persistent identity, work tracking).

## Quick Setup (Standalone — No Gas Town)

If you just want the agents, knowledge bases, RAG search, and slash commands:

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
| 4 | Links 24 slash commands | `~/.claude/commands/` |
| 5 | Links agents + knowledge to GT directives (if GT installed) | `~/gt/directives/` |
| 6 | Builds RAG vector index | `mcp-rag-server/.rag-index/` |

The installer output should show all steps completing:
```
[1/4] Registering RAG MCP server...        MCP server registered globally.
        CLAUDE.md linked to ~/.claude/CLAUDE.md (auto-updates).
[2/4] Installing slash commands...          Slash commands linked.
[3/4] Setting up GT directives...           Agents and knowledge linked to GT directives (auto-updates).
[4/4] Building initial RAG index...
Indexed 68 files, 736 chunks
         Index built successfully.
```

**Important**: The installer sets `RAG_PROJECT_ROOT` to your ClaudeBoost directory so the
RAG server can find the index and XML files from any project. If you move ClaudeBoost to
a different location, re-run `install.bat` (Windows) or `./install.sh` (macOS/Linux) to update the path.

### 3. Verify

Open any project in Claude Code and try:
- `rag_status` — should show collections with chunk counts (counts vary based on file count)
- `rag_search "SQL injection"` — should return results from security.xml
- `/list-agents` — should list all 24 agents

That's it. Every Claude Code session now has:
- Semantic search over 45 knowledge bases and 25 agent XML files
- Global CLAUDE.md telling Claude when and how to use RAG
- 24 slash commands for task management

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
| knowledge | `knowledge/*.xml` (44 files) | Coding standards, security, architecture, debugging, etc. |
| agents | `agents/*.xml` (24 files) | Agent definitions with capabilities, guidelines, output formats |

---

## Full Setup (With Gas Town)

Gas Town adds: multi-agent coordination, persistent identity, beads (issue tracking),
message passing, automated supervision, and work dispatch to polecats.

### Additional Prerequisites

- **Go 1.26+** (64-bit ONLY)
- **Dolt 1.84+**
- **Chocolatey** (optional, for quick install)

### Quick Install (Chocolatey)

If you have Chocolatey, install both Go and Dolt in one step. This requires an
**elevated (admin) PowerShell** — run this from Git Bash or any terminal:

```bash
powershell -Command "Start-Process powershell -Verb RunAs -ArgumentList '-Command choco install golang dolt -y; pause'"
```

This opens an elevated PowerShell window that installs both packages from the official
Chocolatey community repository. The window pauses when done so you can verify the
output. No script files are created — it's a one-liner that runs inline.

**Package verification** (independently verified April 2026):
- **`golang`** — community-maintained, pulls installers directly from `golang.org` official distribution ([package page](https://community.chocolatey.org/packages/golang))
- **`dolt`** — maintained by DoltHub team members (zachmu, coffeegoddd), pulls from official `github.com/dolthub/dolt` releases ([package page](https://community.chocolatey.org/packages/dolt))

After the elevated window finishes, verify in a **new terminal**:
```bash
go version    # Should show windows/amd64
dolt version  # Should show 1.84.0+
```

Then skip to **4. PATH Setup** below.

### Manual Install

#### 1. Go (64-bit ONLY)

Download the latest **`goX.Y.Z.windows-amd64.msi`** from https://go.dev/dl/ (tested with go1.26.1)

**CRITICAL**: You MUST download the **amd64** version, NOT the 386 (32-bit) version.
- Look for the **Windows** row, **x86-64** column
- It should install to `C:\Program Files\Go\` (NOT `Program Files (x86)`)
- Verify after install: `go version` should show `windows/amd64`

If you accidentally installed 32-bit:
1. Uninstall via Windows Settings > Apps > "Go Programming Language"
2. Delete `C:\Program Files (x86)\Go\` if it still exists
3. Install the amd64 version

#### 2. Dolt

Download **`dolt-windows-amd64.msi`** from https://github.com/dolthub/dolt/releases

- Get the **Latest** release (tested with 1.84.0)
- Run the MSI installer — it adds `dolt` to PATH automatically
- Verify: `dolt version`

#### 3. Git (2.25+)

You likely already have this. If not: https://git-scm.com/downloads
- Verify: `git --version`

### 4. PATH Setup

After installing Go and Dolt, add this to your `~/.bashrc` (Git Bash):

```bash
export PATH="/c/Program Files/Go/bin:/c/Program Files/Dolt/bin:$HOME/go/bin:$PATH"
```

**You must restart your terminal / Claude Code session** after installing Go or Dolt,
otherwise the new PATH entries won't be picked up.

## Install Gastown

### 1. Clone the repo

```bash
cd <install-path>  # wherever you cloned ClaudeBoost
git clone https://github.com/steveyegge/gastown.git
```

### 2. Build gt

```bash
cd gastown
go build -o gt.exe ./cmd/gt
cp gt.exe "$HOME/go/bin/gt.exe"
```

### 3. Install beads CLI

```bash
go install github.com/steveyegge/beads/cmd/bd@latest
```

Note: `bv` is not a separate package — it may be bundled with beads or available as a `bd` subcommand.

### 4. Initialize workspace

```bash
gt install ~/gt --git
```

This creates the `~/gt/` workspace directory with all the scaffolding.

## Windows-Specific Fixes

Gastown was designed for macOS/Linux. The following issues affect Windows:

### Issue 1: `gt dolt start` fails with "not supported by windows"

**Root cause**: Go's `process.Signal(syscall.Signal(0))` doesn't work on Windows.
It's used to check if Dolt is alive during startup and in `IsRunning()`.

**Fix**: Edit `internal/doltserver/doltserver.go` in three places:

1. **Startup health check** (~line 1574): Replace `Signal(0)` with `os.FindProcess` on Windows
2. **IsRunning check** (~line 514): Replace `Signal(0)` with `isDoltServerOnPort` on Windows
3. **Stop function** (~line 1680): Replace `SIGTERM` with `process.Kill()` on Windows

All changes are gated behind `runtime.GOOS == "windows"`.

### Issue 2: PID file not written

**Root cause**: The `daemon/` directory may not exist on first start.

**Fix**: Add `os.MkdirAll(filepath.Dir(config.PidFile), 0755)` before `os.WriteFile` for the PID file.

### Issue 3: YAML config path escaping

**Root cause**: `writeServerConfig` writes Windows backslash paths (`C:\Users\...`)
into YAML double-quoted strings, where `\U` is interpreted as a hex escape.

**Fix**: Wrap `config.DataDir` with `filepath.ToSlash()` in `writeServerConfig`.

### After all fixes, rebuild:

```bash
cd $CLAUDEBOOST_HOME/gastown
go build -o gt.exe ./cmd/gt
cp gt.exe "$HOME/go/bin/gt.exe"
```

### Issue 4: tmux not available

tmux doesn't run natively on Windows. This causes ~10 warnings in `gt doctor`.
These are harmless — all tmux-related features (session management, feed dashboard)
require WSL or a future Windows-native tmux alternative.

**Workaround**: Use `--no-start` flag when running `gt doctor --fix` to skip daemon/session
operations.

## Start Dolt Server

```bash
cd ~/gt
gt dolt start
gt dolt status   # Should show "running" with port 3307
```

If Dolt won't start, you can run it directly as a fallback:

```bash
dolt sql-server --config ~/gt/.dolt-data/config.yaml &
echo $DOLT_PID > ~/gt/daemon/dolt.pid
```

## Run Doctor

```bash
cd ~/gt
gt doctor --fix --no-start
```

This auto-fixes most issues. Expected remaining warnings on Windows:
- tmux-related (5-6 warnings) — harmless
- daemon not running — needs tmux
- global-state not initialized — run `gt enable` when ready

## Run ClaudeBoost Installer

After GT is set up and working, run the ClaudeBoost installer:

```batch
cd <install-path>
.\install.bat
```

This registers agents, knowledge, RAG search, slash commands, and CLAUDE.md globally.
See the Quick Setup section above for full details on what gets installed where.

With GT installed, `install.bat` also copies agents and knowledge to `~/gt/directives/`
so they're available via `gt prime`.

## GT Integration Files

These extend Gas Town with ClaudeBoost's quality system:

### Directives (`~/gt/directives/`)
- `mayor.md` — 7-domain planning checklist, alternatives analysis, SOLID design review
- `polecat.md` — Self-reflection, code critique, teaching, SOLID spot-check, confidence levels
- `witness.md` — Output validation, MAST failure detection, escalation triggers
- `crew.md` — Interactive quality standards
- `agents/` — 24 specialist agents + orchestrator (25 XML files, linked by `install.bat`)
- `knowledge/` — 44 domain knowledge bases (linked by `install.bat`)

### Hooks (`~/.gt/`)
- `hooks-base.json` — Full 3-tier permission model (180 allow / 60 ask / 50 deny)
- `hooks-overrides/polecat.json` — Restricted permissions for worker agents
- `hooks-overrides/crew.json` — Full permissions for you
- `hooks-overrides/witness.json` — Read-only for monitors

Run `gt hooks sync` after any changes.

### Formulas (`~/gt/.beads/formulas/`)
10 specialist formulas, each extending `mol-polecat-work`:
- `mol-polecat-test` — TDD, coverage, test quality
- `mol-polecat-security` — OWASP, threat modeling, secure code review
- `mol-polecat-review` — Structured code review, SOLID compliance
- `mol-polecat-architect` — Design patterns, Clean Architecture, DDD
- `mol-polecat-debug` — Root cause analysis, structured diagnosis
- `mol-polecat-refactor` — Code smell detection, incremental improvement
- `mol-polecat-perf` — Profiling, bottleneck analysis, optimization
- `mol-polecat-browser` — Playwright MCP testing, URL safety enforcement
- `mol-polecat-ui` — Component-first dev, accessibility, responsive
- `mol-polecat-docs` — Technical writing, progressive disclosure

Dispatch with: `gt sling <bead-id> <rig> --formula mol-polecat-<type>`

### Plugins (`~/gt/plugins/`)
- `compliance-audit/plugin.md` — 4h periodic quality section enforcement
- `standards-check/plugin.md` — 6h periodic SOLID/metrics validation

### Guard Scripts (`~/gt/scripts/`)
- `cm-migration-guard.sh` — Blocks accidental migrations/deploys
- `cm-browser-guard.sh` — Localhost-only browser testing
- `cm-forbidden-libs.sh` — jQuery/banned library detection

## Adding Your First Rig

```bash
cd ~/gt
gt rig add <rig-name> <repo-url>
```

**Important**: After adding a rig, restart Dolt so it picks up the new database:
```bash
gt dolt stop
gt dolt start   # Now shows the new database
```

Then init beads schema and add crew:
```bash
cd ~/gt/<rig-name>
bd init --force --prefix <2-letter-prefix>
cd ~/gt
gt crew add <your-name> --rig <rig-name>
gt hooks sync
gt doctor --fix --no-start   # Fix agent beads and any other issues
```

### Dolt Goes Read-Only?

If you see "SERVER IS READ-ONLY" in `gt dolt status`, run:
```bash
gt dolt recover
```

### Stale polecats/.claude/settings.json

`gt doctor` may report 1 failure for a "stale" polecats settings.json.
This is a false positive — the file is pre-created for when polecats launch.
Running `gt doctor --fix` clears it, and `gt hooks sync` recreates it.
This is harmless and expected when no polecats are running.

## Quick Start with gtstart

For new projects, copy `gtstart.bat` (Windows) or `gtstart.sh` (macOS/Linux) into your project root. Running it will:

1. Check if the project is already a registered rig — if so, jump straight to launch
2. If not, set up everything automatically:
   - Ensure Dolt is running
   - Initialize git if needed
   - Register the rig with GT
   - Restart Dolt to pick up the new database
   - Initialize beads with a 2-letter prefix
   - Create the crew workspace
   - Sync hooks and run doctor

On launch, it presents a session menu:
- **[1] New session** — fresh start, auto-primes with `gt prime`
- **[2] Continue** — resumes the most recent session, auto-primes
- **[3] Resume** — pick from a list of past sessions

The script lives in your source project directory (e.g., `~/projects/MyProject/gtstart.sh`),
but the actual workspace it creates is at `~/gt/<project-name>/crew/<your-username>/`.

## Verification Checklist

```bash
# Standalone (always works)
rag_status                    # In Claude Code — shows collection counts
rag_search "SQL injection"    # Should return security.xml results
ls ~/.claude/commands/        # 24 slash commands
cat ~/.claude/CLAUDE.md       # Global orchestration rules with RAG instructions

# Gas Town (if installed)
go version                    # Should show windows/amd64
dolt version                  # Should show 1.84.0+
bd list --json | head -3      # Should return JSON (even if empty)
gt dolt status                # Should show "running"
ls ~/gt/directives/agents/    # 25 agent XML files (24 specialist + orchestrator)
ls ~/gt/directives/knowledge/ # 45 knowledge XML files

# Health
gt doctor                     # Should be mostly green
gt hooks sync                 # Should show targets synced
```

## Current Tested Versions

As of 2026-03-31:
- **Python**: 3.11+
- **Go**: 1.26.1 (windows/amd64)
- **Dolt**: 1.84.0
- **gt**: 0.12.1
- **bd (beads)**: 0.62.0
- **Claude Code**: v2.1.88
- **Model**: Claude Opus 4.6 (1M context)
- **sentence-transformers**: 3.0+ (all-MiniLM-L6-v2, 384 dimensions)
- **ChromaDB**: 0.5+ (embedded SQLite mode)
