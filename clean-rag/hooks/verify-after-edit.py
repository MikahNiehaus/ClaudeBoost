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


def _is_code_file(file_path: str) -> bool:
    if not file_path:
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

    if payload.get("tool_name") not in ("Edit", "Write", "MultiEdit"):
        return 0

    file_path = payload.get("tool_input", {}).get("file_path", "")
    if _is_code_file(file_path):
        print(_REMINDER)
    return 0


if __name__ == "__main__":
    sys.exit(main())
