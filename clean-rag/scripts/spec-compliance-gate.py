#!/usr/bin/env python3
"""spec-compliance-gate.py: Stop hook that blocks a turn ending when the
original task prompt named a technology/framework that never shows up in
what got written.

Citation: workspace/llama-server-wifi-switch-2026-07-01/context.md, v14
finding -- a task explicitly said "use react" and the model shipped a
vanilla-JS game with no package.json/React import anywhere. proof-gate.py
enforces that edits are research-backed; it has no way to check whether an
edit satisfies what the user actually asked for. This hook fills that gap.

A regex-based command hook, not an LLM call. Payload fields confirmed via
code.claude.com/docs/en/hooks (Stop event): session_id, transcript_path,
cwd, hook_event_name, stop_hook_active -- there is no pre-parsed prompt or
file list, so this hook reads transcript_path itself and extracts both
from the JSONL.

This is one of exactly two Stop hooks that genuinely block; auto-test-gate.py
is the other. Blocking earns a per session firing cap, copied from that
hook, so a compliance check the model cannot satisfy cannot wedge the
session shut. stop_hook_active alone only stops an immediate bounce; it
does nothing about the same mismatch recurring later in a long session.

Exit codes:
  0 = allow (no tracked keyword was requested, every requested keyword
      shows up somewhere in the files changed this turn, or the session
      already spent its block budget)
  2 = block (a keyword from the prompt never appears in anything written)
"""

import json
import os
import re
import sys
from pathlib import Path

CLEAN_RAG_HOME = Path(os.environ.get("CLEAN_RAG_HOME") or Path(__file__).resolve().parent.parent)
STATE_DIR = CLEAN_RAG_HOME / "state"
BLOCK_DIR = STATE_DIR / "spec-compliance-gate"
MAX_BLOCKS_PER_SESSION = 2

# Small fixed keyword list -- no NLP needed. Each entry is the keyword to
# look for in the prompt, paired with the patterns to search for in the
# written files (case-insensitive). Extend this list as new gaps are found.
TRACKED_KEYWORDS = {
    "react": [r"\breact\b", r'"react"\s*:', r"from ['\"]react['\"]"],
    "vue": [r"\bvue\b", r'"vue"\s*:', r"from ['\"]vue['\"]"],
    "typescript": [r"\btypescript\b", r"\.tsx?\b"],
    "svelte": [r"\bsvelte\b", r'"svelte"\s*:'],
    "angular": [r"\bangular\b", r'"@angular/core"'],
    "tailwind": [r"\btailwind\b", r'"tailwindcss"\s*:'],
    "docker": [r"\bdocker\b", r"Dockerfile"],
}


def _extract_requested_keywords(prompt_text: str) -> list[str]:
    found = []
    lowered = prompt_text.lower()
    for keyword in TRACKED_KEYWORDS:
        if re.search(rf"\b{re.escape(keyword)}\b", lowered):
            found.append(keyword)
    return found


def _read_transcript_events(transcript_path: str) -> list[dict]:
    events = []
    path = Path(transcript_path)
    if not path.exists():
        return events
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return events


def _first_user_prompt(events: list[dict]) -> str:
    """The task prompt is the first real user-role text block, skipping
    synthetic system reminders and tool_result blocks."""
    for event in events:
        if event.get("type") != "user":
            continue
        message = event.get("message", {})
        content = message.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            for block in content:
                if block.get("type") == "text":
                    return block.get("text", "")
    return ""


def _changed_files_this_turn(events: list[dict]) -> list[Path]:
    """Files touched by Write/Edit/MultiEdit tool_use blocks anywhere in
    the transcript. Reruns the whole transcript rather than just the last
    turn, since spec compliance is a whole-task property, not a
    single-turn one -- a file written early and never touched again still
    counts."""
    changed = set()
    for event in events:
        message = event.get("message", {})
        content = message.get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if block.get("type") != "tool_use":
                continue
            if block.get("name") not in ("Write", "Edit", "MultiEdit"):
                continue
            file_path = block.get("input", {}).get("file_path")
            if file_path:
                changed.add(file_path)
    return [Path(f) for f in changed if Path(f).exists()]


def _keyword_present_in_files(keyword: str, changed_files: list[Path]) -> bool:
    patterns = TRACKED_KEYWORDS[keyword]
    for file_path in changed_files:
        for pattern in patterns:
            if re.search(pattern, file_path.name, re.IGNORECASE):
                return True
        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for pattern in patterns:
            if re.search(pattern, content, re.IGNORECASE):
                return True
    return False


def _block_count(session_id: str) -> int:
    f = BLOCK_DIR / f"{session_id or 'nosession'}.count"
    try:
        return int(f.read_text(encoding="utf-8").strip())
    except Exception:
        return 0


def _bump_block_count(session_id: str) -> bool:
    """Record one more block for this session. True if it actually persisted.

    The return value is the whole point. If the count cannot be written (the
    state directory is unwritable, the disk is full, a scanner holds the file),
    then _block_count reads back 0 forever and the cap can never be reached. A
    caller that blocks anyway would wedge the session shut permanently, which is
    the exact failure the cap exists to prevent. So the caller checks this and
    declines to block when the budget cannot be tracked.
    """
    f = BLOCK_DIR / f"{session_id or 'nosession'}.count"
    try:
        BLOCK_DIR.mkdir(parents=True, exist_ok=True)
        f.write_text(str(_block_count(session_id) + 1), encoding="utf-8")
        return True
    except Exception:
        return False


def _reset_block_count(session_id: str) -> None:
    """Clear the cap once the turn actually complies.

    Without this, the cap silences the check for the rest of the session
    the first time two blocks land, even if every turn after that is
    compliant. The cap exists to stop a stuck loop, not to give up on
    checking for the rest of a long session.
    """
    f = BLOCK_DIR / f"{session_id or 'nosession'}.count"
    try:
        f.unlink(missing_ok=True)
    except Exception:
        pass


def _build_consolidated_message(missing: list[str]) -> str:
    lines = "\n".join(f"  - {kw}" for kw in missing)
    return (
        "CLEAN-RAG: the original task asked for the following, but none of "
        "them show up anywhere in the files changed this session:\n"
        f"{lines}\n\n"
        "If this was intentional (the user changed their mind mid-task, or "
        "the requirement genuinely does not apply), say so explicitly. "
        "Otherwise, add what's missing before ending the turn."
    )


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, ValueError):
        return 0  # can't parse -- never block on our own malfunction

    # Same loop guard convention as proof-stop-gate.py and speak-tts.py --
    # never block the same turn twice in a row.
    if payload.get("stop_hook_active", False):
        return 0

    session_id = payload.get("session_id") or ""
    if not isinstance(session_id, str):
        session_id = ""

    transcript_path = payload.get("transcript_path", "")
    if not transcript_path:
        return 0

    events = _read_transcript_events(transcript_path)
    if not events:
        return 0

    prompt_text = _first_user_prompt(events)
    if not prompt_text:
        return 0

    requested = _extract_requested_keywords(prompt_text)
    if not requested:
        return 0

    changed_files = _changed_files_this_turn(events)
    if not changed_files:
        return 0

    missing = [
        kw for kw in requested
        if not _keyword_present_in_files(kw, changed_files)
    ]

    if not missing:
        _reset_block_count(session_id)
        return 0

    if _block_count(session_id) >= MAX_BLOCKS_PER_SESSION:
        print(
            "[spec-compliance-gate] Still missing "
            f"{', '.join(missing)} after {MAX_BLOCKS_PER_SESSION} blocks "
            "this session. Not blocking again (anti loop). Add what the "
            "task asked for, or say plainly that it no longer applies.",
            file=sys.stderr,
        )
        return 0

    if not _bump_block_count(session_id):
        # The budget could not be recorded, so the cap above can never fire and
        # every future Stop would block again. An uncounted block is an unbounded
        # one, so this allows instead and says why.
        print(
            "[spec-compliance-gate] Could not record the block budget under "
            f"{BLOCK_DIR}, so the anti loop cap cannot work. Not blocking "
            f"(missing: {', '.join(missing)}).",
            file=sys.stderr,
        )
        return 0

    print(_build_consolidated_message(missing), file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
