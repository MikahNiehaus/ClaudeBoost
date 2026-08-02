# ClaudeBoost

Research gated development for Claude Code. Every code edit is researched before
it happens, and search runs over your own indexed projects, not a scraped
knowledge base. Works standalone or with Gas Town.

## The research gate (this is the operative rule)

Every edit to a code file is checked against whether `researcher` or `swiper`
has run this session and declared that it covered that file. The gate is a
hard PreToolUse block: an uncovered file cannot be edited. Coverage persists
across follow-up messages (not reset on every message) and expires after one
hour of inactivity or when new research runs. The block is keyed off a real
agent completion stamped by a PostToolUse hook — it cannot be satisfied by
claiming you researched.

When the gate blocks:

1. **Spawn `researcher` and/or `swiper`** (Sonnet, foreground). Tell them what
   you're changing, why, and the code you intend to write. Both cover depth and
   breadth and report with sources and a `COVERS:` line naming the files they
   covered. That scope is what the gate checks: an edit to an uncovered file is
   blocked, not just flagged. Wait for them before attempting the edit — there is
   no point trying the edit first. Spawn in the foreground (`run_in_background:
   false`), never backgrounded — a backgrounded completion arrives later as a
   `TaskNotificationMessage`, not a tool result, so the hook that stamps the turn
   record never fires for it and the gate never sees the coverage.
   Its report also names a `MATCH_STRATEGY:`. If it's `clone-and-patch`, copy the
   verbatim quoted reference as the literal starting point and make only the
   smallest set of changes that fixes the actual issue — no rewrite, no restyle,
   no swapped libraries or approaches, no added structure the reference didn't
   have. That's a hard ceiling on the diff, not a suggestion. `pattern-only`
   allows a real diff; `clone-and-patch` does not. There is no `adapt` tier.
2. There is no cheap triage tier. A change either has research covering the
   file or it doesn't. If it doesn't, the gate blocks. `/ps` is the human's
   escape for a turn they already know is trivial.
3. Genuinely trivial work that needs no research is the human's call, not a
   model's. Run `/ps` for a quick turn that skips the gate (and the verifier) when
   you already know the change is trivial.

Markdown and non code files are exempt. So are `workspace/`, `state/`, `plans/`,
`docs/`, `.claude/`, and temp dirs.

**Depth versus breadth**, the split both agents use:
- **Depth** is the general engineering question, the one an unrelated project
  would get the same answer to. Structure, separation of responsibility,
  testability, the standard approach to this class of problem.
- **Breadth** is the task specific question. How this exact kind of thing gets
  built, what people get wrong with it, what good looks like. "What's the best
  way to build this" is breadth too, not just pitfalls.

research-agent cannot write files, and its Bash is caged to the local clean-rag
server. It reads untrusted web content, so removing its ability to act is the real
defense against a prompt injection.

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
- **A real separate context review runs on every real code change**, unless the
  human marked the turn `/ps`. It used to be reserved for high stakes surfaces
  (auth, money, SQL, a subprocess, concurrency); now it's the default after any
  code change, because green tests and correct code are different questions
  everywhere, not only there. Spawn `bad-cop` first, a fresh context critic, NOT
  the research agent (that one reads untrusted web and stays capability stripped,
  and any agent that wrote or researched the change inherits its own blind spot on
  review). bad-cop writes adversarial tests, runs the code, adds logging, and
  reports the real failures it finds, with actual execution output attached.
  If it finds nothing real, it stamps `VERIFIED:` itself: no separate
  `good-cop` run needed to re-confirm a clean adversarial pass. Only when it
  finds something real, spawn `good-cop` next, same rules, handed bad-cop's
  findings instead of the requirements alone: it researches the correct fix,
  applies it, and reruns bad-cop's new tests plus the existing suite until
  everything is actually green, and it is the one that stamps `VERIFIED:` in
  that case. After good-cop stamps, spawn bad-cop again for a final
  adversarial re-check on the fix. If bad-cop finds nothing on that re-check,
  it stamps `VERIFIED:` itself and the loop ends. If it finds more issues,
  spawn good-cop again. The loop (bad-cop → good-cop → bad-cop) continues
  until bad-cop stamps `VERIFIED:` itself — that is the only terminal
  condition, not good-cop claiming done. Give both of them the
  requirements, the correctness properties, and the diff, never your reasoning
  for the change, since that reasoning is exactly what biases a reviewer into
  agreeing. If research-agent grounded the build in a real GitHub reference (a
  `GITHUB_FILE_READ:` line plus the verbatim snippet it quoted), pass that
  snippet forward into their correctness properties too, not just its
  description. Neither has web fetch access on purpose, only search, so this is
  the only way a real reference reaches their review; do not give either its own
  GitHub/web fetch access, that would duplicate the one injection-exposed agent
  this codebase deliberately keeps to one. `hooks/verifier-gate.py`
  (a Stop hook) requires a real stamp before the turn can end: bad-cop always
  provides the terminal stamp — either directly on a clean initial pass, or
  after a final re-check that finds nothing following good-cop's fix —
  writing a `VERIFIED:` line naming the files it covered, checked
  per file the same way the research gate checks `COVERS:`, invalidated if a
  file is edited again after being reviewed. `high_stakes.py`
  labels which surface it touched so the review points at the sharpest risk. A
  `/ps` turn skips both, the same quick mode escape that skips the research gate.

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

If the logic you changed has no test at all, writing one IS part of verifying it,
not an optional extra. Do not skip verification because none exists, that is the
gap the tests were supposed to close. Write the missing test, then prove it bites
(next paragraph), because a test written without that proof reliably asserts the
current behavior instead of catching a bug, which is worse than no test.

Passing tests are necessary, not proof the tests catch bugs. For non trivial logic
on a real bug surface, after the tests pass run the mutation check on just the
files you changed: `POST http://127.0.0.1:8613/mutation-test` with
`{"project_path": "<abs>", "changed_files": [...]}`. It runs the language's real
mutation tool (`mutmut`, `StrykerJS`, `cargo-mutants`) and returns a kill score; a
surviving mutant is a test that would pass on broken code, so tighten it. When the
edge cases matter, let the language's property based library (`Hypothesis`,
`fast-check`, `jqwik`) generate them instead of hand listing a few. Both beat
guessing which inputs to test, which is the weak version the research warned about.

## Debugging, testing and QA

When a bug does not yield, the failure mode is applying one technique harder.
Two or three iterations with no new information means the technique is wrong,
not that you need more logging. Invoke the **`debugging-methodology`** skill and
pick a different one by name from its symptom table:

- Regressed since a known good commit, use `git bisect` (`git bisect run <cmd>`
  automates it entirely).
- Large input fails, small ones pass, use delta debugging to shrink it.
- Long call chain with one bad value, binary search on state.
- A working case sits beside the failing one, differential debugging.
- Reproduces but the cause is unclear, hypothesis first: write the claim down,
  then design the smallest test that would falsify it.
- Intermittent or a race, record replay (`rr`). Re running it is not a strategy.
- No reliable reproduction at all, stop and get one. A fix without a repro is a
  guess you cannot validate.

That skill also carries the per stack recipes for surfaces no MCP server
reaches: React Native (`adb logcat`, `npx react-native log-ios`, Hermes over CDP
through `chrome-devtools`, since RN DevTools replaced Flipper), .NET
(`dotnet-trace`, `dotnet-dump`, `dotnet-gcdump`, `dotnet-counters`), and Python
(`py-spy dump`/`record`, which attach to a live process without restarting it).

**Reach for the debugger over print statements.** `mcp-debugger` covers Python,
Ruby, Node, Go, Java, .NET and Rust: `create_debug_session` → `set_breakpoint` →
`start_debugging` or `attach_to_process` → `get_variables`. Browser, network and
performance work is `chrome-devtools`. Coverage is `test-coverage`. Native C/C++
is `mdb` (GDB/LLDB). If a tool is missing at runtime its server was never
registered, so run the installer; every server comes from one table there.

**Databases are read only.** Understand the schema from the project's own
artifacts (EF Core `DbContext` and `Migrations/`, `models.py`, Alembic versions,
`schema.sql`), reason about the query, and hand it to the human to run. Do not
execute against a live database and do not automate SSMS or any equivalent GUI
client. A wrong statement against real data is not recoverable by a retry.

Running `/qa` gives the full session: inventory, a risk ranked test plan, and
execution with evidence. `/debug` is the focused single bug path. Both enumerate
the debugging tools already, and both point back at this same skill.

## UI / Frontend Work

When the task involves editing or creating frontend files (`.tsx`, `.jsx`,
`.html`, `.css`, `.scss`, `.vue`, `.svelte`), invoke the `frontend-design`
skill before making any design decisions. Run the two-pass process: compact
token system (palette, typefaces, layout concept, signature element) then
self-critique against the brief before building. Never skip to code without
the brief-grounding pass.

After any UI change, invoke the `eyes` skill to capture a screenshot and
verify visually before calling it done. Propose changes with pixel-precise
numbers. Confirm with the user before applying. Verify with a before/after
comparison screenshot.

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
  edit, and a full sweep every 60 minutes for outside changes. The server runs
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
- **Opus**: architect-agent, reviewer-agent, ticket-analyst-agent, good-cop.
- **Sonnet**: research-agent, researcher, bad-cop, and all other specialists.

### Starting a new build or feature

For an edit intent task, a new build or feature, run `/start` instead of
diving straight into research-agent: it spawns `researcher` first (codebase
structure via clean-rag's own index and graph, plus the general engineering
standard for this class of change), then `swiper` informed by researcher's
findings (what can be swiped, from the project, the stdlib, a dependency,
GitHub, or StackOverflow, reported only, swiper never writes to the project
itself), then consults the user with real options before anything is
written. `researcher` also replaces an ad hoc codebase exploring subagent for
understanding a project: it has clean-rag's real indexed vector and graph
databases behind it, so route codebase understanding tasks to it instead.

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
