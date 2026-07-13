#!/usr/bin/env python
"""PLACEHOLDER. Does nothing. Exits 0.

This file exists so a branch switch cannot brick Claude.

Hook commands are registered in the global ~/.claude/settings.json, which does
not change when you check out a different branch. The scripts they point at do
live in this repo. A branch that lacks a registered script leaves the hook
pointing at nothing: python exits 2, and Claude Code reads exit 2 from a
PreToolUse hook as "block this tool call". Every Edit, Write, and Bash refused
until you switch back. A file that exits 0 makes it a harmless no op.

WHAT THIS ONE IS

debug-gate.py is a real hook on the main branch. It was never implemented on this
branch.

This is a stub, not a deletion. On a branch where the real one exists, you get the
real one.
"""

import sys

sys.exit(0)
