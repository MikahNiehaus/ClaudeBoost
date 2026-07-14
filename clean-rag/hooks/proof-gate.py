#!/usr/bin/env python
"""PLACEHOLDER. Does nothing. Exits 0.

This file exists so a branch switch cannot brick Claude.

Hook commands are registered in ~/.claude/settings.json, which is global and
survives a checkout. The scripts they point at live in this repo. So switching to
a branch where a hook script does not exist leaves a live registration pointing
at nothing, python exits 2, and Claude Code reads exit 2 from a PreToolUse hook
as "block this tool call". Not a warning. Every Edit, Write, and Bash refused.

An empty file that exits 0 turns that into a no op.

WHAT THIS ONE USED TO BE, AND WHY IT IS NOT COMING BACK

proof-gate.py was the old enforcement mechanism, registered on the main branch.
It asked the model to write a JSON "proof" file attesting that it had researched
an edit, then checked that file before allowing the edit.

That design proves nothing. The model writes the file, so the file says whatever
the model wants it to say. It was replaced by hooks/research-gate.py, which keys
off something the model cannot fabricate: an agent completion, stamped by a
PostToolUse hook only after Claude Code has actually run research-agent to the end.

So this was deleted on purpose. It was not lost. Do not restore it. If you want
the enforcement, it is in research-gate.py, and it is stricter.
"""

import sys

sys.exit(0)
