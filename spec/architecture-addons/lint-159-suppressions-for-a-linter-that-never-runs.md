# 159 lint suppressions are in the tree for a linter this project has never run

- **Kind:** architecture-addon
- **Area:** repo-wide (86 tracked Python files), plus whatever runs them
- **Found by:** researcher on 2026-09-17, while answering a narrower question
  about four silent `except Exception` blocks in `clean-rag/server/store.py`.
  Counts below were re-measured by the orchestrator, because researcher
  reported four files and the real number is 86.
- **Why it is not a bounded text edit:** the fix in one direction is a new
  dependency plus wiring to run it. `spec/README.md` names that bar directly.
  The fix in the other direction is deleting 159 comments, which is bounded but
  is the losing half of a decision nobody has made yet.

## What is there now

159 `# noqa:` comments across 86 tracked Python files. Measured with
`git ls-files "*.py"`, venvs excluded:

| Rule | Count | What it suppresses |
|---|---|---|
| `E402` | 115 | Module level import not at top of file |
| `BLE001` | 38 | Blind `except:` / `except Exception:` with no handling |
| `F401` | 5 | Imported and unused |
| `S606` | 1 | Starting a process without a shell |

No lint configuration belongs to this project. `git ls-files` matched no
`ruff.toml`, `pyproject.toml`, `.flake8`, `setup.cfg` or `tox.ini`. The only
copies on disk are vendored inside `clean-rag-venv` and `graphrag-venv`, plus
one unrelated repo under `workspace/`.

`ruff` is not installed:

```
$ clean-rag/clean-rag-venv/Scripts/python.exe -m ruff --version
No module named ruff
```

So all 159 suppressions are inert. Nothing has ever read one.

The `E402` bulk is correct in intent. Every sampled site follows a `sys.path`
manipulation, which is the legitimate reason to import below the top:

```
clean-rag/cli/audit.py:21        import research_audit  # noqa: E402
clean-rag/cli/reindex_batch.py:54 import psutil  # noqa: E402
```

The `BLE001` sites are concentrated, not scattered:

| File | BLE001 count |
|---|---|
| `clean-rag/install.py` | 12 |
| `clean-rag/server/mutation.py` | 5 |
| `clean-rag/graphrag/graph_service.py` | 4 |
| `plans/test_powerpoint_env.py` | 3 |
| 12 other files | 1 to 2 each |

## Why this matters, stated carefully

The weak version of this argument is that a linter catches bugs. Measured on
this repo the same day, that is false: bandit, radon and a hand written
invariant check were run against the four files where the cop loop had found
nine real bugs, and between them they caught **zero** of the nine. bandit
produced 21 findings and all 21 were noise. Do not adopt ruff expecting it to
find defects.

The real argument is narrower and survives that measurement. `BLE001` enforces
a rule this project has already written down and currently polices by hand.
Both `CLAUDE.md` copies say:

> "Missing `logger.error` in a catch or error block is a blocker."

That is a blocker-severity rule with no mechanical check behind it. It is
enforced today only when a reviewer happens to read the file. The live example:
`clean-rag/server/store.py` has four methods (`vacuum_if_needed`, `count`,
`count_sources`, `sample_dimension`) that swallow `Exception` and return a
default with no logging. None of them carries a `noqa`, because nothing would
have asked for one. `BLE001` flags exactly that shape, and explicitly does not
flag a broad catch that logs with `exc_info`, which is the shape the rule wants.

A suppression comment for a linter that never runs is worse than no comment.
It reads as "this was considered and waived" when nothing considered it.

## The decision

Adopt ruff, or delete the comments. Both are defensible; drifting is not.

**If adopting**, the two rules that carry this project's own stated policy are
`BLE001` and `TRY400`. Note a real conflict before wiring them: `TRY400` says
prefer `logger.exception()` over `logger.error()` inside an `except` block,
while the CLAUDE.md rule names `logger.error` specifically. `logger.exception`
is `logger.error(..., exc_info=True)`, so it satisfies the rule literally and
adds a traceback, but the wording should be settled rather than left to collide.

Open sub-questions, none answered here:

- What runs it? There is no CI in this repo to hang it off, and a pre-commit
  hook is another new dependency.
- Does it block or nudge? This codebase has a recorded position that objective
  cheap checks may block and judgement calls must not (`CLAUDE.md`, the split
  between `auto-test-gate.py` and `verifier-gate.py`). A lint failure is
  objective, which argues for blocking, but `verifier-gate.py`'s own docstring
  records two reverts of a blocking reviewer on this surface.
- What happens to the 38 existing `BLE001` suppressions on first run? Several
  sit in deliberate fail-open gate hooks whose contract is to never raise
  (`research_state.py:478`, `quick-cop-bash-guard.py:313`,
  `research-agent-bash-guard.py:218`, `verify-loop-git-guard.py:331`). Those are
  correct and should stay suppressed. The `install.py` dozen have not been
  examined.

**If deleting**, say so in the file that records the decision, or the comments
come back the next time somebody writes one from habit.

## Sources

- Ruff `BLE001` (blind-except): https://docs.astral.sh/ruff/rules/blind-except/
  Documents the logged-with-`exc_info` exemption.
- Ruff `TRY400` (error-instead-of-exception):
  https://docs.astral.sh/ruff/rules/error-instead-of-exception/
- Google Python Style Guide, on catching `Exception`:
  https://google.github.io/styleguide/pyguide.html
- PEP 8, on limiting the `try` clause:
  https://peps.python.org/pep-0008/
