# ClaudeBoost

Research gated development for Claude Code. Every code edit is researched before
it happens, and search runs over your own indexed projects, not a scraped
knowledge base. Works standalone or with Gas Town.

## The research gate (this is the operative rule)

Every edit to a code file is checked against whether `researcher` or `swiper`
has run this session and declared that it covered that file, and nudges toward
research when neither has. Those two are the only agents the gate counts
(`RESEARCH_AGENTS` in `clean-rag/hooks/research_state.py`); `research-agent`
does not satisfy it. Coverage persists across follow-up messages and expires
after one hour (`TURN_MAX_AGE_S = 3600`) or when new research lands on top.

The gate used to block the edit. It doesn't now. `clean-rag/hooks/research-gate.py`
exits 0 on every payload shape, by decision: an unresearched edit is
recoverable, so it gets a nudge and an honest audit trail rather than a
refusal. The first block attempt also predated the session scoping above, so
coverage was wiped by every follow-up message and the gate fired on files
swiper had just covered.

What can't be faked is the record, not the refusal. Only Claude Code can start
an agent, and a PostToolUse hook stamps the coverage after the agent finishes,
so "I researched it" is never what gets written down.

When the gate nudges toward research:

1. **Spawn `researcher` and/or `swiper`** (Sonnet). Tell them what you're
   changing, why, and the code you intend to write. Both cover depth and breadth
   and report with sources and a `COVERS:` line naming the files they covered.
   That scope is what the audit trail
   checks; nothing refuses the edit, but an uncovered file shows up as uncovered.
   Wait for it before editing anyway; that's still the point. Spawn it in the
   foreground (`run_in_background: false`), never backgrounded — a backgrounded
   completion arrives later as a `TaskNotificationMessage`, not a tool result, so
   the hook that stamps the turn record never fires for it and the record never
   shows the coverage no matter how long you wait.
   Its report also names a `MATCH_STRATEGY:`. If it's `clone-and-patch`, copy the
   verbatim quoted reference as the literal starting point and make only the
   smallest set of changes that fixes the actual issue — no rewrite, no restyle,
   no swapped libraries or approaches, no added structure the reference didn't
   have. That's a hard ceiling on the diff, not a suggestion. `pattern-only`
   allows a real diff; `clone-and-patch` does not. There is no `adapt` tier.
2. There is no cheap triage tier anymore. The old one decided whether a change
   needed research WITHOUT reading the code, and that blind guess was wrong often
   enough to remove. researcher and swiper look first, so their judgment is
   grounded. They do real research every time they run; do not build a
   triviality shortcut into them or any other agent.
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
  Its last line says what happens next, and there are three of them. If it
  finds nothing, it stamps `VERIFIED:` itself: no separate `good-cop` run
  needed to re-confirm a clean adversarial pass. If everything it found is
  Nit severity, it emits `NITS:` instead and good-cop is still not spawned:
  a nit is non blocking by definition (Google's engineering practices coined
  the `Nit:` prefix for exactly this, polish the author may ignore), so you
  apply those fixes directly and re-run bad-cop for the re-check that earns
  the stamp. bad-cop deliberately does not stamp on a nit only run, because
  `verifier_state.py` invalidates a stamp once the file's mtime advances
  past it, so a stamp written before the fixes land erases itself. Only when
  it emits `HANDOFF:`, meaning at least one finding is Critical or High, do
  you spawn `good-cop` next, same rules, handed bad-cop's findings instead
  of the requirements alone: it researches the correct fix,
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
  agreeing. If researcher or swiper grounded the build in a real GitHub reference (a
  `GITHUB_FILE_READ:` line plus the verbatim snippet it quoted), pass that
  snippet forward into their correctness properties too, not just its
  description. Neither has web fetch access on purpose, only search, so this is
  the only way a real reference reaches their review; do not give either its own
  GitHub/web fetch access, that would duplicate the one injection-exposed agent
  this codebase deliberately keeps to one. `clean-rag/hooks/verifier-gate.py`
  (a Stop hook) asks for a real stamp but never refuses the stop: it exits 0
  always and writes its nudge to stderr, naming the unverified files and who to
  spawn. bad-cop provides the terminal stamp — either directly on a clean
  initial pass, or after a final re-check that finds nothing following
  good-cop's fix — writing a `VERIFIED:` line naming the files it covered,
  checked per file the same way the research gate checks `COVERS:`, invalidated
  if a file is edited again after being reviewed (an mtime comparison in
  `clean-rag/hooks/verifier_state.py`). `clean-rag/hooks/high_stakes.py`
  labels which surface it touched so the review points at the sharpest risk. A
  `/ps` turn skips both, the same quick mode escape that skips the research gate.

**Check bad-cop and good-cop's actual diff yourself, not their self report.**
After either stamps or reports done, read the real result: `git diff` on the
files they touched, or Read the changed files directly. Confirm two things
concretely: the diff stays inside the scope you gave that agent (no unrelated
files, no drive by refactors, no touching config, secrets, or infra it was
never asked about), and nothing in it is a destructive or irreversible action.
Do this by reading the resulting files or `git diff`, never by opening the
agent's own JSONL transcript to watch its reasoning; that pulls tool noise
into your context for no reason and is not what this check is for. If the
diff looks wrong, say so and stop, do not silently revert it yourself and do
not just trust the agent's own "done" claim.

**Use quick-cop far more than you currently do.** Every time you say
something is done, fixed, verified, confirmed, or has no gaps, that sentence
is exactly the trigger quick-cop exists for (see its own agent description).
Dispatch it liberally and backgrounded, meaning fire it and keep working,
do not block waiting on it. This includes your own claims after a bad-cop or
good-cop run: their self reported "VERIFIED" or "all tests green" is still a
claim, so hand it to quick-cop to independently confirm rather than repeating
it to the user as settled fact.

Trivial one liners need no check. This is the cheap post write complement to the
gate's pre write research: research narrows the approach, running the code
confirms it.

This verify step is partly enforced, and `clean-rag/hooks/auto-test-gate.py` is
the one Stop hook in this family that genuinely blocks. It runs the project's
tests when code changed this turn, and if they really fail it blocks the stop
(exit 2) and hands you back the real failure output to fix from. It is loop
safe: it honors `stop_hook_active`, caps at `MAX_BLOCKS_PER_SESSION = 2`, and
allows on anything ambiguous (no tests, a missing runner, an environment
problem). So on a project with tests you will often get the actual assertion
diff or stack trace pushed back at you automatically. Fix from that, do not
self review.

Note the split, because it is deliberate and easy to misread. A test failure is
objective and cheap to check, so it blocks. A review verdict is a judgment call,
so it nudges and routes through fresh context subagents instead. Do not
"upgrade" the research or verifier gate to a hard block; see the recorded
decision at the end of this section.

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

### Every QA session ends with bad-cop judging it. This is not optional

Running `/qa`, or doing any QA by hand, is not finished when the tests are done.
It is finished when a fresh context has judged the evidence. A QA session cannot
audit its own artifacts for the same reason you do not self review your own
diff: it knows what it meant to prove, so it reads its own evidence as proving
it.

When the testing is done, spawn **`bad-cop` with `MODE: evidence-judge`** and
hand it exactly three things:

1. The requirements **verbatim**, the pasted ticket or the user's actual words,
   never your paraphrase of the goal.
2. Every proof artifact path: logs, captures, screenshots, the report itself.
3. The tool inventory the QA session had available.

Give it the correctness properties and what to attack. Never give it your
reasoning about why you think the QA was sufficient, since that reasoning is
what talks a reviewer into agreeing.

It stamps `FULLY VERIFIED` or `TEST AGAIN` with specific gaps. On `TEST AGAIN`
you retest those gaps and send it back. **The loop ends only when bad-cop stamps
`FULLY VERIFIED`, never when the QA session declares itself satisfied.**

Then check bad-cop's own claims the same way you check good-cop's: open the
artifacts it cites, do not take its summary on trust.

This catches a class of failure green results never surface, because every one
of these looks like a pass from inside the session:

- **Persistence claimed from a screenshot** with no server read-back. A value
  rendered in a form is not a value in the database.
- **Results that exist only as prose** in the report, with no capture on disk.
  If it is not in an artifact it was not measured, whatever the table says.
- **A build identifier quoted without resolving it.** Confirm the commit is a
  real object in the repo. A dashboard's "version" field is often an internal
  build id and not a commit at all.
- **Comparing two runs that tested different code.** Before attributing a
  behaviour change to the environment or to test technique, diff the commits.
  This is the one that most often produces a confident wrong conclusion.
- **A blank or mistargeted screenshot** passing as evidence because nobody
  opened it. Open every image you save.
- **Measurement windows too short for a deployed backend.** A response under
  100ms locally can take ten seconds deployed, so a window sized for local turns
  a success into a phantom failure or an unresolved null.
- **Verifying a fix in a minified bundle by grepping identifier names.** Local
  names are renamed and comments stripped, so the grep reads zero for a fix that
  is present. Grep an object property, which survives, then read the code around
  it.
- **A marker check that covers only half the change.** Confirm the marker you
  chose actually appears in every file the diff touched.

`quick-cop` is the cheap non blocking version for a single "it is done" claim.
It stamps nothing and never substitutes for bad-cop on a full QA session.

### Recorded decision: no blocking external model reviewer on Stop

Considered and declined, 2026-08-18. The proposal was a Stop hook that shells a
separate model (`claude -p`, `codex exec`, `gemini`) at `git diff HEAD` and
blocks the turn on a FAIL verdict. Do not build it. The reasons, in order of
weight:

- A hard blocking reviewer was already built on this exact surface and reverted
  twice. `clean-rag/hooks/verifier-gate.py` records both reverts in its own
  docstring.
- Anthropic's own `security-guidance` plugin does this, and it only works
  because of three things a hand rolled version has none of: `asyncRewake`
  instead of a synchronous block, a `MAX_STOP_HOOK_FIRINGS` cap, and a
  continuation suffix so the model does not abandon the user's original request
  after being blocked.
- `abiswas97/gemini-plugin-cc` warns in its own README that this class of hook
  "can create a long-running Claude/Gemini loop. Only enable it when actively
  monitoring the session."
- Claude Code re-runs every Stop hook on every Stop event. A new blocking hook
  without a `stop_hook_active` guard loops against `auto-test-gate.py` and
  `stop-context-guard.py`.
- The review responsibility is already owned by bad-cop and good-cop, which are
  fresh context subagents. A second reviewer on the same Stop event duplicates
  or contradicts them.

If the goal ever becomes security specific review, adopt the whole plugin
(`/plugin install security-guidance@claude-plugins-official`, `SECURITY_REVIEW_MODEL`
selects the reviewer) rather than writing a hook. If only a Stop hook loop guard
is wanted for some other purpose, `hamelsmu/claude-review-loop`'s `stop-hook.sh`
is the reference for the retry and fail open state machine, MIT licensed.

Two corrections to the advice that prompted this, for anyone who reads it later:
the Stop payload carries `transcript_path` but no changed files list, so a hook
must derive that itself with `git status --porcelain`; and launching `claude -p`
from inside a live session requires unsetting `CLAUDECODE` in the child env
(`scripts/chat-watcher.py` does this).

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

### Never start an app without naming the environment
Starting a local app is the single most dangerous routine command, because the
damage comes from what you *omit*, not from anything visibly dangerous you type.

Always name the environment explicitly, and never pass a flag that skips the
launch profile:

```
ASPNETCORE_ENVIRONMENT=Development ASPNETCORE_URLS="https://localhost:PORT" \
  dotnet run --project "<path to csproj>"
```

Then read the startup log and confirm `Hosting environment: Development` before
opening a browser or running any test against it. Anything else is a stop.

Why this is a hard rule: ASP.NET Core defaults to **Production** whenever
`ASPNETCORE_ENVIRONMENT` is unset. `dotnet run --no-launch-profile` skips
`launchSettings.json`, which is usually the only thing setting that variable, so
config binds `appsettings.json` instead of `appsettings.Development.json`. On a
real project that routinely means the production database and the production
secret store, reached from a dev machine, with no prompt and no warning.

Do not count on a failure to save you. Whether such a run actually connects
depends on incidental things like credential resolution order, which is not a
safeguard and can change without notice.

Note what makes this class hard to catch: the dangerous command contains no
dangerous looking token at all. Do not rely on a command "looking risky" to
decide whether to check the environment. `scripts/bash-guard.py` blocks the known
shapes (`check_production_environment`), but it only knows the flags already
discovered, so the rule above is what actually generalizes.

The same reasoning applies to any framework with an environment default: Rails
`RAILS_ENV`, Django `DJANGO_SETTINGS_MODULE`, Node `NODE_ENV`, Spring
`SPRING_PROFILES_ACTIVE`. Name it, then verify it from the app's own startup
output rather than from what you intended.

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
