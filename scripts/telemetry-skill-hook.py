"""
UserPromptSubmit hook — tracks skill invocations in skill-invocations.jsonl.

Reads Claude Code's UserPromptSubmit JSON payload from stdin. If the prompt
starts with /skill-name, writes a record to workspace/[id]/Telemetry/skill-invocations.jsonl.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

BOOST_HOME = Path(os.environ.get("CLAUDEBOOST_HOME") or Path(__file__).resolve().parent.parent)
sys.path.insert(0, str(BOOST_HOME / "scripts"))

from telemetry_writer import (  # noqa: E402
    _DISABLED,
    now_iso,
    session_id,
    write_telemetry,
)

_SKILL_RE = re.compile(r"^/([a-zA-Z][a-zA-Z0-9_-]*)(\s|$)")


def main() -> None:
    try:
        _run()
    except Exception:
        pass  # Never let a telemetry hook surface errors to the user


def _run() -> None:
    if _DISABLED:
        return

    try:
        payload = json.loads(sys.stdin.read())
    except Exception:
        return

    prompt: str = payload.get("prompt", "")
    match = _SKILL_RE.match(prompt.strip())
    if not match:
        return

    skill_name = match.group(1)

    record = {
        "ts": now_iso(),
        "session_id": session_id(),
        "skill": skill_name,
        "prompt_prefix": prompt.strip()[:120],
    }

    write_telemetry(record, "skill-invocations.jsonl")


if __name__ == "__main__":
    main()
