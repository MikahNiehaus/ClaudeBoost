# Two unreferenced scripts build the same C# benchmark file two different ways

- **Kind:** bloat
- **Area:** scripts
- **Found by:** bad-cop on 2026-09-07
- **Why it was not fixed in place:** deciding which downloader to keep (or
  whether to keep both) needs a judgment call about network dependency,
  licensing, and data quality that a mechanical review cannot make. Removing
  either is "removing a feature entirely" per spec/README.md's bar.

## What is there now

Three scripts in `scripts/` generate C# code and docstring pairs for the RAG
benchmark, and two of them write to the exact same output path with nothing
choosing between them:

- `scripts/download_csharp_benchmark.py:1-23` streams C# files from the
  `codeparrot/github-code` dataset on HuggingFace (`pip install datasets`) and
  extracts `<summary>` XML doc comments. Its own docstring says the output is
  `mcp-rag-server/tests/data/codesearchnet_csharp_full.jsonl:20`.
- `scripts/download_csharp_github.py:1-21` downloads GitHub zip archives of
  seven named repos (Newtonsoft.Json, AutoMapper, Polly, FluentValidation,
  Dapper, MediatR, Serilog) and parses the same `<summary>` XML doc comment
  shape. Its docstring says the output is the identical path:
  `mcp-rag-server/tests/data/codesearchnet_csharp_full.jsonl:20`.
- `scripts/download_codesearchnet_full.py:1-4` is the sibling for every other
  language CodeSearchNet already covers ("C# is not in CodeSearchNet" is the
  first line of `download_csharp_benchmark.py`, which is why the other two
  exist at all), and unlike them it is at least mentioned in `README.md` and
  named as a real dependency of
  `mcp-rag-server/tests/test_codesearchnet_1k_pool.py:4`.

Neither `download_csharp_benchmark.py` nor `download_csharp_github.py` is
referenced anywhere else in the tracked tree: not in `README.md`, not in
`docs/`, not in any `.claude/commands/*.md`, not in `scripts/setup.py`, and
neither has a test in `scripts/tests/`. Confirmed by
`git grep -l download_csharp_benchmark.py` and
`git grep -l download_csharp_github.py` across the whole repository, both
returning only the file itself.

## Why it is a problem

Two scripts that produce the same artifact by two different methods, with no
comment in either pointing at the other and no record of which one actually
produced the `codesearchnet_csharp_full.jsonl` that ships in
`mcp-rag-server/tests/data/`, is exactly the failure mode a future reader (AI
or human) hits blind: editing or rerunning one of them silently produces a
benchmark file whose format or provenance no longer matches whichever one was
actually used the first time, and there is nothing in either file that says
so. It also means one of the two network dependencies
(`pip install datasets`, or a plain zip download) is being carried for no
benefit if the other was the one actually used.

No evidence either script has caused a real failure yet: neither appears to
have been run recently (no dated output file with a matching name is tracked),
so this is a maintenance and discoverability cost, not an active bug.

## What to do instead

Determine (from git history or whoever last touched
`mcp-rag-server/tests/data/codesearchnet_csharp_full.jsonl`) which of the two
scripts actually produced the current benchmark file, keep that one, and
either delete the other or fold a comment into the survivor explaining the
tradeoff and pointing at the deleted approach in git history. If both remain
useful (e.g. one as a fallback when HuggingFace `datasets` is unavailable),
say so explicitly in both docstrings and cross-reference them by name so a
reader who opens one knows the other exists and why.

Files it would touch: `scripts/download_csharp_benchmark.py`,
`scripts/download_csharp_github.py`, and possibly `README.md` if either is
worth documenting the way `download_codesearchnet_full.py` already is.

## What it would break

Neither script is imported or invoked by anything else in the tree (confirmed
by the same `git grep` above), so removing either breaks no caller. The only
risk is losing a genuinely-needed fallback data source if the two methods
produce meaningfully different benchmark quality, which is the open question
below.

## Open questions

Which of the two actually generated the benchmark data currently checked in
under `mcp-rag-server/tests/data/`, and does `test_codesearchnet_1k_pool.py`
(or anything else) assume a specific one of the two extraction methods'
output shape. Neither script's diff was reviewed for this, since resolving it
means reading git blame on the data file and the test, which is a judgment
call for whoever owns that benchmark, not a review-time fix.
