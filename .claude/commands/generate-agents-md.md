---
description: Generate an AGENTS.md file from CLAUDE.md for cross-tool AI compatibility
allowed-tools: Read, Write, Bash, Glob
---

# /generate-agents-md

Extract operational content from the project's `CLAUDE.md` and write an `AGENTS.md` file for cross-tool compatibility with Cursor, Codex, Copilot, and other AI coding assistants.

---

## When to Use

Use this command when:
- The project has multiple AI tools working on the same codebase
- You need a standalone `AGENTS.md` for an open-source project
- Symlinks are unreliable on the target system (e.g. Windows)
- You want to maintain `AGENTS.md` separately from `CLAUDE.md`

If the system supports symlinks and only Claude Code is used, a symlink is simpler:
```bash
ln -s CLAUDE.md AGENTS.md
```

---

## Steps

### Step 1: Detect Project Context

Read `CLAUDE.md` in the current directory. If not found, check parent directories up to the git root.

Also scan for:
- `package.json` — Node.js/TypeScript project
- `pyproject.toml` or `requirements.txt` — Python project
- `go.mod` — Go project
- `Cargo.toml` — Rust project
- `Makefile` or `justfile` — custom task runner
- `.github/workflows/` — CI/CD configuration

### Step 2: Extract Operational Content

From `CLAUDE.md`, identify:
1. **Setup commands** — install dependencies, configure environment
2. **Test commands** — run tests, coverage targets
3. **Build and deploy commands** — production build, lint, typecheck
4. **Code style rules** — formatter, linter, naming conventions
5. **Boundaries** — files not to modify, things to never commit, things to ask before changing

If commands are not explicit in `CLAUDE.md`, derive them from `package.json` scripts, `Makefile` targets, or CI/CD workflow files.

### Step 3: Generate AGENTS.md

Write `AGENTS.md` to the project root using this structure:

```markdown
# AGENTS.md

> Auto-generated from CLAUDE.md | Last updated: YYYY-MM-DD
> Full documentation: [CLAUDE.md](./CLAUDE.md)

## Project Overview

[PROJECT_NAME] — [BRIEF_DESCRIPTION]

**Tech Stack**: [PRIMARY_TECHNOLOGIES]
**Language**: [PRIMARY_LANGUAGE]

## Setup Commands

```bash
# Install dependencies
[INSTALL_COMMAND]

# Start development server
[DEV_COMMAND]

# Environment setup
cp .env.example .env
```

## Testing

```bash
# Run all tests
[TEST_COMMAND]

# Run with coverage
[COVERAGE_COMMAND]
```

## Build and Deploy

```bash
# Production build
[BUILD_COMMAND]

# Type check
[TYPECHECK_COMMAND]

# Lint
[LINT_COMMAND]
```

## Code Style

```bash
# Format
[FORMAT_COMMAND]

# Lint and fix
[LINT_FIX_COMMAND]
```

**Conventions:**
- [STYLE_RULE_1]
- [STYLE_RULE_2]

## Boundaries

### Do Not Modify
- Lock files (`package-lock.json`, `yarn.lock`, `Cargo.lock`)
- Environment files (`.env`, `.env.local`)
- CI/CD configurations (`.github/workflows/`)
- Applied database migrations

### Never Commit
- Secrets, API keys, credentials
- `.env` files (use `.env.example`)
- Build artifacts, `node_modules/`, `target/`

### Ask Before Changing
- Authentication or authorization logic
- Database schemas
- Public API contracts
- Major dependencies

---

*For detailed guardrails and methodology, see [CLAUDE.md](./CLAUDE.md)*
```

Fill in all `[PLACEHOLDER]` values from the actual project. Omit sections that have no content rather than leaving them with empty placeholders.

### Step 4: Present and Confirm

Show the generated `AGENTS.md` content to the user and ask: "Save to `./AGENTS.md`?"

Do not write the file until the user confirms (or says "go ahead").

### Step 5: Save

Write to `./AGENTS.md` in the project root.

Inform the user: "Saved to `./AGENTS.md`. Regenerate this file whenever the Operations section of `CLAUDE.md` changes."

---

## Monorepo Support

For monorepos, generate nested `AGENTS.md` files per package:

```
project/
├── AGENTS.md          # Root — general guidelines and shared commands
├── CLAUDE.md          # Full methodology
├── packages/
│   ├── api/
│   │   └── AGENTS.md  # API-specific commands
│   └── web/
│       └── AGENTS.md  # Web-specific commands
```

Each nested file should focus on that package's commands and reference the root `AGENTS.md` for general guidelines.

---

## Keeping AGENTS.md in Sync

Regenerate `AGENTS.md` when:
- Setup, test, or build commands change in `CLAUDE.md`
- New tooling is added to the project
- Project structure changes significantly

Run `/generate-agents-md` again — it will overwrite the previous file.
