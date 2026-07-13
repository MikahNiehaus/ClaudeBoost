#!/usr/bin/env python3
"""spec-compliance-gate.py: Stop hook that blocks a turn ending when the
original task prompt named a technology/framework that never shows up in
what got written.

Citation: workspace/llama-server-wifi-switch-2026-07-01/context.md, v14
finding -- a task explicitly said "use react" and the model shipped a
vanilla-JS game with no package.json/React import anywhere. proof-gate.py
enforces that edits are research-backed; it has no way to check whether an
edit satisfies what the user actually asked for. This hook fills that gap.

Modeled on research-stop-gate.py's shape: a regex-based command hook, not
an LLM call. Payload fields confirmed via code.claude.com/docs/en/hooks
(Stop event): session_id, transcript_path, cwd, hook_event_name,
stop_hook_active -- there is no pre-parsed prompt or file list, so this
hook reads transcript_path itself and extracts both from the JSONL.

Exit codes:
  0 = allow (no tracked keyword was requested, or every requested keyword
      shows up somewhere in the files changed this turn)
  2 = block (a keyword from the prompt never appears in anything written)
"""

import json
import re
import sys
from pathlib import Path

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
        return 0

    print(_build_consolidated_message(missing), file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
