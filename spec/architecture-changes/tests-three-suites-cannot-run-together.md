# Three test suites that cannot be collected in one invocation

**Status:** open, needs a decision. Not a bug in any test; a packaging problem
in how the three suites are laid out.

## The measurement

```
$ python -m pytest clean-rag/tests/test_graph_cache.py scripts/tests/test_bash_guard.py -q
E   ModuleNotFoundError: No module named 'tests.test_graph_cache'
ERROR clean-rag/tests/test_graph_cache.py
1 error in 0.36s
```

Two pre-existing files, no new code involved. Naming any file from two
different suite directories in one `pytest` call fails at collection.

Three directories, each of which must be invoked separately:

| Suite | Tests |
|---|---|
| `scripts/tests/` | 1484 passed, 67 skipped |
| `clean-rag/tests/` | 1196 passed, 1 failed |
| `tests/` (repo root) | 334 passed, 2 xfailed |

## Why this is more than an inconvenience

**It is the reason the root suite went unrun.** For most of 2026-09-08, two
review rounds and the orchestrator all reported "both suites green" while a
third directory holding 336 tests was never invoked. Nobody was being careless.
There is no single command that runs everything, so "run the tests" naturally
means one directory, and the habit forms around whichever two someone learned
first.

The root suite was green when finally run, so nothing was lost. The next time
it will not be.

**It also hides a real failure.** `clean-rag/tests` currently has one failure,
the Windows `os.replace` race in `test_state_and_audit_concurrent_writes.py`.
That suite passes in isolation and fails in a full run, which is exactly the
shape that gets written off as flakiness. A single invocation would at least
make the failure consistent.

## The cause

Two `tests` directories become the same top-level module name once pytest
inserts their parents on `sys.path` in rootdir-relative order. The second one
collected shadows the first, so `tests.test_graph_cache` resolves against the
wrong package.

Standard pytest behaviour with no `__init__.py` files: the module name is the
basename, so two files with the same basename, or two packages with the same
name, collide.

## Options, none of them free

1. **Add `__init__.py` to each suite directory.** Makes each a real package, so
   the module names become `clean_rag.tests.x` and cannot collide. Cheapest
   change. Cost: every test that relies on the current implicit `sys.path`
   insertion for its imports may break, and `scripts/tests/helpers.py` is
   imported as a bare `from helpers import ...` in many files.
2. **Set `consider_namespace_packages` or an explicit `rootdir` plus
   `importmode=importlib`** in a config file. `importlib` mode is the modern
   pytest answer to exactly this and does not need `__init__.py`. Cost: the
   repo currently has **no** `pyproject.toml`, `pytest.ini`, `setup.cfg` or
   `tox.ini`, so this introduces the first one, and that is a decision with a
   longer tail than the problem.
3. **Rename the directories** so no two share a basename. Most invasive, and
   every path in every doc, brief and CI reference moves with it.
4. **Leave the layout and add one runner** that invokes the three in sequence
   and aggregates the result. Does not fix collection, but it does fix the
   thing that actually bit: there would be one command that means "all the
   tests". Cheapest by far, and it composes with any of the above later.

Option 4 plus option 2 is the likely answer. Option 4 alone stops the recurrence
today.

## Related

- `spec/STATUS.md`, the 8612 sweep, for the same shape: a check that existed and
  was never wired to anything that runs it.
- `clean-rag/hooks/auto-test-gate.py` asks the server to detect and run the
  project's tests. Worth checking which of the three it finds, since it is the
  one Stop hook that genuinely blocks.
