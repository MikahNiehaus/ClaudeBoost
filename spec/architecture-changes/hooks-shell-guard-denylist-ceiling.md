# quick-cop's Bash guard is a denylist wearing a fail-closed docstring

- **Kind:** architecture-change
- **Area:** hooks
- **Found by:** good-cop on 2026-09-08, answering the question round four was asked
- **Why it was not fixed in place:** removing a feature entirely (the broad Bash
  quick-cop can currently run), and changing a contract other files depend on.
  It is a live guard whose refusals users would notice, which `spec/README.md`
  names explicitly as coming here even when the direction is obvious.

## What is there now

Three Bash guards, two shapes.

`clean-rag/hooks/research-agent-bash-guard.py` is an **allowlist**. Ten binaries
(`SAFE_COMMANDS`, line 28), one host (`ALLOWED_HOST_RE`, line 25), and a flat
refusal of every chaining or substitution character wherever it appears
(`CHAINING`, line 44):

```python
CHAINING = re.compile(r"[;&|`\n\r]|\$\(|>>|>")
```

It has never appeared in any of the four rounds of shell-parsing findings.

`clean-rag/hooks/verify-loop-git-guard.py` is a **denylist** over one binary,
and says so at line 19: "Unlike research-agent's guard, this is a denylist, not
an allowlist: these two agents legitimately need broad Bash for builds, tests,
and static analysis." Twelve blocked git subcommands at line 49.

`clean-rag/hooks/quick-cop-bash-guard.py` is **also a denylist**, but its
docstring describes an allowlist. Lines 9 to 15:

> Fail closed by design, per an explicit user requirement: only basic, safe,
> reversible actions pass. [...] Anything that writes a file, changes git
> state, installs or removes a package, deletes or moves something, or controls
> a process or service is refused, even if this guard cannot name the exact
> command in advance, because an unrecognized command is not evidence it is
> safe.

The implementation is three enumerated sets (`_GIT_BLOCKED` line 54,
`_PACKAGE_MUTATIONS` line 64, `_BLOCKED_BINARIES` line 90) and a walk that ends
`return None` at line 198, meaning allow. An unrecognized command is allowed.
The code does the opposite of what the docstring says, on the one sentence the
docstring says is an explicit user requirement.

## Why it is a problem

This has already caused real failures, four rounds of them, and the pattern in
`spec/STATUS.md` records that each round found a different class rather than a
recurrence. Round four closed two more: a command substitution nested in a
double-quoted span was copied through as inert data, and a value-taking global
git flag walked `git commit` past quick-cop.

The reason the rounds keep coming is not that the scanner is badly written. It
is that a denylist over a shell has to enumerate two unbounded surfaces at once,
and only one of them is grammar:

**Surface one, shell grammar.** Rounds one to three. Operator delimitation,
quote termination, what is executable inside a span. A real parser would close
this surface by construction.

**Surface two, per-binary argument semantics.** Round four's second finding.
`git -C <path> commit` needs the guard to know that `-C` consumes the next
token. No parser supplies that. It is one entry per flag per binary, forever,
and the same shape exists for `npm --prefix`, `docker --context`, `sed
--expression`, and every other tool on the blocked list.

**Surface three, indirection, which neither a parser nor an enumeration can
reach.** Measured against the fixed guard on 2026-09-08, by invoking it and
reading its exit code, and confirmed to really execute in the repo's own bash:

| Command | Guard verdict | Real bash |
|---|---|---|
| `G=git; $G push origin main` | ALLOW (exit 0) | `G=echo; $G VAR_INDIRECTION_RAN` printed `VAR_INDIRECTION_RAN` |
| `eval "git push origin main"` | ALLOW (exit 0) | `eval "echo EVAL_RAN"` printed `EVAL_RAN` |
| `sh -c "git push origin main"` | ALLOW (exit 0) | `sh -c "echo SH_C_RAN"` printed `SH_C_RAN` |
| `source ./deploy.sh` | ALLOW (exit 0) | runs whatever the file contains |

These are not exotic. They are three lines of ordinary shell, and no amount of
parsing resolves a string that only exists at runtime. A denylist that allows
`eval "$x"` has no floor, whatever it enumerates above it.

So the fifth round is available today, and a sixth after it. The cost is not
only the rounds: it is that each one ends with a green suite and a stamp, which
reads as "the guard is correct" rather than "the guard is correct about the
cases someone thought of".

## What to do instead

Three decisions, and they are not the same for the three guards.

**1. quick-cop moves to an allowlist. This is the substantive change.**

quick-cop's contract is genuinely narrow, which is what makes this possible
where it is not possible for the other two: read a file, grep, run a test or
build command that already exists, report. That is a listable set. Invert
`_check_subcommand_chain` (`quick-cop-bash-guard.py:155`) so the final
`return None` at line 198 becomes a refusal, and enumerate what passes rather
than what does not:

- read binaries: `cat`, `head`, `tail`, `ls`, `wc`, `grep`, `rg`, `find`,
  `sed -n`, `echo`, `pwd`, `diff`
- test and build runners: `pytest`, `python -m pytest`, `npm test|run`,
  `yarn test`, `pnpm test`, `dotnet test|build`, `cargo test|build`,
  `go test|build`, `make` with no target that writes
- `git` restricted to read-only subcommands, which is the inverse of
  `_GIT_BLOCKED` and a shorter list
- refuse any command containing `eval`, `source`, `.`, `sh -c`, `bash -c`, or a
  variable in command position, since none of those can be judged

Failure mode inverts with it: an unrecognized command refuses and quick-cop
reports what it wanted to run, which its own `_refuse` message (line 100)
already instructs it to do. That message was written for this design.

**2. verify-loop-git-guard.py stays a denylist.** Do not invert it. bad-cop and
good-cop need arbitrary build, test and static-analysis commands across
arbitrary projects, so the allowlist would be "everything except", which is the
denylist again with worse ergonomics. Its blast radius is also bounded and
recoverable in a way quick-cop's is not: the worst case is a commit or a push,
which is the incident at line 4 of its own docstring.

**3. Do not adopt `bashlex` or any other bash parser.** It is the option that
looks strongest and is not. It closes surface one only. Round four's value-flag
finding, and all three indirection rows above, parse perfectly and mean nothing
without semantics the parser does not have. Against that it costs a third-party
runtime dependency inside a `PreToolUse` hook that must never fail to load, in a
directory that installs onto other machines, and the degradation path for a
security parser that fails to import is the hand-rolled scanner, so both would
have to be maintained. If the grammar surface alone were the problem this would
be the right answer. It is not the problem.

**4. Move the boundary that actually matters, off the machine.** The incident
`verify-loop-git-guard.py:4` exists to prevent is an agent reaching a shared
remote. A branch protection rule or a push restriction on the remote stops that
regardless of how the command was spelled locally, including through `eval`.
That is one setting, it is not bypassable by string manipulation, and it makes
the local guard what it should honestly be: a speed bump against a mistake, not
a security boundary.

Files this would touch: `clean-rag/hooks/quick-cop-bash-guard.py`, its tests in
`clean-rag/tests/test_quick_cop_guard_*.py`, and the description of quick-cop's
cage in `clean-rag/CLAUDE.md`. `shell_tokens.py` is unaffected and stays; an
allowlist still needs to find word boundaries the way a shell does.

## What it would break

- **Every command quick-cop currently runs that is not on the new list.**
  This is the real cost and it is not small. quick-cop is dispatched liberally
  and backgrounded by design, so a refusal it cannot work around costs a
  reported gap instead of an answer. The list above is a first draft written
  from the docstring, not from a measurement of what quick-cop actually runs.
- `clean-rag/tests/test_quick_cop_guard_unspaced_chaining_bypass.py` and
  `clean-rag/tests/test_quick_cop_guard_value_flag_bypass.py` both assert
  allows for read-only work (`git -C /some/repo status`, `pytest`). Those
  assertions survive an inversion only if the allowlist covers them; each is a
  case the new list has to include on purpose.
- `clean-rag/tests/test_git_guard_nested_command_substitution_bypass.py`
  asserts `echo "a > b"` is allowed. `echo` has to stay listed.
- `clean-rag/CLAUDE.md` describes quick-cop's guard behaviour and would drift
  the moment the code inverts.
- Nothing in `verify-loop-git-guard.py` or `research-agent-bash-guard.py`
  changes, so bad-cop, good-cop and swiper are untouched.

## Open questions

- **What does quick-cop actually run?** The allowlist above is derived from its
  docstring, which is the same source that already disagreed with its code. The
  honest way to build the list is to log quick-cop's real Bash commands for a
  week and enumerate from that, not from what the guard's author expects. That
  measurement does not exist yet and should probably come first.
- **Is `make` listable at all?** A Makefile target can do anything, so `make`
  is `eval` with extra steps. Same question for `npm run <script>`, which
  executes whatever `package.json` says. Both are things quick-cop plausibly
  needs and neither can be judged from the command line alone.
- **Does the branch protection recommendation belong to this project?** It is
  the highest-value item here and it is a repository setting, not code, so
  nobody reviewing `clean-rag/` will action it. It may need to live somewhere
  else entirely to get done.
- **How many more rounds is the status quo worth?** Round four's fix is real
  and its tests bite, so keeping the scanner is a defensible answer. The
  argument for inverting is not that the current code is wrong today; it is
  that its failure direction is allow, and four rounds is evidence about the
  direction rather than about any one defect.

  Answered on 2026-09-09. See below.

## Rounds five and six, and the decision to stop

The question above got answered by running two more rounds. Recorded here so
nobody starts a seventh believing it is new ground.

**Round five** fixed a real defect. `_HEREDOC_RE` demanded a newline
immediately after the heredoc tag, so any operator line with trailing content
(`cat <<EOF > f.txt`, `<<EOF | grep x`, `<<EOF 2>&1`) never matched. The body
was then scanned as command text and ordinary correct commands were refused.
Fixing it also closed a genuine bypass nobody had reported: `cat|bash <<EOF`
with no space before the pipe, where the whitespace split read `cat|bash` as
one word and never saw the shell, while bash really executed the body.

**Round six found that round five's fix opened five new bypasses.** Quoting the
reader defeated the shell check, because the operator-line split did not split
on quote characters and `_SHELL_WORD_RE` requires a word ending in `sh`:

| case | HEAD | after round five |
|---|---|---|
| `cat <<EOF \| bash` | BLOCK | BLOCK |
| `cat <<EOF \| "bash"` | BLOCK | **allow** |
| `cat <<EOF \| 'bash'` | BLOCK | **allow** |
| `cat <<EOF \| "/usr/bin/bash"` | BLOCK | **allow** |
| `cat <<EOF \| "bash.exe"` | BLOCK | **allow** |
| `cat <<EOF \| "sh"` | BLOCK | **allow** |

HEAD blocked all five **by accident**, not by design: its narrower regex failed
to recognise the heredoc at all, so the body fell through to a raw scan and the
write landed in command position. Round five made the classifier work, and a
working classifier that misjudges one word is worse than a broken one that
gives up.

Net across the two rounds: one bypass closed, five opened, three false
positives fixed. Neither version dominated the other.

### Why it does not converge

The guard answers "will this text be executed?" from a string. That is
undecidable in general, and `eval "$x"` is the one-line proof. Each round finds
a new spelling because there is no finite list of spellings.

Six rounds, six genuinely different defect classes, and two rounds that made
the guard worse before making it better. The evidence is about the approach,
not about any single regex.

### What was decided

The quoted-reader case was fixed, because it is a strict improvement over both
HEAD and round five's state, and then **patching stopped**. The user made that
call on 2026-09-09.

Do not open a seventh round to close the next exotic spelling. If a new bypass
of this shape is found, record it here and leave the code alone unless it is
reachable by an agent making an ordinary mistake rather than by deliberate
construction.

### The proportion that justifies stopping

This guard exists to stop bad-cop and good-cop running `git commit` and
`git push` when nobody asked, which is recorded in
`clean-rag/hooks/verify-loop-git-guard.py`'s own docstring as a real incident.
It is a guardrail against an agent's mistake, not a control against an
adversary.

An agent that means to push types `git push`, which is blocked in every round
of this file's history. It does not construct `cat <<EOF | "bash"`. The exotic
bypasses are cheap to find and expensive to close, and closing them protects
against a threat model this project does not have.

### What actually guarantees it

Remote-side branch protection, which is the recommendation already at the top of
this file and still the highest-value item in it. A string parser can be argued
out of its verdict. A remote that refuses the push cannot.

The open question above asks whether that belongs to this project, since it is a
repository setting rather than code. That question is now the blocking one: it
is the only remaining item here that changes the outcome.

### Round six's fix, and the two gaps left open on purpose

The quoted-reader case was closed by dequoting **only at a command name**, in a
new `_shell_reads_body_in_command_position`. The pre-existing position-blind
scan was kept, so the change only ever moves a case from allow to block.

Worth recording why the three obvious fixes were all rejected, because each
looks correct and each was measured wrong. Splitting on quote characters,
adding quotes to the shell pattern's boundary, and stripping paired quotes from
every word all close the five bypasses **and** all break
`cat <<EOF | grep "bash"`, which must stay allowed. They are position blind, and
`"bash"` as the reader and `"bash"` as grep's argument are the same token. No
position-blind rule can separate them. POSIX 2.6 applies quote removal before
2.9.1 takes the first remaining field as the command name, which is the actual
basis for dequoting at that position and nowhere else.

Reusing the file's existing `_ROUTER_PREFIX` as whole tokens closed three
adjacent bypasses for free: `VAR=1 "bash"`, `xargs "bash"` and `"ba"sh`.

**Two gaps left open, deliberately, on the last round:**

```
cat <<EOF | "/my dir/bash"     allow    quoted path containing a space
cat <<EOF | timeout 5 "bash"   allow    _ROUTER_PREFIX models `timeout \S+`
```

Both need whitespace-aware quote parsing, which is the machinery this file
already declined to import. The unquoted form of each still blocks. They are
listed here rather than fixed because they are the next spelling in an
unbounded family, and the decision above was to stop closing spellings.

**A third performance incident, same defect as the previous two.** The first
attempt reused `_in_command_position` per candidate, which copies a growing
prefix each time: 4299ms at n=8000 against a 5s bound. Segment-local reasoning
removed the look-back and brought it to 96ms, linear out to 32000 candidates on
a 160KB line. Three rounds, three catastrophic-complexity regressions in the
same file. Any future change here should be measured at n=32000 before it ships,
not reasoned about.

### A comment that overstates what the code reuses

`_ROUTER_WORD_RE` (`scripts/bash-guard.py:945`) is commented as reusing
`_ROUTER_PREFIX` (`:834`) "as whole tokens", but it adds a bare `-\S*`
alternative that `_ROUTER_PREFIX` does not have. `_ROUTER_PREFIX` allows flags
only after `xargs`.

No behavioural effect found in either direction. It cannot create a bypass: a
real shell name never matches `_ROUTER_WORD_RE`, so broadening what counts as
skippable can only make the walk reach the true command name and check it,
never skip past it unchecked. And no false positive was constructible, because
shell syntax does not put a bare flag in front of an arbitrary command name
outside the wrapper tools that already have entries.

Left as is. Recorded because the comment claims a correspondence the code does
not have, and the next reader will otherwise trust it.

### Also found while measuring, not fixed

`check_cat_heredoc` in `scripts/bash-guard.py` blocks `cat > file <<EOF` and
forces the Write tool. It allows `cat >> file <<EOF` and `tee file <<EOF`, which
are the same intent. Same rule, half enforced. Reported, out of scope for the
rounds above.

The data carve-out is load bearing and should not be removed to simplify this.
Measured: six of eight ordinary heredoc shapes would be wrongly refused without
it, including `cat <<EOF | grep x` and `python <<EOF`.
