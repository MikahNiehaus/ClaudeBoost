#!/usr/bin/env python
"""PostToolUse on Edit, Write, MultiEdit. Nudges "verify by running" after code.

The research gate fires BEFORE a code edit and makes you research the approach.
It does nothing about whether the code you then wrote is actually correct. This
is the other half: right after you write code, a reminder to confirm it by
running something, at the moment that's cheapest to act on.

Why a run, not a review: a research spawn this session found (arXiv 2310.01798,
CRITIC ablation) that a model re reading its own diff in the same context is
close to useless and sometimes worse, while execution feedback (run a check, fix
from the real error) had the strongest measured first try correctness gain per
token, 12 to 46 percent. So this nudges toward running, and explicitly away from
self review.

Why PostToolUse and not a Stop hook: a Stop gate that blocks finishing can loop,
and it burns tokens re deciding every turn. This just prints once, after the
edit, and never blocks. Exit 0 always.
"""

import json
import os
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Same set the research gate uses. Only real source code gets the nudge.
CODE_EXTENSIONS = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs",
    ".java", ".cs", ".go", ".rs", ".rb", ".php", ".swift", ".kt", ".scala",
    ".c", ".h", ".cpp", ".hpp", ".cc", ".m", ".mm",
    ".sh", ".bash", ".ps1", ".sql", ".vue", ".svelte",
}

# Matched as whole path segments, not substrings.
EXEMPT_SEGMENTS = {
    "workspace", "state", "plans", "docs", "node_modules",
    ".claude", ".claudeboost", ".git", "__pycache__", "scratchpad",
}

_REMINDER = """
## Now verify it by running (not by re reading)

You just wrote code. Research narrowed the approach; it did not confirm these
exact lines work. Confirm them the cheap way:

- Run a check: a test, an assert based `__main__` self check, or drive the real
  flow. If it fails, feed the actual error back and fix once. That's the highest
  first try correctness signal there is, and it costs interpreter time, not
  tokens, except for the rare fix.
- Do NOT self review your own diff instead. Measured evidence says same context
  self critique is close to useless. Running it is grounded, re reading it is not.
- A trivial one liner needs no check.

For a high stakes surface (auth, money, SQL, a subprocess, a trust boundary),
also get a fresh context review. Otherwise, just run it.
"""

# The rationale above is worth saying once. Saying it on all 98 edits of a
# session cost 19,502 measured tokens and told the reader nothing new after the
# first time. The nudge still fires on every edit, because the moment is the
# point; only its restated reasoning is dropped.
_REMINDER_SHORT = (
    "\n[verify-by-running] Run a check on what you just wrote: a test, an "
    "assert, or drive the real flow. Do not self review the diff instead.\n"
)


def _reminder(session_id: str) -> str:
    """Full text on the first code edit of a session, one line on the rest."""
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from research_state import claim_session_once

        first = claim_session_once(session_id, "verify-by-running")
    except Exception:
        # A broken state layer must not be able to silence the nudge.
        return _REMINDER
    return _REMINDER if first else _REMINDER_SHORT


def _is_code_file(file_path: str) -> bool:
    if not file_path or not isinstance(file_path, str):
        return False
    path = Path(file_path)
    if path.suffix.lower() not in CODE_EXTENSIONS:
        return False
    if {p.lower() for p in path.parts} & EXEMPT_SEGMENTS:
        return False
    temp = os.environ.get("TEMP") or os.environ.get("TMP")
    if temp:
        try:
            path.resolve().relative_to(Path(temp).resolve())
            return False
        except (ValueError, OSError):
            pass
    return True


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read())
    except Exception:
        return 0

    # json.loads succeeds for any JSON value, so a payload of `null`, a list or
    # a bare string parses fine and then fails at the first .get(). The
    # docstring above promises exit 0 always, which means checking the shape.
    if not isinstance(payload, dict):
        return 0

    if payload.get("tool_name") not in ("Edit", "Write", "MultiEdit"):
        return 0

    tool_input = payload.get("tool_input")
    file_path = tool_input.get("file_path", "") if isinstance(tool_input, dict) else ""
    if _is_code_file(file_path):
        print(_reminder(payload.get("session_id", "")))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        # Same net research-gate.py, verifier-gate.py and record-edit.py carry.
        sys.exit(0)
