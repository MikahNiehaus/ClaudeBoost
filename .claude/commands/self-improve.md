---
argument-hint: [focus — docs | enforcement | xml | counts | rag | all]
description: Run ClaudeBoost self-improvement audit — reindex, audit, self-test, fix, verify, loop
allowed-tools: Read, Write, Edit, Bash, Glob, Grep, Agent, mcp__rag-server__rag_context, mcp__rag-server__rag_index, mcp__rag-server__rag_index_project, mcp__rag-server__rag_search, mcp__rag-server__rag_status
---

# /self-improve — ClaudeBoost Self-Improvement Audit Loop

Arguments: **$ARGUMENTS**
(Format: `[focus]` — one of `docs`, `enforcement`, `xml`, `counts`, `rag`, `all`. Default: `all`)

---

## Phase 0: Setup

**0a — Parse arguments.**
Split `$ARGUMENTS`. First token = `FOCUS`. Valid values: `docs`, `enforcement`, `xml`, `counts`, `rag`, `rules`, `memory`, `all`. Default to `all` if omitted or unrecognized.

**0b — Read current round state.**
Read `workspace/self-improvement/context.md`. Find the current round number N in the round log. The next round is N+1.

If `workspace/self-improvement/context.md` does not exist, N = 0.

Announce: `Starting self-improvement round R[N+1], focus: $FOCUS`

---

## Phase 1: Reindex (Mandatory Every Round)

Call both in sequence — do NOT skip:

1. `rag_index(force=true, scope=all)` — rebuilds ClaudeBoost RAG (agents + knowledge)
2. `rag_index_project(project_path=$CLAUDEBOOST_HOME, force=true)` — rebuilds project RAG (codebase)

The PostToolUse hook on `rag_index_project` writes `state/last-indexed-head.json` automatically.

Report: "Indexed X files (ClaudeBoost RAG), Y files (project RAG)"

---

## Phase 2: Audit

Run lenses filtered by FOCUS. Every finding MUST cite `file:line` — no citation = drop the finding.

| FOCUS value | Lenses to run |
|-------------|--------------|
| `docs` | Count accuracy: stated counts in CLAUDE.md, README.md, docs/SETUP-GUIDE.md, docs/CLAUDEBOOST-REFERENCE.md vs actual file counts |
| `enforcement` | Phase gates (prose-only vs file-read gates); hook exit codes vs documented claims; REQUIRED/MUST language vs actual behavior |
| `xml` | Well-formedness of all agents/*.xml and knowledge/*.xml; cross-reference resolution (knowledge-base file attrs) |
| `counts` | Count agents/*.xml, knowledge/*.xml, .claude/commands/*.md; compare to all docs that state a number |
| `rag` | RAG search spot-checks (see Phase 3 ST-07/08) + rag_status chunk count health |
| `rules` | CLAUDE.md rule staleness: for each Hard Rule and behavioral rule in CLAUDE.md (both global and project), verify at least one `file:line` in the codebase still reflects it; flag rules whose patterns no longer appear anywhere in the codebase |
| `memory` | Memory staleness: read `~/.claude/projects/C--Development-ClaudeBoost/memory/MEMORY.md`; for each linked file, check its `last_modified` date; flag entries older than 60 days for user review — stale memories mislead more than no memory |
| `all` | All of the above |

Use `rag_search` to find relevant files before reading them. Do not guess file paths.

---

## Phase 3: Non-Destructive Self-Tests

Run ALL tests regardless of FOCUS. All tests are read-only.

| ID | Check | Pass condition |
|----|-------|----------------|
| ST-01 | `ls agents/*.xml \| wc -l` | Count matches stated count in CLAUDE.md |
| ST-02 | `ls knowledge/*.xml \| wc -l` | Count matches stated count in CLAUDE.md |
| ST-03 | `ls .claude/commands/*.md \| wc -l` | Count matches section 5 in docs/CLAUDEBOOST-REFERENCE.md |
| ST-04 | `xmllint --noout agents/*.xml 2>&1` | Zero parse errors |
| ST-05 | `xmllint --noout knowledge/*.xml 2>&1` | Zero parse errors |
| ST-06 | Each `<knowledge-base file="...">` attr in agents/*.xml | All referenced files exist |
| ST-07 | `rag_search("OWASP SQL injection", scope="knowledge")` | security.xml appears in top 3 |
| ST-08 | `rag_search("playwright browser testing", scope="agents")` | playwright.xml or e2e-testing.xml in top 3 |
| ST-09 | Each .claude/commands/*.md has `description:` in frontmatter | No commands missing description |
| ST-10 | `rag_status` | ClaudeBoost chunks > 700, project chunks > 300 |
| ST-11 | Read `~/.claude/projects/C--Development-ClaudeBoost/memory/MEMORY.md`; for each linked `.md` file, check its last-modified date | No linked memory file is older than 60 days without a user-confirmed reason; flag (not fail) entries older than 60 days for review |
| ST-12 | For each Hard Rule listed in `CLAUDE.md` (jQuery ban, logger.error, parameterized queries), grep the codebase for at least one supporting occurrence | Each rule has at least one file:line citation OR is documented as aspirational |

Report each ST-XX as PASS or FAIL (with observed vs expected on failure).
For ST-11 and ST-12, report as INFO (not FAIL) when flagging — these are review prompts, not blockers.

**PHASE 3 GATE:** If more than 3 self-tests FAIL (INFO items do not count), STOP. Print: "Self-test gate: N failures detected. Fix ST failures before proceeding to audit." Investigate the failures before continuing.

---

## Phase 4: Pre-Fix Gate

For each finding from Phase 2 with a `file:line` citation:

Spawn a fresh `evaluator-agent` (Sonnet) with ONLY:
- The finding text
- The cited `file:line` reference
- No other context from this session

Evaluator confirms: **CONFIRMED** (finding is real) or **UNVERIFIED** (not found at cited location).

Drop all UNVERIFIED findings. Only proceed with CONFIRMED findings.

Print: "Pre-fix gate: N confirmed, M dropped as unverified."

If zero confirmed findings: skip to Phase 7.

---

## Phase 5: Fix

Apply minimal targeted changes for CONFIRMED findings only.

Rules:
- One finding = one fix. Do not bundle unrelated changes.
- No scope creep — do not improve surrounding code while fixing.
- Document each fix: "Fixed: [finding] at [file:line]"

---

## Phase 6: Post-Fix Verify

1. Re-run self-tests from Phase 3 — all must pass.
2. Spawn fresh evaluator-agent on each changed file:
   - Pass: file path + the change made
   - Evaluator returns: CORRECT or NEEDS_IMPROVEMENT
3. If NEEDS_IMPROVEMENT: rework the fix, re-run evaluator.

---

## Phase 7: Document + Loop

**7a — Update context.md.**

Append to `workspace/self-improvement/context.md`:

```
### R[N+1] — [date]
**Focus:** $FOCUS
**Self-tests:** N/10 passed
**Findings:** N confirmed, M dropped
**Fixes applied:**
- [list each fix with file:line]
**Status:** CLEAN (no findings) | FIXED (N findings resolved)
```

**7b — Loop control.**

- If any confirmed findings were fixed: print "Changes made — starting R[N+2]" → return to Phase 1
- If zero confirmed findings: print "R[N+1] clean — self-improvement complete for this run"

---

## Non-Destructive Guarantee

All self-tests are read-only. State files written:
- `state/last-indexed-head.json` (via rag_index_project PostToolUse hook — automatic)
- `workspace/self-improvement/context.md` (round log append only)

No source files are modified during testing. No app data is created or deleted.
The browser-based `/end-to-end-test` is separate — not used here (ClaudeBoost has no web UI).
