# ClaudeBoost Improvement Roadmap

This document captures the gaps identified through a competitive analysis of ClaudeBoost against the 2026 Claude agent toolkit landscape. Items are ordered by impact on core value, not implementation difficulty.

---

## Priority 1 — Fixes to the Core Value Proposition

These are the gaps that directly erode what makes ClaudeBoost worth using.

### 1.1 Knowledge Base Staleness Detection

**The problem.** The 96 XML knowledge files are the engine of ClaudeBoost's intelligence advantage. They have no version pinning, no "last validated against framework X vY" metadata, and no automated check for freshness. When React 20, a new OWASP advisory, or a Python 3.14 feature lands, the relevant files go silently wrong. You won't notice until you get bad advice.

**What to build.**
- Add a `<metadata>` block to each XML file with `last_validated`, `framework_version`, and `source_url` fields.
- Build a `scripts/stale-check.py` that reads those fields, compares against a pinned versions file (`knowledge/versions.json`), and reports files whose `framework_version` is behind.
- Wire the stale check into `reindex-check.py` so it fires at SessionStart alongside the index staleness check.
- Optionally: a `/check-knowledge` slash command that runs the stale check on demand.

**Closes the gap with:** Nothing — no other personal toolkit has this. This is a gap you'd be the first to close.

---

### 1.2 Mechanical Evaluator-Agent Routing

**The problem.** The evaluator-agent is triggered by a PostToolUse nudge — an LLM prompt. The CLAUDE.md explicitly says "it is an LLM nudge, not a mechanical gate." If the orchestrator is confident (rightly or wrongly), it skips the evaluator. Your anti-hallucination system depends on Claude following instructions about when to verify.

LangGraph's equivalent is a conditional edge in a directed graph — it's code that routes to the evaluator node deterministically when a finding is flagged `NEEDS_VERIFICATION`. The routing cannot be overridden by model confidence.

**What to build.**
- Upgrade the PostToolUse hook to a command-type hook that reads `NEEDS_VERIFICATION` from tool output and exits 2 (blocking) if evaluator-agent hasn't been spawned since the last such flag.
- Track evaluator spawns in a session state file (`state/session-evaluator-log.json`).
- If a Stop event fires while `NEEDS_VERIFICATION` findings are unresolved, `stop-context-guard.py` should block and report which findings need verification.

**Closes the gap with:** LangGraph's deterministic conditional routing.

---

## Priority 2 — Reliability and Trust

These don't affect day-to-day quality when things work, but they're invisible failure modes waiting to surface.

### 2.1 Hook Test Harness

**The problem.** The hooks — `rag-agent-guard.py`, `rag-read-guard.py`, `agent-spawn-gate.py`, `compaction-primer.py`, and the rest — have no automated tests. A bug in `rag-agent-guard.py` that causes false positives (blocking valid spawns) or false negatives (passing spawns that miss RAG) won't surface until something breaks in a session you care about.

**What to build.**
- A `scripts/tests/` folder with one test file per hook script.
- Each test simulates the stdin JSON that Claude Code passes to the hook, runs the script as a subprocess, and asserts on exit code and stderr output.
- Happy path + at least two failure cases per hook.
- A `scripts/test-hooks.py` runner that executes all hook tests and reports pass/fail.
- Wire into a `/test-hooks` slash command for manual verification after changes.

**Reference:** Treat each `.py` script as a small CLI utility and test it that way — subprocess, stdin fixture, assert exit code.

---

### 2.2 RAG Server Observability

**The problem.** The RAG server has a `/status` endpoint and a `rag-error-guard.py` hook that surfaces crashes. That's it. You have no visibility into query latency trends, retrieval quality over time, cache hit rates, or which knowledge files are being hit frequently versus ignored.

This matters because retrieval quality degrades silently. A knowledge file that was frequently retrieved last month and isn't this month could mean it's become irrelevant — or it could mean the embeddings drifted and it's no longer matching queries it should.

**What to build.**
- Add a query log to the RAG server: append each `/search` call to a SQLite table with timestamp, query, scope, top result sources, and top scores.
- Build a `scripts/rag-stats.py` that reads the log and reports: top retrieved files (last 7 days), average query latency, queries with no results or low scores, and files with zero retrieval in 30 days.
- A `/rag-stats` slash command that calls the script and prints the report.

**Closes the gap with:** LangSmith's observability for LangGraph pipelines (a simplified version, but directionally correct).

---

## Priority 3 — Architecture Gaps vs. Competitors

These are real limitations but require more design work before implementation.

### 3.1 Peer-to-Peer Agent Communication

**The problem.** ClaudeBoost agents are hub-and-spoke: every agent reports to the orchestrator. Agents cannot negotiate with each other mid-task. Anthropic Agent Teams supports peer-to-peer messaging and a shared task list with dependency tracking. This means two ClaudeBoost agents working on related subtasks can't coordinate without going back through the orchestrator, which creates bottlenecks and potential context waste.

**What to consider.** Full peer-to-peer communication is a significant architectural change. A lighter-weight improvement is a shared workspace state file (`workspace/[task-id]/agent-state.json`) that agents read and write to during a task, letting them leave structured notes for sibling agents without routing everything through the orchestrator. This doesn't give real-time communication, but it gives asynchronous coordination.

**Closes the gap with:** Anthropic Agent Teams' shared task list.

---

### 3.2 CI/CD Integration

**The problem.** ClaudeBoost's workflow ends at PR description generation. There's no hook into GitHub Actions results, test run feedback, or deployment status. Agents that implement a feature don't know if it passed CI.

**What to consider.** A `/ci-status` command that calls `gh run list` for the current branch and surfaces the latest CI run result would be a useful start. Deeper integration (agents that react to CI failures) requires more thought about session lifecycle.

**Closes the gap with:** LangGraph agents embedded in CI pipelines.

---

### 3.3 Summary Format Enforcement

**The problem.** The `## Summary (≤300 words)` requirement at the end of every agent response is advisory. The orchestrator reads the summary block and trusts it. There's no hook that verifies the summary block exists before the orchestrator proceeds.

**What to build.** In `stop-context-guard.py` (or a new PostToolUse hook on the Agent tool), parse the agent response for a `## Summary` section. If it's missing, return an `additionalContext` injection that asks the agent to add it before the orchestrator reads the result. This doesn't require blocking — a prompt injection is enough since the orchestrator checks before acting on agent output.

---

## Priority 4 — Ecosystem Reach

Lower priority because they don't affect quality for the current user, but worth noting.

### 4.1 Cross-Platform Friction

ClaudeBoost is Windows-first. The memory files, CLAUDE.md, and tooling documentation call out Windows-specific issues: PowerShell BOM problems with `Set-Content`, `$LOCALAPPDATA` unavailability in the sandbox, Unicode rendering failures. A Mac/Linux developer adopting ClaudeBoost would hit these immediately.

Fixing this means auditing all scripts for Windows-specific assumptions, testing the setup on a Mac or WSL environment, and updating the setup guide to call out platform differences explicitly.

### 4.2 Team Deployment

ClaudeBoost is a single-user toolkit. The human voice standard, the specific hook scripts, and the session state files are all tied to one developer's preferences and workflow. oh-my-claudecode exists specifically for sharing Claude Code configuration across a team. ClaudeBoost has no equivalent concept.

This is intentional for now, but worth a design note: if you ever want to share this with colleagues, you'd need a "core" layer (agents, knowledge, hooks) that's team-portable and a "personal" layer (memory, voice rules, TTS preferences) that stays per-user.

---

## Quick Reference: Improvements by Gap

| Improvement | Category | Closes gap with |
|---|---|---|
| Knowledge staleness detection | Core value | (unique, no competitor has this) |
| Mechanical evaluator routing | Anti-hallucination | LangGraph |
| Hook test harness | Reliability | General software quality |
| RAG server observability | Reliability | LangSmith |
| Peer-to-peer agent notes | Architecture | Anthropic Agent Teams |
| CI/CD integration | Workflow | LangGraph in CI |
| Summary format enforcement | Output quality | (tightens existing protocol) |
| Cross-platform | Reach | oh-my-claudecode, knowledge-rag |
| Team deployment | Reach | oh-my-claudecode |
