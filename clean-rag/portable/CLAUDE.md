# ClaudeBoost

Research gated development for Claude Code. Every code edit is researched before
it happens, and search runs over your own indexed projects, not a scraped
knowledge base. Works standalone or with Gas Town.

## The research gate (this is the operative rule)

Every edit to a code file is blocked until a research or triage agent has run
this turn and declared that it covered that file. Not asked for. Required. The
gate is a PreToolUse hook that keys off a real agent completion, so there is no
way to satisfy it by claiming you researched.

When the gate blocks an edit:

1. **Spawn `triage-agent`** (Haiku, cheap, fast). Tell it what you're changing,
   why, and the code you intend to write. It answers in about 15 seconds with
   either `NONE` (trivial, no research needed) or a short list of what to
   research. Its report ends with a `COVERS:` line naming the files it covers.
   That scope is what unlocks the edit.
2. If triage says `RESEARCH`, **spawn `research-agent`** (Sonnet) with those
   aspects. It researches depth and breadth, checks whether the thing already
   exists, reads the project's import graph, and reports with sources and its
   own `COVERS:` line. Wait for it before editing.
3. `NONE` is a real answer and the common case. A trivial edit is not a failure
   to find something.

Markdown and non code files are exempt. So are `workspace/`, `state/`, `plans/`,
`docs/`, `.claude/`, and temp dirs.

**Depth versus breadth**, the split both agents use:
- **Depth** is the general engineering question, the one an unrelated project
  would get the same answer to. Structure, separation of responsibility,
  testability, the standard approach to this class of problem.
- **Breadth** is the task specific question. How this exact kind of thing gets
  built, what people get wrong with it, what good looks like. "What's the best
  way to build this" is breadth too, not just pitfalls.

The two research agents cannot write files, and their Bash is caged to the local
clean-rag server. They read untrusted web content, so removing their ability to
act is the real defense against a prompt injection.

## Verify by running, not by reviewing (the post write half)

Research before the edit lowers the odds of a bug. It does not confirm the code
you wrote is correct. To actually know, after writing any non trivial logic:

- **Leave one small runnable check and RUN it.** An assert, a tiny test, or
  drive the real flow. If it fails, feed the actual error back and fix once.
  Execution feedback is the highest quality per token signal there is (measured
  12 to 46 percent first try correctness gains), and it costs interpreter time,
  not tokens, except for the rare fix.
- **Do not self review your own diff in the same context.** Measured evidence
  says intrinsic self critique without external grounding is close to useless
  and sometimes makes things worse. Running the code is grounded. Re reading it
  is not.
- **A real separate context review is for high stakes surfaces only**: auth,
  money, SQL, a subprocess, anything at a trust boundary. It costs like a second
  write, so it is not the default.

Trivial one liners need no check. This is the cheap post write complement to the
gate's pre write research: research narrows the approach, running the code
confirms it.

This verify step is now partly enforced. `hooks/auto-test-gate.py` (a Stop hook)
runs the project's tests when code changed this turn, and if they really fail it
blocks the stop once and hands you back the real failure output to fix from. It is
loop safe: it honors `stop_hook_active`, caps blocks per session, and allows on
anything ambiguous (no tests, a missing runner, an environment problem). So on a
project with tests you will often get the actual assertion diff or stack trace
pushed back at you automatically. Fix from that, do not self review.

## clean-rag (the search backend, port 8613)

Search runs over projects you've indexed, plus live web search. There is no
scraped topic knowledge base.

- `POST http://127.0.0.1:8613/search` with `sources: ["project:<abs path>"]` and
  `mode: "both"` runs vector similarity and import graph traversal together.
  Graph results carry `relation` (imports, inherits, implements, calls) and
  `seed_file`. Use `mode: "both"` on every code search, vector and graph surface
  different files.
- `POST http://127.0.0.1:8613/web-search` is DuckDuckGo, source ranked (GitHub
  and StackOverflow first, content farms last), sanitized against hidden
  characters. Snippets are cheap, so survey with it and only fetch a full page
  when you need the substance.
- Index a project once with `/index-project`. It reindexes itself: after every
  edit, and a full sweep every 10 minutes for outside changes. The server runs
  headed so you can watch it.

If the server is down, run `/rag` or `clean-rag/cli/server_ctl.py start`.

## Decision Flow

Two paths, not five mandatory steps.

**Simple task?** Just do it. No workspace, no ceremony.

**Complex task?** (ticket attached, multi-agent, multi-session, user says "plan
this")
1. Create `workspace/[task-id]/` and announce with one line.
2. Sweep then verify across domains (testing, docs, security, architecture,
   performance, review, clarity).
3. Spawn the right agent(s).

Sweep then verify: scan all domains, but for every flag you raise, prove it from
actual code. If you can't cite specific lines, drop the flag. "Nothing found" is
always valid.

## Agent Spawning

Spawn agents when they add value: parallelism, isolation, deep specialization.
Do the work directly when they don't. A one line fix doesn't need an agent.

Specialist agents (architect, reviewer, debug, security, performance, refactor,
ui, docs, test, and the rest) are available for focused work. They are spawned
as needed, not on every task.

### Model Routing
- **Opus**: architect-agent, reviewer-agent, ticket-analyst-agent.
- **Sonnet**: research-agent and all other specialists.
- **Haiku**: triage-agent.

### Parallel Limits
- Context below 50%: up to 3 agents.
- Context 50 to 75%: up to 2 agents.
- Context above 75%: 1 agent, sequential.

## Verify Gate (anti hallucination)

Applies everywhere: reviews, planning, bug diagnosis, security audits, test
planning.

- Every finding must be proven from actual code before acting on it.
- Cite specific file and line for every flag.
- "No issues found" is always a valid outcome.
- Finding something is not the goal. Finding real things is.

## Collaborative Mode (CONSULT / AUTO)

Default is **CONSULT**. Before an architectural decision, research the project,
present options, let the user add constraints, then implement. Architectural
triggers: a new endpoint, DB table, dependency, module, middleware, or a new
auth/validation/error/logging strategy. Not triggers: typos, one line fixes,
tests, docs, renames in one file.

`/auto [reason]` switches to autonomous AUTO mode for prototyping and low rework
cost work. `/consult` restores CONSULT.

## Hard Rules (non negotiable)

### jQuery Ban
jQuery is banned unless the user explicitly asks for it. Detect `$()`, `jQuery`,
imports, and CDN tags. Use React hooks, vanilla JS, and native fetch instead.

### Security Standards
- Parameterized queries always. Never string concatenation in SQL.
- Transactions for multi step database operations.
- OWASP top 10 awareness.
- No secrets in logs, URLs, or source.
- Input validation at system boundaries.
- Auth and authz checks on endpoints.

### Logging Standards
- Missing `logger.error` in a catch or error block is a blocker.
- Sensitive data in log output is a blocker.
- Missing INFO level on service methods and before/after on external calls is a
  suggestion.

## Token Efficiency

Do it right the first time. Rework costs more than ceremony.

- Route by weight. Full ceremony (verify gate plus evaluator) for reviewer,
  security, performance. Standard for the rest. Lightweight for explore,
  research, docs.
- Always spawn an evaluator to verify findings, never self verify. A fresh
  context catches hallucinations that same context confirmation misses.
- Web research is cheap when you survey with snippets and fetch sparingly. The
  research agent's cost is mostly full page fetches, not searches.

## Gas Town Compatibility

Works with `gt prime`, `gt hook`, `gt sling`, `gt mail`, `gt nudge`,
`gt handoff`, and beads. The workspace convention is bead compatible, and agent
spawning is compatible with `gt sling` to polecats.

## OpenCode

clean-rag has an OpenCode integration too (`clean-rag/opencode/`): the same MCP
search tools, the two research agents ported as OpenCode subagents, and a
research gate plugin. Install with `clean-rag/opencode/install.py`. The gate is
enforced for the primary agent; a known OpenCode bug means subagent edits may
bypass it until upstream fixes it.

## Browser Testing Safety

Playwright and browser automation are localhost only. Allowed: localhost,
127.0.0.1, 0.0.0.0, and `*.local` / `*.test`. If unsure whether a URL is local,
ask before navigating. Default to a headed browser, not headless.
