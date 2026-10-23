# TODO: revisit the GitHub write gate after the main build is done

Status: works for normal use. Not a security boundary against a hostile model.

## What works
- Typing exactly `3.14` unlocks approved git/gh writes for that session, 10 minutes.
- Any other message revokes it.
- Force push, public gist/repo, merge, delete stay blocked.
- Tests: `python -m pytest scripts/tests -k "bash_guard or github_write_gate or github_approval" -q`

## Known gaps (found by bad-cop, last round)
Each lets the model run a git write without `3.14`:
- `$'a\'b'; git commit` hides the second command from `_split_segments`.
- Nested backticks hide the inner command.
- A quoted `)` inside `$(...)` ends the substitution early (old code).
- `\'` opens a quote in `_shell_words`, merging flags into one word.
- Obfuscated verbs skip the check: `'gi't commit`, `g\it commit`, `! git commit`, `{ git commit; }`.
- Interpreter obfuscation can forge the approval file.
- A push to a public repo is not detectable.

Six failing tests for these are in `scripts/tests/test_bash_guard_hidden_commands.py`.

## Options
1. Accept as a bar-raiser.
2. Another good-cop and bad-cop round on the five holes. Expect more findings.
3. Replace parser guessing with an exact-command wrapper script.
