# Mikah's Gas Town Setup — How It All Works

This documents **your specific GT configuration** — the custom layer on top of
the upstream [gastown](gastown/) repo. For core GT concepts (rigs, polecats,
convoys, hooks, etc.), see the [gastown README](gastown/README.md).

## What You Added

The upstream gastown repo is a generic multi-agent framework. Your setup adds:

1. **ClaudeBoost integration** — quality directives, formulas, plugins, and guard scripts
2. **Windows compatibility fixes** — patches to make GT run on Windows (no tmux, no Unix signals)
3. **gtstart.bat** — one-click launcher that bootstraps any project into a GT rig
4. **Custom directives** — behavioral rules for each agent role

## Your Workspace Layout

```
<ClaudeBoost>/                        <-- This repo (source + config)
  gastown/                           <-- Upstream GT source (build gt.exe from here)
  SETUP-GUIDE.md                     <-- Windows installation guide
  HOW-IT-WORKS.md                    <-- This file

~/gt/                                <-- Live GT workspace (created by `gt install`)
  .dolt-data/                        <-- Dolt databases (one per rig)
  mayor/                             <-- Mayor config + town.json + overseer.json
  deacon/                            <-- Deacon watchdog config
  directives/                        <-- Your custom role directives
  plugins/                           <-- Periodic quality audit plugins
  scripts/                           <-- Guard scripts (hooks)
  rigs.json                          <-- Registry of all rigs
  CLAUDE.md                          <-- Base instructions for all agent sessions
  <rig>/                             <-- Each registered project
    crew/mikah/                      <-- Your interactive workspace
    polecats/                        <-- Autonomous worker workspaces

~/OneDrive/prj/<project>/            <-- Your source projects
  gtstart.bat                        <-- Drop this in any project to GT-enable it
```

## The gtstart.bat Flow

When you run `gtstart.bat` from any project directory:

```
Is this already a rig?
  |
  YES --> cd ~/gt/<name>/crew/mikah --> Session Menu --> Claude Code
  |
  NO  --> [1] Start Dolt
          [2] Init git (if needed)
          [3] Register rig (gt rig add)
          [4] Restart Dolt (picks up new DB)
          [5] Init beads (bd init --prefix XX)
          [6] Create crew workspace
          [7] Sync hooks + doctor
          --> Session Menu --> Claude Code
```

Session menu:
- **[1] New session** — `claude -p "gt prime"` (fresh, auto-primes)
- **[2] Continue** — `claude --continue -p "gt prime"` (resume last session)
- **[3] Resume** — `claude --resume` (pick from list)

## ClaudeBoost Integration

### Directives (`~/gt/directives/`)

Behavioral rules injected into each agent role:

| File | Role | Key Rules |
|------|------|-----------|
| `mayor.md` | Mayor | 7-domain planning checklist, alternatives analysis, SOLID design review, model routing (Opus vs Sonnet) |
| `polecat.md` | Polecat | Self-critique table, teaching section, SOLID spot-check, code metrics, ticket verbatim rule |
| `crew.md` | Crew | Same quality standards as polecats, but interactive (report + wait for input) |
| `witness.md` | Witness | Output validation, MAST failure detection (design 32%, alignment 28%, verification 24%, infra 16%) |

### Formulas (`~/gt/.beads/formulas/`)

10 specialist formulas, each extending `mol-polecat-work`:

| Formula | Specialization |
|---------|---------------|
| `mol-polecat-test` | TDD, coverage, test quality |
| `mol-polecat-security` | OWASP, threat modeling, secure code review |
| `mol-polecat-review` | Structured code review, SOLID compliance |
| `mol-polecat-architect` | Design patterns, Clean Architecture, DDD |
| `mol-polecat-debug` | Root cause analysis, structured diagnosis |
| `mol-polecat-refactor` | Code smell detection, incremental improvement |
| `mol-polecat-perf` | Profiling, bottleneck analysis, optimization |
| `mol-polecat-browser` | Playwright MCP testing, URL safety |
| `mol-polecat-ui` | Component-first dev, accessibility, responsive |
| `mol-polecat-docs` | Technical writing, progressive disclosure |

Dispatch: `gt sling <bead-id> <rig> --formula mol-polecat-<type>`

### Plugins (`~/gt/plugins/`)

Periodic quality audits run by the Deacon:

| Plugin | Interval | Purpose |
|--------|----------|---------|
| `compliance-audit` | 4h | Checks polecat completions for required quality sections (critique, teaching, SOLID) |
| `standards-check` | 6h | Validates SOLID compliance and code metrics on merge diffs |

Both report violations to the Mayor via `gt mail send`.

### Guard Scripts (`~/gt/scripts/`)

Hook scripts that block dangerous operations:

| Script | Blocks |
|--------|--------|
| `cm-migration-guard.sh` | Accidental migrations/deploys |
| `cm-browser-guard.sh` | Non-localhost browser testing |
| `cm-forbidden-libs.sh` | Banned libraries (jQuery, etc.) |

### Hooks Permission Model (`~/.gt/`)

Three-tier permission system:

| File | For | Permissions |
|------|-----|------------|
| `hooks-base.json` | Default | 180 allow / 60 ask / 50 deny |
| `hooks-overrides/crew.json` | You (crew) | Full permissions |
| `hooks-overrides/polecat.json` | Workers | Restricted |
| `hooks-overrides/witness.json` | Monitors | Read-only |

Sync after changes: `gt hooks sync`

## Code Metrics Thresholds

These are enforced by polecat directives and the standards-check plugin:

| Metric | Threshold |
|--------|-----------|
| Cyclomatic complexity | 10 max per method |
| Method length | 40 lines max |
| Class length | 300 lines max |
| Parameter count | 4 max |
| Nesting depth | 3 max |

## Windows-Specific Notes

GT was designed for macOS/Linux. Your setup includes these Windows fixes
(applied to the gastown source before building):

1. **Signal handling** — `Signal(0)` replaced with `os.FindProcess` + port check
2. **Process stop** — `SIGTERM` replaced with `process.Kill()`
3. **PID directory** — `os.MkdirAll` added before PID file write
4. **YAML paths** — `filepath.ToSlash()` for config paths (prevents `\U` hex escapes)
5. **No tmux** — Session management features unavailable; use `--no-start` with doctor

After making source changes, rebuild:
```bash
cd $CLAUDEBOOST_HOME/gastown
go build -o gt.exe ./cmd/gt
cp gt.exe "$HOME/go/bin/gt.exe"
```

## Current Versions (as of 2026-03-31)

| Tool | Version |
|------|---------|
| Go | 1.26.1 (windows/amd64) |
| Dolt | 1.84.0 |
| gt | 0.12.1 |
| bd (beads) | 0.62.0 |
| Claude Code | v2.1.88 |
| Model | Claude Opus 4.6 (1M context) |

## Daily Workflow

```bash
# Option A: Use gtstart.bat from any project
cd ~/OneDrive/prj/MyProject
./gtstart.bat

# Option B: Go directly to crew workspace
cd ~/gt/MyProject/crew/mikah
claude -p "gt prime"
```

Once in a session:
- Agent auto-primes with `gt prime` (loads role context)
- Check for work: `gt mol status` then `gt mail inbox`
- Create issues: `bd create "title" -t bug`
- Dispatch work: `gt sling TE-001 Test --formula mol-polecat-test`
- Monitor: `gt status`, `gt trail`, `gt dolt status`

## Useful Diagnostic Commands

```bash
gt doctor --fix --no-start    # Auto-fix workspace issues
gt dolt status                # Dolt health + orphan count
gt dolt cleanup               # Remove test database orphans
gt vitals                     # Unified health dashboard
gt costs                      # Session cost tracking
gt whoami                     # Current agent identity
```
