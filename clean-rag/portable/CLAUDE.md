# ClaudeBoost

Research gated development for Claude Code. Every code edit is researched before
it happens, and search runs over your own indexed projects, not a scraped
knowledge base.

## The research gate (this is the operative rule)

Every edit to a code file is checked against whether `researcher` or `swiper`
has run this session and declared that it covered that file, and nudges toward
research when neither has. Only those two count (`RESEARCH_AGENTS` in
`clean-rag/hooks/research_state.py`); `research-agent` does not. Coverage
persists across follow-up messages and expires after one hour
(`TURN_MAX_AGE_S = 3600`) or when new research lands on top.

`clean-rag/hooks/research-gate.py` exits 0 on every payload shape, by decision:
an unresearched edit is recoverable, so it gets a nudge and an honest audit
trail rather than a refusal. What can't be faked is the record: only Claude
Code can start an agent, and a hook stamps coverage after it finishes. Why the
gate stopped blocking, why spawns are backgrounded, and why good-cop now
reproduces first are recorded in `docs/global-instructions-notes.md`.

When the gate nudges toward research:

1. **Spawn `researcher` and/or `swiper`.** Tell them what you're changing, why,
   and the code you intend to write. Both cover depth and breadth and report
   with sources and a `COVERS:` line naming the files they covered. The audit
   trail checks that scope; nothing refuses the edit, but an uncovered file
   shows up as uncovered. Wait for the report before editing anyway.

   **Every agent spawn runs in the background. You cannot choose otherwise.**
   `run_in_background` is a `Bash` input, not an agent one, so a completion
   arrives as a `TaskNotificationMessage`, not a tool result, and `PostToolUse` on `Task|Agent`
   never fires for a subagent. `SubagentStop` is registered because it is the
   only event that can stamp coverage. There is no other way to spawn.
   The report also names a `MATCH_STRATEGY:`. On `clone-and-patch`, copy the
   verbatim quoted reference as the literal starting point and make only the
   smallest change that fixes the actual issue: no rewrite, restyle, swapped
   library or approach, or structure the reference didn't have. That is a hard
   ceiling on the diff. `pattern-only` allows a real diff; `clone-and-patch`
   does not. There is no `adapt` tier.
2. There is no cheap triage tier, because guessing without reading the code was
   wrong too often. researcher and swiper look first and do real research every
   run; do not build a triviality shortcut into them or any other agent.
3. Trivial work is the human's call, not a model's: `/ps` gives a quick turn
   that skips the gate (and the verifier).

Markdown and non code files are exempt. So are `workspace/`, `state/`, `plans/`,
`docs/`, `.claude/`, and temp dirs.

**Depth versus breadth**, the split both agents use:
- **Depth** is the general engineering question any unrelated project would
  get the same answer to: structure, separation of responsibility,
  testability, the standard approach to this class of problem.
- **Breadth** is the task specific question: how this exact kind of thing gets
  built, what people get wrong, what good looks like, and what's the best way.

research-agent cannot write files, and its Bash is caged to the local clean-rag
server, because it reads untrusted web content and that removes its ability
to act on a prompt injection.

## Verify by running, not by reviewing (the post write half)

Research lowers the odds of a bug; it does not confirm the code is correct.
After writing any non trivial logic:

- **Leave one small runnable check and RUN it** (an assert, a tiny test, or
  the real flow). On failure, feed the actual error back and fix once.
  Execution feedback is the best signal per token (measured 12 to 46 percent
  first try correctness gains) and costs interpreter time, not tokens.
- **Do not self review your own diff in the same context.** Measured evidence
  says intrinsic self critique without external grounding is close to useless
  and sometimes makes things worse. Running code is grounded;
  re reading it is not.
- **A separate context review runs on every real code change** unless the
  human marked the turn `/ps`. It used to be reserved for high stakes surfaces
  (auth, money, SQL, a subprocess, concurrency); now it is the default, because
  green tests and correct code are different questions everywhere. Spawn
  `bad-cop` first, a fresh context critic, NOT the research agent (it reads
  untrusted web, and any agent that wrote or researched the change shares its
  blind spot). bad-cop writes adversarial tests, runs the code, adds logging,
  and reports real failures with execution output. Its last line is one of
  three. Nothing found: it stamps `VERIFIED:` itself, no `good-cop` needed.
  Only Nit severity: it emits `NITS:` (a `Nit:` is non blocking polish, per
  Google's engineering practices); you fix those directly and re-run bad-cop
  for the stamp. It does not stamp a nit only run because `verifier_state.py`
  invalidates a stamp once the file's mtime passes it. On `HANDOFF:` (at
  least one Critical or High finding), spawn `good-cop`, same rules, handed
  bad-cop's findings instead of the requirements alone: it researches the
  correct fix, applies it, reruns bad-cop's new tests plus the existing suite
  until everything is actually green, and stamps `VERIFIED:` in that case.
  After good-cop stamps, spawn bad-cop again for a final adversarial re-check
  on the fix. If bad-cop finds nothing on that re-check, it stamps `VERIFIED:`
  itself and the loop ends. If it finds more issues, spawn good-cop again. The
  loop (bad-cop → good-cop → bad-cop) continues until bad-cop stamps
  `VERIFIED:` itself; that is the only terminal condition, not good-cop
  claiming done.

  **The fix is good-cop's job, not yours.** You orchestrated or wrote the
  change, so you carry its blind spot the way its author does, and the fix you
  reach for first targets the symptom the test caught, not the cause. A one
  line change that turns the suite green is the most dangerous shape. If you
  already patched something, say so, hand good-cop the finding and your
  patch, and tell it in writing not to accept the patch merely because it is
  in the tree, since a fix sitting in the working tree reads as decided.

  **good-cop reproduces each finding before it fixes it, and grounds the fix
  in real practice, a real standard or a real example.** Its own agent
  definition holds the three repro outcomes and the citation format. Require
  the repro evidence and the cited sources in its report. A fix with no cited
  grounding has not been researched, whatever it says: send it back, do not
  ship it. Only execution output overturns execution output,
  never reading alone. Hand it the tradeoffs, not the answer you expect,
  because naming your preferred fix turns the research into agreement.

  Give both cops the requirements, the correctness properties, and the diff,
  never your reasoning for the change, because it biases them into agreeing.
  If researcher or swiper quoted a real GitHub reference (a
  `GITHUB_FILE_READ:` line plus a verbatim snippet), pass the snippet itself
  into their correctness properties. Neither has web fetch access on purpose,
  only search, so this is the only way a real reference reaches their review
  (see MCP servers, and using them safely). `clean-rag/hooks/verifier-gate.py`
  (a Stop hook) asks for a real stamp but never refuses the stop: it exits 0
  always and writes its nudge to stderr, naming the unverified files and who to
  spawn. bad-cop provides the terminal stamp, either directly on a clean
  initial pass or after a final re-check that finds nothing following
  good-cop's fix, writing a `VERIFIED:` line naming the files it covered,
  checked per file the same way the research gate checks `COVERS:`, invalidated
  if a file is edited again after being reviewed (an mtime comparison in
  `clean-rag/hooks/verifier_state.py`). `clean-rag/hooks/high_stakes.py`
  labels which surface it touched so the review points at the sharpest risk.
  A `/ps` turn skips both, the same quick mode escape that skips the research
  gate.

**Both cops review the diff by default, and whatever you name instead.** The
default is the uncommitted working tree, or the branch against its merge base
when the tree is clean. A human `REVIEW SCOPE:` line in any words replaces it
(`entire project`, `anything that touches security`, `anything that touches
OrderService`, `anything around this bug fix`, a bare path). Pass it verbatim;
do not paraphrase it or resolve it to files yourself. bad-cop resolves it with
search and the import graph and prints the resolved file list at the top of
its report, the only place a misread scope gets caught, so read that first.
Copy the `REVIEW SCOPE:` and `RESOLVED:` lines into good-cop's prompt. The
list bounds where a root cause may live, not what good-cop may change; that
stays at what the findings require.

**Check bad-cop and good-cop's actual diff yourself, not their self report.**
Read `git diff` or the changed files, never the agent's JSONL transcript,
which only adds tool noise. Confirm the diff stays in the scope you gave (no
unrelated files, no drive by refactors, no touching config, secrets, or infra
it was never asked about) and holds no destructive or irreversible action. If
it looks wrong, say so and stop; do not silently revert it or trust the
agent's "done" claim.

**Use quick-cop far more than you currently do.** Every "done", "fixed",
"verified", "confirmed" or "no gaps" you say is its trigger, including relaying
a cop's "VERIFIED" or "all tests green". Fire it backgrounded and keep working,
rather than repeating the claim to the user as settled fact.

Trivial one liners need no runnable check. That check is the cheap post write
complement to the gate's pre write research: research narrows the approach,
running the code confirms it.

**Execution proves behaviour in the environment it ran in, and nothing more.**
An env var made mandatory at module load passed every cop and the orchestrator:
two tests spawned a subprocess that inherited the whole environment, and the
value sat in the developer's own `.env`. A static reviewer reading the import
chain caught it in one pass; removing the value failed both tests instantly. So two things, neither optional:

1. **Any test that spawns a subprocess must be run once with a scrubbed or
   explicitly declared environment, not the inherited one**, before anything
   is stamped, because that reproduces the failure mechanically.
2. **Any change that introduces a new hard requirement at module load** (a
   throw, an assert, a required config read) must be traced through its import
   graph to every process that could load it: a subprocess spawn, a worker, a
   cron entry, a CI job. The current shell proves nothing about the others.

A test that passes because of what is ambiently present is an undeclared
dependency; declare what it needs, as clean CI and hermetic builds do.
`scripts/tests/helpers.py` learned this for `cwd`, after a hook test read
whatever was uncommitted in the working tree, but never for the environment.

`clean-rag/hooks/auto-test-gate.py` is the one Stop hook here that genuinely
blocks: when code changed this turn and the project's tests really fail, it
blocks the stop (exit 2) and hands back the failure output to fix from, not to
self review. It is loop safe: it honors `stop_hook_active`, caps at
`MAX_BLOCKS_PER_SESSION = 2`, and allows anything ambiguous (no tests, a
missing runner, an environment problem).

A test failure is objective and cheap to check, so it blocks. A review verdict
is a judgment call, so it nudges and routes through fresh context subagents.
Do not "upgrade" the research or verifier gate to a hard block; see the
recorded decision at the end of this section.

If the logic you changed has no test, writing one is part of verifying it. Then
prove it bites (next paragraph), because an unproven test reliably asserts
current behavior instead of catching a bug, which is worse than no test.

Passing tests do not prove the tests catch bugs. For non trivial logic on a
real bug surface, after tests pass run the mutation check on the changed files:
`POST http://127.0.0.1:8613/mutation-test` with
`{"project_path": "<abs>", "changed_files": [...]}`. It runs the real tool
(`mutmut`, `StrykerJS`, `cargo-mutants`) and returns a kill score; a surviving
mutant is a test that passes on broken code, so tighten it. When edge cases
matter, let a property based library (`Hypothesis`, `fast-check`, `jqwik`)
generate them instead of hand listing a few. Both beat guessing which inputs
to test, which is the weak version the research warned about.

### Every QA session ends with bad-cop judging it. This is not optional

`/qa` or hand QA ends only when **`bad-cop` with `MODE: evidence-judge`**
stamps `FULLY VERIFIED`, never when the session declares itself satisfied,
because a session reads its own evidence as proving what it meant to prove.
Hand it exactly three things: the requirements **verbatim** (the pasted ticket
or the user's words, never a paraphrase), every proof artifact path (logs,
captures, screenshots, the report) and the tool inventory. Give it the
correctness properties and what to attack, never your reasoning, since that
talks a reviewer into agreeing. On `TEST AGAIN`, retest its gaps and send it
back. Then open the artifacts the judge cites; do not take its summary on
trust. Step 5d of `.claude/commands/qa.md` explains eight failures that look
like a pass from inside a session; check them in hand QA too: persistence
claimed from a screenshot, results only in prose, an unresolved build id,
runs of different code compared, an unopened screenshot, a timing window too
short for a deployed backend, a minified bundle grepped by identifier, and a
marker checked in only part of the diff. `quick-cop` stamps nothing and never
substitutes for bad-cop on a full QA session.

### Recorded decision: no blocking external model reviewer on Stop

Declined 2026-08-18: do not build a Stop hook that has a separate model review
`git diff HEAD` and blocks the turn on a FAIL verdict, because a hard blocking
reviewer was already built on this surface and reverted twice. The full
reasons and references are in `docs/global-instructions-notes.md`. For security
specific review, adopt the whole `security-guidance` plugin rather than writing
a hook. The notes also name the reference loop guard and two Stop hook
gotchas: the payload has no changed files list, and a child `claude -p` needs
`CLAUDECODE` unset.

## Debugging, testing and QA

When a bug does not yield, the failure mode is applying one technique harder.
Two or three iterations with no new information means the technique is wrong,
not that you need more logging. Invoke the **`debugging-methodology`** skill
and pick a different one by name from its symptom table. The skill also holds
the per stack recipes no MCP server reaches (React Native, .NET, Python) and
the debugger tools; reach for a debugger over print statements. A tool missing
at runtime means its server was never registered, so run the installer; every
server comes from one table there (see MCP servers, and using them safely).

**Databases are read only.** Never execute against a live database or automate
SSMS or any equivalent GUI client, because a wrong statement against real data
is not recoverable by a retry. Read the schema from the project's own
artifacts (EF Core `DbContext` and `Migrations/`, `models.py`, Alembic
versions, `schema.sql`), reason about the query, and hand it to the human to run.

`/qa` runs the full session: inventory, a risk ranked test plan, execution with
evidence. `/debug` is the focused single bug path. Both enumerate the debugging
tools already, and both point back at this same skill.

## UI / Frontend Work

For frontend files (`.tsx`, `.jsx`, `.html`, `.css`, `.scss`, `.vue`,
`.svelte`), invoke the `frontend-design` skill before any design decision. Run
its two-pass process: a compact token system (palette, typefaces, layout
concept, signature element), then a self-critique against the brief. Never
skip to code without that brief-grounding pass.

After any UI change, invoke the `eyes` skill to screenshot and verify visually
before calling it done. Propose changes with pixel-precise numbers, confirm
with the user before applying, and verify with a before/after screenshot.

## clean-rag (the search backend, port 8613)

Search runs over projects you've indexed, plus live web search. There is no
scraped topic knowledge base.

- `POST http://127.0.0.1:8613/web-search` is DuckDuckGo, source ranked (GitHub
  and StackOverflow first, content farms last), sanitized against hidden
  characters. Survey with snippets (see Token Efficiency).
- Index a project once with `/index-project`. It reindexes after every edit,
  plus a full sweep every 10 minutes for outside changes. The server runs
  headed so you can watch it. If it is down, run `/clean-rag-server start`.

## Plugins

Installed from `PLUGINS` in `scripts/setup.py`, mirrored in
`clean-rag/install.py` for the same standalone reason as `MCP_SERVERS`, so add
each one to BOTH tables. A row needs `marketplace` (the repo) and `name` (the
`plugin@marketplace` id); the marketplace alone installs nothing. The tuning
detail and how each setting was verified are in
`docs/global-instructions-notes.md`.

- **ponytail** (`DietrichGebert/ponytail`, MIT) stops the agent over-building
  by walking a ladder before it writes code. Validation, error handling,
  security and accessibility are never on its chopping block. Its two lifecycle hooks are Node,
  so `node` must be on PATH or they fail on every prompt.
  **It pulls against this file, on purpose.** Its first rung is "skip it". The
  ladder decides what to build and this file decides how to check it, so
  research and bad-cop still run, usually on less code. If a turn feels
  ceremonious for a one line change, use `/ps` rather than switching either off.
- **pipe-down** (`hoo29/claude-pipe-down`, MIT) refuses an Edit or Write that
  adds an over-long or low value comment. Being a `PreToolUse` hook is the
  point: `comment-humanness-check.py` is `PostToolUse`, so its nudge lands
  after the comment is on disk and gets ignored (see Plain writing).
  `PIPE_DOWN_MAX_WORDS` is 20. `PIPE_DOWN_LLM` is `0` because it ships **on**,
  spawning a `claude -p` Haiku subprocess per write, a real latency cost on
  every edit; turn it on only if the regex rules prove too blunt.

### Calling it correctly

**8613 is the only server.** The old 8612 server is deleted. Any mention of
`8612`, `/context`, `/index` or a `scope=` parameter is stale, and following it
gets a quiet connection refused. The whole contract is one route:

```
POST http://127.0.0.1:8613/search
{"query":"how does auth work","sources":["project:C:/abs/path"],"mode":"both","limit":8}
```

- `sources`, not `scope`: a list of `project:<absolute path>`. Several are fine;
  each is queried with the embedding model its own index was built with.
- `mode: "both"` on every code search runs vector similarity and import graph
  traversal together, because they surface different files and one without
  the other leaves a gap. Graph results carry `relation` (imports, inherits,
  implements, calls) and `seed_file`.
- A source works only for a registered project; an unindexed directory returns
  nothing, silently. Check `GET /status`.
- `stale_projects` with `served: false` means the index exists but was refused,
  and its reason field says why. Zero results plus that field is a broken
  index, not an empty codebase, so read it before concluding the code is not
  there.

Other routes: `/index-project`, `/reindex-file`, `/status`, `/projects`,
`/web-search`, `/github-search`, `/github-file`, `/stackoverflow-search`,
`/run-tests`, `/mutation-test`, `/security-scan`. `clean-rag/CLAUDE.md` has the
full table, and `clean-rag/tests/test_skill_rag_routes.py` fails if any skill
names a route the server does not serve, so the list cannot drift silently.

When spawning an agent, hand it a real search line against a real indexed
project, never a server that no longer exists.

## MCP servers, and using them safely
The installer registers these from `MCP_SERVERS` in `scripts/setup.py`, mirrored
in `clean-rag/install.py`; add a server to BOTH tables, or
`tests/test_mcp_server_registration.py` fails. All are free. **They act as
you**, with your PAT, Atlassian rights and filesystem, and most enable write
tools by default. The control is a narrowly scoped (read only) credential, never
the server's behaviour or a README promise. Per server:
- **ast-grep**: structural AST search for codemods, local, 4 tools. The MCP
  wrapper is experimental, so check a rewrite's output.
- **context7**: version pinned library docs. Queries go to Upstash, so never
  put code or anything internal in one.
- **semgrep**: local SAST. Do NOT set `SEMGREP_APP_TOKEN` unless you actually
  want findings shipped to Semgrep's cloud; without it nothing leaves the
  machine.
- **osv**: citable CVE and advisory IDs from Google's public database. Read
  only, no credential.
- **socket**: scores a package (license, malware, maintenance) before swiper
  takes it. `depscore` is Socket's own composite, so triage, not a citation.
  The free tier has a monthly scan cap.
- **arxiv**: paper sections, because `researcher` has WebSearch but no WebFetch
  and clean-rag has no general fetch route. Scope prompts to a section; whole papers
  flood context.
- **antv-chart**: mind maps, flowcharts, network and fishbone diagrams to PNG
  by default via an Ant Group hosted endpoint, so **diagram data leaves the machine**. Set
  `VIS_REQUEST_SERVER` to self host before drawing internal systems.
- **jupyter**: re-runnable `.ipynb` evidence. It executes code, so treat it as
  an execution surface. Gated on `JUPYTER_TOKEN`; skipped without Jupyter.
- **mobile-mcp**: drives a real app (install, tap, type, screenshot, device
  logs, crashes); Android via `adb` on any OS, iOS needs a Mac with Xcode. It
  can uninstall apps, replace the clipboard and override GPS, so use an
  emulator or test device, never a personal phone. Its row sets
  `MOBILEMCP_DISABLE_TELEMETRY=1` in its `env`, as telemetry is on by default.
- **github**: PRs, issues and Actions; it can merge, push and close for real, so
  use a fine grained PAT scoped to the needed repos, never a classic token with
  full `repo`. Secret scanning needs paid Secret Protection on private repos, so
  do not count on it. The hosted endpoint needs Copilot enrolment (Free is $0).
- **atlassian**: live Jira and Confluence writes as your user, which colleagues
  see. Confirm before creating or editing anything, the same as any outward
  facing action.
**Credentials.** `GITHUB_MCP_TOKEN` and `JUPYTER_TOKEN` are passed as `${VAR}`
placeholders that Claude Code expands from **its own process environment** at
launch, so set them in the shell that starts Claude Code or in the `env` block
of `~/.claude/settings.json` (both confirmed by reading the received header).
**Not `clean-rag/.env`.** Only clean-rag's server reads it, so the failure is
quiet: registration succeeds and the literal `${GITHUB_MCP_TOKEN}` is sent as
the bearer token. `claude mcp list` prints `Missing environment variables: ...`,
and the installer refuses to register a server whose credential is unset.
`GITHUB_MCP_TOKEN` is deliberately NOT `GITHUB_TOKEN` (clean-rag's read only
search token), because sharing it would break the server or widen search. An
unset credential skips that server with a warning, never failing the install.
Never resolve a credential into the payload; the placeholder keeps it out of
`~/.claude.json`.
**The injection boundary.** `bad-cop` and `good-cop` get no WebFetch and no
network fetching server (context7, arxiv, socket), because a reviewer reading
untrusted content can be talked out of a finding. Those go only to `researcher`
and `swiper`; `test_reviewers_get_no_fetch_shaped_tools` enforces it. Giving the
cops local readers (semgrep, ast-grep) is **not wired**: it needs real tool
names from a running server. **Tool names are enumerated literally, never
wildcarded**, because Claude Code silently drops unknown names and
`mcp__<server>__*` (bad-cop once had no coverage data for months this way).
`tests/test_mcp_server_registration.py` confirms the servers behind them exist.

## Decision Flow
**Simple task?** Just do it, no workspace. **Complex task?** (ticket attached,
multiple agents or sessions, or "plan this"): 1. create `workspace/[task-id]/`
and announce it in one line; 2. sweep then verify across testing, docs,
security, architecture, performance, review and clarity, proving every flag
from actual code and dropping any you cannot cite by line; 3. spawn the right agent(s).

## Agent Spawning
Spawn agents when they add value: parallelism, isolation or deep
specialization. Do the work directly when they don't; a one line fix doesn't
need an agent. The six in Model Routing spawn as needed, not on every task;
any other shipped agent belongs to the skill that spawns it.

### Never delete scratchpad files. Leave them
Scratch work goes in the session scratchpad directory, and it stays there.
Never `rm` or tidy scratchpad files or backups: the directory is disposable and
every `rm` costs a permission prompt. Say a file is no longer needed instead.

### What the rm rules do, and why they are shaped that way
Non recursive `rm` is allowed with no prompt, recursive `rm` asks, and sixteen
catastrophic shapes such as `rm -rf /` are denied, because deleting a tree is
where nearly all of the danger lives. Never replace them with one broad
`Bash(rm **)` in `ask`. The full rule list, and why no narrower rule can carve
out a safe directory, are in `docs/global-instructions-notes.md`.

### Model Routing
- **Opus**: good-cop.
- **Sonnet**: bad-cop, quick-cop, research-agent, researcher, swiper.
That is the roster, 6 agents; a skill may ship a helper spawned only from it.
A name with no agent file silently becomes a generic agent, with no error.

### Starting a new build or feature
For a new build or feature, run `/start`, not research-agent directly. It runs
`researcher` (structure from clean-rag's index and graph, plus the engineering
standard), then `swiper` on those findings (what to swipe from the project,
stdlib, a dependency, GitHub or StackOverflow; it never writes to the project),
then consults the user with options before anything is written. Send codebase
understanding tasks to `researcher`, not an ad hoc subagent, because it has
clean-rag's indexed vector and graph databases.

### Parallel Limits
- Context below 50%: up to 3 agents.
- Context 50 to 75%: up to 2 agents.
- Context above 75%: 1 agent, sequential.

### Fan-out mode

"Go into fast mode", "use fast mode", or "go quickly" turn on fan-out mode.

**It is not Anthropic's `/fast`.** That toggle speeds up one model's output and
bills at a premium. This is a different thing on the same model: more agents
working at once. The words collide, so the first time it comes up in a session,
say which one you took it to mean.

**What changes: how the work is cut.** Work for `researcher`, `swiper`,
`bad-cop` and `good-cop` gets decomposed into independent slices, and those
slices go out as multiple Agent tool calls in a single message so they run
concurrently. That is Claude Code's own documented mechanic: "When asking
Claude to run agents 'in parallel', it will send a single message with multiple
Agent tool calls, launching all of them simultaneously. You should be explicit
about what should run in parallel vs. what must be sequential."

**What does not change: the Parallel Limits above.** They still bind in fan-out
mode. Three concurrent agents below 50% context, two from 50 to 75%, one above.
Fan-out changes the decomposition, not the ceiling. More agents than that is a
documented failure rather than a speedup: Anthropic's own multi-agent research
writeup names "spawning excessive subagents (50+) for simple queries" as a real
cost, alongside parallel workers duplicating each other's work when none of
them knows what the others are doing.

**Slice by concern, never by file.** This is the part that goes wrong under
time pressure. `researcher` and `swiper` decompose safely along independent
aspects, because one aspect's answer does not depend on another's. A reviewer
does not decompose that way. Split `bad-cop` and `good-cop` by dimension
(correctness, security, concurrency, error handling, test quality) and hand
every parallel instance the **full** diff. A bad-cop that sees only file B
cannot see that a signature change in file A broke it. Cross file bugs are
invisible to a file sliced reviewer, which is why `.claude/commands/audit.md`
already fans out by dimension and passes each auditor the entire input verbatim.
Copy that shape, including how it handles the count: pick the dimensions the
diff actually earns, then run them in waves the current tier allows. Five
dimensions under a three agent ceiling is two waves, not one overfull message.
`audit.md` selects 3 to 6 dimensions and then says "Spawn one agent per
selected dimension. Wait for each batch to complete before starting the next."
The ceiling is on how many run at once, never on how many dimensions the diff
deserves.

**Sequential stays sequential.** `swiper` still runs after `researcher`,
because it needs those findings to avoid recommending a swipe for something the
project already has. `good-cop` still runs after `bad-cop`, and the closing
`bad-cop` re-check still runs after `good-cop`. Fan-out widens each stage. It
does not collapse the pipeline into one round.

**No lock file is needed, and do not repurpose the one that exists.** The two
gates this pipeline runs on, `clean-rag/hooks/research-gate.py` and
`clean-rag/hooks/verifier-gate.py`, return 0 on every path and only write a
nudge to stderr, so concurrent agents never serialize on them. That is what
makes fan-out safe here. `state/audit-in-progress.json` is a different thing
and is still load-bearing: `scripts/skill-verify-gate.py`, a registered
PreToolUse hook on the Skill tool, exits 2 for an action skill while
`needs-verification.json` is pending unless that flag is set, and three more
registered hooks read it: `scripts/verify-gate-cmd.py` (PostToolUse on Task),
`scripts/context-nudge.py` (PostToolUse on everything) and
`scripts/rules-compliance-check.py` (Stop). `scripts/action-gate.py` reads the
flag too, but it is registered nowhere. Its hook registration was removed from
the installer at the user's own request, recorded in
`clean-rag/state/proof-log.jsonl` on 2026-07-06, so that branch exists and
never runs. Do not register it again to make the list tidy.
`/audit` sets it at its Phase 0 and clears it at Phase 5 precisely because its
own batch would otherwise be gated agent by agent.

Fan-out mode does not set it. One flag with two writers means whichever batch
finishes first clears it out from under the other, and a batch that dies
mid-run leaves all four registered checks suppressed for the rest of the
session, on disk, with nothing to notice. If fan-out ever trips one of them,
fix that gate, do not switch it off.

## Verify Gate (anti hallucination)
Everywhere (reviews, planning, bug diagnosis, security audits, test planning):
prove every finding from actual code before acting, citing file and line. "No
issues found" is always valid; the goal is real findings, not any finding.

## Hard Rules (non negotiable)

### Never start an app without naming the environment
This is the most dangerous routine command, because the damage comes from what
you *omit*, and nothing in it looks risky. Name the environment and never skip
the launch profile:
```
ASPNETCORE_ENVIRONMENT=Development ASPNETCORE_URLS="https://localhost:PORT" \
  dotnet run --project "<path to csproj>"
```
Confirm `Hosting environment: Development` in the startup log before any
browser or test; anything else is a stop. ASP.NET Core defaults to
**Production** when `ASPNETCORE_ENVIRONMENT` is unset, and
`dotnet run --no-launch-profile` skips `launchSettings.json`, so config binds
`appsettings.json`, not `appsettings.Development.json`: the production database
and secret store, silently. A connection failure is no safeguard.
`scripts/bash-guard.py` (`check_production_environment`) only knows flags
already found, so this rule is what generalizes. It applies to Rails
`RAILS_ENV`, Django `DJANGO_SETTINGS_MODULE`, Node `NODE_ENV` and Spring
`SPRING_PROFILES_ACTIVE` too: name it, then verify it from startup output.

### Plain writing (enforced by output style, not by hope)
Everything you write (chat, comments, PR descriptions, docs) is plain and
short: one idea per sentence, point first, no throat clearing, idiom or filler
intensifiers. Fewer words, not softer claims; still say plainly when something
is uncertain, failed, unverified or skipped. It lives in the output style
`~/.claude/output-styles/plain.md` (`"outputStyle": "Plain"` in
`~/.claude/settings.json`), because that rewrites the system prompt while
CLAUDE.md and memory are appended as a user message and drift. A rule the
human keeps restating is a rule in the wrong layer, so tone rules go there.
Two narrower layers run alongside it and are not substitutes.
`human-voice-guard.py` (Stop hook) bans 39 AI tell words and filler phrases in
chat prose only. `comment-humanness-check.py` (PostToolUse) blocks (exit 2) on
any dash in a code comment and nudges on five older patterns needing three or
more hits, plus two from 2026-09-18 that fire on a single comment:
- **comment-length**: a comment body over 20 words, so it is not one line.
- **comment-narration**: the comment's opening verb restates the line it sits
  on. `tests/test_comment_humanness_check.py` pins examples of it and the
  false positive boundary for comments that genuinely explain something.
Both exempt comments giving a reason (`because`, `so that`, `must`, `race`,
`security`, `bug`, `only`, `unless`, rest of `_EXPLANATORY_RE`), because a why
comment earns its words however it opens. Why this was built rather than
installed is in `docs/global-instructions-notes.md`.

### Swipe before you build, including for your own tooling
For "how do I make Claude do X", first check whether the harness or community
already does it (output styles, hooks, settings fields). Hand rolling a solved
problem is the failure this file exists to stop, in tooling and config too.

### No machine specific paths in anything committed
No absolute path, home directory or username in any committed file, comments
and docs included. Derive it: `Path(__file__).resolve().parents[N]` in Python,
`$(git rev-parse --show-toplevel)` or `${CLAUDEBOOST_HOME}` in shell, and a
placeholder like `C:/Users/<user>` in prose. It failed twice here, leaking home
directories and a client's hostnames to a public repo, because a hardcoded path
always works on the machine that wrote it. Ask "whose machine does this
reveal", not "does it work here". `tests/test_no_machine_specific_paths.py`
scans only tracked files with known suffixes, so it is a net, not a substitute.
Exception: a one off Bash command is not committed, so use an absolute path or
`${BRACE}` form there, because Claude Code's simple_expansion scanner prompts
on a bare `$VAR` regardless of the allow list. The moment the same path is
written into a file, the rule above applies again.

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
Do it right the first time; rework costs more than ceremony. Route by weight:
full ceremony (verify gate plus evaluator) for reviewer, security and
performance, standard for the rest, lightweight for explore, research and docs.
Always spawn an evaluator to verify findings, never self verify, because a
fresh context catches hallucinations that same context confirmation misses.
Web research is cheap if you survey snippets and fetch sparingly, since the
research agent's cost is mostly full page fetches, not searches.

## OpenCode
`clean-rag/opencode/` ports the same MCP search tools, the two research agents
as OpenCode subagents, and a research gate plugin; install with
`clean-rag/opencode/install.py`. The gate binds the primary agent; a known
OpenCode bug means subagent edits may bypass it until upstream fixes it.

## Browser Testing Safety
Playwright and browser automation reach only local and named test or dev hosts:
- localhost, 127.0.0.1, 0.0.0.0, `::1`, and `*.local` / `*.test`
- hosts in `.claude/browser-targets.local.json`, gitignored because they are
  private; `.claude/browser-targets.example.json` documents its shape and
  rules. `scripts/bash-guard.py` reads the same file, so they cannot drift.
  With no file present, only the line above is reachable.
Never production or any host not confirmed as test or dev. `dev` in a name
proves nothing, and a shared dev environment can still hold real data. A lower
environment restored from a production snapshot is production data, so get
approval before any write there. Read only browsing and screenshots are fine.
Never browse a control plane or management dashboard. Drive SSO only to the
prompt and hand over; never enter credentials or approve MFA. If unsure about a
URL, ask first. Default to a headed browser.
