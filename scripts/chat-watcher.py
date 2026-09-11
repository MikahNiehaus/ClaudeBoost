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

# Sibling module, same pattern as telemetry-hook.py: this file's own name has a
# hyphen and cannot be imported, so scripts/ goes on the path explicitly.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from claude_cli import claude_cmd, reject_unsafe_args  # noqa: E402

POLL_INTERVAL = 3       # seconds between checks
MAX_RUNTIME = 15 * 60  # 15 minutes then exit
CLI_TIMEOUT = 60       # seconds to wait for one answer
REAP_TIMEOUT = 10      # seconds to drain the pipes after killing a stalled CLI

# The CLI reads and writes UTF-8 regardless of the machine's code page, so say
# so rather than letting subprocess fall back to locale.getpreferredencoding().
# `errors` is not decoration: a lone surrogate survives json.loads() and even
# UTF-8 cannot encode one, so a strict codec would fail mid-write. See
# _spawn_cli for what a strict codec costs.
CLI_ENCODING = "utf-8"
CLI_ENCODING_ERRORS = "replace"

CHAT_FILES = [
    Path(os.environ.get("TEMP", "/tmp")) / "claudeboost" / "changes_chat.json",
]

SYSTEM_PROMPT = (
    "You are answering a developer's question about a specific piece of code shown in a diff viewer. "
    "Give a concise, direct answer in 1-3 sentences. No preamble, no markdown headers, just the answer. "
    "If the question is a test ('are you there', 'hello'), confirm you're working."
)


def _terminate_tree(proc: subprocess.Popen) -> None:
    """Kill the CLI and anything it started, so its pipes actually close.

    Popen.kill() reaches the direct child only. On Windows that child is
    cmd.exe, because the CLI ships as claude.cmd, and the real CLI it launches
    keeps the stdout and stderr handles it inherited. A read on those pipes
    then never sees EOF, so the wait that follows a timeout has nothing
    bounding it. `taskkill /T` takes the whole tree, which is what npm's own
    spawn layer uses on Windows for this reason.

    POSIX has a shim too, but npm's is a /bin/sh script whose last line is
    `exec "$basedir/.../claude"`, so the shell is replaced rather than left
    waiting and the pid we hold is the CLI itself. Popen.kill() reaches it.
    """
    if os.name == "nt":
        try:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                capture_output=True, timeout=REAP_TIMEOUT,
            )
        except (OSError, subprocess.SubprocessError) as e:
            # Not fatal on its own. proc.kill() below still frees the direct
            # child, which is what Popen.__exit__ waits on. Say it happened,
            # because the leftover is a live process on the user's machine.
            print(f"[chat-watcher] taskkill failed for pid {proc.pid}: {e}", flush=True)
    proc.kill()


def _spawn_cli(argv: list[str], prompt: str, env: dict) -> tuple[int, str, str]:
    """Run the CLI with *prompt* on stdin and return (rc, stdout, stderr).

    Not subprocess.run(), and the timeout is the reason. run() does raise
    TimeoutExpired on schedule, then calls communicate() a second time with no
    timeout at all to collect the output Windows buffers on reader threads
    (python/cpython#87512). That second call waits on pipes an orphaned
    grandchild still holds, so the declared bound is not the bound: measured
    here at 851 seconds against a declared 60, which is 94% of this watcher's
    entire 15-minute lifetime spent on one question. Killing the tree first is
    what makes the number in CLI_TIMEOUT the number that happens.
    """
    with subprocess.Popen(
        argv,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        encoding=CLI_ENCODING,
        errors=CLI_ENCODING_ERRORS,
        env=env,
    ) as proc:
        try:
            stdout, stderr = proc.communicate(prompt, timeout=CLI_TIMEOUT)
        except subprocess.TimeoutExpired:
            _terminate_tree(proc)
            try:
                proc.communicate(timeout=REAP_TIMEOUT)
            except subprocess.TimeoutExpired:
                # Nothing swallowed: the output of a killed CLI is not wanted,
                # and the raise below is what the caller sees either way.
                pass
            raise RuntimeError(f"claude -p gave no answer within {CLI_TIMEOUT}s") from None
    return proc.returncode, stdout, stderr


def answer_question(question: str, context_file: str, context_code: str) -> str:
    """Use `claude -p` to answer the question with code context."""
    context_parts = []
    if context_file:
        context_parts.append(f"File: {context_file}")
    if context_code:
        context_parts.append(f"Code:\n```\n{context_code}\n```")
    context_parts.append(f"Question: {question}")

    prompt = "\n\n".join(context_parts)

    cmd = claude_cmd()
    if cmd is None:
        raise RuntimeError("claude CLI is not on PATH")

    # Unset CLAUDECODE so `claude -p` can launch outside the parent session
    env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}

    # None of these is untrusted: two literals and a module constant. The
    # prompt is the untrusted one and it is deliberately not here.
    args = [
        "-p",
        "--model", "claude-haiku-4-5-20251001",
        "--append-system-prompt", SYSTEM_PROMPT,
    ]
    reject_unsafe_args(cmd, args)

    # A diff hunk can hold text UTF-8 cannot encode: json.loads() turns a
    # "\ud800" escape into a real lone surrogate. CLI_ENCODING_ERRORS keeps
    # that from failing mid-write, and this says so rather than substituting
    # in silence.
    try:
        prompt.encode(CLI_ENCODING)
    except UnicodeEncodeError as e:
        print(f"[chat-watcher] prompt holds text UTF-8 cannot encode ({e.reason}) "
              "and was sent with substitutions", flush=True)

    # The prompt goes on stdin, never in argv. It is built from context_code,
    # which is the literal text of a diff hunk off a JSON file in the temp dir,
    # so anything that can write that file chooses it. On Windows the CLI is a
    # .cmd shim, which means cmd.exe re-parses the command line and a quote in
    # an argument becomes live shell syntax (CVE-2024-24576). Nothing quotes
    # stdin. Anthropic's headless docs say the print mode reads stdin, so you
    # can pipe data in and redirect the response out like any other command
    # line tool.
    returncode, stdout, stderr = _spawn_cli(cmd + args, prompt, env)
    if returncode != 0:
        raise RuntimeError(f"claude -p failed (rc={returncode}): {stderr.strip()[:200]}")
    return stdout.strip()


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
    cmd = claude_cmd()
    if cmd is None:
        print("[chat-watcher] 'claude' CLI not found on PATH", flush=True)
        sys.exit(1)
    try:
        subprocess.run(cmd + ["--version"], capture_output=True, check=True, timeout=5)
    except (subprocess.SubprocessError, FileNotFoundError) as e:
        print(f"[chat-watcher] 'claude' CLI would not run: {e}", flush=True)
        sys.exit(1)

    start = time.monotonic()
    print(f"[chat-watcher] Started — polling every {POLL_INTERVAL}s for {MAX_RUNTIME // 60}min", flush=True)

    while time.monotonic() - start < MAX_RUNTIME:
        for chat_file in CHAT_FILES:
            check_and_answer(chat_file)
        time.sleep(POLL_INTERVAL)

    print("[chat-watcher] 15-minute window elapsed — exiting", flush=True)


if __name__ == "__main__":  # pragma: no cover
    main()
