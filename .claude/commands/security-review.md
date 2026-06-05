---
argument-hint: [--full]
description: Security-focused review of pending branch changes, or full project audit with --full
allowed-tools: Read, Write, Bash, Glob, Grep, Agent
---

# /security-review — Security Review

Arguments: $ARGUMENTS

Performs a security-focused review. Without arguments, reviews pending branch changes. With `--full`, scans the entire project for a baseline security posture assessment.

---

## Phase 0: RAG Context

**0a — Detect project path (before loading context):**

1. Read `$CLAUDEBOOST_HOME/state/workspaces.json` — use the `project_path` from the entry whose `workspace_path` was most recently modified
2. Fall back to current working directory if no registry entry found

Set `PROJECT_PATH` to the detected value.

Call `POST http://127.0.0.1:8612/context with agent="security-agent", task_description="security review $ARGUMENTS", project_path="<PROJECT_PATH>", max_tokens=5000` as your FIRST action.

**0b — Verify project is indexed** (required for codebase search to work):

Call `GET http://127.0.0.1:8612/status` and check `indexed_projects` for `PROJECT_PATH`.

- **Indexed**: note file/chunk counts and continue.
- **Not indexed**: run `Skill(skill="index-project", args="<PROJECT_PATH>")` immediately. Do not continue until indexing completes.
- **RAG offline**: stop and tell the user to run `/rag` first.

---

## Branch Changes Mode (default — no arguments)

Reviews the diff between the current branch and its base for security issues.

### Step 1: Get the diff

```bash
BASE=$(git rev-parse --abbrev-ref HEAD@{upstream} 2>/dev/null | sed 's|origin/||' || git symbolic-ref refs/remotes/origin/HEAD 2>/dev/null | sed 's|refs/remotes/origin/||' || echo "main")
git diff origin/$BASE...HEAD
```

If the diff is empty, report "No branch changes to review" and stop.

### Step 2: Spawn security-agent

Spawn `security-agent` with the full diff and the following checks:

**OWASP Top 10 review (branch diff scope):**

| ID | Category | What to look for in the diff |
|----|----------|------------------------------|
| A01 | Broken Access Control | New endpoints without auth/authz checks; RBAC changes |
| A02 | Cryptographic Failures | Weak algorithms, plaintext secrets, HTTP instead of HTTPS |
| A03 | Injection | String concatenation in SQL/shell/LDAP; missing parameterization |
| A04 | Insecure Design | Missing trust boundaries, privilege escalation paths |
| A05 | Security Misconfiguration | Debug flags left on, verbose error messages, insecure headers |
| A06 | Vulnerable Components | New dependencies added without known-safe version pins |
| A07 | Authentication Failures | Weak password policy, missing rate limiting, session not regenerated |
| A08 | Data Integrity | Missing checksums, unsigned data passed to interpreters |
| A09 | Logging Failures | Security events (auth, access denied) not logged; sensitive data in logs |
| A10 | SSRF | User-controlled URLs passed to HTTP clients without allowlist |

**CIA Triad lens:**
- Confidentiality: Does this diff expose data to unauthorized parties?
- Integrity: Can this diff be exploited to tamper with data?
- Availability: Does this diff introduce DoS vectors?

**Hardcoded secrets scan (diff only):**
Grep the diff for: `password=`, `secret=`, `api_key=`, `token=`, `AKIA`, `sk_live_`, `-----BEGIN`, `bearer`, `Authorization:`

### Step 3: Verify and Output

Before presenting findings to the user, run `/audit` on the security-agent findings output with:
- Input type: `output`
- Dimensions: O2 Evidence Quality, O1 Completion Coverage, X1 Red Flags/Anomalies
- (CL3 Source Credibility omitted — that dimension applies to `claim` input type; security agent output is `output` type, verified by O2 instead)

Verify:
- Every finding has a specific `file:line` citation and an impact statement
- Findings that reference the diff specifically (not hypothetical or templated patterns not in the actual code) are retained
- Findings without `file:line` and impact are false positives and should be surfaced as such to the user

If verdict is VERIFIED or PARTIALLY VERIFIED: present findings as normal.
If verdict is UNVERIFIED: surface the unverified findings separately (labeled "Evidence insufficient — review before acting") alongside the verified findings.

Findings use severity levels:
- **CRITICAL** — Exploitable vulnerability, must fix before merge
- **HIGH** — Significant risk, should fix before merge
- **MEDIUM** — Worth addressing, plan for near-term
- **LOW** — Best practice gap, track for later

Format each finding as:
```
[SEVERITY] file:line — Description
  Impact: what an attacker could do
  Fix: specific remediation
```

If no issues found: "No security issues found in branch diff."

---

## Full Project Audit Mode (`/security-review --full`)

When called with `--full`, scans the entire project rather than just branch changes.

**Scope**: All source files in the project, not limited to git diff.
**Use when**: No active branch changes, or you want a baseline security posture assessment.

### Additional checks (full mode only)

These checks are impractical on a diff but valuable across the full codebase.

#### Dependency Vulnerability Scan

Run the appropriate audit command for the project's language(s):

```bash
# Detect project type
ls package.json 2>/dev/null && echo "node"
ls requirements.txt pyproject.toml setup.py 2>/dev/null && echo "python"
ls go.mod 2>/dev/null && echo "go"
ls Cargo.toml 2>/dev/null && echo "rust"
ls Gemfile 2>/dev/null && echo "ruby"
```

Then run:
```bash
# Node.js
npm audit --audit-level=moderate

# Python
pip-audit
# fallback: safety check

# Go
govulncheck ./...

# Rust
cargo audit

# Ruby
bundle audit check
```

Record findings by severity. Use this response matrix:

| Severity | Action | Timeline |
|----------|--------|----------|
| Critical | Block — fix or remove before any release | Hours |
| High | Fix in current sprint | Days |
| Moderate | Schedule fix | Weeks |
| Low | Track for next release | Next release |

#### Secrets Detection

```bash
# Preferred
gitleaks detect --source . --verbose

# Fallback options
git secrets --scan-history
trufflehog filesystem .
```

Manual grep for common patterns if tooling unavailable:
```bash
# These are intentional regex pattern scans for literal tokens — RAG cannot detect hardcoded
# secrets because it uses semantic similarity, not pattern matching. Direct grep is correct here.
grep -rn "password\s*=" . --include="*.py" --include="*.js" --include="*.ts" --include="*.env" | grep -v ".git"
grep -rn "AKIA[0-9A-Z]" .   # AWS keys
grep -rn "sk_live_" .        # Stripe keys
grep -rn "ghp_\|ghs_" .      # GitHub tokens
```

Check `.env` hygiene:
- [ ] `.env` in `.gitignore`
- [ ] No `.env` files tracked in git history (`git log --all --full-history -- "*.env"`)
- [ ] `.env.example` present with no real secrets

#### Authentication and Session Security

For projects with auth, check:

**Password storage:**
- [ ] bcrypt (cost >= 10) or argon2 — not MD5, SHA-1, or plain SHA-256
- [ ] No passwords written to logs
- [ ] Rate limiting on login and password reset endpoints
- [ ] Account lockout or exponential backoff after N failures

**Session management:**
- [ ] `HttpOnly` cookie flag set
- [ ] `Secure` cookie flag set (HTTPS only)
- [ ] `SameSite` attribute set (Lax or Strict)
- [ ] Session timeout configured
- [ ] Session invalidated on logout
- [ ] Session ID regenerated after privilege change (login, role escalation)

**JWT / OAuth tokens:**
- [ ] Strong signing algorithm — RS256 or ES256 (not HS256 with a weak secret, not `none`)
- [ ] Token expiration (`exp` claim) set
- [ ] Refresh token rotation and revocation capability
- [ ] No sensitive data in the JWT payload (it is base64-decodable by anyone)

#### File Upload Security

For any file upload endpoint:
- [ ] File type validated by magic bytes — not just extension or MIME header
- [ ] File size limits enforced at the server level
- [ ] Files stored outside the web root (not directly browsable)
- [ ] Randomized storage filenames (not using the original user-supplied name)
- [ ] No execute permissions on upload directory
- [ ] Virus/malware scanning if uploads are sensitive

#### API Security

- [ ] Rate limiting enabled on all public endpoints
- [ ] Stricter rate limits on auth endpoints (login, register, reset)
- [ ] CORS `origin` is an explicit allowlist — not `*` when `credentials: true`
- [ ] Error responses use generic messages to clients; details go to logs only
- [ ] No stack traces in production responses
- [ ] HTTP security headers present:
  - `X-Content-Type-Options: nosniff`
  - `X-Frame-Options: DENY`
  - `Content-Security-Policy: default-src 'self'`
  - `Strict-Transport-Security: max-age=31536000`

#### Input Validation Coverage

For each input source, verify validation exists:

| Source | Risk | Check |
|--------|------|-------|
| File uploads | Critical | Schema + size + magic bytes |
| Request body (JSON/form) | High | Schema validation (Zod, Pydantic, etc.) |
| URL parameters | High | Type check + allowlist where applicable |
| Query strings | High | Sanitized for output context |
| Custom headers | Medium | Validated at ingress |
| Cookies | Medium | Signed or validated server-side |

#### Security Event Logging

Verify these events are logged at WARNING or ERROR level:
- [ ] Failed authentication attempts (with IP, not password)
- [ ] Access denied / authorization failures
- [ ] Input validation failures on sensitive fields
- [ ] Privilege escalation events
- [ ] Account lockout triggers

### Full Audit Report Output

```markdown
# Security Audit Report

**Date**: [today]
**Scope**: Full project — [project name / path]
**Mode**: /security-review --full

## Executive Summary

| Severity | Count |
|----------|-------|
| Critical | N |
| High     | N |
| Medium   | N |
| Low      | N |

**Overall Risk**: [Low / Medium / High / Critical]

## Findings

### [SEVERITY]: [Issue Title]
**Location**: file:line (or "project-wide" for structural issues)
**Description**: What the issue is
**Impact**: What an attacker could do
**Remediation**: Specific fix
**Timeline**: When to address

## Dependency Scan Results

[Output from npm audit / pip-audit / govulncheck / cargo audit]

## Secrets Scan Results

[Clean / or list of findings with file:line]

## Recommendations

1. [Most impactful fix first]
2. ...

## Next Steps

- [ ] Create tickets for Critical and High findings
- [ ] Schedule remediation sprint
- [ ] Integrate automated scanning into CI/CD (gitleaks, npm audit, pip-audit)
- [ ] Plan re-audit after remediation
```
