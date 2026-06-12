---
description: Review code changes with structured grading (A-F)
allowed-tools: Bash(git diff:*), Bash(git rev-parse:*), Bash(gh pr diff:*)
argument-hint: [--staged | --branch | --pr <url>]
---

Review code and provide a structured assessment with grading.

Arguments: $ARGUMENTS

## Phase 0: Load RAG Context (MANDATORY FIRST ACTION)

**0a — Detect project path (before loading context):**

1. Read `$CLAUDEBOOST_HOME/state/workspaces.json` — use the `project_path` from the entry whose `workspace_path` was most recently modified
2. Fall back to current working directory if no registry entry found

Set `PROJECT_PATH` to the detected value.

Call `POST http://127.0.0.1:8612/context with agent="workflow-agent", task_description="code change review and grading", project_path="<PROJECT_PATH>", max_tokens=3000`.

This loads relevant knowledge before any work begins. If `POST http://127.0.0.1:8612/context` fails: stop and tell the user "RAG is not connected. Run /boost before using this skill."

**0b — Verify project is indexed** (required for codebase search to work):

Call `GET http://127.0.0.1:8612/status` and check `indexed_projects` for `PROJECT_PATH`.

- **Indexed**: note file/chunk counts and continue.
- **Not indexed**: run `Skill(skill="index-project", args="<PROJECT_PATH>")` immediately. Do not continue until indexing completes.
- **RAG offline**: stop and tell the user to run `/rag` first.

---

## Diff Source Resolution

Determine the diff to review based on arguments:

| Argument | Diff command | Use case |
|----------|-------------|----------|
| (none) | `git diff` + `git diff --staged` | Review uncommitted + staged changes |
| `--staged` | `git diff --staged` | Review only staged changes |
| `--branch` | `git diff origin/<base>...HEAD` | Review branch diff vs base branch |
| `--pr <url>` | `gh pr diff <url>` | Review a GitHub PR |

### Step 1: Get the diff

Based on the arguments, run the appropriate diff command:

```bash
# Default (no args): uncommitted + staged
DIFF=$(git diff; git diff --staged)

# --staged: only staged
DIFF=$(git diff --staged)

# --branch: branch diff (detect base branch; ${BASE:-main} instead of || echo, which bash-guard blocks)
BASE=$(git rev-parse --abbrev-ref HEAD@{upstream} 2>/dev/null | sed 's|origin/||' || git symbolic-ref refs/remotes/origin/HEAD 2>/dev/null | sed 's|refs/remotes/origin/||')
DIFF=$(git diff "origin/${BASE:-main}...HEAD")

# --pr <url>: PR diff
DIFF=$(gh pr diff <url>)
```

If the diff is empty, report "No changes to review" and stop.

### Step 2: Review the diff

Review the diff systematically. For each issue found, classify by severity:

**CRITICAL** - Must fix before merge:
- Security vulnerabilities (injection, auth bypass, secrets in code)
- Data loss risks (missing transactions, unsafe deletes)
- Correctness bugs (race conditions, nil dereference, logic errors)

**MAJOR** - Should fix before merge:
- Logic errors that may not crash but produce wrong results
- Missing error handling on external calls
- API contract violations
- Missing tests for critical paths

**MINOR** - Nice to fix:
- Style inconsistencies with surrounding code
- Naming issues (unclear or misleading names)
- Missing comments on non-obvious logic
- Minor code smells

For each issue, note:
- File and line number
- Severity (CRITICAL, MAJOR, MINOR)
- Description of the issue
- Suggested fix (specific, actionable)

### Step 3: Assign grade

Grade is determined by the highest severity issue found:

| Grade | Criteria | Verdict |
|-------|----------|---------|
| **A** | No CRITICAL, MAJOR, or MINOR issues | PASS |
| **B** | MINOR issues only (no CRITICAL or MAJOR) | PASS |
| **C** | MAJOR issues present (no CRITICAL) | FAIL |
| **D** | CRITICAL issues present | FAIL |
| **F** | Unreviewable (empty diff, binary files, generated code only) | SKIP |

### Step 4: Output structured review

Output the review in this exact format:

```
Grade: <A|B|C|D|F>

CRITICAL (<count> issues)
  <file>:<line> — <description>
    Suggested fix: <actionable fix>

MAJOR (<count> issues)
  <file>:<line> — <description>
    Suggested fix: <actionable fix>

MINOR (<count> issues)
  <file>:<line> — <description>
    Suggested fix: <actionable fix>

Summary: <N> CRITICAL, <N> MAJOR, <N> MINOR
Verdict: <PASS|FAIL|SKIP>
```

Omit empty severity sections (e.g., if no CRITICAL issues, don't print the CRITICAL section).

If Grade is A, output:
```
Grade: A

No issues found.

Summary: 0 CRITICAL, 0 MAJOR, 0 MINOR
Verdict: PASS
```

## Final Step: Evidence Verification

Before presenting to the user, spawn a single `evaluator-agent` with this prompt:

"Read the review output above (Grade, issue list, Summary, Verdict). Verify that:
1. Every CRITICAL and MAJOR issue cites a specific file:line.
2. The Grade is consistent with the issue counts (e.g., a D grade requires at least one CRITICAL issue; a C grade requires at least one MAJOR and no CRITICAL).
3. The Verdict (PASS/FAIL) is consistent with the Grade (A/B = PASS, C/D = FAIL).

Output a simple table:
| Claim | Evidence present? | Verdict (CONFIRMED/NEEDS_EVIDENCE) |

Flag any NEEDS_EVIDENCE items. Under 500 tokens."

Surface any NEEDS_EVIDENCE items alongside the review output so the user sees them before acting on the grade.
