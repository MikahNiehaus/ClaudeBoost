# Repo layout: what may move, what may not

- **Kind:** architecture-change
- **Area:** repo-wide
- **Written:** 2026-09-25
- **Status:** proposed, nothing applied

This is a reorganisation spec, not a spec-folder item. The three folders under
`spec/` hold one architectural finding each; this file is cross-cutting and sits
beside `README.md` and `STATUS.md` for that reason.

## The rule that makes a reorg safe

A path in this repo is either referenced by something outside the repo or it is
not. That single split decides the whole plan, because everything that can break
a live session is on one side of it.

Four path prefixes are **frozen**. Nothing inside them moves, gets renamed, or
changes case:

| Frozen prefix | Who holds the reference | What breaks if it moves |
|---|---|---|
| `scripts/*.py` | `~/.claude/settings.json` hook commands, written as `"$CLAUDEBOOST_HOME/scripts/<name>.py"` (`scripts/setup.py:406`) | Every hook firing that script errors until the user re-runs `scripts/setup.py` |
| `clean-rag/hooks/*.py` | Same mechanism, `base_dir="clean-rag/hooks"` (`scripts/setup.py:774`) | Same |
| `.claude/commands/` | `~/.claude/commands` is a symlink to this directory (confirmed on disk: `commands -> <clone>/.claude/commands/`) | Every slash command in every project disappears the moment the directory is renamed. No re-install is needed to break it, and none to notice |
| `clean-rag/portable/` | `clean-rag/install.py::install_user_assets()` copies agents and skills from here into `~/.claude/agents/` and `~/.claude/skills/`. `scripts/setup.py::install_clean_rag()` runs that installer as a subprocess, so setup.py is the entry point but not the copier | The next install copies nothing, or copies a stale tree. The current session keeps working, so the breakage stays invisible until someone else installs |

The repo root itself may move. `~/.claude/claudeboost-home.txt` holds
the clone path and `$CLAUDEBOOST_HOME` resolves from the setup
script's own location, so relocating the clone and re-running setup is
supported. Moving a file within the clone is what is not.

Everything outside those four prefixes is free to move, and that covers every
piece of mess actually worth fixing.

## What is there now

Counted 2026-09-25: 701 tracked files, 4413 tests collected from the root.

### Stray artifacts at the repo root

`detector-blocked-login.png` and `quillbot-result.png` are tracked. Both are QA
screenshots from a finished session.

`~/.claude/pipe-down/denials.json` is tracked, inside a directory literally
named `~`. A shell expanded `~` as a relative path and the result was committed.
`.gitignore` cannot catch this class, because the name reads as a home directory
to a person and as an ordinary folder to git.

`results/` is empty and untracked. `pip/` is a gitignored cache directory
sitting in the root listing.

### `plans/` is scratch that the test suite runs

Seven tracked files: `debug_mcp_refs.py`, `test_install_qa_tools.py`,
`test_presentation_env.py`, `test_skill_frontmatter.py`,
`test_walkthrough_url_validation.py`, and two `.js` walkthrough probes.

`pytest.ini` excludes `workspace` from collection but not `plans`, so a root run
collects 37 tests out of `plans/`. `clean-rag/hooks/auto-test-gate.py` is the one
Stop hook that genuinely blocks on a red suite, so a scratch file someone left in
`plans/` can block a turn on unrelated work.

This is also the directory the research gate exempts: `plans/` is named in the
exempt list in the canonical `CLAUDE.md`. Files land there precisely because
nothing is watching them.

### Three test suites, plus an undeclared fourth

Collected from the repo root and grouped by path prefix: `scripts/` 2151,
`clean-rag/` 1782, `tests/` 443, `plans/` 37, summing to the 4413 total.

Those numbers hold only for a root run. Collecting each directory scoped to
itself gives 2127, 1782, 442 and 37, which sums to 4388. The 25 test gap is a
different rootdir producing a different collection, not flakiness; both counts
reproduce. Any check phrased as a count has to say which run it means, which is
why the checks below do.

The collision between the first three already has an entry at
`spec/architecture-changes/tests-three-suites-cannot-run-together.md`. This spec
does not duplicate it and does not merge them. It removes only the undeclared
fourth.

Two test files also sit loose in `scripts/` rather than `scripts/tests/`:
`scripts/test_human_voice_guard_adversarial.py` and
`scripts/test_memory_watcher.py`. Nothing outside those files names either one.

### Documentation scattered across three levels

`docs/` holds seven guides at the root. `clean-rag/` holds four more as loose
top-level markdown: `DEPRECATION_PLAN.md`, `FORCED_INJECTION_SPEC.md`,
`OPENCODE_SETUP.md`, `PORTABLE_SETUP.md`. `clean-rag/opencode/` holds two more.
No rule says which level a document goes to.

### Scripts inside a state directory

`state/` is gitignored runtime state and contains three Python files:
`cb_branch_check.py`, `cb_detect_device.py`, `fix_computer_agnostic.py`. Being
gitignored, they exist on one machine and in no history.

### Single use maintenance tools at the `clean-rag/` root

`fix_boat_bug.py` and `fix-boat-bug.bat` sit beside the package. Nothing imports
them. `clean-rag/server/app.py:924` and
`clean-rag/tests/test_exec_routes_require_registered_project.py:426` reference
`fix_boat_bug.py` in comments only. `debug-install.py` and `debug-uninstall.py`
are referenced by nothing at all.

## Why it is a problem

The measurable cost is the test gate. 37 scratch tests in `plans/` run inside the
hook that blocks a turn, so abandoned scratch can stop unrelated work. That is
not a prediction: `pytest.ini`'s own docstring records the same failure already
happening once with `workspace/`, and the fix stopped at that one directory.

The rest bites more slowly. A root listing mixing two QA screenshots, an empty
`results/`, a pip cache and a directory named `~` trains a reader to stop reading
the root listing, which is where a genuinely wrong file would show up. Three
documentation levels with no rule means the next document goes wherever the
writer happened to be standing.

## What to do instead

Five phases, ordered by blast radius. Each is independently revertible and each
names its own check. No phase touches a frozen prefix.

### Phase 1: delete what nothing reads

Everything in this phase is provably dead. Each line carries the evidence that
makes it safe, because "nobody seems to use it" is not evidence and is how a live
hook gets deleted.

#### Stray artifacts

| Delete | Evidence |
|---|---|
| `detector-blocked-login.png` | Tracked QA screenshot from a finished session. No reference in the tree |
| `quillbot-result.png` | Same |
| the `~` directory and `~/.claude/pipe-down/denials.json` under it | A shell expanded `~` as a relative path and the result was committed. Nothing reads it |
| `results/` | Empty and untracked. A local tidy, no commit |

Removing the `~` directory is the human's to run in a terminal, with the path
spelled out explicitly and read before pressing enter. The literal character in
that name is the one shape a shell expands into a home directory, and
`scripts/bash-guard.py` blocks the recursive form of that command on purpose.

Then add to `.gitignore`:

```
# A shell expanded ~ as a relative path once and the result got committed.
/~/
```

`pip/` stays. It is already ignored, and moving a cache buys nothing.

#### Scripts that serve a tree which no longer exists

`mcp-rag-server/` was deleted. These files exist only to serve it, so they cannot
run and produce nothing:

| Delete | Evidence |
|---|---|
| `scripts/fix-graph-resolution.py` | Line 6 puts `mcp-rag-server/src` on `sys.path`, then lines 8 to 10 import `rag_server.core.project`, `rag_server.adapters.sqlite_graph_store` and `rag_server.indexing.engine`. That package is gone, so the file raises `ImportError` on any run |
| `scripts/download_csharp_benchmark.py` | Writes to `mcp-rag-server/tests/data/codesearchnet_csharp_full.jsonl`. `git grep` returns only itself and its spec entry |
| `scripts/download_csharp_github.py` | Same output path, same result |
| `scripts/download_codesearchnet_full.py` | Same output path. `README.md` no longer names it; `git grep` returns only itself and its spec entry |

`spec/bloat/scripts-duplicate-csharp-benchmark-downloaders.md` filed the three
downloaders as needing a judgment call about which to keep. That judgment is no
longer needed and the spec entry should be updated to say so: the bar in
`spec/README.md` has a deprecation exception for exactly this, that removing
something naming a subsystem which no longer exists is a fix rather than a
decision. The decision was made when `mcp-rag-server/` was deleted.

One thing to handle in the same commit: `download_csharp_github.py` is named in
the `KNOWN_UNFIXED` set at `clean-rag/tests/test_python_floor_compatibility.py:72`.
That set is used as a subtraction at line 174 (`offenders - KNOWN_UNFIXED`), so a
stale entry for a deleted file is harmless and the test does not fail. Remove the
line anyway, or it becomes a reference to a file nobody can find.

#### Scripts nothing registers or imports

| Delete | Evidence |
|---|---|
| `scripts/proc_utils.py` | Zero inbound references. `git grep -n "proc_utils"` across the whole tree returns nothing at all, including by module name |
| `scripts/strip-claude-attribution.py` | Count 0 in `.claude/settings.json`, `~/.claude/settings.json`, `scripts/setup.py` and `clean-rag/install.py`. It is a hook that was never registered |

Check both by module name as well as filename before deleting. A Python import
reads `import proc_utils`, not `proc_utils.py`, so a filename grep alone produces
a false positive and would have here.

**Check:** `git status` clean, the three suites still green, and
`python scripts/check-hooks.py` reports no registration pointing at a missing
file.

### What must not be deleted, though it looks dead

This list is the other half of Phase 1 and is the reason the phase is safe to
run. Four files match every mechanical signal for dead code and every one of
them would cost something real.

`clean-rag/hooks/proof-gate.py` and `clean-rag/hooks/rag-search-on-edit.py` are
1376 and 1415 byte files that do nothing but `sys.exit(0)`. Both open with
"PLACEHOLDER. Does nothing. Exits 0. This file exists so a branch switch cannot
brick Claude."

Be precise about why they stay, because the obvious reason is not the true one.
Neither name appears in this machine's `~/.claude/settings.json` or in
`.claude/settings.json`, count 0 in both, so on this machine the stubs are
currently inert. They are not protecting a live registration here.

They protect other machines. Hook commands live in the global settings file and
survive a checkout, so a registration pointing at a missing script makes python
exit 2, which Claude Code reads from a PreToolUse hook as "block this tool call".
The uninstallers carry these names in their legacy removal lists, which is the
evidence that stale registrations under them are real and still out there on
installs that have not been refreshed. `clean-rag/uninstall.py:40-41` lists both;
`scripts/uninstall.py:141` lists `proof-gate.py` only, so a stale
`rag-search-on-edit.py` registration survives that uninstaller. Deleting the stub turns any such
registration into a hard block on every Edit, Write and Bash.

So the cost of keeping them is 2.7KB, and the cost of deleting them is someone
else's session refusing every tool call. That asymmetry is the argument, not
current registration.

`scripts/action-gate.py` is registered nowhere, confirmed count 0 in both
settings files and in `setup.py`. It is dead on purpose: its hook registration
was removed at the user's own request, recorded in
`clean-rag/state/proof-log.jsonl` on 2026-07-06, and the canonical `CLAUDE.md`
says not to register it again to make the list tidy. A deliberate dead branch is
a decision, so deleting it needs the human who made that decision.

`scripts/telemetry-skill-hook.py` is registered nowhere either, count 0 in both
settings files. `spec/bloat/scripts-two-dead-files-in-the-hook-directory.md`
filed it deliberately "so the second one gets a decision rather than a delete,
because it is a working feature nobody connected". It is finished code that
tracks skill invocations and imports `telemetry_writer.py` correctly. Either wire
it up or drop it, but that is a call about whether the feature is wanted.

The general shape: a file is safe to delete when nothing reads it **and** nothing
outside the repo names it. The four above fail the second test, and it is the
test a grep cannot perform, because the reference lives in a settings file on a
machine or in a decision in a log.

### A live bug this sweep surfaced, filed not fixed

Two registered hooks compute a path into the deleted tree:
`scripts/rag-read-guard.py:62` and `scripts/rag-statusline.py:42` both build
`<repo>/mcp-rag-server/.rag-index`. `rag-read-guard.py` is wired to `Read` and
`Grep` in `.claude/settings.json`, so it runs constantly against a directory that
does not exist.

That is a correctness bug, not a layout problem, and fixing it is out of scope
here. It is recorded because the sweep found it and because it shows the
difference this spec turns on: a live file with a stale string gets fixed, while
a file that exists only to serve the stale thing gets deleted.

The scale of the first kind, counted separately because the two terms do not
overlap the way a single grep suggests: 36 files mention `8612`, 37 mention
`mcp-rag-server`, and the union is 59. Use 59 for any completeness check. Most of
those 59 are live files carrying a stale string, not deletion candidates.

### Phase 2: stop collecting scratch

Add `plans` to `norecursedirs` in `pytest.ini`, beside `workspace`, with the same
reasoning the existing comment already gives for `workspace`.

Then decide per file, not in bulk. `test_skill_frontmatter.py` and
`test_install_qa_tools.py` read like real checks that belong in `tests/`.
`debug_mcp_refs.py` and the two `.js` probes read like finished scratch. Read
each one before moving it.

**Check:** a root `python -m pytest --collect-only -q` drops from 4413 to 4376,
and the `plans/` group disappears from the per-prefix count. Use the root run for
this, not a scoped one: a scoped run collects a different total, as recorded
above.

**What this breaks:** nothing references `plans/*` by path. The directory keeps
its role in the research-gate exempt list in `CLAUDE.md`.

### Phase 3: move the two loose test files

`scripts/test_human_voice_guard_adversarial.py` and
`scripts/test_memory_watcher.py` move into `scripts/tests/`.

**What this breaks:** these are the only two files under `scripts/` matching
`test_*.py` that are not hook scripts, so no hook command names them. Confirm
with `git grep -n "scripts/test_memory_watcher\|test_human_voice_guard_adversarial"`
before and after. Today it returns the two files themselves and nothing else.

**Check:** total collected count unchanged, `scripts/` count unchanged.

### Phase 4: one rule for documentation

The rule: a document lives at the level of the thing it describes.

Repo-wide guides stay in `docs/`. Anything describing the clean-rag server, its
install, or its ports moves to `clean-rag/docs/`, which means
`DEPRECATION_PLAN.md`, `FORCED_INJECTION_SPEC.md`, `OPENCODE_SETUP.md` and
`PORTABLE_SETUP.md` leave the `clean-rag/` root.

`clean-rag/CLAUDE.md` and `clean-rag/portable/CLAUDE.md` do not move. Claude Code
loads `CLAUDE.md` by directory position, so relocating either one stops it
loading and nothing reports the loss.

**What this breaks:** `git grep -l "docs/[A-Z]"` currently returns 17 files,
including `README.md`, `spec/STATUS.md`, four `spec/` entries and
`scripts/audit-hooks.py`. Every cross-reference to a moved document has to be
updated in the same commit. `tests/test_no_dead_architecture_claims.py` is the
test most likely to notice a stale reference; run it after.

**Check:** `git grep -n "DEPRECATION_PLAN\|FORCED_INJECTION_SPEC\|OPENCODE_SETUP\|PORTABLE_SETUP"`
returns no path that no longer exists.

### Phase 5: the single use tools

`fix_boat_bug.py`, `fix-boat-bug.bat`, `debug-install.py` and
`debug-uninstall.py` move to `clean-rag/tools/`, or get deleted if the bug they
fix is gone.

**What this breaks:** two comment references, at `clean-rag/server/app.py:924`
and `clean-rag/tests/test_exec_routes_require_registered_project.py:426`. They
are comments, not imports, so the code keeps working while the prose goes stale
silently. Update both in the same commit or the move costs more than it returns.

`state/*.py` is a separate call and not part of this phase. Those three files are
gitignored, so they exist on one machine with no history. Read them first: live
tooling belongs in `scripts/`, which freezes it, and dead tooling should go. Do
not move them blind.

## What it would break

The full list, so the risk sits in one place.

Phase 1 breaks one line of one test, and only cosmetically:
`clean-rag/tests/test_python_floor_compatibility.py:72` names
`scripts/download_csharp_github.py` in a set that line 174 uses as a subtraction,
so a stale entry does not fail the test. Everything else in Phase 1 is either
unreferenced or imports a package that no longer exists. Phases 2 and 3 break
nothing: no hook command, no symlink, no installer table and no test references
any path they touch, verified per file with `git grep` on both the filename and
the module name.

Phase 4 breaks prose links only, across roughly 17 files. No runtime path.

Phase 5 breaks two comments. No runtime path.

Anything touching the four frozen prefixes breaks a live session, which is why no
phase does.

The failure mode to watch is the one this repo has already recorded: a hook
command in `~/.claude/settings.json` points at a path that no longer exists, the
hook fails, and hook failure is quiet. `scripts/check-hooks.py` and
`scripts/audit-hooks.py` exist for exactly this and should run after every phase,
including the ones that provably touch nothing.

## Verification after every phase

```
python -m pytest clean-rag/tests -q
python -m pytest scripts/tests -q
python -m pytest tests -q
python scripts/check-hooks.py
```

Run the three suites separately. `pytest.ini` records why: `scripts/tests` and
`clean-rag/tests` collide on a `tests.conftest` import when run together, tracked
at `spec/architecture-changes/tests-three-suites-cannot-run-together.md`.

Collection from the root does currently succeed at 4413 tests, but that is the
collection step alone and is not a substitute for the three runs.

## Open questions

`.claudeboost/knowledge/` holds 129 flat research markdown files with topic
prefixes in the filenames (`rag-reranking-`, `prompt-caching-`,
`context-compression-`). Foldering them by topic is the obvious tidy, but
`scripts/fetch-docs.py` and `scripts/prompt-rules-injector.py` both read that
directory, and the session-start hook advertises the flat path to every agent.
Not attempted here; it needs those two readers checked first.

Whether `plans/` should exist at all. It is the research-gate exempt scratch
directory, and a scratch directory that git tracks is a contradiction. Making it
gitignored would solve Phase 2 permanently instead of per file, at the cost of
seven files' history.

`state/*.py`. Three uncommitted Python files in a gitignored runtime directory.
Someone has to read them to decide.
