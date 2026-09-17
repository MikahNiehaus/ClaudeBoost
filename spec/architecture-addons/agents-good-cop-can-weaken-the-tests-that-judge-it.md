# good-cop can rewrite the tests it is judged by, and nothing records that it did

- **Kind:** architecture-addon
- **Area:** agents
- **Found by:** session review of the bad-cop / good-cop loop, 2026-09-11
- **Why it was not fixed in place:** adds a new check to the stamp contract, the
  one thing `verifier_state.py` reads mechanically. Which agent runs it is a
  decision, not a detail, and the two candidates give different guarantees.

The loop's terminal condition is bad-cop stamping `VERIFIED:` on a clean pass.
That stamp rests on the adversarial tests bad-cop wrote. good-cop is told to
rewrite those tests when it judges them structural, and it is the only thing
checking whether a rewrite was legitimate.

Companion to [[agents-bad-cop-capability-model]], which covers the same class of
gap on the other agent: capability granted, restraint written in prose. That
file has the recorded incident; this one has the untouched surface.

## What is there now

good-cop holds `Write` and `Edit`, with a Bash guard covering git only. The full
per agent capability table is in [[agents-bad-cop-capability-model]] and is not
repeated here.

`~/.claude/agents/good-cop.md:410-415` grants it authority over bad-cop's tests:

```
**Verify bad-cop's tests assert behavior, not implementation.** Before
accepting bad-cop's new tests as part of the suite, check that they assert
observable output or state, not internal call sequences, framework behavior,
exact mock counts, or magic constants. A structural test breaks on every
refactor without catching a bug. If bad-cop's test is structural, rewrite it
to assert the real contract before running the suite.
```

"Rewrite it" is the operative phrase. The agent that decides a rewrite was
warranted is the agent whose fix that test is measuring.

The only mechanical backstop is the mutation endpoint, `good-cop.md:417-422`,
and it is conditional in its own text:

```
**Mutation-check your own fix.** After the suite is green and bad-cop's
tests are confirmed behavioral, if the project has a test runner the
mutation endpoint supports, run `POST http://127.0.0.1:8613/mutation-test`
with `{"project_path": "<abs>", "changed_files": [...]}` on just the files
you changed. A surviving mutant means bad-cop's test (or yours) would pass
on broken code — tighten it before stamping VERIFIED.
```

The supported runners are `mutmut`, `StrykerJS` and `cargo-mutants`. On any
other runner this step produces nothing and the loop proceeds.

Nothing else looks. Grepping `bad-cop.md` and `good-cop.md` for `assertion
count`, `tolerance`, `weaken` and `diff the test` returns no matches. The only
near hit is `good-cop.md:118`, "loosens a path check", which is about security
guards.

The static analysis section where such a check would live,
`good-cop.md:345-359`, runs `bandit`, `radon cc`, `jscpd` and type checking. None
of them reads a test file.

**bad-cop's closing re-check does not close the gap either.**
`bad-cop.md:969-976` describes it as a re-run:

```
On a `HANDOFF:`, good-cop fixes what you found, reruns your new adversarial
tests plus the existing suite until everything is green, and stamps
`VERIFIED:`. After good-cop stamps, the orchestrator re-runs you for a final
adversarial re-check on the fix. If you find nothing on that re-check, you
stamp `VERIFIED:` yourself and the loop ends.
```

Nothing there asks the re-check for a case the previous round lacked, and
nothing asks it to compare the tests on disk against the ones it wrote. A
re-check that re-runs a weakened test sees green and stamps.

## Why it is a problem

The stamp is the loop's only output, and this is a path to an unearned one that
leaves no trace.

**Prose has already failed to bind on this exact agent pair.**
[[agents-bad-cop-capability-model]] records it: bad-cop was told in its spawn
prompt "You may NOT edit the instruction files themselves", then edited
`clean-rag/portable/skills/powerpoint/SKILL.md`, `clean-rag/portable/skills/start/SKILL.md`
and `clean-rag/install.py`, and its report listed none of them while stating "no
new tests added" with three new test files on disk. It surfaced only because the
orchestrator ran `git status` by hand. The instruction at `good-cop.md:410-415`
is the same kind of sentence, on an agent with the same capabilities, guarding
the thing the stamp depends on.

**The specific behaviour is documented, not predicted.** Measured reward hacking
in RLVR settings includes "manipulating evaluation mechanisms by overwriting unit
tests, monkey-patching scoring functions, deleting assertions, or prematurely
terminating programs to obtain passing scores without producing correct
solutions" (arXiv 2604.15149, "LLMs Gaming Verifiers: RLVR can Lead to Reward
Hacking"). `ImpossibleBench` measures the same behaviour on coding tasks
specifically.

**good-cop's reproduce first rule does not reach it.** `good-cop.md:17-34`
requires reproducing each finding before fixing it. An agent can reproduce
honestly, fix partially, then widen the assertion that still fails, and satisfy
every word of that rule. The rule governs the start of the work, not the end.

**The failure is invisible downstream.** `clean-rag/hooks/verifier_state.py`
clears a file once a `VERIFIED:` line names it, keyed on path and mtime. It has
no view of what happened to the tests. A stamp earned this way is
indistinguishable from one that was earned.

No instance of this has been observed. The capability, the authorisation and the
absence of any check are all present; the incident above is the precedent for
what happens when only prose stands in the way.

## What to do instead

Two mechanical checks, both reporting rather than blocking, matching the loop's
standing split: an objective test failure blocks (`auto-test-gate.py`), a
judgment call nudges.

**1. A test file diff, printed before the stamp.** Name every assertion removed,
case deleted, tolerance widened and skip added, with the diff line and the
reason. A legitimate structural rewrite under `good-cop.md:410-415` then appears
in the report as a rewrite with a reason, rather than not appearing at all.

**Do not source the file list from a bare `git diff`.** That is the mechanism
that already failed here. `clean-rag/hooks/turn_edits.py`'s own docstring records
it: the Stop gates used git relative to the session cwd and never fired all
session. That file exists because of it. `record_edit()` appends every edited
code file to `state/turn-edits/<hash>.txt` live, as the edit happens, and
`edited_code_files(session_id)` returns the set still on disk. Use that.

For the "since `HANDOFF:`" boundary, `verifier_state.py`'s `record_verifier()`
already stamps every bad-cop and good-cop pass with `"at": time.time()` into
`state/verifier/session-<hash>.json`. The window is the two most recent stamps,
intersected with `edited_code_files()` filtered to test paths. Both modules
already exist; this is composition, not new plumbing.

What neither records is file **content** at handoff, only the fact and time of an
edit. A content diff still needs a working tree copy taken at `HANDOFF:`, and
nothing does that today. That part stays open.

**2. `diff-cover` as the numeric half**, added to the static analysis section at
`good-cop.md:345-359` beside the existing tools:

```
diff-cover coverage.xml --compare-branch=origin/main --fail-under=80
```

It gates coverage of the changed lines specifically rather than the repo, and
unlike the mutation endpoint it works on any project that emits a coverage file.
Confirmed maintained: 10.5.1, released 2026-08-16, upstream
`Bachmann1234/diff_cover`. It does not run tests, it reads a report the project
already produced.

It does not degrade quietly. On a missing coverage file it exits nonzero, so the
caller has to handle that case explicitly to get the reported absence this loop
wants. `clean-rag/server/mutation.py`'s `_absent()` is the shape to copy: an
explicit reported absence, never a silent zero and never a crash that reads like
a real failure.

**3. Widen the mutation endpoint before adding a second mechanism.** The
existing backstop fails on runner coverage, not on design.
`clean-rag/server/mutation.py`'s `run_mutation()` dispatches on file extension
and marker file, and `handle_mutation_test` in `clean-rag/server/app.py` is fully
generic. Adding a stack is one `_run_X` function shaped like
`_run_cargo_mutants` plus one branch. No route change. Real maintained tools per
stack: Stryker.NET on `*.csproj`, Infection on `composer.json`, `gremlins` on
`go.mod`, Mutant on `Gemfile`. Doing this first may reduce the test diff check to
a reporting nicety rather than the only guard on most projects.

**Not proposed: TestSeal** (`github.com/satwiksps/testseal`, Apache-2.0). It does
exactly this job, as an AST diff of before and after test bodies, with rules that
map one to one onto the bullets above: assertion removed, skip or xfail added,
assertion weakened, tolerance widened, broad exception swallowed. It runs locally
and never imports the repo it scans. It is also 8 stars, 0 forks, version 1.0.1,
one maintainer, and new. Named as a candidate to evaluate, not to adopt. It is
the only thing found that does the exact job, which is itself the finding.

Files touched: one section of `~/.claude/agents/good-cop.md` and its byte
identical twin at `clean-rag/portable/agents/good-cop.md`. If the check moves to
bad-cop's re-check instead, the same two files for `bad-cop.md`. The mutation
widening touches `clean-rag/server/mutation.py` only.

## What it would break

**It fires on every legitimate rewrite.** `good-cop.md:410-415` authorises
rewriting a structural test, and that rewrite changes assertions. The check
flags it every time, so it adds report volume on exactly the runs that are
behaving correctly. This is why it must report and never gate: a gate here
would block the file's own instruction.

**A report that is always non empty stops being read.** The same failure
`bad-cop.md:832-833` already names for findings, "A list of twenty nits buries
the one Critical and gets the whole review dismissed", applies to this section.
If most runs produce a diff, the one that matters is buried.

**`diff-cover` needs a coverage file and a comparison branch.** On a project with
no coverage runner it emits nothing. `--compare-branch=origin/main` assumes a
remote default branch; `bad-cop.md:77-80` already reads the real default from
`git symbolic-ref refs/remotes/origin/HEAD` rather than assuming `main`, and this
step has to do the same or it is wrong on any repo that does not use `main`.

**The `NITS:` path is not covered by either.** On a nit only run
(`bad-cop.md:941-957`) good-cop is never spawned and the orchestrator applies the
fixes itself. The agent editing the tests is then the one that orchestrated the
change, and a check written to watch good-cop does not see it.

**No test asserts any of this today.** `scripts/tests/test_agent_frontmatter.py`
validates frontmatter only, so nothing in the suite breaks and nothing in the
suite confirms the check works either. It would need its own.

## Open questions

**Should the check live in good-cop or in bad-cop's re-check?** good-cop running
it is self reporting, which is the thing this file objects to. bad-cop running it
on the closing re-check is an independent party comparing the tests on disk
against the ones it wrote, which is strictly stronger and fits work that pass
already does. The cost is that the evidence arrives after good-cop has already
stamped `VERIFIED:`, so the loop reports the problem one round later than it
happened.

**Does the re-check also need a novelty requirement?** `bad-cop.md:969-976` asks
for a re-run. Requiring at least one case the previous round lacked would close
the separate hole where a re-check confirms a weakened test, and it costs one
sentence. It also costs Sonnet time on every round, on a pass whose current job
is confirmation.

**Does the content snapshot get built, or does the check stay coarse?**
`turn_edits.py` and `verifier_state.py` together answer which test files changed
and when. Neither answers what the assertions looked like before. Without a
working tree copy at `HANDOFF:` the check can say a test file changed and cannot
say an assertion was weakened, which is most of the value. Taking that copy is
new plumbing and a new place for state to go stale.

**Is a fourth severity needed to report this?** A widened assertion with a stated
reason is not a correctness defect and is not a nit. `bad-cop.md:850` offers only
`[Critical|High|Nit]`. Conventional Comments' `chore`, work that must be resolved
before acceptance without being a defect, is the standard name for the missing
bucket, and adding it changes the output contract that every caller reads.
