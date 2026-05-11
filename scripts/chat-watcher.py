#!/usr/bin/env python3
"""
ClaudeBoost Chat Watcher — answers questions from the changes TUI viewer.

Polls the chat JSON file every 3 seconds and answers unanswered questions
using `claude -p` (Claude Code CLI non-interactive mode). No API key needed —
uses the same OAuth credentials as the running Claude Code session.
Runs for up to 15 minutes then exits. Launch via: python chat-watcher.py

Chat file format:
  {
    "question": "what does this do?",
    "context_file": "src/foo.py",
    "context_code": "...",
    "asked_at": "2026-05-09T...",
    "answer": "",
    "answered_at": ""
  }
"""

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

POLL_INTERVAL = 3       # seconds between checks
MAX_RUNTIME = 15 * 60  # 15 minutes then exit

CHAT_FILES = [
    Path(os.environ.get("TEMP", "/tmp")) / "claudeboost" / "changes_chat.json",
]

SYSTEM_PROMPT = (
    "You are answering a developer's question about a specific piece of code shown in a diff viewer. "
    "Give a concise, direct answer in 1-3 sentences. No preamble, no markdown headers, just the answer. "
    "If the question is a test ('are you there', 'hello'), confirm you're working."
)


def answer_question(question: str, context_file: str, context_code: str) -> str:
    """Use `claude -p` to answer the question with code context."""
    context_parts = []
    if context_file:
        context_parts.append(f"File: {context_file}")
    if context_code:
        context_parts.append(f"Code:\n```\n{context_code}\n```")
    context_parts.append(f"Question: {question}")

    prompt = "\n\n".join(context_parts)

    # Unset CLAUDECODE so `claude -p` can launch outside the parent session
    env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}

    result = subprocess.run(
        [
            "claude", "-p",
            "--model", "claude-haiku-4-5-20251001",
            "--append-system-prompt", SYSTEM_PROMPT,
            prompt,
        ],
        capture_output=True,
        text=True,
        timeout=60,
        env=env,
    )
    if result.returncode != 0:
        raise RuntimeError(f"claude -p failed (rc={result.returncode}): {result.stderr.strip()[:200]}")
    return result.stdout.strip()


def check_and_answer(chat_file: Path) -> None:
    """Check one chat file and answer the question if unanswered."""
    if not chat_file.exists():
        return
    try:
        data = json.loads(chat_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return

    if data.get("answer"):  # already answered
        return

    question = data.get("question", "").strip()
    if not question:
        return

    try:
        answer = answer_question(
            question,
            data.get("context_file", ""),
            data.get("context_code", ""),
        )
        data["answer"] = answer
        data["answered_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        chat_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
        print(f"[chat-watcher] Answered: {question[:60]}", flush=True)
    except Exception as e:
        print(f"[chat-watcher] Error: {e}", flush=True)


def main() -> None:
    # Verify claude CLI is available
    try:
        subprocess.run(["claude", "--version"], capture_output=True, check=True, timeout=5)
    except (subprocess.SubprocessError, FileNotFoundError) as e:
        print(f"[chat-watcher] 'claude' CLI not found: {e}", flush=True)
        sys.exit(1)

    start = time.monotonic()
    print(f"[chat-watcher] Started — polling every {POLL_INTERVAL}s for {MAX_RUNTIME // 60}min", flush=True)

    while time.monotonic() - start < MAX_RUNTIME:
        for chat_file in CHAT_FILES:
            check_and_answer(chat_file)
        time.sleep(POLL_INTERVAL)

    print("[chat-watcher] 15-minute window elapsed — exiting", flush=True)


if __name__ == "__main__":
    main()
