#!/usr/bin/env python
"""PLACEHOLDER. Does nothing. Exits 0.

This file exists so a branch switch cannot brick Claude.

Hook commands are registered in the global ~/.claude/settings.json, which does
not change when you check out a different branch. The scripts they point at do
live in this repo. So a branch that lacks a registered script leaves the hook
pointing at nothing: python exits 2, and Claude Code reads exit 2 from a
PreToolUse hook as "block this tool call". Every Edit, Write, and Bash gets
refused until you switch back. A file that exits 0 makes it a harmless no op.

WHAT THIS ONE IS

agent-spawn-gate.py is a real hook on the main branch. It blocks agent spawns
that have not loaded RAG context first. It was never implemented on this branch,
which uses a different enforcement model (hooks/research-gate.py, which gates
code edits rather than agent spawns).

This is a stub, not a deletion. If you are on a branch where the real one exists,
you get the real one. If you are here, you get nothing, which is correct: this
branch does not use it.
"""

import sys

sys.exit(0)
