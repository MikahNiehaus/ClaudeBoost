#!/usr/bin/env python3
"""
PreCompact hook: re-inject 5 standing orders immediately before context compaction.
Ensures behavior rules survive the compaction boundary and are present in the
summary that Claude builds from compressed context.

Exit codes:
  0 = always (this hook never blocks)
"""
import sys
import json

print(json.dumps({
    "additionalContext": (
        "STANDING ORDERS (re-injected before compaction): "
        "Search RAG before reading files. "
        "Cite file:line for every finding. "
        "Spawn evaluator-agent — never self-verify. "
        "CONSULT before new endpoints/tables/dependencies. "
        "POST http://127.0.0.1:8612/context first in every agent spawn prompt."
    )
}))
sys.exit(0)
