#!/usr/bin/env python
"""PreToolUse gate on Edit, Write, and MultiEdit.

Blocks a code edit unless a research or triage agent actually ran this turn.

This replaces the old proof gate idea outright. That one asked the model to
write a proof file attesting it had researched, which proves nothing: the model
writes the file, so the file only ever says what the model wanted it to say.
This one keys off something the model cannot fabricate. Only Claude Code can
start an agent, and the record is stamped by a PostToolUse hook after the agent
finishes. No agent run, no record, no edit.

Markdown and other non code files pass through untouched. So do the usual
scratch directories. Research is for code, and gating a doc tweak on a subagent
spawn would just teach you to hate the gate.

Exit codes: 0 allows, 2 blocks and shows stderr to the model.
"""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from research_state import turn_has_research  # noqa: E402

# Only these get gated. Everything else, including .md, .json, .yaml, and configs,
# passes. A markdown edit has nothing to research.
CODE_EXTENSIONS = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs",
    ".java", ".cs", ".go", ".rs", ".rb", ".php", ".swift", ".kt", ".scala",
    ".c", ".h", ".cpp", ".hpp", ".cc", ".m", ".mm",
    ".sh", ".bash", ".ps1", ".sql", ".vue", ".svelte",
}

# Matched as whole path segments, not substrings, so a project legitimately named
# something like "docs-site" isn't accidentally exempt.
EXEMPT_SEGMENTS = {
    "workspace", "state", "plans", "docs", "node_modules",
    ".claude", ".claudeboost", ".git", "__pycache__", "scratchpad",
}


def _is_exempt(file_path: str) -> tuple[bool, str]:
    if not file_path:
        return True, "no file path in the payload"

    path = Path(file_path)

    if path.suffix.lower() not in CODE_EXTENSIONS:
        return True, f"{path.suffix or 'no extension'} is not code"

    parts = {p.lower() for p in path.parts}
    hit = parts & EXEMPT_SEGMENTS
    if hit:
        return True, f"lives under {sorted(hit)[0]}/"

    temp = os.environ.get("TEMP") or os.environ.get("TMP")
    if temp:
        try:
            path.resolve().relative_to(Path(temp).resolve())
            return True, "temp directory"
        except (ValueError, OSError):
            pass

    return False, ""


def _block(file_path: str, reason: str) -> int:
    print(
        f"BLOCKED: no research has run this turn ({reason}).\n\n"
        f"About to edit: {file_path}\n\n"
        "Every code edit gets researched first. Not asked for, required.\n\n"
        "Spawn triage-agent now. It is cheap and fast, and for a trivial edit it\n"
        "will come straight back with NONE, which satisfies this gate. Give it:\n"
        "  - what you are about to change and why\n"
        "  - the file path\n"
        "  - the code you intend to write\n\n"
        "If it returns RESEARCH with a list of aspects, spawn research-agent with\n"
        "those aspects and wait for it before editing.\n\n"
        "Do not work around this by editing a .md file instead, and do not ask the\n"
        "user to disable it. Spawn the agent.",
        file=sys.stderr,
    )
    return 2


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read())
    except Exception:
        # Can't read the payload, so can't tell what's being edited. Failing open
        # is right here: a broken gate must not brick all editing.
        return 0

    if payload.get("tool_name") not in ("Edit", "Write", "MultiEdit"):
        return 0

    if os.environ.get("CLEAN_RAG_RESEARCH_GATE") == "off":
        return 0

    file_path = payload.get("tool_input", {}).get("file_path", "")

    exempt, _why = _is_exempt(file_path)
    if exempt:
        return 0

    session_id = payload.get("session_id", "")
    ok, reason = turn_has_research(session_id)
    if ok:
        return 0

    return _block(file_path, reason)


if __name__ == "__main__":
    sys.exit(main())
