#!/usr/bin/env python
"""PreToolUse gate on Edit, Write, and MultiEdit.

Nudges toward research when the file hasn't been covered this session, and
allows the edit either way. Nothing here refuses an edit.

This replaces the old proof gate idea outright. That one asked the model to
write a proof file attesting it had researched, which proves nothing: the model
writes the file, so the file only ever says what the model wanted it to say.

Markdown and other non code files pass through untouched. So do the usual
scratch directories. Research is for code, and gating a doc tweak on a subagent
spawn would just teach you to hate the gate.

This hook is a nudge on purpose, and it stays one. It blocked once, and the
per-turn scoping wiped coverage on every follow-up message, so a file swiper
had just covered needed covering again the moment another message arrived.
open_turn() later fixed that scoping by preserving stamps across messages,
which made a real block possible again. It is still not one, by decision: the
research the gate asks for is a process step, not a safety boundary, and the
measured tradeoff (arxiv 2604.11088) is that a hard boundary is worth its
friction for something irreversible, not for ceremony. An unresearched edit is
recoverable. A nudge plus an honest audit trail is the whole job here.

The audit trail is the part that still cannot be faked. Only Claude Code can
start an agent, and the record is stamped by a PostToolUse hook after the agent
finishes, so "I researched it" is never what gets recorded.

Exit codes: 0 always, on any payload shape. Nothing here blocks. The payload
arrives on stdin from outside this process, so its fields are read defensively
(_str_field) and the __main__ guard catches anything left over: a gate that
crashes on a surprising payload is a gate that reports nothing.
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


def _str_field(source, key: str) -> str:
    """A string field read out of an untrusted payload object, or "" if it isn't one.

    Stdin is a system boundary, and every shape that breaks a naive
    source[key] read is still valid JSON: the containing object present but null
    (so .get's default never applies) or a string instead of an object, and the
    field itself a number or a list rather than a string. Each of those reaches
    code that assumes str and raises somewhere unrelated -- Path() raises
    TypeError on an int file_path, and a non-str session_id raises AttributeError
    on .encode() while being hashed. Reading them all as "" routes them to the
    same paths that already handle a genuinely absent field.
    """
    value = source.get(key) if isinstance(source, dict) else None
    return value if isinstance(value, str) else ""


def _block(file_path: str, reason: str) -> int:
    print(
        f"[research-gate] NUDGE: {reason}.\n\n"
        f"Editing without research coverage: {file_path}\n\n"
        "Consider spawning researcher and/or swiper before editing this file.\n"
        "Use /ps to acknowledge this is intentionally unresearched.",
        file=sys.stderr,
    )
    # Nudge, not block: warn but allow the edit to proceed.
    return 0


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read())
    except Exception:
        # Can't read the payload, so can't tell what's being edited. Failing open
        # is right here: a broken gate must not brick all editing.
        return 0

    # Valid JSON is not necessarily an object. A bare scalar or list has no .get,
    # so it tells us nothing about the edit either, same as an unparseable payload.
    if not isinstance(payload, dict):
        return 0

    if payload.get("tool_name") not in ("Edit", "Write", "MultiEdit"):
        return 0

    if os.environ.get("CLEAN_RAG_RESEARCH_GATE") == "off":
        return 0

    file_path = _str_field(payload.get("tool_input"), "file_path")

    exempt, _why = _is_exempt(file_path)
    if exempt:
        return 0

    session_id = _str_field(payload, "session_id")

    # A /ps turn is the human's explicit skip. Allow the edit, but still chain an
    # audit entry so a quick turn is permanently visible, not an invisible bypass.
    if is_quick_turn(session_id):
        research_audit.append(
            file_path=file_path, session_id=session_id,
            allowed=True, reason="quick mode (/ps)", covering_agent="",
        )
        return 0

    ok, reason = check_file_researched(session_id, file_path)

    # Every code edit gets a line, covered or not, chained to the one before.
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
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)
