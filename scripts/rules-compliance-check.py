"""
ClaudeBoost rules-compliance-check — Stop hook.

Reads the last assistant turn and checks that it contains a populated
[Rules Check] block with all required fields filled in. Forces Claude
to articulate how it followed each behavioral rule before stopping.

Fires on any non-trivial response, including read-only work (file reads,
searches, grep). Not just writes/edits. Anything more than a one-liner.

Required block format (must appear at end of response):

  [Rules Check]
  tone: <concise, informal, polite — no banned vocab>
  no dashes: <confirmed none used, or note any violations>
  rag used: <which tiers searched (vector/graph/context), or n/a if no codebase lookup needed>
  context updated: <what was added to context.md, or n/a>
  architecture confirmed: <confirmed or n/a>
  destructive actions: <confirmed with user or n/a>
  instructions followed: <yes + brief summary, or what was flagged>

Exit codes:
  0 = block present with all fields populated, or response too short, or loop guard
  2 = block missing or any field empty — force Claude to add it
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from pathlib import Path

MIN_RESPONSE_CHARS = 80

REQUIRED_FIELDS = [
    "tone",
    "no dashes",
    "rag used",
    "context updated",
    "architecture confirmed",
    "destructive actions",
    "instructions followed",
]


def get_last_assistant_text(transcript_path: str) -> str:
    """Return the plain text of the last assistant turn."""
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
                last = "\n".join(parts)
    return last


def check_compliance_block(text: str) -> list[str]:
    """Return list of missing or empty fields. Empty list means all good."""
    header_match = re.search(r'\[rules check\]', text, re.IGNORECASE)
    if not header_match:
        return ["[Rules Check] block is missing entirely"]

    block_text = text[header_match.start():]
    missing = []
    for field in REQUIRED_FIELDS:
        pattern = re.compile(
            r"^\s*" + re.escape(field) + r"\s*:\s*(.+)",
            re.IGNORECASE | re.MULTILINE,
        )
        match = pattern.search(block_text)
        if not match or not match.group(1).strip():
            missing.append(f'"{field}:" is missing or empty')
    return missing


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
    state_path = home / "state" / "rules-compliance-check.json"

    # Skip during audit runs so the parallel audit agents aren't blocked.
    audit_flag = home / "state" / "audit-in-progress.json"
    if audit_flag.exists():
        try:
            flag_data = json.loads(audit_flag.read_text(encoding="utf-8"))
            if flag_data.get("active"):
                return 0
        except Exception:
            return 0

    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except Exception:
        state = {}

    last_msg = get_last_assistant_text(transcript_path)
    if not last_msg:
        return 0

    # Skip very short responses (quick confirmations, one-liners).
    if len(last_msg.strip()) < MIN_RESPONSE_CHARS:
        return 0

    msg_hash = hashlib.md5(last_msg.encode()).hexdigest()

    # Loop prevention: if we already blocked this exact message once, let it
    # through. Claude tried to fix it and either couldn't or did — don't loop.
    if state.get("last_blocked_hash") == msg_hash:
        try:
            state_path.parent.mkdir(parents=True, exist_ok=True)
            state_path.write_text(json.dumps({}), encoding="utf-8")
        except Exception:
            pass
        return 0

    missing = check_compliance_block(last_msg)

    if not missing:
        try:
            state_path.parent.mkdir(parents=True, exist_ok=True)
            state_path.write_text(json.dumps({}), encoding="utf-8")
        except Exception:
            pass
        return 0

    try:
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps({"last_blocked_hash": msg_hash}), encoding="utf-8")
    except Exception:
        pass

    missing_list = "\n".join(f"  - {m}" for m in missing)
    reason = (
        "RULES COMPLIANCE BLOCK REQUIRED — add before stopping.\n\n"
        f"Missing or empty fields:\n{missing_list}\n\n"
        "Add this block at the end of your response:\n\n"
        "  [Rules Check]\n"
        "  tone: <concise, informal, polite — no banned vocab>\n"
        "  no dashes: <confirmed none used, or note any violations>\n"
        "  rag used: <which tiers searched (vector/graph/context), or n/a if no codebase lookup needed>\n"
        "  context updated: <what you added to context.md, or n/a>\n"
        "  architecture confirmed: <confirmed or n/a>\n"
        "  destructive actions: <confirmed with user or n/a>\n"
        "  instructions followed: <yes + brief summary, or what you flagged>\n\n"
        "Every field must have a non-empty value. 'n/a' is acceptable when a rule does not apply this turn.\n"
        "The 'rag used' field must be honest: if you did codebase work without searching RAG, say so."
    )

    print(json.dumps({"decision": "block", "reason": reason}))
    return 2


if __name__ == "__main__":
    sys.exit(main())
