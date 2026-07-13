#!/usr/bin/env python
"""Run a hook script, but never brick Claude if the script isn't there.

    python ~/.claude/hook-run.py <script.py> [args...]

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
"""

import os
import subprocess
import sys
from pathlib import Path


def _expand(raw: str) -> Path:
    # settings.json writes paths like "$CLEAN_RAG_HOME/hooks/foo.py". The shell
    # normally expands those, but expand here too so this works when invoked
    # directly.
    return Path(os.path.expandvars(os.path.expanduser(raw)))


def main() -> int:
    if len(sys.argv) < 2:
        print("hook-run: no script given", file=sys.stderr)
        return 0

    script = _expand(sys.argv[1])
    args = sys.argv[2:]

    if not script.is_file():
        # The whole point. A hook whose script vanished with a branch switch is
        # not an error worth blocking work over.
        print(
            f"hook-run: {script.name} not on this branch, skipping this hook",
            file=sys.stderr,
        )
        return 0

    # stdin is the hook payload and the child needs it, so hand our own stdin
    # straight over rather than reading and re-piping it.
    try:
        result = subprocess.run(
            [sys.executable, str(script), *args],
            stdin=sys.stdin,
        )
        return result.returncode
    except Exception as e:
        # A launcher that crashes would block every tool call, which is the exact
        # failure it exists to prevent. Report and get out of the way.
        print(f"hook-run: failed to run {script.name}: {type(e).__name__}: {e}",
              file=sys.stderr)
        return 0


if __name__ == "__main__":
    sys.exit(main())
