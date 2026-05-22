"""
ClaudeBoost human-voice-guard -- Stop hook.

Reads the last assistant turn from the conversation transcript and checks for:
- Banned AI vocabulary (delve, pivotal, robust, seamless, etc.)
- Banned filler phrases (Certainly!, Great question!, Furthermore,, etc.)
- Em-dash overuse (more than 1 in the response)

Skips text inside:
- Fenced code blocks (``` ... ```)
- Inline code (` ... `)
- Double-quoted strings (examples shown in quotes don't count per user rule)

Blocks Claude from stopping if violations found. Includes loop prevention:
if the same message hash was already blocked once, let it through rather than
looping forever.

Exit codes:
  0 = no violations, or loop guard triggered -- allow stop
  2 = violations found -- block and list exactly what to fix
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from pathlib import Path

BANNED_WORDS: set[str] = {
    "delve", "delving", "delved",
    "underscore", "underscores", "underscored",
    "pivotal",
    "robust",
    "seamless", "seamlessly",
    "comprehensive", "comprehensively",
    "nuanced",
    "leverage", "leverages", "leveraged", "leveraging",
    "utilize", "utilizes", "utilized", "utilizing",
    "facilitate", "facilitates", "facilitated", "facilitating",
    "harness", "harnesses", "harnessed", "harnessing",
    "illuminate", "illuminates", "illuminated", "illuminating",
    "bolster", "bolsters", "bolstered", "bolstering",
    "tapestry",
    "realm", "realms",
    "beacon", "beacons",
    "cacophony",
    "foster", "fosters", "fostered", "fostering",
    "intricate", "intricately",
    "palpable", "palpably",
    "transformative",
    "revolutionary",
    "paradigm", "paradigms",
    "synergy", "synergies", "synergistic",
    "holistic", "holistically",
    "empower", "empowers", "empowered", "empowering",
    "embark", "embarks", "embarked", "embarking",
    "spearhead", "spearheads", "spearheaded",
}

BANNED_PHRASES: list[str] = [
    "certainly!",
    "great question",
    "absolutely!",
    "of course!",
    "i'd be happy to",
    "i'd be glad to",
    "it's worth noting",
    "it is worth noting",
    "it's important to note",
    "it is important to note",
    "it goes without saying",
    "as an ai",
    "in today's rapidly evolving",
    "in today's fast-paced",
    "at its core",
    "at the end of the day",
    "the fact of the matter",
    "furthermore,",
    "moreover,",
    "additionally,",
    "consequently,",
]

EM_DASH = "\u2014"  # —
EM_DASH_LIMIT = 1


def strip_noise(text: str) -> str:
    """Remove fenced code blocks, inline code, and double-quoted strings."""
    # Fenced code blocks
    text = re.sub(r"```[\s\S]*?```", "", text)
    # Inline code
    text = re.sub(r"`[^`\n]+`", "", text)
    # Double-quoted strings (user rule: examples in quotes don't count)
    text = re.sub(r'"[^"]{3,300}"', "", text)
    return text


def get_last_assistant_text(transcript_path: str) -> str:
    """Return the plain text of the last assistant turn in the transcript."""
    try:
        raw_lines = Path(transcript_path).read_text(encoding="utf-8").splitlines()
    except Exception:
        return ""

    last = ""
    for line in raw_lines:
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except Exception:
            continue
        if entry.get("role") != "assistant":
            continue
        content = entry.get("content", "")
        if isinstance(content, str):
            last = content
        elif isinstance(content, list):
            parts = [
                block.get("text", "")
                for block in content
                if isinstance(block, dict) and block.get("type") == "text"
            ]
            if parts:
                last = " ".join(parts)
    return last


def check_violations(text: str) -> list[str]:
    clean = strip_noise(text)
    violations: list[str] = []

    # Banned vocabulary (word boundary match)
    words_found = [w for w in re.findall(r"\b\w+\b", clean.lower()) if w in BANNED_WORDS]
    if words_found:
        unique = list(dict.fromkeys(words_found))
        violations.append(f"Banned vocabulary used: {', '.join(unique)}")

    # Banned phrases (substring match, case-insensitive)
    lower = clean.lower()
    found_phrases = [p for p in BANNED_PHRASES if p in lower]
    if found_phrases:
        violations.append(f"Banned phrases used: {', '.join(found_phrases)}")

    # Em-dash overuse
    em_count = clean.count(EM_DASH)
    if em_count > EM_DASH_LIMIT:
        violations.append(f"Em-dash overuse: {em_count} em-dashes in response (max {EM_DASH_LIMIT})")

    return violations


def main() -> int:
    raw = sys.stdin.read() if not sys.stdin.isatty() else ""
    try:
        payload = json.loads(raw) if raw else {}
    except Exception:
        payload = {}

    transcript_path = payload.get("transcript_path", "")
    if not transcript_path:
        return 0

    home = Path(os.environ.get("CLAUDEBOOST_HOME") or Path(__file__).resolve().parent.parent)
    state_path = home / "state" / "human-voice-check.json"

    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except Exception:
        state = {}

    last_msg = get_last_assistant_text(transcript_path)
    if not last_msg:
        return 0

    msg_hash = hashlib.md5(last_msg.encode()).hexdigest()

    # Loop prevention: if we already blocked on this exact message, let it through.
    # Claude tried to fix it and couldn't — don't loop forever.
    if state.get("last_blocked_hash") == msg_hash:
        try:
            state_path.write_text(json.dumps({}), encoding="utf-8")
        except Exception:
            pass
        return 0

    violations = check_violations(last_msg)

    if not violations:
        try:
            state_path.write_text(json.dumps({}), encoding="utf-8")
        except Exception:
            pass
        return 0

    # Save hash so we don't loop on the same message
    try:
        state_path.write_text(json.dumps({"last_blocked_hash": msg_hash}), encoding="utf-8")
    except Exception:
        pass

    violation_list = "\n".join(f"  - {v}" for v in violations)
    reason = (
        "HUMAN VOICE VIOLATION -- rewrite before stopping.\n\n"
        f"{violation_list}\n\n"
        "Fix rules:\n"
        "  - Banned words: replace with plain English (see knowledge/human-voice.xml)\n"
        "  - Banned phrases: cut entirely, start with the substance\n"
        "  - Em-dashes: rewrite as separate sentences\n"
        "Quoted examples and code blocks are excluded from this check."
    )

    print(json.dumps({"decision": "block", "reason": reason}))
    return 2


if __name__ == "__main__":
    sys.exit(main())
