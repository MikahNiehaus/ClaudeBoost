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

scripts/agent-spawn-gate.py is a real hook on feat/uninstall-and-bash-guard and
on feature/workspace-better-understanding-active-2026-06-15. It blocks agent
spawns that have not loaded RAG context first. It was never implemented on this
branch, which enforces research at the edit rather than at the spawn
(clean-rag/hooks/research-gate.py).

This is a stub, not a deletion. On a branch where the real one exists, you get the
real one.

Note there is also a clean-rag/hooks/agent-spawn-gate.py stub, for the main
branch's copy of the same idea in a different location.
"""

import sys

sys.exit(0)
