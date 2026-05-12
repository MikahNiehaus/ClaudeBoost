"""
ClaudeBoost handoff-core — transcript extraction for context handoff.

Parses a Claude Code transcript JSONL and extracts recent conversation
highlights: user messages, assistant snippets, and file paths touched.

Adapted from who96/claude-code-context-handoff (MIT) with Windows path
support and no external state directory dependency.
"""
from __future__ import annotations

import json
import re
from difflib import SequenceMatcher
from pathlib import Path
from typing import Optional


def _is_file_path(value: str) -> bool:
    """Accept Unix and Windows absolute paths. Reject shell injection patterns."""
    if not isinstance(value, str) or len(value) < 3:
        return False
    # Reject shell metacharacters
    if any(c in value for c in ("&&", "||", "|", ";", "$(", "`", "\n", "\r")):
        return False
    # Unix absolute path
    if value.startswith("/"):
        return True
    # Windows: C:\ or C:/
    if re.match(r"^[A-Za-z]:[/\\]", value):
        return True
    return False


def _collect_paths(obj: object, paths: set) -> None:
    """Recursively walk JSON object collecting values of 'file_path' and 'path' keys."""
    if isinstance(obj, dict):
        for key, val in obj.items():
            if key in ("file_path", "path") and isinstance(val, str) and _is_file_path(val):
                paths.add(val)
            else:
                _collect_paths(val, paths)
    elif isinstance(obj, list):
        for item in obj:
            _collect_paths(item, paths)


def _similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a[:200], b[:200]).ratio()


def _dedup(messages: list, threshold: float = 0.85) -> list:
    """Remove near-duplicate messages, keeping first occurrence."""
    result: list = []
    for msg in messages:
        if not any(_similarity(msg, kept) >= threshold for kept in result):
            result.append(msg)
    return result


_JUNK_ASSISTANT = (
    "API Error:",
    "rate_limit",
    "invalid_request_error",
    "overloaded",
    "No response requested",
    "(no content)",
)

_JUNK_USER = (
    "[Request interrupted by user]",
)


def extract_conversation(
    transcript_path: str,
    max_user: int = 15,
    max_assistant_chars: int = 800,
    max_snippets: int = 10,
    max_files: int = 20,
    dedup_threshold: float = 0.85,
) -> Optional[dict]:
    """
    Parse a Claude Code transcript JSONL and extract conversation highlights.

    Returns:
        {"user_messages": [...], "assistant_snippets": [...], "files_touched": [...]}
    Returns None if transcript is unreadable or contains no useful content.
    """
    path = Path(transcript_path)
    if not path.exists() or not path.is_file():
        return None

    user_messages: list = []
    assistant_snippets: list = []
    files_touched: set = set()

    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except Exception:
        return None

    # Guard against timeout on very long sessions: only parse last MAX_LINES lines
    MAX_LINES = 2000
    if len(lines) > MAX_LINES:
        lines = lines[-MAX_LINES:]

    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except Exception:
            continue

        entry_type = entry.get("type", "")

        if entry_type == "user":
            message = entry.get("message", {})
            content = message.get("content", "")
            if isinstance(content, str):
                text = content.strip()
            elif isinstance(content, list):
                parts = []
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        parts.append(block.get("text", ""))
                text = " ".join(parts).strip()
            else:
                text = ""

            if text and not any(junk in text for junk in _JUNK_USER):
                user_messages.append(text)

        elif entry_type == "assistant":
            message = entry.get("message", {})
            content = message.get("content", [])
            if isinstance(content, list):
                for block in content:
                    if not isinstance(block, dict):
                        continue
                    if block.get("type") == "text":
                        text = block.get("text", "").strip()
                        if text and not any(junk in text for junk in _JUNK_ASSISTANT):
                            snippet = text[:max_assistant_chars]
                            assistant_snippets.append(snippet)
                    elif block.get("type") == "tool_use":
                        _collect_paths(block.get("input", {}), files_touched)

    # Deduplicate and trim
    user_messages = _dedup(user_messages, dedup_threshold)[-max_user:]
    assistant_snippets = _dedup(assistant_snippets, dedup_threshold)[-max_snippets:]
    files_list = sorted(files_touched)[:max_files]

    if not user_messages and not files_list:
        return None

    return {
        "user_messages": user_messages,
        "assistant_snippets": assistant_snippets,
        "files_touched": files_list,
    }


def format_conversation_md(conversation: dict) -> str:
    """Format conversation dict as a markdown block for additionalContext."""
    if not conversation:
        return ""

    parts = []

    user_messages = conversation.get("user_messages", [])
    if user_messages:
        parts.append("## Recent User Messages")
        for i, msg in enumerate(user_messages, 1):
            display = msg[:500] + ("..." if len(msg) > 500 else "")
            parts.append(f"{i}. {display}")

    assistant_snippets = conversation.get("assistant_snippets", [])
    if assistant_snippets:
        parts.append("\n## Key Assistant Responses")
        for snippet in assistant_snippets:
            display = snippet[:300] + ("..." if len(snippet) > 300 else "")
            parts.append(f"- {display}")

    files_touched = conversation.get("files_touched", [])
    if files_touched:
        parts.append("\n## Files Touched This Session")
        for f in files_touched:
            parts.append(f"- {f}")

    return "\n".join(parts)
