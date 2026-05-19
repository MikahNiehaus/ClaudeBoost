---
description: Safe one-at-a-time dependency update workflow with audit, license check, and rollback plan
argument-hint: "[package-manager]"
allowed-tools: Bash, Read, Glob
---

# /dependency-update

Safe and systematic dependency updates with vulnerability management, license checking, and rollback planning.

Scope: **$ARGUMENTS** (e.g. `npm`, `python`, `go`, `rust` — or omit to auto-detect)

---

## Prerequisites

Before starting, verify:

- [ ] All tests passing
- [ ] Clean git working directory (`git status`)
- [ ] You have time for testing and potential rollback

---

## Phase 1: Detect Ecosystem and Audit

Auto-detect the project ecosystem, then list outdated packages:

```bash
# Node.js
npm outdated

# Python
pip list --outdated

# Go
go list -u -m all

# Rust
cargo outdated

# Ruby
bundle outdated
```

Create a mental inventory, prioritizing direct dependencies over transitive ones.

---

## Phase 2: Check Vulnerabilities

Run a security audit for the detected ecosystem:

```bash
# Node.js
npm audit

# Python
pip-audit

# Go
govulncheck ./...

# Rust
cargo audit

# Ruby
bundle audit check
```

Prioritize by severity: Critical (fix within hours) → High (days) → Moderate (weeks) → Low (monthly cycle).

---

## Phase 3: Check License Compatibility

Before updating or adding packages:

```bash
# Node.js
npx license-checker --summary

# Python
pip-licenses
```

Safe licenses: MIT, Apache-2.0, BSD, ISC.
Require legal review: GPL-3.0, AGPL-3.0, SSPL, Unlicensed.

---

## Phase 4: Plan Updates

Order of priority: **Security fixes → Patches → Minor versions → Major versions**

Update strategies:
- **Individual updates**: Use for major versions and risky dependencies
- **Batched**: Use for patches and minor updates together
- **All at once**: Only for fresh projects with comprehensive test coverage

---

## Phase 5: Execute Updates

Create a branch first:

```bash
git checkout -b chore/dependency-updates-$(date +%Y-%m)
```

Update commands by ecosystem:

```bash
# Individual package
npm install pkg@version
pip install pkg==version
go get pkg@version
cargo update -p pkg

# Batch (patches/minor only)
npm update
pip install -U pkg1 pkg2
go get -u ./...
cargo update
```

Verify lock files are updated. Commit after each meaningful update with a conventional commit message.

---

## Phase 6: Test and Validate

Run the full validation suite after each update:

```bash
# Tests
npm test | pytest | go test ./... | cargo test

# Type checks
npm run typecheck | mypy . | cargo check

# Lint
npm run lint | ruff check . | golangci-lint run | cargo clippy

# Build
npm run build | go build ./... | cargo build --release
```

For major version updates, manually verify critical paths through the application.

---

## Phase 7: Document and Submit

Create a PR documenting:
- Security fixes (include CVE numbers)
- Packages updated and their version changes
- Breaking changes encountered and how they were addressed
- Testing performed
- Rollback plan

---

## Rollback Procedures

### If tests fail after an update

```bash
# Node.js
git checkout package.json package-lock.json
npm install

# Python
git checkout requirements.txt
pip install -r requirements.txt
```

### If production issues appear

```bash
git revert <update-commit-hash>
# Reinstall and redeploy
```

### To pin a problematic dependency

```json
// package.json — pin to last known good version
{
  "dependencies": {
    "problematic-package": "1.2.3"
  },
  "resolutions": {
    "problematic-package": "1.2.3"
  }
}
```

---

## Quick Reference

| Task | Node.js | Python | Go | Rust |
|------|---------|--------|----|------|
| List outdated | `npm outdated` | `pip list --outdated` | `go list -u -m all` | `cargo outdated` |
| Security audit | `npm audit` | `pip-audit` | `govulncheck ./...` | `cargo audit` |
| Update all | `npm update` | `pip install -U` | `go get -u ./...` | `cargo update` |
| Update one | `npm install pkg@ver` | `pip install pkg==ver` | `go get pkg@ver` | `cargo update -p pkg` |
