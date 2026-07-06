#!/usr/bin/env python3
"""clean-rag debug gate: PreToolUse hook on Edit|Write|MultiEdit.

Temporary enforcement hook for self-improvement. When debug mode is active
and a proof-gate rejection has created debug-fix-required.json, this hook
blocks ALL edits to non-clean-rag files until the enforcement gap is fixed.

Edits to clean-rag/ files are always allowed so Claude can fix the gap.
Read, Grep, Glob, and Bash are not affected (investigation stays open).

Install with: python clean-rag/debug-install.py
Remove with:  python clean-rag/debug-uninstall.py

Exit codes:
  0 = pass (no fix required, or target is a clean-rag file)
  2 = block (fix required, target is not a clean-rag file)
"""

import json
import os
import sys
from pathlib import Path


def _clean_rag_home() -> Path:
    env = os.environ.get("CLEAN_RAG_HOME")
    if env:
        return Path(env)
    return Path(__file__).resolve().parent.parent


def _canonicalize(file_path: str) -> str:
    try:
        resolved = Path(file_path).resolve()
    except (OSError, ValueError):
        resolved = Path(file_path)
    return resolved.as_posix().lower()


def _is_clean_rag_file(canonical: str) -> bool:
    """Check if the file is under the clean-rag directory."""
    home = _clean_rag_home()
    home_canonical = home.resolve().as_posix().lower()
    return canonical.startswith(home_canonical)


DEBUG_FIX_MESSAGE = """
===================================================================
DEBUG ENFORCEMENT: Fix required before continuing.

A proof-gate rejection was detected while debug mode is active.
You must analyze the mistake and update clean-rag before editing
any other files.

  Mistake type : {mistake_type}
  File blocked : {file_blocked}
  Reason       : {reason}

  Fix instruction:
  {fix_instruction}

What to do:
1. Read the fix instruction above
2. Search RAG for the right pattern/approach
3. Edit the relevant clean-rag file to prevent this class of mistake
4. Delete clean-rag/state/debug-fix-required.json when the fix is done

You CAN edit clean-rag/ files right now (to apply the fix).
You CANNOT edit anything else until the fix is applied.
===================================================================
"""


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, ValueError):
        return 0  # Can't parse, don't block

    tool_name = payload.get("tool_name", "")
    tool_input = payload.get("tool_input", {})

    if tool_name not in ("Edit", "Write", "MultiEdit"):
        return 0

    home = _clean_rag_home()
    state_dir = home / "state"

    # Check if debug mode is active
    debug_mode = state_dir / "debug-mode.json"
    if not debug_mode.exists():
        return 0

    # Check if a fix is required
    fix_file = state_dir / "debug-fix-required.json"
    if not fix_file.exists():
        return 0

    # Fix is required. Allow edits to clean-rag files, block everything else.
    file_path = tool_input.get("file_path", "")
    canonical = _canonicalize(file_path)

    if _is_clean_rag_file(canonical):
        return 0  # Allow fixes to clean-rag itself

    # Block with details from the fix-required file
    try:
        fix_data = json.loads(fix_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        fix_data = {
            "mistake_type": "unknown",
            "file_blocked": "unknown",
            "reason": "unknown",
            "fix_instruction": "Read state/debug-fix-required.json for details.",
        }

    print(
        DEBUG_FIX_MESSAGE.format(
            mistake_type=fix_data.get("mistake_type", "unknown"),
            file_blocked=fix_data.get("file_blocked", "unknown"),
            reason=fix_data.get("reason", "unknown"),
            fix_instruction=fix_data.get("fix_instruction", "Fix the enforcement gap."),
        ),
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
