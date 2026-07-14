#!/usr/bin/env python
"""PostToolUse on Edit, Write, MultiEdit: record the edited file for the Stop gates.

The gates detect changes via git in the session cwd, which misses edits made in a
different repo than the cwd. This records what was actually edited so they can look
in the right place. Never blocks, never raises.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from turn_edits import record_edit  # noqa: E402


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read())
    except Exception:
        return 0
    if payload.get("tool_name") not in ("Edit", "Write", "MultiEdit"):
        return 0
    record_edit(
        payload.get("session_id", ""),
        payload.get("tool_input", {}).get("file_path", ""),
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)
