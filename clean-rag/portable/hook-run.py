#!/usr/bin/env python
"""Run a hook script, but never brick Claude if the script isn't there.

    python ~/.claude/hook-run.py [--fail-closed] <script.py> [args...]

WHY THIS EXISTS

Hook commands are registered in settings.json, which is global and does not
change when you switch git branches. The scripts they point at DO live in the
repo. So checking out a branch that predates a hook silently removes the script
out from under a live registration.

That is not a soft failure. Python exits 2 when it can't open a file, and Claude
Code reads exit 2 from a PreToolUse hook as "block this tool call". So switching
to an older branch does not merely log an error, it blocks every Edit, Write, and
Bash call until you switch back. Measured across this repo's real branches:
switching to main breaks 4 live hooks (2 of them blocking), and the two feature
branches break 11 (4 blocking).

Stubbing the missing files on each branch would work, but only for branches that
exist today, and only until someone adds a hook and forgets to backfill it
everywhere. This file lives outside the repo, so no checkout can remove it, and
it covers branches that have not been created yet.

BEHAVIOUR

  script missing  -> exit 0, one line on stderr. The hook is a no op.
  script present  -> run it, pass stdin through, pass its exit code back
                     unchanged, so a real gate can still block a real edit.

The only thing it swallows is absence.

--fail-closed

For a SAFETY guard, "the guard crashed" must not be spelled the same way as
"the guard allowed this". Claude Code reads exit 2 from a PreToolUse hook as
block and treats every other non-zero code as a non-blocking error, so a guard
that dies on a traceback exits 1 and the tool call proceeds unguarded.

That is not hypothetical. verify-loop-git-guard.py annotated a return as
`str | None` (PEP 604, 3.10+) with no `from __future__ import annotations`, so
on macOS's system python 3.9.6 the annotation was evaluated at def time and
raised TypeError. Exit 1. `git push origin main` -- the exact command the guard
was written to stop -- ran.

With --fail-closed, a script that is present but exits with anything other than
its own documented decision (0 allow / 2 block) is reported as undecided and
returns 2. Absence still returns 0: a branch that predates the script never had
the guard, and blocking every Bash call after a checkout is the brick this file
exists to prevent.

Limit worth stating: this can only act once hook-run.py is itself running. If
the interpreter chosen by the registration cannot start hook-run.py at all,
nothing here executes.
"""

import os
import subprocess
import sys
from pathlib import Path

ALLOW = 0
BLOCK = 2

#: Exit codes a guard produces on purpose. Anything else means it did not reach
#: a decision, whatever it printed on the way out.
_GUARD_DECISIONS = (ALLOW, BLOCK)

_FAIL_CLOSED_FLAG = "--fail-closed"


def _expand(raw: str) -> Path:
    # settings.json writes paths like "$CLEAN_RAG_HOME/hooks/foo.py". The shell
    # normally expands those, but expand here too so this works when invoked
    # directly.
    return Path(os.path.expandvars(os.path.expanduser(raw)))


def _undecided(script: Path, detail: str, fail_closed: bool) -> int:
    """A guard that never reached a verdict. Block it under --fail-closed."""
    if not fail_closed:
        return ALLOW

    print(
        f"BLOCKED: the safety guard {script.name} could not run ({detail}), so "
        "this tool call was not checked. Blocking rather than allowing it, "
        "because an unchecked call is exactly what the guard exists to stop.\n\n"
        "Fix the guard, or have the orchestrator run this command instead.",
        file=sys.stderr,
    )
    return BLOCK


def main() -> int:
    argv = sys.argv[1:]

    fail_closed = bool(argv) and argv[0] == _FAIL_CLOSED_FLAG
    if fail_closed:
        argv = argv[1:]

    if not argv:
        print("hook-run: no script given", file=sys.stderr)
        return ALLOW

    script = _expand(argv[0])
    args = argv[1:]

    if not script.is_file():
        # The whole point. A hook whose script vanished with a branch switch is
        # not an error worth blocking work over. Deliberately still ALLOW under
        # --fail-closed: a branch that predates the guard never had it, and
        # blocking every call after a checkout is the brick this file prevents.
        print(
            f"hook-run: {script.name} not on this branch, skipping this hook",
            file=sys.stderr,
        )
        return ALLOW

    # stdin is the hook payload and the child needs it, so hand our own stdin
    # straight over rather than reading and re-piping it.
    try:
        result = subprocess.run(
            [sys.executable, str(script), *args],
            stdin=sys.stdin,
        )
    except Exception as e:
        # A launcher that crashes would block every tool call, which is the exact
        # failure it exists to prevent. Report and get out of the way.
        print(f"hook-run: failed to run {script.name}: {type(e).__name__}: {e}",
              file=sys.stderr)
        return _undecided(script, f"{type(e).__name__}: {e}", fail_closed)

    if fail_closed and result.returncode not in _GUARD_DECISIONS:
        return _undecided(script, f"exit {result.returncode}", fail_closed)

    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
