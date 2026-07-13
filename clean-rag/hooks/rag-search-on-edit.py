#!/usr/bin/env python
"""PLACEHOLDER. Does nothing. Exits 0.

This file exists so a branch switch cannot brick Claude.

Hook commands live in the global ~/.claude/settings.json and survive a checkout.
The scripts they point at live in this repo. Switch to a branch where the script
is absent and python exits 2, which Claude Code reads from a PreToolUse hook as
"block this tool call". Every Edit, Write, and Bash refused until you switch
back. A file that exits 0 makes it a no op instead.

WHAT THIS ONE USED TO BE, AND WHY IT IS NOT COMING BACK

rag-search-on-edit.py ran a RAG search before every edit. The problem: it
searched a hardcoded constant string, "code editing patterns refactoring
maintainability clarity", regardless of what you were actually editing. It had no
file context at all. So it injected the same generic results into every edit,
forever.

That is the same class of bug that got the topic knowledge base deleted: a query
with no judgment behind it returns a confident answer to a question nobody asked.
Measured scores on that kind of junk ran 0.80 to 0.87, so no threshold catches it.

Deleted deliberately. Not lost. Do not restore it. Pre edit research now happens
in hooks/code-pattern-inject.py, which queries with the actual code being written,
and hooks/research-gate.py, which requires a real research agent to have run.
"""

import sys

sys.exit(0)
