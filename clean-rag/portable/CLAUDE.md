# ClaudeBoost

Research gated development for Claude Code. Every code edit is researched before
it happens, and search runs over your own indexed projects, not scraped
knowledge base.

## The research gate (this is the operative rule)

Every edit to code file is checked against whether `researcher`  `swiper`
has run this session and declared that it covered that file, and nudges toward
research when neither has. Those two are only agents gate counts
(`RESEARCH_AGENTS` in `clean-rag/hooks/research_state.py`); `research-agent`
does not satisfy it. Coverage persists across follow-up messages and expires
after one hour (`TURN_MAX_AGE_S = 3600`) or when new research lands on top.

 gate used to block edit. It doesn't now. `clean-rag/hooks/research-gate.py`
exits 0 on every payload shape, by decision: unresearched edit is
recoverable, so it gets nudge and honest audit trail rather than
refusal. first block attempt also predated session scoping above,
coverage was wiped by every follow-up message and gate fired on files
swiper had covered.

What can't be faked is record, not refusal. Only Claude Code can start
 agent, and PostToolUse hook stamps coverage after agent finishes,
so "I researched it" is never what gets written down.

When gate nudges toward research:

1. **Spawn `researcher` and/or `swiper`** (Sonnet). Tell them what you're
   changing, why, and code you intend to write. Both cover depth and breadth
   and report with sources `COVERS:` line naming files they covered.
   That scope is what audit trail
   checks; nothing refuses edit, but uncovered file shows up as uncovered.
   Wait for it before editing anyway; that's still point.

   **Every agent spawn runs in background. You cannot choose otherwise.**
   This paragraph used to say "spawn it in foreground
   (`run_in_background: false`), never backgrounded". That instruction asked
   for something agent tool does not offer. Its inputs are `description`
   `isolation` `model` `prompt`  `subagent_type`and nothing else;
   `run_in_background` is `Bash` input, not agent one. Verified
   2026-09-18 by reading live tool schema.

    consequence is structural, not mistake anyone made. completion
   arrives as `TaskNotificationMessage` rather than tool result,
   `PostToolUse` on `Task|Agent` never fires for subagent and can never
   stamp coverage. `SubagentStop` is only event that can, and it is
   registered for that reason. Do not try to work around this by spawning
   differently; there is no other way to spawn.
   Its report also names `MATCH_STRATEGY:`. If it's `clone-and-patch`copy
   verbatim quoted reference as literal starting point and make only
   smallest set of changes that fixes actual issue — no rewrite, no restyle,
   no swapped libraries or approaches, no added structure reference didn't
   have. That's hard ceiling on diff, not suggestion. `pattern-only`
   allows real diff; `clone-and-patch` does not. There is no `adapt` tier.
2. There is no cheap triage tier anymore. old one decided whether change
   needed research WITHOUT reading code, and that blind guess was wrong often
   enough to remove. researcher and swiper look first, so their judgment is
   grounded. They do real research every time they run; do not build
   triviality shortcut into them or any other agent.
3. Genuinely trivial work that needs no research is human's call, not
   model's. Run `/ps` for quick turn that skips gate (and verifier) when
   you already know change is trivial.

Markdown and non code files are exempt. So are `workspace/` `state/` `plans/`
`docs/` `.claude/`and temp dirs.

**Depth versus breadth**, split both agents use:
- **Depth** is general engineering question, one unrelated project
  would get same answer to. Structure, separation of responsibility,
  testability, standard approach to this class of problem.
- **Breadth** is task specific question. How this exact kind of thing gets
  built, what people get wrong with it, what good looks like. "What's best
  way to build this" is breadth too, not pitfalls.

research-agent cannot write files, and its Bash is caged to local clean-rag
server. It reads untrusted web content, so removing its ability to act is real
defense against prompt injection.

## Verify by running, not by reviewing (the post write half)

Research before edit lowers odds of bug. It does not confirm code
you wrote is correct. To know, after writing any non trivial logic:

- **Leave one small runnable check and RUN it.** assert, tiny test,
  drive real flow. If it fails, feed actual error back and fix once.
  Execution feedback is highest quality per token signal there is (measured
  12 to 46 percent first try correctness gains), and it costs interpreter time,
  not tokens, except for rare fix.
- **Do not self review your own diff in same context.** Measured evidence
  says intrinsic self critique without external grounding is close to useless
  and sometimes makes things worse. Running code is grounded. Re reading it
  is not.
- **A real separate context review runs on every real code change**, unless
  human marked turn `/ps`. It used to be reserved for high stakes surfaces
  (auth, money, SQL, subprocess, concurrency); now it's default after any
  code change, because green tests and correct code are different questions
  everywhere, not only there. Spawn `bad-cop` first, fresh context critic, NOT
   research agent (that one reads untrusted web and stays capability stripped,
  and any agent that wrote or researched change inherits its own blind spot on
  review). bad-cop writes adversarial tests, runs code, adds logging,
  reports real failures it finds, with actual execution output attached.
  Its last line says what happens next, and there are three of them. If it
  finds nothing, it stamps `VERIFIED:` itself: no separate `good-cop` run
  needed to re-confirm clean adversarial pass. If everything it found is
  Nit severity, it emits `NITS:` instead and good-cop is still not spawned:
   nit is non blocking by definition (Google's engineering practices coined
   `Nit:` prefix for exactly this, polish author may ignore), so you
  apply those fixes directly and re-run bad-cop for re-check that earns
   stamp. bad-cop deliberately does not stamp on nit only run, because
  `verifier_state.py` invalidates stamp once file's mtime advances
  past it, so stamp written before fixes land erases itself. Only when
  it emits `HANDOFF:`meaning at least one finding is Critical or High, do
  you spawn `good-cop` next, same rules, handed bad-cop's findings instead
  of requirements alone: it researches correct fix,
  applies it, and reruns bad-cop's new tests plus existing suite until
  everything is green, and it is one that stamps `VERIFIED:` in
  that case. After good-cop stamps, spawn bad-cop again for final
  adversarial re-check on fix. If bad-cop finds nothing on that re-check,
  it stamps `VERIFIED:` itself and loop ends. If it finds more issues,
  spawn good-cop again. loop (bad-cop → good-cop → bad-cop) continues
  until bad-cop stamps `VERIFIED:` itself — that is only terminal
  condition, not good-cop claiming done.

  **The fix is good-cop's job, not yours.** When bad-cop reports something
  real, hand it to good-cop. Fixing it yourself instead is specific failure
  this paragraph exists to stop, and it has happened. Two reasons, both
  same ones that put bad-cop in fresh context to begin with. You orchestrated
  or wrote change, so you carry its blind spot exactly way its author
  does. And fix you reach for first is symptom bad-cop's test caught,
  because symptom is visible part and cause usually is not. one
  line change that turns suite green is most dangerous shape of this,
  since afterwards nothing about it looks like shortcut. If you already
  patched something before thinking, do not quietly keep it: say so, hand
  good-cop both finding and your interim patch, and tell it in writing not
  to accept that patch merely because it is already in tree. fix sitting
  in working tree reads as already decided, and that is precisely bias
   fresh context is there to resist.

  **good-cop reproduces finding before it fixes it.** Its opening used to say
   opposite, that its job was not to re-litigate whether bad-cop's findings
  were real, while passage near end of same file told it to disprove
  false positives. instruction at top of file outweighs one at
  bottom, so contradiction resolved wrong way. It now runs each repro
  first and reports one of three outcomes: it reproduces and gets fixed at
  root cause, it does not reproduce and is recorded as false positive with
  command and output that show it, or it reproduces for different reason than
  bad-cop stated and real cause gets fixed with difference named.
  Require that evidence in its report. What it may never do is dismiss finding
  on reading alone: only execution output overturns execution output.

  **good-cop researches before it fixes, and cites what it found.** Its own
  definition requires grounding fix in real practice, real standard
  real example ahead of its own opinion, for same reason research gate
  exists on write side: ungrounded fix is guess that happens to
  compile. Require sources in its report. fix that arrives with no cited
  grounding has not been researched whatever it says, and right response is
  to send it back, not to ship it. Hand it tradeoffs to weigh rather than
   answer you expect, because naming your preferred fix in prompt turns
   research into agreement with you.

  Give both of them
  requirements, correctness properties, and diff, never your reasoning
  for change, since that reasoning is exactly what biases reviewer into
  agreeing. If researcher or swiper grounded build in real GitHub reference (a
  `GITHUB_FILE_READ:` line plus verbatim snippet it quoted), pass that
  snippet forward into their correctness properties too, not its
  description. Neither has web fetch access on purpose, only search, so this is
   only way real reference reaches their review; do not give either its own
  GitHub/web fetch access, that would duplicate one injection-exposed agent
  this codebase deliberately keeps to one. `clean-rag/hooks/verifier-gate.py`
  (a Stop hook) asks for real stamp but never refuses stop: it exits 0
  always and writes its nudge to stderr, naming unverified files and who to
  spawn. bad-cop provides terminal stamp — either directly on clean
  initial pass, or after final re-check that finds nothing following
  good-cop's fix — writing `VERIFIED:` line naming files it covered,
  checked per file same way research gate checks `COVERS:`invalidated
  if file is edited again after being reviewed (an mtime comparison in
  `clean-rag/hooks/verifier_state.py`). `clean-rag/hooks/high_stakes.py`
  labels which surface it touched so review points at sharpest risk.
  `/ps` turn skips both, same quick mode escape that skips research gate.

**Both cops review diff by default, and whatever you name instead.** With
no review scope given, bad-cop resolves diff itself: uncommitted working
tree, or branch against its merge base when tree is clean. Anything
human names on `REVIEW SCOPE:` line replaces that, in their own words, with no
fixed vocabulary. `entire project` `anything that touches security` `anything
that touches OrderService`, `anything around this bug fix`, a bare path, all
valid. Pass their sentence through verbatim; do not paraphrase it and do not
resolve it to files yourself. bad-cop resolves it with search and import
graph, then prints resolved file list at top of its report, which is
only place misread scope gets caught, so read that block first. Copy same
`REVIEW SCOPE:`  `RESOLVED:` lines into good-cop's prompt. Both work same
surface. That list bounds where root cause is allowed to live; it does not
widen what good-cop may change, which stays at what findings require.

**Check bad-cop and good-cop's actual diff yourself, not their self report.**
After either stamps or reports done, read real result: `git diff` on
files they touched, or Read changed files directly. Confirm two things
concretely: diff stays inside scope you gave that agent (no unrelated
files, no drive by refactors, no touching config, secrets, or infra it was
never asked about), and nothing in it is destructive or irreversible action.
Do this by reading resulting files `git diff`never by opening
agent's own JSONL transcript to watch its reasoning; that pulls tool noise
into your context for no reason and is not what this check is for. If
diff looks wrong, say so and stop, do not silently revert it yourself and do
not trust agent's own "done" claim.

**Use quick-cop far more than you currently do.** Every time you say
something is done, fixed, verified, confirmed, or has no gaps, that sentence
is exactly trigger quick-cop exists for (see its own agent description).
Dispatch it liberally and backgrounded, meaning fire it and keep working,
do not block waiting on it. This includes your own claims after bad-cop
good-cop run: their self reported "VERIFIED" or "all tests green" is still
claim, so hand it to quick-cop to independently confirm rather than repeating
it to user as settled fact.

Trivial one liners need no check. This is cheap post write complement to
gate's pre write research: research narrows approach, running code
confirms it.

**Execution proves behaviour in environment it ran in, and nothing more.**
That is limit of rule above, and it has already cost real bug.
change made env var mandatory at module load. Two tests spawned subprocess
that inherited whole environment and only overrode one named variable.
value happened to sit in developer's own `.env`so bad-cop, good-cop,
second bad-cop re-check and orchestrator all ran suite and all passed.
 static reviewer reading import chain caught it in one pass, because it
did not care what was in that machine's environment. Removing value from
`.env` afterwards failed both tests instantly.

So two things, neither optional:

1. **Any test that spawns subprocess must be run once with scrubbed
   explicitly declared environment, not inherited one**, before anything is
   stamped. This is check that mechanically reproduces failure with no
   reasoning required, which is why it belongs here rather than in reviewer's
   judgement.
2. **Any change that introduces new hard requirement at module load** (a
   throw, assert, required config read) must be traced through its import
   graph to every process that could load it: subprocess spawn, worker,
   cron entry, CI job. Running it in current shell proves nothing about
    others.

 general form: test that passes because of what is ambiently present is
not passing test, it is undeclared dependency. Established practice is to
declare what test needs rather than inherit it, which is why CI runs in clean
containers and why hermetic builds exist. `scripts/tests/helpers.py` already
learned this once for `cwd`after hook test read whatever happened to be
uncommitted in working tree; lesson was never generalised to
environment.

This verify step is partly enforced, `clean-rag/hooks/auto-test-gate.py` is
 one Stop hook in this family that genuinely blocks. It runs project's
tests when code changed this turn, and if they fail it blocks stop
(exit 2) and hands you back real failure output to fix from. It is loop
safe: it honors `stop_hook_active`caps at `MAX_BLOCKS_PER_SESSION = 2`
allows on anything ambiguous (no tests, missing runner, environment
problem). So on project with tests you will often get actual assertion
diff or stack trace pushed back at you automatically. Fix from that, do not
self review.

Note split, because it is deliberate and easy to misread. test failure is
objective and cheap to check, so it blocks. review verdict is judgment call,
so it nudges and routes through fresh context subagents instead. Do not
"upgrade" research or verifier gate to hard block; see recorded
decision at end of this section.

If logic you changed has no test at all, writing one IS part of verifying it,
not optional extra. Do not skip verification because none exists, that is
gap tests were supposed to close. Write missing test, then prove it bites
(next paragraph), because test written without that proof reliably asserts
current behavior instead of catching bug, which is worse than no test.

Passing tests are necessary, not proof tests catch bugs. For non trivial logic
on real bug surface, after tests pass run mutation check on
files you changed: `POST http://127.0.0.1:8613/mutation-test` with
`{"project_path": "<abs>", "changed_files": [...]}`. It runs language's real
mutation tool (`mutmut` `StrykerJS` `cargo-mutants`) and returns kill score;
surviving mutant is test that would pass on broken code, so tighten it. When
edge cases matter, let language's property based library (`Hypothesis`
`fast-check` `jqwik`) generate them instead of hand listing few. Both beat
guessing which inputs to test, which is weak version research warned about.

### Every QA session ends with bad-cop judging it. This is not optional

Running `/qa`or doing any QA by hand, is not finished when tests are done.
It is finished when fresh context has judged evidence. QA session cannot
audit its own artifacts for same reason you do not self review your own
diff: it knows what it meant to prove, so it reads its own evidence as proving
it.

When testing is done, spawn **`bad-cop` with `MODE: evidence-judge`**
hand it exactly three things:

1.  requirements **verbatim**, pasted ticket or user's actual words,
   never your paraphrase of goal.
2. Every proof artifact path: logs, captures, screenshots, report itself.
3.  tool inventory QA session had available.

Give it correctness properties and what to attack. Never give it your
reasoning about why you think QA was sufficient, since that reasoning is
what talks reviewer into agreeing.

It stamps `FULLY VERIFIED`  `TEST AGAIN` with specific gaps. On `TEST AGAIN`
you retest those gaps and send it back. **The loop ends only when bad-cop stamps
`FULLY VERIFIED`never when QA session declares itself satisfied.**

Then check bad-cop's own claims same way you check good-cop's: open
artifacts it cites, do not take its summary on trust.

This catches class of failure green results never surface, because every one
of these looks like pass from inside session:

- **Persistence claimed from screenshot** with no server read-back. value
  rendered in form is not value in database.
- **Results that exist only as prose** in report, with no capture on disk.
  If it is not in artifact it was not measured, whatever table says.
- **A build identifier quoted without resolving it.** Confirm commit is
  real object in repo. dashboard's "version" field is often internal
  build id and not commit at all.
- **Comparing two runs that tested different code.** Before attributing
  behaviour change to environment or to test technique, diff commits.
  This is one that most often produces confident wrong conclusion.
- **A blank or mistargeted screenshot** passing as evidence because nobody
  opened it. Open every image you save.
- **Measurement windows too short for deployed backend.** response under
  100ms locally can take ten seconds deployed, so window sized for local turns
   success into phantom failure or unresolved null.
- **Verifying fix in minified bundle by grepping identifier names.** Local
  names are renamed and comments stripped, so grep reads zero for fix that
  is present. Grep object property, which survives, then read code around
  it.
- **A marker check that covers only half change.** Confirm marker you
  chose appears in every file diff touched.

`quick-cop` is cheap non blocking version for single "it is done" claim.
It stamps nothing and never substitutes for bad-cop on full QA session.

### Recorded decision: no blocking external model reviewer on Stop

Considered and declined, 2026-08-18. proposal was Stop hook that shells
separate model (`claude -p` `codex exec` `gemini`) at `git diff HEAD`
blocks turn on FAIL verdict. Do not build it. reasons, in order of
weight:

-  hard blocking reviewer was already built on this exact surface and reverted
  twice. `clean-rag/hooks/verifier-gate.py` records both reverts in its own
  docstring.
- Anthropic's own `security-guidance` plugin does this, and it only works
  because of three things hand rolled version has none of: `asyncRewake`
  instead of synchronous block, `MAX_STOP_HOOK_FIRINGS` cap,
  continuation suffix so model does not abandon user's original request
  after being blocked.
- `abiswas97/gemini-plugin-cc` warns in its own README that this class of hook
  "can create long-running Claude/Gemini loop. Only enable it when actively
  monitoring session."
- Claude Code re-runs every Stop hook on every Stop event. new blocking hook
  without `stop_hook_active` guard loops against `auto-test-gate.py`
  `stop-context-guard.py`.
-  review responsibility is already owned by bad-cop and good-cop, which are
  fresh context subagents. second reviewer on same Stop event duplicates
  or contradicts them.

If goal ever becomes security specific review, adopt whole plugin
(`/plugin install security-guidance@claude-plugins-official` `SECURITY_REVIEW_MODEL`
selects reviewer) rather than writing hook. If only Stop hook loop guard
is wanted for some other purpose, `hamelsmu/claude-review-loop`'s `stop-hook.sh`
is reference for retry and fail open state machine, MIT licensed.

Two corrections to advice that prompted this, for anyone who reads it later:
 Stop payload carries `transcript_path` but no changed files list, so hook
must derive that itself with `git status --porcelain`and launching `claude -p`
from inside live session requires unsetting `CLAUDECODE` in child env
(`scripts/chat-watcher.py` does this).

## Debugging, testing and QA

When bug does not yield, failure mode is applying one technique harder.
Two or three iterations with no new information means technique is wrong,
not that you need more logging. Invoke **`debugging-methodology`** skill
pick different one by name from its symptom table:

- Regressed since known good commit, use `git bisect` (`git bisect run <cmd>`
  automates it entirely).
- Large input fails, small ones pass, use delta debugging to shrink it.
- Long call chain with one bad value, binary search on state.
-  working case sits beside failing one, differential debugging.
- Reproduces but cause is unclear, hypothesis first: write claim down,
  then design smallest test that would falsify it.
- Intermittent or race, record replay (`rr`). Re running it is not strategy.
- No reliable reproduction at all, stop and get one. fix without repro is
  guess you cannot validate.

That skill also carries per stack recipes for surfaces no MCP server
reaches: React Native (`adb logcat` `npx react-native log-ios`Hermes over CDP
through `chrome-devtools`since RN DevTools replaced Flipper), .NET
(`dotnet-trace` `dotnet-dump` `dotnet-gcdump` `dotnet-counters`), and Python
(`py-spy dump`/`record`which attach to live process without restarting it).

**Reach for debugger over print statements.** `mcp-debugger` covers Python,
Ruby, Node, Go, Java, .NET and Rust: `create_debug_session` → `set_breakpoint` →
`start_debugging`  `attach_to_process` → `get_variables`. Browser, network
performance work is `chrome-devtools`. Driving mobile app is `mobile-mcp`.
Coverage is `test-coverage`. Native C/C++
is `mdb` (GDB/LLDB). If tool is missing at runtime its server was never
registered, so run installer; every server comes from one table there.

**Databases are read only.** Understand schema from project's own
artifacts (EF Core `DbContext`  `Migrations/` `models.py`Alembic versions,
`schema.sql`), reason about query, and hand it to human to run. Do not
execute against live database and do not automate SSMS or any equivalent GUI
client. wrong statement against real data is not recoverable by retry.

Running `/qa` gives full session: inventory, risk ranked test plan,
execution with evidence. `/debug` is focused single bug path. Both enumerate
 debugging tools already, and both point back at this same skill.

## UI / Frontend Work

When task involves editing or creating frontend files (`.tsx` `.jsx`
`.html` `.css` `.scss` `.vue` `.svelte`), invoke `frontend-design`
skill before making any design decisions. Run two-pass process: compact
token system (palette, typefaces, layout concept, signature element) then
self-critique against brief before building. Never skip to code without
 brief-grounding pass.

After any UI change, invoke `eyes` skill to capture screenshot
verify visually before calling it done. Propose changes with pixel-precise
numbers. Confirm with user before applying. Verify with before/after
comparison screenshot.

## clean-rag (the search backend, port 8613)

Search runs over projects you've indexed, plus live web search. There is no
scraped topic knowledge base.

- `POST http://127.0.0.1:8613/search` with `sources: ["project:<abs path>"]`
  `mode: "both"` runs vector similarity and import graph traversal together.
  Graph results carry `relation` (imports, inherits, implements, calls)
  `seed_file`. Use `mode: "both"` on every code search, vector and graph surface
  different files.
- `POST http://127.0.0.1:8613/web-search` is DuckDuckGo, source ranked (GitHub
  and StackOverflow first, content farms last), sanitized against hidden
  characters. Snippets are cheap, so survey with it and only fetch full page
  when you need substance.
- Index project once with `/index-project`. It reindexes itself: after every
  edit, and full sweep every 10 minutes for outside changes. server runs
  headed so you can watch it.

If server is down, run `/clean-rag-server start`.

## Plugins

Installed from `PLUGINS` in `scripts/setup.py`mirrored in
`clean-rag/install.py` for same standalone reason as `MCP_SERVERS`. Adding
one means adding row to BOTH tables. Each row needs `marketplace` (the repo)
and `name` (the `plugin@marketplace` id); adding marketplace alone installs
nothing.

Installed today:

- **ponytail** (`DietrichGebert/ponytail`MIT) stops agent over-building.
  Before writing code it walks ladder: does this need to exist, does
  stdlib do it, is there native platform feature, is it already dependency,
  can it be one line. Validation, error handling, security and accessibility are
  never on chopping block. Its two lifecycle hooks are Node, `node` has
  to be on PATH or they fail on every prompt.

  **It pulls against this file, on purpose.** Everything above mandates research
  before edit and fresh context review after one. Ponytail's first rung is
  "skip it". When they disagree, ladder decides what to build and this file
  decides how to check it, so research still runs and bad-cop still runs;
  ladder usually means there is less to review. If turn feels ceremonious
  for one line change, that is `/ps`not reason to switch either off.

- **pipe-down** (`hoo29/claude-pipe-down`MIT) refuses Edit or Write that
  adds over-long or low value comment. It is `PreToolUse`which is
  whole point: `comment-humanness-check.py` is `PostToolUse`so its length
  nudge arrives after comment is already on disk and gets ignored. Only
  dash rule there ever blocked. pipe-down covers 30 plus languages from its own
  `Lang` table, including `/* */` blocks, which our extractor does not reach.

  Two env vars are set for it, with `setdefault` in both installers so retune
  survives re-run. `PIPE_DOWN_MAX_WORDS` is 20, not its shipped 25, matching
   cap our own hook already used. `PIPE_DOWN_LLM` is `0` because it ships
  **on**: left alone it spawns `claude -p` Haiku subprocess per write, with
  40 second timeout, to judge borderline comments. That is real latency cost
  on every edit. Turn it back on only if regex rules prove too blunt.

  It fails open on malformed payload and caps itself at
  `PIPE_DOWN_MAX_DENIALS = 2` per file, so it cannot wedge session. Verified
  by driving real hook rather than reading it: same 22 word comment is
  denied at cap of 20 and allowed at 25, so setting does real work.

### Calling it correctly

**8613 is only server.** There used to be second on 8612 carrying topic
knowledge base. Both were deleted. If you see `8612` `/context` `/index`
`scope=` parameter anywhere, that text is stale, and doing what it says gets you
connection refused rather than error you would notice.

 whole contract is one route:

```
POST http://127.0.0.1:8613/search
{"query":"how does auth work","sources":["project:C:/abs/path"],"mode":"both","limit":8}
```

- `sources`not `scope`. list of `project:<absolute path>`. Several at once is
  fine, and each is queried with embedding model its own index was built
  with.
- `mode: "both"` on every code search. Vector and graph surface different files
  and one without other leaves gap.
-  source only works if that path is registered project. directory of
  markdown you never indexed returns nothing, silently. Check `GET /status`.
- `stale_projects` in response with `served: false` means index exists
  but was refused, and reason field says why. Zero results plus that field is
   broken index, not empty codebase. Read it before concluding code is
  not there.

Other routes worth knowing: `/index-project` `/reindex-file` `/status`
`/projects` `/web-search` `/github-search` `/github-file`
`/stackoverflow-search` `/run-tests` `/mutation-test` `/security-scan`.
`clean-rag/CLAUDE.md` has full table,
`clean-rag/tests/test_skill_rag_routes.py` fails if any skill names route
server does not serve, so that list cannot drift again without red test.

When spawning agent, hand it real search line against real indexed
project. Do not tell it to load context from server that no longer exists.

## MCP servers, and using them safely

 installer registers these from `MCP_SERVERS` in `scripts/setup.py`mirrored
in `clean-rag/install.py`. Adding server means adding row to BOTH tables,
and `tests/test_mcp_server_registration.py` fails if they drift. Every one of
them is free.

**The rule that generalises: these servers act as you.** They carry your PAT,
your Atlassian permissions, your filesystem. Most ship write tools enabled by
default. mitigation is always scope of credential you hand over,
never server's own good behaviour. read only token is control;
promise in README is not.

What each one is for, and specific thing to watch:

- **serena** gives real symbol references, call hierarchy and rename through
  language servers. Local. It writes `.serena/` index into whatever project
  it is pointed at, which is gitignored. Its C# backend is flaky part.
- **ast-grep** does structural AST search for codemods. Local, 4 tools.
  maintainers call MCP wrapper experimental, so check rewrite's output.
- **context7** fetches version pinned library docs. Your query strings go to
  Upstash. Never put code or anything internal in query.
- **semgrep** is real SAST. Scans stay entirely local. Do NOT set
  `SEMGREP_APP_TOKEN` unless you want findings shipped to Semgrep's
  cloud; without it nothing leaves machine.
- **osv** returns citable CVE and advisory IDs from Google's public database.
  Read only, no credential, nothing sensitive sent.
- **socket** scores package before swiper takes it: license, malware,
  maintenance. Its `depscore` is Socket's own composite number, so it is triage,
  not citation. free tier has monthly scan cap.
- **arxiv** pulls real paper sections. This exists because `researcher` has
  WebSearch but no WebFetch and clean-rag has no general fetch route, so it
  otherwise works from snippets. Scope prompts to section; whole papers flood
  context.
- **antv-chart** renders mind maps, flowcharts, network graphs and fishbone
  diagrams to PNG. By default it renders through Ant Group hosted endpoint,
  so **diagram data leaves machine**. Set `VIS_REQUEST_SERVER` to self host
  before drawing anything that describes internal systems.
- **jupyter** produces executable `.ipynb` evidence human can re-run. It
  executes code, so treat it as real execution surface. Gated on
  `JUPYTER_TOKEN`without live Jupyter it is skipped.
- **mobile-mcp** drives real mobile app: install build, tap, type,
  screenshot, read device logs and crashes. Android works through `adb` on any
  OS; iOS needs Mac with Xcode. It acts on device for real, including
  uninstalling apps, replacing clipboard and overriding GPS, so point it at
   emulator or test device, never personal phone. Upstream telemetry is
  on by default, so row sets `MOBILEMCP_DISABLE_TELEMETRY=1` in its own
  `env`.
- **github** does PRs, issues and Actions as structured calls. Use fine
  grained PAT scoped to repos you want reachable, never classic
  token with full `repo`. It can merge, push and close for real. Its secret
  scanning needs paid Secret Protection on private repos, so do not count on
  that tool. hosted endpoint requires Copilot enrolment; Copilot Free is $0.
- **atlassian** reads and writes live Jira and Confluence as your user. write
  here is write to something colleagues see. Confirm before creating
  editing anything, same as any outward facing action.

**Credentials.** `GITHUB_MCP_TOKEN`  `JUPYTER_TOKEN` are passed as `${VAR}`
placeholders, which Claude Code expands from **its own process environment** at
launch. They have to live somewhere that environment sees: real environment
variable in shell you start Claude Code from, `env` block of
`~/.claude/settings.json`. Both were confirmed by pointing credentialed HTTP
server at local listener and reading header that arrived.

**Not `clean-rag/.env`.** Only clean-rag's server process reads that file,
token set there never reaches Claude Code, and failure is quiet:
registration succeeds and literal `${GITHUB_MCP_TOKEN}` goes out as
bearer token. `claude mcp list` does print `Missing environment variables: ...`
and installer refuses to register server whose credential is unset, which
is guard that holds.

`GITHUB_MCP_TOKEN` is deliberately NOT `GITHUB_TOKEN`that one is clean-rag's
read only search token, and sharing name would either break server
quietly widen what search can do. unset credential skips that one server with
 warning and never fails install. Never resolve credential into
registration payload; placeholder is what keeps it out of `~/.claude.json`.

**The injection boundary.** `bad-cop`  `good-cop` do NOT get context7, arxiv,
socket or anything else that fetches from network, for same reason they
never had WebFetch: reviewer that reads untrusted content is reviewer that
can be talked out of finding. Fetch shaped servers go to `researcher`
`swiper` only, two agents that already carry that exposure.
`test_reviewers_get_no_fetch_shaped_tools` enforces that, so it is checked
invariant and not promise in document.

 other half of that routing, giving cops local code readers (serena,
semgrep, ast-grep), is **not wired**. Neither cop enumerates those tools today.
Wiring it needs real tool names read off running server, because Claude
Code silently drops name it does not recognise, which is exact bug
`tests/test_mcp_server_registration.py` exists to catch.

**Tool names are enumerated literally, never wildcarded.** Claude Code silently
drops `mcp__<server>__*`which is how bad-cop believed it had coverage data for
months while having none. Add server's tools by real name, and let
`tests/test_mcp_server_registration.py` confirm server behind them exists.

## Decision Flow

Two paths, not five mandatory steps.

**Simple task?** do it. No workspace, no ceremony.

**Complex task?** (ticket attached, multi-agent, multi-session, user says "plan
this")
1. Create `workspace/[task-id]/` and announce with one line.
2. Sweep then verify across domains (testing, docs, security, architecture,
   performance, review, clarity).
3. Spawn right agent(s).

Sweep then verify: scan all domains, but for every flag you raise, prove it from
actual code. If you can't cite specific lines, drop flag. "Nothing found" is
always valid.

## Agent Spawning

Spawn agents when they add value: parallelism, isolation, deep specialization.
Do work directly when they don't. one line fix doesn't need agent.

 six agents in Model Routing below are spawned as needed, not on every
task. Any other shipped agent belongs to skill that spawns it.

### Never delete scratchpad files. Leave them

Scratch work goes in session scratchpad directory, and it stays there. Do not
`rm` it, do not tidy it up, do not delete your own backup copies when you are
finished. directory is session specific and disposable, so nothing is gained
by cleaning it, and every `rm` costs human permission prompt for no reason.
Say file is no longer needed if it matters; do not remove it.

### What the rm rules do, and why they are shaped that way

Reworked 2026-09-16. `rm` is split by whether command is recursive, because
that is where nearly all of danger lives. Deleting named file is ordinary
work; deleting tree is not.

- **Allowed, no prompt**: non recursive `rm`such as `rm build.log`
  `rm -f render/s-01.png`.
- **Ask**: anything recursive. `rm -r*` `rm -R*` `rm -fr*` `rm -fR*`
  `rm -f -r*` `rm --recursive*`and couple of catch alls for odd flag orders.
- **Deny**: sixteen catastrophic shapes that should never run at all, including
  `rm -rf /` `~` `.` `..` `$HOME` `C:*` and Git Bash drive paths `/c`
  and `/c/*`.

Do not replace this with single broad `Bash(rm **)` in `ask`. That was old
shape and it prompted on every scratch file, which trains people to approve
without reading. Do not try to carve safe directory out of broad rule either,
because it cannot be done: permission rules evaluate deny, then ask, then allow,
first match wins, and "rule specificity doesn't change order", so narrower
`allow` never fires. Bash patterns have no `!` negation; that exists only for Read
and Edit. PreToolUse hook cannot help either, since "a matching ask rule still
prompts even when hook returned `allow`". Hooks tighten, never loosen. All
three quotes are from `code.claude.com/docs/en/permissions.md`.

Splitting on recursive flag is one cut that IS expressible, which is why
 rules look like this.

### Model Routing
- **Opus**: good-cop.
- **Sonnet**: bad-cop, quick-cop, research-agent, researcher, swiper.

That is pipeline roster, 6 agents. skill may ship its own helper agent, spawned only from that skill. spawn of name with no agent file does not error; it quietly resolves to generic agent while session believes it got specialist.

### Starting a new build or feature

For edit intent task, new build or feature, run `/start` instead of
diving straight into research-agent: it spawns `researcher` first (codebase
structure via clean-rag's own index and graph, plus general engineering
standard for this class of change), then `swiper` informed by researcher's
findings (what can be swiped, from project, stdlib, dependency,
GitHub, or StackOverflow, reported only, swiper never writes to project
itself), then consults user with real options before anything is
written. `researcher` also replaces ad hoc codebase exploring subagent for
understanding project: it has clean-rag's real indexed vector and graph
databases behind it, so route codebase understanding tasks to it instead.

### Parallel Limits
- Context below 50%: up to 3 agents.
- Context 50 to 75%: up to 2 agents.
- Context above 75%: 1 agent, sequential.

### Fan-out mode

"Go into fast mode", "use fast mode", or "go quickly" turn on fan-out mode.

**It is not Anthropic's `/fast`.** That toggle speeds up one model's output
bills at premium. This is different thing on same model: more agents
working at once. words collide, so first time it comes up in session,
say which one you took it to mean.

**What changes: how work is cut.** Work for `researcher` `swiper`
`bad-cop`  `good-cop` gets decomposed into independent slices, and those
slices go out as multiple Agent tool calls in single message so they run
concurrently. That is Claude Code's own documented mechanic: "When asking
Claude to run agents 'in parallel', it will send single message with multiple
Agent tool calls, launching all of them simultaneously. You should be explicit
about what should run in parallel vs. what must be sequential."

**What does not change: Parallel Limits above.** They still bind in fan-out
mode. Three concurrent agents below 50% context, two from 50 to 75%, one above.
Fan-out changes decomposition, not ceiling. More agents than that is
documented failure rather than speedup: Anthropic's own multi-agent research
writeup names "spawning excessive subagents (50+) for simple queries" as real
cost, alongside parallel workers duplicating each other's work when none of
them knows what others are doing.

**Slice by concern, never by file.** This is part that goes wrong under
time pressure. `researcher`  `swiper` decompose safely along independent
aspects, because one aspect's answer does not depend on another's. reviewer
does not decompose that way. Split `bad-cop`  `good-cop` by dimension
(correctness, security, concurrency, error handling, test quality) and hand
every parallel instance **full** diff. bad-cop that sees only file B
cannot see that signature change in file broke it. Cross file bugs are
invisible to file sliced reviewer, which is why `.claude/commands/audit.md`
already fans out by dimension and passes each auditor entire input verbatim.
Copy that shape, including how it handles count: pick dimensions
diff earns, then run them in waves current tier allows. Five
dimensions under three agent ceiling is two waves, not one overfull message.
`audit.md` selects 3 to 6 dimensions and then says "Spawn one agent per
selected dimension. Wait for each batch to complete before starting next."
 ceiling is on how many run at once, never on how many dimensions diff
deserves.

**Sequential stays sequential.** `swiper` still runs after `researcher`
because it needs those findings to avoid recommending swipe for something
project already has. `good-cop` still runs after `bad-cop`and closing
`bad-cop` re-check still runs after `good-cop`. Fan-out widens each stage. It
does not collapse pipeline into one round.

**No lock file is needed, and do not repurpose one that exists.** two
gates this pipeline runs on, `clean-rag/hooks/research-gate.py`
`clean-rag/hooks/verifier-gate.py`return 0 on every path and only write
nudge to stderr, so concurrent agents never serialize on them. That is what
makes fan-out safe here. `state/audit-in-progress.json` is different thing
and is still load-bearing: `scripts/skill-verify-gate.py`registered
PreToolUse hook on Skill tool, exits 2 for action skill while
`needs-verification.json` is pending unless that flag is set, and three more
registered hooks read it: `scripts/verify-gate-cmd.py` (PostToolUse on Task),
`scripts/context-nudge.py` (PostToolUse on everything)
`scripts/rules-compliance-check.py` (Stop). `scripts/action-gate.py` reads
flag too, but it is registered nowhere. Its hook registration was removed from
 installer at user's own request, recorded in
`clean-rag/state/proof-log.jsonl` on 2026-07-06, so that branch exists
never runs. Do not register it again to make list tidy.
`/audit` sets it at its Phase 0 and clears it at Phase 5 precisely because its
own batch would otherwise be gated agent by agent.

Fan-out mode does not set it. One flag with two writers means whichever batch
finishes first clears it out from under other, and batch that dies
mid-run leaves all four registered checks suppressed for rest of
session, on disk, with nothing to notice. If fan-out ever trips one of them,
fix that gate, do not switch it off.

## Verify Gate (anti hallucination)

Applies everywhere: reviews, planning, bug diagnosis, security audits, test
planning.

- Every finding must be proven from actual code before acting on it.
- Cite specific file and line for every flag.
- "No issues found" is always valid outcome.
- Finding something is not goal. Finding real things is.

## Collaborative Mode (CONSULT / AUTO)

Default is **CONSULT**. Before architectural decision, research project,
present options, let user add constraints, then implement. Architectural
triggers: new endpoint, DB table, dependency, module, middleware, or new
auth/validation/error/logging strategy. Not triggers: typos, one line fixes,
tests, docs, renames in one file.

`/auto [reason]` switches to autonomous AUTO mode for prototyping and low rework
cost work. `/consult` restores CONSULT.

## Hard Rules (non negotiable)

### Never start an app without naming the environment
Starting local app is single most dangerous routine command, because
damage comes from what you *omit*, not from anything visibly dangerous you type.

Always name environment explicitly, and never pass flag that skips
launch profile:

```
ASPNETCORE_ENVIRONMENT=Development ASPNETCORE_URLS="https://localhost:PORT" \
  dotnet run --project "<path to csproj>"
```

Then read startup log and confirm `Hosting environment: Development` before
opening browser or running any test against it. Anything else is stop.

Why this is hard rule: ASP.NET Core defaults to **Production** whenever
`ASPNETCORE_ENVIRONMENT` is unset. `dotnet run --no-launch-profile` skips
`launchSettings.json`which is usually only thing setting that variable,
config binds `appsettings.json` instead of `appsettings.Development.json`. On
real project that routinely means production database and production
secret store, reached from dev machine, with no prompt and no warning.

Do not count on failure to save you. Whether such run connects
depends on incidental things like credential resolution order, which is not
safeguard and can change without notice.

Note what makes this class hard to catch: dangerous command contains no
dangerous looking token at all. Do not rely on command "looking risky" to
decide whether to check environment. `scripts/bash-guard.py` blocks known
shapes (`check_production_environment`), but it only knows flags already
discovered, so rule above is what generalizes.

 same reasoning applies to any framework with environment default: Rails
`RAILS_ENV`Django `DJANGO_SETTINGS_MODULE`Node `NODE_ENV`Spring
`SPRING_PROFILES_ACTIVE`. Name it, then verify it from app's own startup
output rather than from what you intended.

### GitHub writes: state safety and reversibility, then wait for 3.14

Non-dangerous, non-read-only GitHub operations are allowed. Examples: `git add`
`git commit`plain `git push` (no force), `git remote add` `gh pr create`
`edit`  `close` `gh issue create`  `close` `gh gist create`  `edit`
`gh repo create --private`.

Before each one, send two short lines and stop:

1. **Safety**: what it touches and who can see it.
2. **Reversibility**: how to undo it, or "not reversible".

Then wait. Run it only after human types `3.14` as message. Their original
request is not approval, `3.14` covers only operations named in
two lines above it.

Still never run, with or without `3.14`force push, `git reset --hard`
`git branch -D` `git clean -fdx` `gh pr merge` `gh release` `gh gist delete`
`gh repo delete`or any push to public repo. Those stay in `deny`.

### Plain writing (enforced by output style, not by hope)
Everything you write, chat replies, drafted comments, PR descriptions, docs, is
plain and short. One idea per sentence. Point first, never built up to. No throat
clearing openers, no idiom, no filler intensifiers. Fewer words, not softer
claims: still say plainly when something is uncertain, failed, unverified,
skipped.

This lives in **output style**, `~/.claude/output-styles/plain.md`activated
via `"outputStyle": "Plain"` in `~/.claude/settings.json`. That matters: output
style rewrites system prompt, whereas CLAUDE.md and memory are appended as
user message and lose to drift over long session. rule that kept getting
restated by human is rule in wrong layer. Put tone rules in output
style, not here.

Two narrower layers already run alongside it and are not substitutes:
`human-voice-guard.py` (Stop hook) bans 39 AI tell words and filler phrases in
chat prose; `comment-humanness-check.py` (PostToolUse) covers code comments.
`human-voice-guard.py` is vocabulary check and nothing more; it reads chat
transcript and never sees file.

`comment-humanness-check.py` blocks (exit 2) on any dash, and nudges on five
older patterns plus two added 2026-09-18 that do enforce concision:

- **comment-length**: single comment body over 20 words, so it is not one line.
- **comment-narration**: comment's opening verb restates line it sits on.
  `// Return the total` above `return a.total` `// Save the record` above
  `saveRecord(x)` `// Get the active user` above assignment.

Both exempt any comment carrying reason (`because` `so that` `must` `race`
`security` `bug` `only` `unless` and rest of `_EXPLANATORY_RE`), because
comment that says why has earned its words however it opens. Both fire on
single comment; five older nudges still need three or more, which is hole
these two fill.

Why this was built rather than installed: nothing external covers it.
narration rule is ported from `no-redundant-comments` in
`pertrai1/eslint-plugin-llm-core` (MIT), which is JS and TS only through ESLint's
AST and cannot run against C# and Python here. No Roslyn equivalent exists.
 port trades AST for line matching, so failure mode to watch is
false positive on comment that genuinely explains something;
`tests/test_comment_humanness_check.py` pins that boundary.

### Swipe before you build, including for your own tooling
When question is "how do I make Claude do X", check whether harness
community already does X before writing anything. Output styles, hooks,
settings fields already exist for most of it. Hand rolling solution to solved
problem is failure this whole file is meant to prevent, and it applies to
tooling and config, not project code.

### No machine specific paths in anything committed

Never write absolute path, home directory, or username into file that
gets committed. Not in code, not in test fixture, not in config file, not
in comment, not in doc. Derive root instead:
`Path(__file__).resolve().parents[N]` in Python,
`$(git rev-parse --show-toplevel)`  `${CLAUDEBOOST_HOME}` in shell,
visible placeholder like `C:/Users/<user>` in prose.

This is rule that already failed, twice, in this repo. Two developers' home
directories and client's internal hostnames reached public repository one
hardcoded line at time, and every one of those lines looked harmless on
machine that wrote it. `tests/test_no_machine_specific_paths.py` catches
shape now, and its own docstring records that "a second developer's home
directory sat in three tracked files whole time suite was green". That
test scans only tracked files with known suffix, so it is net under this
rule and not substitute for it.

 trap is that hardcoded path is never wrong on machine you are sitting
at. It fails on someone else's clone, in CI, and in public diff, which is to
say it fails everywhere you are not looking. So check is never "does this
work here", it is "what does this say about whose machine this is".

One narrow exception. path typed into one off Bash command during live
session is not committed, and there it should be absolute, because Claude
Code's simple_expansion scanner prompts on bare `$VAR` whatever allow
list says. Use `${BRACE}` form or literal absolute path in that case.
moment same path is written into file, rule above applies again.

### jQuery Ban
jQuery is banned unless user explicitly asks for it. Detect `$()` `jQuery`
imports, and CDN tags. Use React hooks, vanilla JS, and native fetch instead.

### Security Standards
- Parameterized queries always. Never string concatenation in SQL.
- Transactions for multi step database operations.
- OWASP top 10 awareness.
- No secrets in logs, URLs, or source.
- Input validation at system boundaries.
- Auth and authz checks on endpoints.

### Logging Standards
- Missing `logger.error` in catch or error block is blocker.
- Sensitive data in log output is blocker.
- Missing INFO level on service methods and before/after on external calls is
  suggestion.

## Token Efficiency

Do it right first time. Rework costs more than ceremony.

- Route by weight. Full ceremony (verify gate plus evaluator) for reviewer,
  security, performance. Standard for rest. Lightweight for explore,
  research, docs.
- Always spawn evaluator to verify findings, never self verify. fresh
  context catches hallucinations that same context confirmation misses.
- Web research is cheap when you survey with snippets and fetch sparingly.
  research agent's cost is mostly full page fetches, not searches.

## OpenCode

clean-rag has OpenCode integration too (`clean-rag/opencode/`): same MCP
search tools, two research agents ported as OpenCode subagents,
research gate plugin. Install with `clean-rag/opencode/install.py`. gate is
enforced for primary agent; known OpenCode bug means subagent edits may
bypass it until upstream fixes it.

## Browser Testing Safety

Playwright and browser automation may go to any site task needs. When
production and dev environment both exist, always default to dev. Use
production only when user specifically says to use production, in their own
words, for that task. That approval does not carry to next task.

- localhost, 127.0.0.1, 0.0.0.0, `::1` `*.local` / `*.test` are always fine.
- `.claude/browser-targets.local.json` (gitignored) can still name extra hosts.
  `scripts/bash-guard.py` reads it for curl, so that check is unchanged.

hostname is not evidence on its own: `dev` in name proves nothing, and shared
dev environment can still hold real data. lower environment restored from
production snapshot is production data with friendlier name, so treat every
write there as write to shared state and get approval first. When there is no
dev environment, ask before writing anything; read only navigation, hovering,
and screenshots are fine.

Two things stay off limits regardless. environment's own control plane
management dashboard is never something to browse. Corporate identity sign in
belongs to human:
drive as far as SSO prompt and hand over rather than entering someone's
credentials or approving their MFA.

If unsure whether URL is in scope, ask before navigating. Default to headed
browser, not headless.

