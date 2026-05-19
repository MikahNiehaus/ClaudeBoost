"""PostToolUse/Task hook: emit verify-gate nudge unless an audit is in progress.

When /audit is running it manages its own evaluator step — the gate nudge is
redundant and serialises the parallel dimension-agent flow.  The audit skill
sets state/audit-in-progress.json; this script checks for it and stays silent.
"""

import json
import os
import sys
from pathlib import Path

BOOST_HOME = Path(os.environ.get("CLAUDEBOOST_HOME", ""))
AUDIT_FLAG = BOOST_HOME / "state" / "audit-in-progress.json" if BOOST_HOME else None

if AUDIT_FLAG and AUDIT_FLAG.exists():
    # Audit skill owns evaluator scheduling — stay silent.
    sys.exit(0)

NUDGE = (
    "VERIFY GATE: Scan agent output for BLOCKER/HIGH/MEDIUM findings.\n"
    "- If findings exist: spawn evaluator-agent to verify (fresh context prevents "
    "confirmation bias). Do NOT self-verify — same context that produced the finding "
    "will confirm it.\n"
    "- Evaluator checks: does each finding cite file:line? Does the code actually "
    "show the issue? Drop false positives.\n"
    "- No findings? No evaluator needed. Present results directly.\n"
    "Rework from false findings costs more than one lightweight evaluator spawn."
)

print(NUDGE)
