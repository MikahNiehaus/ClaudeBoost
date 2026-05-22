---
argument-hint: <input — text, URL, file path, code snippet, config, claim, or process description>
description: Parallel audit — chunks input into dimensions, spawns parallel auditors, synthesizes a final 'is it legit' verdict
allowed-tools: Read, Write, Bash, Glob, Grep, Agent, mcp__rag-server__rag_context, mcp__rag-server__rag_search, mcp__playwright__browser_navigate, mcp__playwright__browser_snapshot, mcp__playwright__browser_take_screenshot, mcp__playwright__browser_evaluate
---

# /audit — Parallel Audit with Verdict

Decompose any input into audit dimensions, run them as parallel agents, then synthesize a final **"is it legit"** verdict using Opus.

Input: **$ARGUMENTS**

---

## Phase 0: Setup

**Set audit flag** (suppresses verify-gate hook during this audit — it fires on every agent and would serialize the parallel flow):
```bash
echo '{"active":true}' > "$CLAUDEBOOST_HOME/state/audit-in-progress.json"
```

Then call `rag_context(agent="reviewer-agent", task_description="audit: $ARGUMENTS", max_tokens=3000)`.

---

## Phase 1: Input Analysis

### 1a — Determine input type

Examine `$ARGUMENTS` and classify it as one of:

| Type | Detection signals |
|------|------------------|
| `code` | Contains code syntax, starts with a code fence, has braces/semicolons/indentation, mentions a function/class/method |
| `file` | Looks like a file path (contains `/` or `\`, has an extension like `.py .ts .cs .json .yaml`) |
| `url` | Starts with `http://` or `https://`, or is a bare domain/path that looks like a link |
| `config` | JSON, YAML, TOML, XML, or key=value structure — configuration data |
| `claim` | A factual assertion, statement, or short text being verified for accuracy |
| `document` | Multi-paragraph text, a pasted document, a ticket description, a spec |
| `process` | Describes a workflow, sequence of steps, or plan |
| `output` | The result of an agent, skill, or task execution. Contains claims that certain work was done, findings that were produced, or artifacts that were created. Typically a file path (plan.md, prd.md, exploration.md) or quoted agent output. |

Set `INPUT_TYPE`.

### 1b — Fetch or read the content

**If `file`:** Read the file at the given path. Store full contents as `INPUT_CONTENT`. Set `STATED_GOAL = "Not provided — audit internal consistency only."`

**If `url`:**

Safety check first — if the URL matches any non-localhost pattern (`staging`, `prod`, `.com`, `.io`, `.net`, etc. that is NOT `localhost` or `127.0.0.1`): this is a legitimate audit target. Proceed with browser navigation.

Navigate to the URL:
```
browser_navigate(url="$ARGUMENTS")
browser_snapshot()
```
Store the page text and visible content as `INPUT_CONTENT`. Set `STATED_GOAL = "Not provided — audit internal consistency only."`

**If `code`, `config`, `claim`, `document`, `process`:** `INPUT_CONTENT` = `$ARGUMENTS` verbatim (already in hand). Set `STATED_GOAL = "Not provided — audit internal consistency only."`

**If `output`:** Read the file(s) at the given path. If multiple files are implied, read all of them. Store full contents as `INPUT_CONTENT`. Also note the stated goal or ticket as `STATED_GOAL` — check for `ticket.md` or `context.md` in the same workspace directory (e.g., if input is `workspace/task-id/plan.md`, look for `workspace/task-id/ticket.md`). If found, store first 500 chars as `STATED_GOAL`. If not found, set `STATED_GOAL = "Not provided — audit internal consistency only."`.

### 1c — Summarize in one sentence

Write: `"Auditing: [one sentence describing what this is and what it claims to be or do]"`

### 1d — Detect audit scope

If `INPUT_TYPE` is `output`, OR the user's request contains "verify completion", "check if done", "did this happen", or "was this actually done":
  Set `AUDIT_SCOPE = completion-verification`

Otherwise:
  Set `AUDIT_SCOPE = general`

---

## Phase 2: Dimension Selection

Choose 3–6 dimensions from the tables below based on `INPUT_TYPE`. Be decisive — fewer targeted dimensions beat many shallow ones.

### Dimension bank by input type

**`code` or `file` (code file):**
| ID | Dimension | Focus |
|----|-----------|-------|
| C1 | Logic & Correctness | Does it do what it claims? Any bugs, wrong conditions, off-by-one errors? |
| C2 | Security | Injection, auth bypass, data exposure, hardcoded secrets, OWASP top 10 |
| C3 | Error Handling | Are all error paths covered? Silent failures? Missing try/catch? |
| C4 | Performance | N+1 queries, blocking loops, memory leaks, unnecessary allocations |
| C5 | Completeness | Missing cases, dead code, TODO remnants, unreachable branches |
| C6 | Conventions | Naming, structure, patterns — does it match how this codebase solves similar problems? |

**`config`:**
| ID | Dimension | Focus |
|----|-----------|-------|
| CF1 | Schema Validity | Conforms to expected format, required fields present, correct value types |
| CF2 | Security | Exposed secrets, insecure defaults, overly permissive settings, cleartext credentials |
| CF3 | Completeness | Missing required options, deprecated keys still in use, placeholder values left in |
| CF4 | Best Practices | Follows conventions for this config type (e.g. env-var references instead of inline secrets) |

**`url`:**
| ID | Dimension | Focus |
|----|-----------|-------|
| U1 | Content Accuracy | Is the content factually accurate and consistent with what it claims to be? |
| U2 | Credibility Signals | Author, date, publisher, citations, contact info, about page |
| U3 | Red Flags | Urgency language, too-good-to-be-true claims, phishing patterns, suspicious redirects |
| U4 | Security Signals | HTTPS, domain age cues, redirect chains, suspicious embedded scripts/iframes |

**`claim`:**
| ID | Dimension | Focus |
|----|-----------|-------|
| CL1 | Factual Accuracy | Are the stated facts verifiable? What's demonstrably true or false? |
| CL2 | Internal Consistency | Does the claim contradict itself or prior known facts? |
| CL3 | Source Credibility | Is there evidence behind this? Are cited sources reliable? |
| CL4 | Logical Validity | Do the conclusions follow from the premises? Any fallacies? |

**`document`:**
| ID | Dimension | Focus |
|----|-----------|-------|
| D1 | Factual Accuracy | Are stated facts, numbers, names, and dates correct? |
| D2 | Internal Consistency | Do sections contradict each other? Are terms used consistently? |
| D3 | Completeness & Gaps | What's missing? What's glossed over? What questions aren't answered? |
| D4 | Logical Validity | Do the arguments hold? Any unsupported leaps? |
| D5 | Bias & Framing | Neutral? Loaded language? Selective omission? Misleading structure? |

**`process`:**
| ID | Dimension | Focus |
|----|-----------|-------|
| P1 | Correctness | Does the process achieve its stated goal? Any steps that would fail? |
| P2 | Security | Any steps that create vulnerabilities or trust boundaries are violated? |
| P3 | Edge Cases | What happens when steps fail? Missing error handling in the flow? |
| P4 | Efficiency | Unnecessary steps, bottlenecks, missing parallelism opportunities |
| P5 | Completeness | Missing steps, implicit assumptions not made explicit |
| P6 | Completion Coverage | Cross-reference the stated goals (ticket, acceptance criteria, or task description) against the output artifacts. For each stated goal: is there specific evidence in the output that it was addressed? Goals with no corresponding artifact are GAPS. |

**`output`:**
| ID | Dimension | Focus |
|----|-----------|-------|
| O1 | Completion Coverage | Does the output address ALL stated goals? For each claim of "done", cite the specific evidence in the output. Claims with no evidence in the artifact are incomplete. |
| O2 | Evidence Quality | Every finding, conclusion, or action item must cite specific file:line, quoted text, or test result. Vague assertions ("this is improved", "security has been reviewed") with no specific citation are not evidence. |
| O3 | Goal Alignment | Does the output match what was originally asked? Are there stated goals that appear nowhere in the output? Are there deliverables in the output that were not in the goal? |
| O4 | Internal Consistency | Does the output contradict itself? Does "COMPLETE" status conflict with open items? Does a summary contradict the details? |
| O5 | Specificity | Are all action items, findings, and next steps specific enough to be actionable? "Needs review" is not specific. "Review auth.py:45 for missing rate limit" is specific. |
| CB1 | ClaudeBoost Protocol Compliance | **Always include for `output` and `process` types.** See CB1 definition in Universal dimensions below. |

**Universal dimensions (always available, include if relevant):**
| ID | Dimension | Focus |
|----|-----------|-------|
| X1 | Red Flags / Anomalies | Anything that doesn't add up, feels off, or contradicts expectations |
| X2 | Missing Context | What additional information would change this assessment? |
| CB1 | ClaudeBoost Protocol Compliance | Did the session follow ClaudeBoost's mandatory protocols? Check each of the following — a violation requires a quoted phrase or named step as evidence, not an assumption: **(1) Dual-mode RAG** — were BOTH `rag_search scope=research mode=vector` AND `rag_search scope=codebase mode=graph` called for every research query? Skipping either is a violation. **(2) rag_context first** — was `rag_context` the first action in every agent spawn prompt? Any agent spawned without it is a violation. **(3) Evaluator never skipped** — was `evaluator-agent` spawned after every set of findings before acting on them? Self-verification is a violation. **(4) Context.md kept current** — was `workspace/[task-id]/context.md` updated after significant work, decisions, or changes? Stale context at session end is a violation. **(5) CONSULT mode respected** — were new endpoints, tables, dependencies, modules, or auth strategies proposed via `architect-agent` and approved before implementation? Architectural changes without consultation are a violation. **(6) /boost before workspace** — was `/boost` run before any workspace was created? Creating a workspace without a verified RAG is a violation. **(7) Verify gate** — were all findings cited with `file:line` before being acted on? Acting on uncited findings is a violation. Flag each violation with the specific step that was skipped and where in the output this is visible. If a step was correctly followed, note it as CONFIRMED — do not leave it silent. |

### Auto-include rules

These dimensions are **mandatory** regardless of what else you select:

| Condition | Always include |
|-----------|---------------|
| `INPUT_TYPE` is `output` | CB1 (ClaudeBoost Protocol Compliance) |
| `INPUT_TYPE` is `process` | CB1 (ClaudeBoost Protocol Compliance) |
| Input mentions agent spawns, workspaces, RAG, or ClaudeBoost workflows | CB1 (ClaudeBoost Protocol Compliance) |

CB1 does not count toward the 3–6 dimension cap — it is additive.

### Selection output

List your selections before spawning:
```
Input type : [TYPE]
Dimensions : [ID1] [Name] — [ID2] [Name] — [ID3] [Name] ...
Auto-added : CB1 ClaudeBoost Protocol Compliance (mandatory for output/process)
```

---

## Phase 3: Spawn Audit Agents (Batched, 3 at a time)

**Context limit rule:** context < 50% → 3 in parallel; 50–75% → 2; > 75% → 1 at a time.

Spawn one agent per selected dimension. Wait for each batch to complete before starting the next.

**EACH AGENT PROMPT must follow this template exactly:**

```
Your FIRST action: call rag_context(agent="reviewer-agent", task_description="audit dimension: <DIMENSION_NAME>", max_tokens=2000)

You are an auditor for ONE specific dimension: **<DIMENSION_NAME>**

Your focus: <DIMENSION_FOCUS>

Do NOT comment on anything outside your dimension. Stay strictly scoped.

== INPUT TYPE ==
<INPUT_TYPE>
== END INPUT TYPE ==

== CONTENT ==
<INPUT_CONTENT verbatim — do not truncate>
== END CONTENT ==

== STATED GOAL (if available) ==
<STATED_GOAL verbatim — the ticket, task description, or acceptance criteria this output is supposed to address>
If no goal is available: "Not provided — audit internal consistency only."
== END STATED GOAL ==

== YOUR DIMENSION ==
<DIMENSION_ID>: <DIMENSION_NAME>
Focus: <DIMENSION_FOCUS>
== END DIMENSION ==

Audit the content for your dimension. Be specific — cite the exact text, line, field, or section you're flagging. Vague findings ("this could be better") are not acceptable.

Output format (JSON only, no prose):
{
  "dimension": "<ID>: <NAME>",
  "findings": [
    {
      "severity": "CRITICAL|HIGH|MEDIUM|LOW",
      "location": "<exact quote, line number, field name, or section heading>",
      "description": "what the issue is — be precise",
      "evidence": "the specific text/code/value that supports this finding",
      "suggestion": "what to do about it — concrete"
    }
  ]
}
If no issues found: {"dimension": "<ID>: <NAME>", "findings": []}

EVIDENCE RULE: If you cannot quote specific text, cite a specific line/field, or name an exact section that supports a finding — do NOT include that finding. An empty or vague `evidence` field ("general concern", "seems wrong", "could be better") is worse than no finding. Return an empty `findings` array instead.

This rule exists because: a finding without evidence is a FALSE POSITIVE by definition (per verdict agent Rule 1). Returning it wastes the verdict agent's processing time and inflates apparent issue counts. Silence is correct when you cannot prove an issue.
```

Collect all JSON outputs as `AUDIT_FINDINGS`.

---

## Phase 4: Verdict Agent (Always Runs, Always Last, Always Opus)

After ALL batches complete, spawn a single verdict agent. Use **Opus model**.

```
Your FIRST action: call rag_context(agent="reviewer-agent", task_description="audit verdict synthesis", max_tokens=2000)

You are the Verdict Agent. You do NOT re-audit the content. You synthesize the findings from all dimension auditors into a single "is it legit" verdict.

== INPUT TYPE ==
<INPUT_TYPE>
== END INPUT TYPE ==

== CONTENT SUMMARY ==
<INPUT_CONTENT — first 500 chars or a summary if longer>
== END CONTENT SUMMARY ==

== ALL FINDINGS ==
<insert JSON output from every completed audit agent, clearly separated by dimension>
== END FINDINGS ==

Rules:
1. A finding without specific evidence (exact quote, line, field) is a FALSE POSITIVE — discard it.
2. Multiple findings about the same issue count as ONE — don't inflate severity by repetition.
3. Resolve contradictions between dimension agents with explicit reasoning.
4. Your verdict must reflect the evidence — don't upgrade or downgrade without citing why.
5. "No findings" from a dimension is positive signal — factor it in.

Output this exact structure (no additional sections):

**VERDICT**: [LEGIT | MOSTLY LEGIT | SUSPICIOUS | INVALID | INCOMPLETE]
- LEGIT: no significant concerns found
- MOSTLY LEGIT: minor issues, proceed with awareness
- SUSPICIOUS: meaningful concerns that warrant investigation before acting
- INVALID: fundamental problems that invalidate the input
- INCOMPLETE: cannot make a definitive call — state exactly what's missing

If AUDIT_SCOPE = completion-verification, use these verdict labels instead of LEGIT/SUSPICIOUS:
**VERIFIED**: all stated goals have specific evidence in the output
**PARTIALLY VERIFIED**: some goals verified with evidence, some lack evidence
**UNVERIFIED**: stated goals are present but without specific supporting evidence
**CANNOT_VERIFY**: insufficient information to assess (missing goal, missing output content)

**CONFIDENCE**: [HIGH | MEDIUM | LOW]
(HIGH = strong evidence for verdict; MEDIUM = reasonable evidence but some gaps; LOW = limited auditability)

**RISK LEVEL**: [NONE | LOW | MEDIUM | HIGH | CRITICAL]

**SUMMARY**: 2–3 sentences. What is this, what did the audit find, and what does it mean.

**KEY FINDINGS** (top 3, most impactful):
1. [SEVERITY] [dimension] — description (evidence: "exact quote or location")
2. ...
3. ...

**DISMISSED FINDINGS** (findings discarded as false positives, with reason):
- [dimension]: discarded because [specific reason]

**RECOMMENDATION**: One concrete sentence on what the user should do.
```

---

## Phase 5: Report

**Clear audit flag first** (before any output — ensures cleanup even if interrupted):
```bash
rm -f "$CLAUDEBOOST_HOME/state/audit-in-progress.json"
```

Output the full verdict report. Lead with the severity count header on the very first line:

**Severity summary (always first):**
> `N CRITICAL | N HIGH | N MEDIUM | N LOW | N dismissed`

Then the VERDICT, CONFIDENCE, RISK LEVEL, and full report body.

Final message to user:
> "Audit complete. **[VERDICT]** (confidence: [CONFIDENCE], risk: [RISK_LEVEL]). [N CRITICAL, N HIGH, N MEDIUM, N LOW — N dismissed as false positives]. [SUMMARY sentence 1]. [RECOMMENDATION]"
