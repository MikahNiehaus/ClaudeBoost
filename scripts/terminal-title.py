#!/usr/bin/env python
"""Rename the terminal tab to say what Claude is doing right now.

Claude Code has no built in setting for this (checked against
code.claude.com/docs/en/settings), so it is a hook. Registered on three events
so the title tracks the thing you actually wait on:

  UserPromptSubmit  ->  the task you just asked for
  PreToolUse/Task   ->  the agent now running, which is the long wait
  Stop              ->  idle

WHY NOT STDOUT
An OSC escape on stdout looks like the obvious answer and is wrong.
UserPromptSubmit stdout is injected into Claude's context rather than printed,
so the escape sequence would land in the conversation as garbage and never reach
the terminal. Titles go to the console directly: SetConsoleTitleW on Windows,
/dev/tty elsewhere.

This hook must never block or speak. Anything it prints on UserPromptSubmit
becomes context, and a non zero exit on PreToolUse is read as "refuse this tool
call". Every path returns 0 and every failure is swallowed.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

MAX_TITLE = 70

# Slash command or leading noise we do not want in the title.
_SLASH = re.compile(r"^/([a-z0-9_-]+)\s*", re.IGNORECASE)
_WS = re.compile(r"\s+")


def _set_title(text: str) -> None:
    """Best effort, on every platform, silent on failure."""
    if sys.platform == "win32":
        try:
            import ctypes

            ctypes.windll.kernel32.SetConsoleTitleW(text)
        except Exception:
            pass
        # Windows Terminal honours OSC too, and a tab title set this way
        # survives some cases SetConsoleTitleW does not.
        try:
            with open("CONOUT$", "w", encoding="utf-8") as con:
                con.write(f"\x1b]0;{text}\x07")
                con.flush()
        except Exception:
            pass
        return
    try:
        with open("/dev/tty", "w", encoding="utf-8") as tty:
            tty.write(f"\x1b]0;{text}\x07")
            tty.flush()
    except Exception:
        pass


def _project(payload: dict) -> str:
    """Short label for which repo this terminal is in.

    The whole point is telling two terminals apart, so the project name earns
    its space in a 70 char budget.
    """
    cwd = payload.get("cwd") or os.getcwd()
    try:
        return Path(cwd).name or "claude"
    except Exception:
        return "claude"


def _clean(text: str, limit: int) -> str:
    """One line, ASCII only, truncated on a word boundary where possible.

    ASCII only is not fussiness: non ASCII in a Windows terminal title renders
    as mojibake, which is worse than dropping the character.
    """
    text = _WS.sub(" ", (text or "").strip())
    text = text.encode("ascii", "ignore").decode("ascii")
    if limit <= 0:
        return ""
    if len(text) <= limit:
        return text
    # The ellipsis counts against the limit. Appending it after cutting to
    # `limit` overshoots by 3, which is how a 70 char budget produced a 71
    # char title.
    if limit <= 3:
        return text[:limit]
    room = limit - 3
    cut = text[:room]
    tail = cut.rfind(" ")
    if tail > room // 2:
        cut = cut[:tail]
    return cut.rstrip(" .,:;") + "..."


def _from_prompt(prompt: str) -> str:
    """Turn the user's message into a short activity label.

    A slash command is the best available summary when present: "/start ..." is
    more informative as "start" than as its first few words of prose.
    """
    prompt = _WS.sub(" ", (prompt or "").strip())
    match = _SLASH.match(prompt)
    if match:
        rest = prompt[match.end():]
        verb = match.group(1)
        return f"/{verb} {rest}".strip() if rest else f"/{verb}"
    return prompt


def _title(payload: dict) -> str | None:
    """The title for this event, or None to leave the current one alone."""
    event = payload.get("hook_event_name", "")
    project = _project(payload)
    budget = MAX_TITLE - len(project) - 3  # " | "

    if event == "UserPromptSubmit":
        activity = _from_prompt(payload.get("prompt", ""))
        if not activity:
            return None
        return f"{project} | {_clean(activity, budget)}"

    if event == "PreToolUse":
        if payload.get("tool_name") not in ("Task", "Agent"):
            return None
        tool_input = payload.get("tool_input") or {}
        agent = tool_input.get("subagent_type") or "agent"
        what = tool_input.get("description") or ""
        label = f"[{agent}] {what}".strip()
        return f"{project} | {_clean(label, budget)}"

    if event == "Stop":
        return f"{project} | idle"

    return None


def main() -> int:
    try:
        raw = sys.stdin.read() if not sys.stdin.isatty() else ""
        payload = json.loads(raw) if raw.strip() else {}
    except Exception:
        return 0
    if not isinstance(payload, dict):
        return 0
    try:
        title = _title(payload)
    except Exception:
        return 0
    if title:
        # _set_title swallows its own failures, but the guard belongs here too.
        # On PreToolUse a non zero exit is read as "refuse this tool call", so a
        # cosmetic hook must not be able to block an Edit if that ever changes.
        try:
            _set_title(title)
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        # A title is cosmetic. It must never be the reason a turn fails.
        sys.exit(0)
