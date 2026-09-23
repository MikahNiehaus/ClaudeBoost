# ClaudeBoost

Research gated development for Claude Code. Every code edit is researched before
it happens, and search runs over your own indexed projects, not a scraped
knowledge base.

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
   Wait for it before editing anyway; that's still the point.

   **Every agent spawn runs in the background. You cannot choose otherwise.**
   This paragraph used to say "spawn it in the foreground
   (`run_in_background: false`), never backgrounded". That instruction asked
   for something the agent tool does not offer. Its inputs are `description`,
   `isolation`, `model`, `prompt` and `subagent_type`, and nothing else;
   `run_in_background` is a `Bash` input, not an agent one. Verified
   2026-09-18 by reading the live tool schema.

   The consequence is structural, not a mistake anyone made. A completion
   arrives as a `TaskNotificationMessage` rather than a tool result, so
   `PostToolUse` on `Task|Agent` never fires for a subagent and can never
   stamp coverage. `SubagentStop` is the only event that can, and it is
   registered for that reason. Do not try to work around this by spawning
   differently; there is no other way to spawn.
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
  condition, not good-cop claiming done.

  **The fix is good-cop's job, not yours.** When bad-cop reports something
  real, hand it to good-cop. Fixing it yourself instead is the specific failure
  this paragraph exists to stop, and it has happened. Two reasons, both the
  same ones that put bad-cop in a fresh context to begin with. You orchestrated
  or wrote the change, so you carry its blind spot exactly the way its author
  does. And the fix you reach for first is the symptom bad-cop's test caught,
  because the symptom is the visible part and the cause usually is not. A one
  line change that turns the suite green is the most dangerous shape of this,
  since afterwards nothing about it looks like a shortcut. If you already
  patched something before thinking, do not quietly keep it: say so, hand
  good-cop both the finding and your interim patch, and tell it in writing not
  to accept that patch merely because it is already in the tree. A fix sitting
  in the working tree reads as already decided, and that is precisely the bias
  a fresh context is there to resist.

  **good-cop reproduces a finding before it fixes it.** Its opening used to say
  the opposite, that its job was not to re-litigate whether bad-cop's findings
  were real, while a passage near the end of the same file told it to disprove
  false positives. An instruction at the top of a file outweighs one at the
  bottom, so the contradiction resolved the wrong way. It now runs each repro
  first and reports one of three outcomes: it reproduces and gets fixed at the
  root cause, it does not reproduce and is recorded as a false positive with the
  command and output that show it, or it reproduces for a different reason than
  bad-cop stated and the real cause gets fixed with the difference named.
  Require that evidence in its report. What it may never do is dismiss a finding
  on reading alone: only execution output overturns execution output.

  **good-cop researches before it fixes, and cites what it found.** Its own
  definition requires grounding the fix in real practice, a real standard or a
  real example ahead of its own opinion, for the same reason the research gate
  exists on the write side: an ungrounded fix is a guess that happens to
  compile. Require the sources in its report. A fix that arrives with no cited
  grounding has not been researched whatever it says, and the right response is
  to send it back, not to ship it. Hand it the tradeoffs to weigh rather than
  the answer you expect, because naming your preferred fix in the prompt turns
  the research into agreement with you.

  Give both of them the
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

**Both cops review the diff by default, and whatever you name instead.** With
no review scope given, bad-cop resolves the diff itself: the uncommitted working
tree, or the branch against its merge base when the tree is clean. Anything the
human names on a `REVIEW SCOPE:` line replaces that, in their own words, with no
fixed vocabulary. `entire project`, `anything that touches security`, `anything
that touches OrderService`, `anything around this bug fix`, a bare path, all
valid. Pass their sentence through verbatim; do not paraphrase it and do not
resolve it to files yourself. bad-cop resolves it with search and the import
graph, then prints the resolved file list at the top of its report, which is the
only place a misread scope gets caught, so read that block first. Copy the same
`REVIEW SCOPE:` and `RESOLVED:` lines into good-cop's prompt. Both work the same
surface. That list bounds where a root cause is allowed to live; it does not
widen what good-cop may change, which stays at what the findings require.

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

**Execution proves behaviour in the environment it ran in, and nothing more.**
That is the limit of the rule above, and it has already cost a real bug. A
change made an env var mandatory at module load. Two tests spawned a subprocess
that inherited the whole environment and only overrode one named variable. The
value happened to sit in the developer's own `.env`, so bad-cop, good-cop, a
second bad-cop re-check and the orchestrator all ran the suite and all passed.
A static reviewer reading the import chain caught it in one pass, because it
did not care what was in that machine's environment. Removing the value from
`.env` afterwards failed both tests instantly.

So two things, neither optional:

1. **Any test that spawns a subprocess must be run once with a scrubbed or
   explicitly declared environment, not the inherited one**, before anything is
   stamped. This is the check that mechanically reproduces the failure with no
   reasoning required, which is why it belongs here rather than in a reviewer's
   judgement.
2. **Any change that introduces a new hard requirement at module load** (a
   throw, an assert, a required config read) must be traced through its import
   graph to every process that could load it: a subprocess spawn, a worker, a
   cron entry, a CI job. Running it in the current shell proves nothing about
   the others.

The general form: a test that passes because of what is ambiently present is
not a passing test, it is an undeclared dependency. Established practice is to
declare what a test needs rather than inherit it, which is why CI runs in clean
containers and why hermetic builds exist. `scripts/tests/helpers.py` already
learned this once for `cwd`, after a hook test read whatever happened to be
uncommitted in the working tree; the lesson was never generalised to the
environment.


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

If the server is down, run `/clean-rag-server start`.

## Plugins

Installed from `PLUGINS` in `scripts/setup.py`, mirrored in
`clean-rag/install.py` for the same standalone reason as `MCP_SERVERS`. Adding
one means adding a row to BOTH tables. Each row needs `marketplace` (the repo)
and `name` (the `plugin@marketplace` id); adding the marketplace alone installs
nothing.

Installed today:

- **ponytail** (`DietrichGebert/ponytail`, MIT) stops the agent over-building.
  Before writing code it walks a ladder: does this need to exist, does the
  stdlib do it, is there a native platform feature, is it already a dependency,
  can it be one line. Validation, error handling, security and accessibility are
  never on the chopping block. Its two lifecycle hooks are Node, so `node` has
  to be on PATH or they fail on every prompt.

  **It pulls against this file, on purpose.** Everything above mandates research
  before an edit and a fresh context review after one. Ponytail's first rung is
  "skip it". When they disagree, the ladder decides what to build and this file
  decides how to check it, so research still runs and bad-cop still runs; the
  ladder just usually means there is less to review. If a turn feels ceremonious
  for a one line change, that is `/ps`, not a reason to switch either off.

- **pipe-down** (`hoo29/claude-pipe-down`, MIT) refuses an Edit or Write that
  adds an over-long or low value comment. It is `PreToolUse`, which is the
  whole point: `comment-humanness-check.py` is `PostToolUse`, so its length
  nudge arrives after the comment is already on disk and gets ignored. Only the
  dash rule there ever blocked. pipe-down covers 30 plus languages from its own
  `Lang` table, including `/* */` blocks, which our extractor does not reach.

  Two env vars are set for it, with `setdefault` in both installers so a retune
  survives a re-run. `PIPE_DOWN_MAX_WORDS` is 20, not its shipped 25, matching
  the cap our own hook already used. `PIPE_DOWN_LLM` is `0` because it ships
  **on**: left alone it spawns a `claude -p` Haiku subprocess per write, with a
  40 second timeout, to judge borderline comments. That is a real latency cost
  on every edit. Turn it back on only if the regex rules prove too blunt.

  It fails open on a malformed payload and caps itself at
  `PIPE_DOWN_MAX_DENIALS = 2` per file, so it cannot wedge a session. Verified
  by driving the real hook rather than reading it: the same 22 word comment is
  denied at a cap of 20 and allowed at 25, so the setting does real work.

### Calling it correctly

**8613 is the only server.** There used to be a second on 8612 carrying a topic
knowledge base. Both were deleted. If you see `8612`, `/context`, `/index` or a
`scope=` parameter anywhere, that text is stale, and doing what it says gets you
connection refused rather than an error you would notice.

The whole contract is one route:

```
POST http://127.0.0.1:8613/search
{"query":"how does auth work","sources":["project:C:/abs/path"],"mode":"both","limit":8}
```

- `sources`, not `scope`. A list of `project:<absolute path>`. Several at once is
  fine, and each is queried with the embedding model its own index was built
  with.
- `mode: "both"` on every code search. Vector and graph surface different files
  and one without the other leaves a gap.
- A source only works if that path is a registered project. A directory of
  markdown you never indexed returns nothing, silently. Check `GET /status`.
- `stale_projects` in the response with `served: false` means the index exists
  but was refused, and the reason field says why. Zero results plus that field is
  a broken index, not an empty codebase. Read it before concluding the code is
  not there.

Other routes worth knowing: `/index-project`, `/reindex-file`, `/status`,
`/projects`, `/web-search`, `/github-search`, `/github-file`,
`/stackoverflow-search`, `/run-tests`, `/mutation-test`, `/security-scan`.
`clean-rag/CLAUDE.md` has the full table, and
`clean-rag/tests/test_skill_rag_routes.py` fails if any skill names a route the
server does not serve, so that list cannot drift again without a red test.

When spawning an agent, hand it a real search line against a real indexed
project. Do not tell it to load context from a server that no longer exists.

## MCP servers, and using them safely

The installer registers these from `MCP_SERVERS` in `scripts/setup.py`, mirrored
in `clean-rag/install.py`. Adding a server means adding a row to BOTH tables,
and `tests/test_mcp_server_registration.py` fails if they drift. Every one of
them is free.

**The rule that generalises: these servers act as you.** They carry your PAT,
your Atlassian permissions, your filesystem. Most ship write tools enabled by
default. The mitigation is always the scope of the credential you hand over,
never the server's own good behaviour. A read only token is the control; a
promise in a README is not.

What each one is for, and the specific thing to watch:

- **serena** gives real symbol references, call hierarchy and rename through
  language servers. Local. It writes a `.serena/` index into whatever project
  it is pointed at, which is gitignored. Its C# backend is the flaky part.
- **ast-grep** does structural AST search for codemods. Local, 4 tools. The
  maintainers call the MCP wrapper experimental, so check a rewrite's output.
- **context7** fetches version pinned library docs. Your query strings go to
  Upstash. Never put code or anything internal in the query.
- **semgrep** is real SAST. Scans stay entirely local. Do NOT set
  `SEMGREP_APP_TOKEN` unless you actually want findings shipped to Semgrep's
  cloud; without it nothing leaves the machine.
- **osv** returns citable CVE and advisory IDs from Google's public database.
  Read only, no credential, nothing sensitive sent.
- **socket** scores a package before swiper takes it: license, malware,
  maintenance. Its `depscore` is Socket's own composite number, so it is triage,
  not a citation. The free tier has a monthly scan cap.
- **arxiv** pulls real paper sections. This exists because `researcher` has
  WebSearch but no WebFetch and clean-rag has no general fetch route, so it
  otherwise works from snippets. Scope prompts to a section; whole papers flood
  context.
- **antv-chart** renders mind maps, flowcharts, network graphs and fishbone
  diagrams to PNG. By default it renders through an Ant Group hosted endpoint,
  so **diagram data leaves the machine**. Set `VIS_REQUEST_SERVER` to self host
  before drawing anything that describes internal systems.
- **jupyter** produces executable `.ipynb` evidence a human can re-run. It
  executes code, so treat it as a real execution surface. Gated on
  `JUPYTER_TOKEN`; without a live Jupyter it is skipped.
- **github** does PRs, issues and Actions as structured calls. Use a fine
  grained PAT scoped to the repos you actually want reachable, never a classic
  token with full `repo`. It can merge, push and close for real. Its secret
  scanning needs paid Secret Protection on private repos, so do not count on
  that tool. The hosted endpoint requires Copilot enrolment; Copilot Free is $0.
- **atlassian** reads and writes live Jira and Confluence as your user. A write
  here is a write to something colleagues see. Confirm before creating or
  editing anything, the same as any outward facing action.

**Credentials.** `GITHUB_MCP_TOKEN` and `JUPYTER_TOKEN` are passed as `${VAR}`
placeholders, which Claude Code expands from **its own process environment** at
launch. They have to live somewhere that environment sees: a real environment
variable in the shell you start Claude Code from, or the `env` block of
`~/.claude/settings.json`. Both were confirmed by pointing a credentialed HTTP
server at a local listener and reading the header that arrived.

**Not `clean-rag/.env`.** Only clean-rag's server process reads that file, so a
token set there never reaches Claude Code, and the failure is quiet: the
registration succeeds and the literal `${GITHUB_MCP_TOKEN}` goes out as the
bearer token. `claude mcp list` does print `Missing environment variables: ...`,
and the installer refuses to register a server whose credential is unset, which
is the guard that actually holds.

`GITHUB_MCP_TOKEN` is deliberately NOT `GITHUB_TOKEN`: that one is clean-rag's
read only search token, and sharing the name would either break the server or
quietly widen what search can do. An unset credential skips that one server with
a warning and never fails the install. Never resolve a credential into the
registration payload; the placeholder is what keeps it out of `~/.claude.json`.

**The injection boundary.** `bad-cop` and `good-cop` do NOT get context7, arxiv,
socket or anything else that fetches from the network, for the same reason they
never had WebFetch: a reviewer that reads untrusted content is a reviewer that
can be talked out of a finding. Fetch shaped servers go to `researcher` and
`swiper` only, the two agents that already carry that exposure.
`test_reviewers_get_no_fetch_shaped_tools` enforces that, so it is a checked
invariant and not a promise in a document.

The other half of that routing, giving the cops the local code readers (serena,
semgrep, ast-grep), is **not wired**. Neither cop enumerates those tools today.
Wiring it needs the real tool names read off a running server, because Claude
Code silently drops a name it does not recognise, which is the exact bug
`tests/test_mcp_server_registration.py` exists to catch.

**Tool names are enumerated literally, never wildcarded.** Claude Code silently
drops `mcp__<server>__*`, which is how bad-cop believed it had coverage data for
months while having none. Add a server's tools by real name, and let
`tests/test_mcp_server_registration.py` confirm the server behind them exists.

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

The six agents in Model Routing below are spawned as needed, not on every
task. Any other shipped agent belongs to the skill that spawns it.

### Never delete scratchpad files. Leave them

Scratch work goes in the session scratchpad directory, and it stays there. Do not
`rm` it, do not tidy it up, do not delete your own backup copies when you are
finished. The directory is session specific and disposable, so nothing is gained
by cleaning it, and every `rm` costs the human a permission prompt for no reason.
Say a file is no longer needed if it matters; do not remove it.

### What the rm rules do, and why they are shaped that way

Reworked 2026-09-16. `rm` is split by whether the command is recursive, because
that is where nearly all of the danger lives. Deleting a named file is ordinary
work; deleting a tree is not.

- **Allowed, no prompt**: non recursive `rm`, such as `rm build.log` or
  `rm -f render/s-01.png`.
- **Ask**: anything recursive. `rm -r*`, `rm -R*`, `rm -fr*`, `rm -fR*`,
  `rm -f -r*`, `rm --recursive*`, and a couple of catch alls for odd flag orders.
- **Deny**: sixteen catastrophic shapes that should never run at all, including
  `rm -rf /`, `~`, `.`, `..`, `$HOME`, `C:*` and the Git Bash drive paths `/c`
  and `/c/*`.

Do not replace this with a single broad `Bash(rm **)` in `ask`. That was the old
shape and it prompted on every scratch file, which trains people to approve
without reading. Do not try to carve a safe directory out of a broad rule either,
because it cannot be done: permission rules evaluate deny, then ask, then allow,
first match wins, and "rule specificity doesn't change the order", so a narrower
`allow` never fires. Bash patterns have no `!` negation; that exists only for Read
and Edit. A PreToolUse hook cannot help either, since "a matching ask rule still
prompts even when the hook returned `allow`". Hooks tighten, never loosen. All
three quotes are from `code.claude.com/docs/en/permissions.md`.

Splitting on the recursive flag is the one cut that IS expressible, which is why
the rules look like this.

### Model Routing
- **Opus**: good-cop.
- **Sonnet**: bad-cop, quick-cop, research-agent, researcher, swiper.

That is the pipeline roster, 6 agents. A skill may ship its own helper agent, spawned only from that skill. A spawn of a name with no agent file does not error; it quietly resolves to a generic agent while the session believes it got a specialist.

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

### Plain writing (enforced by output style, not by hope)
Everything you write, chat replies, drafted comments, PR descriptions, docs, is
plain and short. One idea per sentence. Point first, never built up to. No throat
clearing openers, no idiom, no filler intensifiers. Fewer words, not softer
claims: still say plainly when something is uncertain, failed, unverified, or
skipped.

This lives in an **output style**, `~/.claude/output-styles/plain.md`, activated
via `"outputStyle": "Plain"` in `~/.claude/settings.json`. That matters: an output
style rewrites the system prompt, whereas CLAUDE.md and memory are appended as a
user message and lose to drift over a long session. A rule that kept getting
restated by the human is a rule in the wrong layer. Put tone rules in the output
style, not here.

Two narrower layers already run alongside it and are not substitutes:
`human-voice-guard.py` (Stop hook) bans 39 AI tell words and filler phrases in
chat prose; `comment-humanness-check.py` (PostToolUse) covers code comments.
`human-voice-guard.py` is a vocabulary check and nothing more; it reads the chat
transcript and never sees a file.

`comment-humanness-check.py` blocks (exit 2) on any dash, and nudges on five
older patterns plus two added 2026-09-18 that do enforce concision:

- **comment-length**: a single comment body over 20 words, so it is not one line.
- **comment-narration**: the comment's opening verb restates the line it sits on.
  `// Return the total` above `return a.total`, `// Save the record` above
  `saveRecord(x)`, `// Get the active user` above an assignment.

Both exempt any comment carrying a reason (`because`, `so that`, `must`, `race`,
`security`, `bug`, `only`, `unless` and the rest of `_EXPLANATORY_RE`), because a
comment that says why has earned its words however it opens. Both fire on a
single comment; the five older nudges still need three or more, which is the hole
these two fill.

Why this was built rather than installed: nothing external covers it. The
narration rule is ported from `no-redundant-comments` in
`pertrai1/eslint-plugin-llm-core` (MIT), which is JS and TS only through ESLint's
AST and cannot run against the C# and Python here. No Roslyn equivalent exists.
The port trades the AST for line matching, so the failure mode to watch is a
false positive on a comment that genuinely explains something;
`tests/test_comment_humanness_check.py` pins that boundary.

### Swipe before you build, including for your own tooling
When the question is "how do I make Claude do X", check whether the harness or the
community already does X before writing anything. Output styles, hooks, and
settings fields already exist for most of it. Hand rolling a solution to a solved
problem is the failure this whole file is meant to prevent, and it applies to
tooling and config, not just project code.

### No machine specific paths in anything committed

Never write an absolute path, a home directory, or a username into a file that
gets committed. Not in code, not in a test fixture, not in a config file, not
in a comment, not in a doc. Derive the root instead:
`Path(__file__).resolve().parents[N]` in Python,
`$(git rev-parse --show-toplevel)` or `${CLAUDEBOOST_HOME}` in shell, and a
visible placeholder like `C:/Users/<user>` in prose.

This is the rule that already failed, twice, in this repo. Two developers' home
directories and a client's internal hostnames reached a public repository one
hardcoded line at a time, and every one of those lines looked harmless on the
machine that wrote it. `tests/test_no_machine_specific_paths.py` catches the
shape now, and its own docstring records that "a second developer's home
directory sat in three tracked files the whole time the suite was green". That
test scans only tracked files with a known suffix, so it is a net under this
rule and not a substitute for it.

The trap is that a hardcoded path is never wrong on the machine you are sitting
at. It fails on someone else's clone, in CI, and in a public diff, which is to
say it fails everywhere you are not looking. So the check is never "does this
work here", it is "what does this say about whose machine this is".

One narrow exception. A path typed into a one off Bash command during a live
session is not committed, and there it should be absolute, because Claude
Code's simple_expansion scanner prompts on a bare `$VAR` whatever the allow
list says. Use the `${BRACE}` form or a literal absolute path in that case. The
moment the same path is written into a file, the rule above applies again.

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

## OpenCode

clean-rag has an OpenCode integration too (`clean-rag/opencode/`): the same MCP
search tools, the two research agents ported as OpenCode subagents, and a
research gate plugin. Install with `clean-rag/opencode/install.py`. The gate is
enforced for the primary agent; a known OpenCode bug means subagent edits may
bypass it until upstream fixes it.

## Browser Testing Safety

Playwright and browser automation reach local machines and named test or dev
environments. Nothing else. Allowed:

- localhost, 127.0.0.1, 0.0.0.0, `::1`, and `*.local` / `*.test`
- whatever `.claude/browser-targets.local.json` names. That file is gitignored
  because your environments are nobody else's business, and
  `.claude/browser-targets.example.json` documents the shape and the rules an
  entry has to satisfy. `scripts/bash-guard.py` reads the same file, so the
  guard and this rule cannot drift apart. With no file present, only the line
  above is reachable.

Production is never in scope, and neither is any host you have not confirmed is
a test or dev environment. A hostname is not evidence on its own: `dev` in a
name proves nothing, and a shared dev environment can still hold real data. A
lower environment restored from a production snapshot is production data with a
friendlier name, so treat every write there as a write to shared state and get
approval first. Read only navigation, hovering, and screenshots are fine.

Two things stay off limits regardless. An environment's own control plane or
management dashboard is never something to browse. Corporate identity sign in
belongs to the human:
drive as far as the SSO prompt and hand over rather than entering someone's
credentials or approving their MFA.

If unsure whether a URL is in scope, ask before navigating. Default to a headed
browser, not headless.
