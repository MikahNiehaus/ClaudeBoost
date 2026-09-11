# The install-time sync from `portable/` to `~/.claude/` exists but is silently skipped

- **Kind:** architecture-change
- **Area:** the whole instruction layer (CLAUDE.md, agent defs in
  `~/.claude/agents/` + `clean-rag/portable/agents/`, skills in
  `~/.claude/skills/` + `clean-rag/portable/skills/`), plus `clean-rag/install.py`
- **Found by:** bad-cop (instruction-layer review) on 2026-09-07
- **Why it was not fixed in place:** running the installer to close today's gap
  is a normal action, not a spec item, and is noted below. This file is about
  the standing gap in the mechanism itself: a manually-triggered, silently-
  skippable sync is not a durable fix for content that needs to stay in lock
  step, and closing that gap for good is a design decision, not a bounded
  edit — exactly the "genuine bloat/architecture" case the review brief
  called out in advance.

## Correction to this file's first draft

An earlier version of this file claimed "there is no sync step anywhere."
That was wrong, and the record should say so rather than quietly fix it: a
background grep that had stalled earlier finished after this file was
already written, surfaced `clean-rag/install.py`, and reading it in full
overturned the claim. A real mechanism exists. What follows is the corrected
finding.

## What is there now

`clean-rag/install.py::install_user_assets()` (lines 132-195) treats
`clean-rag/portable/` as canonical and copies it into `~/.claude/` on every
install run:

```python
# The global instructions describing the research gate and the agents. Both
# this installer and ClaudeBoost's setup.py (which delegates here) keep it
# current. A newer local edit is preserved by _copy_file, so hand tweaks
# survive a re-install.
_copy_file(portable / "CLAUDE.md", CLAUDE_DIR / "CLAUDE.md")
...
for md in (portable / "agents").glob("*.md"):
    _copy_file(md, CLAUDE_DIR / "agents" / md.name)
...
skills_src = portable / "skills"
if skills_src.is_dir():
    shutil.copytree(skills_src, CLAUDE_DIR / "skills", dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("__pycache__"))
```

`CLAUDE.md` and every file under `agents/` go through `_copy_file`
(lines 140-170), which is deliberately conservative: if the destination's
mtime is newer than the source's, it skips the copy entirely and prints a
diagnostic instead of overwriting a hand edit —

```python
if dst.exists() and dst.stat().st_mtime > src.stat().st_mtime:
    drift = _differing_lines(src, dst)
    if drift == 0:
        return
    extent = f"{drift} lines differ" if drift > 0 else "content unreadable"
    _warn(
        f"{dst.name} in ~/.claude is newer than the repo copy and {extent}, "
        f"leaving it. Nothing here will overwrite it; reconcile by hand:"
    )
```

— and `clean-rag/tests/test_install_user_asset_copy.py` proves this
diff-reporting behavior directly (`test_skip_reports_how_far_apart_the_two_copies_are`),
with a docstring that names this exact failure by name: *"A skip announced as
a bare 'leaving it' reads as a no-op, which is how `~/.claude/CLAUDE.md` came
to sit hundreds of lines away from `clean-rag/portable/CLAUDE.md` with every
install run saying nothing useful about it."* That test file's own history is
evidence the CLAUDE.md drift found in this review is not new — someone
already caught and partially fixed one symptom of it (silent skip →
diff-count warning), and the underlying mtime-gated skip is still exactly
the mechanism that produced this round's drift.

**Skills use a different, non-gated copy path.** `shutil.copytree(...,
dirs_exist_ok=True)` overwrites every destination file unconditionally on
every install run, with no mtime check and no drift warning at all. This is
the reason every `SKILL.md` pair checked in this review came back byte-
identical (`bad-cop`, `good-cop`, `start`, `powerpoint`, `grill-me` — all
diffed clean) while `CLAUDE.md` and the two agent files did not: skills
cannot drift because they are force-synced every run; `CLAUDE.md` and agents
can drift indefinitely because the sync silently defers to whichever copy
was touched most recently.

This also explains the two orphaned agent files found elsewhere in this
review (`triage-agent.md`, `verifier-agent.md`, reported separately as
findings): the agents loop only copies `.md` files that currently exist
under `clean-rag/portable/agents/` and never deletes anything from
`~/.claude/agents/` that isn't there. An agent removed from the portable set
stays on disk in `~/.claude/agents/` forever, orphaned, regardless of how
many times the installer runs.

Given the mechanism, the drift found in this review is now explained rather
than mysterious:

- `bad-cop.md`: 153 diff lines between the two copies. Each side has content
  the other lacks. The portable copy alone has "Walk the trap table" (a
  `traps` skill invocation), a caller-sweep requirement, and a
  `debugging-methodology` invocation. The global copy alone has "Never name
  anything after yourself or this process," "Ambient environment: run it
  scrubbed," "Two legal forms, and there is no third," "A failing check made
  to pass by weakening it," and the "audit how green was reached" re-check
  guidance.
- `good-cop.md`: 120 diff lines. The portable copy alone has a
  `debugging-methodology` invocation and the "Grounding:" required-citation
  line. The global copy alone has "Never name anything after yourself or
  this process," "Hard stop: green is earned, never bought," and "Two legal
  forms, and there is no third."
- Root `CLAUDE.md` (project) vs global `CLAUDE.md` (`~/.claude/CLAUDE.md`):
  244 diff lines. But this is a three-file chain, not two: root and
  `clean-rag/portable/CLAUDE.md` already agree on the sections root has and
  global lacks ("The fix is good-cop's job, not yours," "good-cop researches
  before it fixes," the ambient-environment scrubbing lesson, "Debugging,
  testing and QA," "UI / Frontend Work" — confirmed present in `portable/
  CLAUDE.md` too by direct read). So someone already hand-forward-ported
  those from root into the canonical `portable/` copy. What broke is the next
  hop: `install.py`'s mtime-gated copy from `portable/` to `~/.claude/` never
  carried them across, because `~/.claude/CLAUDE.md` also contains two
  sections portable does not have ("Calling it correctly," "Plain writing" —
  confirmed absent from `portable/CLAUDE.md`), meaning `~/.claude/CLAUDE.md`
  was hand-edited directly at some point. That edit gave it a newer mtime
  than `portable/CLAUDE.md`, so every install run since has hit exactly the
  `_copy_file` skip branch quoted above and silently left the five sections
  unpropagated. This is not a guess: it is the specific failure the quoted
  test docstring names, reproduced.
- `clean-rag/CLAUDE.md`'s own description of the bad-cop/good-cop loop
  ("## bad-cop and good-cop") never picked up the "reproduces a finding
  before it fixes it" contract that the other three `CLAUDE.md` files
  already carry, even though that contract is a correctness property of the
  same loop this file is documenting.

For `bad-cop.md`/`good-cop.md`, the same mechanism explains the two-way
divergence directly: both copies go through the identical mtime-gated
`_copy_file`. Once someone hand-edits `~/.claude/agents/bad-cop.md` even
once, its mtime moves ahead of the repo copy's, and the installer preserves
that edit forever afterward — including if the *portable* copy then receives
a different, unrelated addition next. Both sides keep changing; the copy
step keeps deferring to "whichever was touched more recently"; nothing ever
merges the two. Two-way drift is the expected steady state of this
mechanism once both sides are ever hand-edited even once each, not a
surprising anomaly.

## Why it is a problem

The sync exists, but three things make it ineffective as an actual parity
guarantee:

1. **It only runs when a human runs `python clean-rag/install.py` by hand.**
   Nothing triggers it automatically, so any drift between installs persists
   for however long the human goes without re-running it.
2. **Its warning is a print statement in installer stdout**, not a test
   failure, not a hook, not anything that shows up unless someone is reading
   the installer's own output at the moment it runs. The quoted test file
   already proves the warning fires correctly; nothing proves anyone reads
   it. A silent skip that now prints a line nobody is watching for is a
   smaller failure than a fully silent skip, not a fixed one.
3. **It has no merge capability, only skip-and-report.** Even a human who
   reads the warning has to open both files and manually reconcile by hand;
   the tool that detected the drift cannot resolve it.

The result is exactly what this review found: whichever copy actually
governs a given session depends on which one was hand-edited most recently,
not on which one is more complete. Every rule found only on one side is
real: an anti-self-patch rule, a "green is earned not bought" guardrail
against silently weakening a failing test, a real measured bug's lesson (the
ambient-environment scrubbing requirement), and a self-naming leak guard
that matters most on the `portable/` copy specifically, since that is the
one that ships into other people's codebases and would leave
`bad-cop`/`P13_`-named test files behind in someone else's repo if the guard
is the copy that is missing.

This will keep recurring at the same rate indefinitely. The mechanism that
exists to prevent it depends on a human noticing an installer's stdout, and
that dependency has already failed at least once, per the test file's own
docstring, before this review ever started looking.

## What to do instead

The instances found today are reported as normal findings and go to good-cop
to reconcile by hand this round (both directions, per file — see the
sibling findings). Reconciling them does not touch this gap: the moment
either side is hand-edited again, `_copy_file`'s mtime check will silently
defer to it again, exactly as it did this time. The standing question is
what closes that gap, roughly in order of how much it changes:

1. **A parity test using the tool that already exists.** `install.py`
   already has `_differing_lines()`, proven correct by
   `test_install_user_asset_copy.py`. A test that imports it (the way that
   test file already does — `load_installer()` loads `install.py` by path)
   and asserts `_differing_lines(portable_file, installed_file) == 0` for
   every `CLAUDE.md`/`agents/*.md` pair, run in CI or by a pre-commit hook,
   turns the exact condition the installer already detects and silently
   accepts into a red test nobody can miss. This is the cheapest option
   because the diffing logic is already written and already tested; only the
   assertion wrapper is missing. Same shape of fix
   `clean-rag/tests/test_skill_rag_routes.py` already applies to route names
   (named directly in the review brief as the existing precedent).
2. **Make the installer's warning impossible to miss**, short of a full
   parity test: have `install.py` exit non-zero (or print a single
   impossible-to-miss summary line) when it found any drifted file, instead
   of a per-file `_warn()` buried among dozens of other install lines. Weaker
   than option 1 because it still depends on someone actually running the
   installer, but cheaper than adding a new test file.
3. **Change the conflict policy itself**, structurally addresses it: replace
   "whichever side has the newer mtime wins, silently" with something that
   cannot silently discard either side — for instance, refuse to skip at all
   and instead always print the diff and require an explicit flag to
   proceed, or track a content hash of what the installer last wrote instead
   of relying on mtime (mtime is flagged as an unreliable freshness signal in
   the installer's own comments, citing apenwarr and moby/moby#9391; a hash
   comparison sidesteps that same weakness the reporting already works
   around). This removes the mechanism's core weakness rather than adding a
   test on top of it, but is the largest change of the three and needs a
   decision on what "conflict" should mean when both sides changed.
4. **Do nothing, rely on periodic manual audits** (a review like this one) to
   catch drift. Not recommended: the drift found today was already
   safety-relevant on three separate files, and the installer's own test
   file shows this exact failure mode was already found and only half-fixed
   once before.

## What it would break

- Option 1 (a parity test) could go red immediately on the very findings
  this review is reporting, before good-cop reconciles them. That is
  arguably correct (the test is supposed to catch exactly this state), but
  means it should land after the reconciliation, or be written to skip
  cleanly until then, so it does not read as a new failure introduced by
  this review.
- Option 3 (changing the conflict policy) directly affects the documented
  guarantee in `install_user_assets()`'s own comment: "A newer local edit is
  preserved by `_copy_file`, so hand tweaks survive a re-install." Any
  redesign has to decide whether that guarantee still holds, and for whom —
  a user who intentionally customized their own `~/.claude/CLAUDE.md` has a
  legitimate reason for permanent local drift that a project's own
  `bad-cop.md` does not.
- `clean-rag/portable/CLAUDE.md` and the user's global `CLAUDE.md` are not
  actually meant to be identical in every paragraph — global's "Calling it
  correctly" and "Plain writing" sections read as legitimate local content
  (the latter is explicitly about the user's personal output-style
  preference), not accidental drift. A parity test on `CLAUDE.md` specifically
  would need to scope to a shared subsection rather than the whole file, or
  it will flag legitimate local content as a false positive on day one.

## Open questions

- Is the "hand tweaks survive a re-install" guarantee still wanted for
  `CLAUDE.md`, or only for agents/skills where identical behavior across
  installs actually matters? The review found no documented answer either
  way, and the two files may reasonably want different policies.
- For the `CLAUDE.md` files specifically: should the shared "Verify by
  running" / bad-cop / good-cop / quick-cop section be factored into one
  file that root, `clean-rag/portable/CLAUDE.md`, and `clean-rag/CLAUDE.md`
  all `@import` or otherwise include, leaving only genuinely local content
  (global's user-wide preferences, `clean-rag`'s server internals) in each
  file? That would remove the duplication at its root instead of syncing
  copies of it, but it is a bigger structural change than anything else in
  this file and needs its own decision.
- Should option 1 (the parity test) ship regardless of which longer-term
  option is chosen, as a stopgap that at minimum turns the next drift into a
  visible failure? This review recommends yes, cheaply, independent of the
  larger decision, but leaves the call to the human since it still requires
  someone to write and land a test that does not exist today.

---

## Measured, 2026-09-08

The divergence was described in this file without numbers. Measured across all
three copies, ignoring line-ending differences:

| Pair | Sizes | Differing lines |
|---|---|---|
| `clean-rag/portable/CLAUDE.md` vs `~/.claude/CLAUDE.md` | 570 vs 611 | **361** |
| `CLAUDE.md` vs `~/.claude/CLAUDE.md` | 665 vs 611 | **232** |
| `CLAUDE.md` vs `clean-rag/portable/CLAUDE.md` | 665 vs 570 | **255** |

**It is three-way, not two-way. No two copies agree with each other.**

The copy that actually governs behaviour in every project on this machine is
`~/.claude/CLAUDE.md`, the middle one, which is closest to neither the shipped
artifact nor the project's own file.

Confirmed independently by two sessions working on this repository at the same
time and unaware of each other. A concurrent session's good-cop found the same
drift while fixing `install.py`'s reporting, and reached the same conclusion this
file already records: reconciling it is a merge of hand-written variants and not
an agent's call to make.

## What made it invisible

`clean-rag/install.py::install_user_assets()` does sync these files, and skips
when the destination is newer than the source. That skip is deliberate and
correct: a local edit should survive a re-install. What was missing is that it
printed one bland line and said nothing about how far apart the two had grown, so
361 lines of divergence accumulated behind a message that read like routine.

That reporting has since been improved by the concurrent session, which added a
`_differing_lines()` helper so the skip now names the extent of the drift. The
skip direction is unchanged. The divergence itself is still there and still
unreconciled.

## Why this is worse than ordinary duplication

These files are not documentation about the system, they are the system's
instructions to itself. A rule that exists in one copy and not another is a rule
that applies in some sessions and not others, with nothing to indicate which.
This session found five sections present in the project root file and absent from
the global one, including the anti-self-patch rule and the recorded lesson from a
real bug where an ambient `.env` value made four separate reviewers pass a broken
change. The global file is the one with wider reach.
