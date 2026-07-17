#!/usr/bin/env python
"""PreToolUse gate on Edit, Write, and MultiEdit.

Blocks a code edit when the file hasn't been covered by research this session.

This replaces the old proof gate idea outright. That one asked the model to
write a proof file attesting it had researched, which proves nothing: the model
writes the file, so the file only ever says what the model wanted it to say.
This one keys off something the model cannot fabricate. Only Claude Code can
start an agent, and the record is stamped by a PostToolUse hook after the agent
finishes. No agent run, no record, no edit.

Markdown and other non code files pass through untouched. So do the usual
scratch directories. Research is for code, and gating a doc tweak on a subagent
spawn would just teach you to hate the gate.

Previously this hook was softened to a nudge (exit 0) because per-turn scoping
wiped coverage on every follow-up message, causing constant false blocks.
That scoping bug is now fixed: open_turn() preserves existing stamps across
messages instead of resetting them. Coverage persists until the TTL expires or
new research runs. With persistent stamps the gate can be a real block again.

Exit codes: 0 = allowed, 2 = blocked (PreToolUse hard refuse).
"""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import research_audit  # noqa: E402
from manifest_files import is_gated_file  # noqa: E402
from research_state import check_file_researched, is_quick_turn  # noqa: E402

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

    if not is_gated_file(path, CODE_EXTENSIONS):
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
        f"[research-gate] BLOCKED: {reason}.\n\n"
        f"Cannot edit: {file_path}\n\n"
        "Spawn researcher and/or swiper before editing this file. Tell them what\n"
        "you are changing, why, and the code you intend to write. Both read the\n"
        "real files and cover depth and breadth every time; neither shortcuts a\n"
        "change it judges trivial. Use /ps to skip this gate for a turn you\n"
        "already know is trivial.\n\n"
        "Spawn in the foreground: run_in_background: false, never true. A\n"
        "backgrounded completion arrives as a TaskNotificationMessage, not a\n"
        "tool result, so the hook that stamps this record never fires for it.\n\n"
        "Their reports end with a line naming every file the research covers:\n\n"
        "    COVERS: clean-rag/server/app.py, clean-rag/hooks/*.py\n\n"
        "One research run can cover a whole coherent change across many files,\n"
        "so you do not need one agent per file.",
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

    # A /ps turn is the human's explicit skip. Allow the edit, but still chain an
    # audit entry so a quick turn is permanently visible, not an invisible bypass.
    if is_quick_turn(session_id):
        research_audit.append(
            file_path=file_path, session_id=session_id,
            allowed=True, reason="quick mode (/ps)", covering_agent="",
        )
        return 0

    ok, reason = check_file_researched(session_id, file_path)

    # Every code edit gets a line, allowed or blocked, chained to the one before.
    #
    # This is the part that survives a forged stamp. Someone can hand themselves
    # a pass in the moment, but they cannot go back and quietly unwrite this
    # entry: the hash chain means editing or deleting it breaks every entry that
    # follows, the same way rewriting an old git commit changes every commit id
    # after it. Prevention isn't achievable at this privilege level. Making the
    # lie permanent and greppable is.
    research_audit.append(
        file_path=file_path,
        session_id=session_id,
        allowed=ok,
        reason=reason,
        covering_agent=reason.replace("covered by ", "") if ok else "",
    )

    if ok:
        return 0

    return _block(file_path, reason)


if __name__ == "__main__":
    sys.exit(main())
