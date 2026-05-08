"""
ClaudeBoost TTS Stop hook — speaks Claude's last response aloud.

Receives JSON on stdin:
  { session_id, transcript_path, cwd, permission_mode,
    hook_event_name, stop_hook_active, last_assistant_message }

Reads state/speak-state.json to check if TTS is enabled. If enabled,
filters the text and spawns speak-play.py as a detached background
process. Never blocks Claude's main loop.

Exit codes:
  0 = pass (Claude stops normally)
  Never returns 2 (never forces continuation)
"""
from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import sys
import tempfile
from pathlib import Path

# Windows: DETACHED_PROCESS so the player runs independently
DETACHED_PROCESS = 0x00000008
MIN_SPEAK_CHARS = 10
DEFAULT_VOICE = "en-US-AndrewNeural"


def kill_existing_player(temp_dir: str) -> None:
    """Stop any currently-playing TTS before starting a new one."""
    # Signal graceful stop via file
    stop_file = os.path.join(temp_dir, "claudeboost_tts.stop")
    try:
        Path(stop_file).write_text("stop", encoding="utf-8")
    except Exception:
        pass

    # Kill by PID as backup
    pid_file = os.path.join(temp_dir, "claudeboost_tts.pid")
    try:
        pid = int(Path(pid_file).read_text(encoding="utf-8").strip())
        os.kill(pid, signal.SIGTERM)
    except Exception:
        pass
    try:
        Path(pid_file).unlink(missing_ok=True)
    except Exception:
        pass


def read_json(path: str | os.PathLike, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return default


def extract_from_transcript(transcript_path: str) -> str:
    """Fallback: read the transcript JSONL and return last assistant text."""
    try:
        with open(transcript_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except Exception:
        return ""

    for line in reversed(lines):
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except Exception:
            continue

        msg = entry.get("message", {})
        if msg.get("role") != "assistant":
            continue

        texts = []
        for block in msg.get("content", []):
            if block.get("type") == "text":
                texts.append(block["text"])
        if texts:
            return "\n".join(texts)

    return ""


def redact_secrets(text: str) -> str:
    """Remove sensitive data before sending text to external TTS service."""
    # API keys / tokens (common patterns)
    text = re.sub(r"sk-[A-Za-z0-9_-]{10,}", "[REDACTED]", text)
    text = re.sub(r"(?i)(api[_-]?key|token|secret|password|credential)\s*[:=]\s*\S+", "[REDACTED]", text)
    # Bearer tokens (Authorization: Bearer ...)
    text = re.sub(r"(?i)bearer\s+\S+", "Bearer [REDACTED]", text)
    # AWS-style keys
    text = re.sub(r"AKIA[0-9A-Z]{16}", "[REDACTED]", text)
    # Long hex/base64 strings (likely secrets, 32+ chars)
    text = re.sub(r"[A-Za-z0-9+/]{32,}={0,2}", "[REDACTED]", text)
    # Environment variable assignments
    text = re.sub(r"(?i)(export\s+)?\w*(?:key|secret|token|password|credential)\w*\s*=\s*\S+", "[REDACTED]", text)
    # File paths with user directories (privacy)
    text = re.sub(r"(?i)C:\\Users\\[^\s\\]+", "C:\\\\Users\\\\[USER]", text)
    text = re.sub(r"/home/[^\s/]+", "/home/[USER]", text)
    text = re.sub(r"/Users/[^\s/]+", "/Users/[USER]", text)
    return text


def strip_markdown(text: str) -> str:
    """Remove markdown formatting, code blocks, and structural elements."""
    # Remove fenced code blocks
    text = re.sub(r"```[\s\S]*?```", "", text)
    # Remove inline code
    text = re.sub(r"`[^`]+`", "", text)
    # Remove markdown headers (keep text)
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
    # Remove bold/italic markers
    text = re.sub(r"\*{1,3}([^*]+)\*{1,3}", r"\1", text)
    # Remove markdown links [text](url) -> text
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    # Remove bare URLs
    text = re.sub(r"https?://\S+", "", text)
    # Remove table formatting
    text = re.sub(r"\|", " ", text)
    text = re.sub(r"^[\s\-:]+$", "", text, flags=re.MULTILINE)
    # Remove list markers
    text = re.sub(r"^\s*[-*+]\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*\d+\.\s+", "", text, flags=re.MULTILINE)
    return text


def condense_for_speech(text: str) -> str:
    """Clean text for speech — remove filler and noise, keep full content."""
    # Remove "Sources:" sections and everything after
    text = re.sub(r"(?i)\n*sources?:[\s\S]*$", "", text)

    # Remove section headers (e.g., "Summary", "Details", "Changes")
    text = re.sub(r"(?i)^(summary|details|changes|overview|context|background|notes?)\s*:?\s*$",
                  "", text, flags=re.MULTILINE)

    # Remove common filler phrases
    filler = [
        r"(?i)^(here'?s?|okay|alright|sure|great|got it|understood)[,.:!]?\s*",
        r"(?i)^(let me|i'll|i will|i'm going to|i am going to)\s+\w+\s+",
        r"(?i)^(now |so |well |basically |essentially |actually )",
        r"(?i)^(as (you can see|mentioned|requested|noted))[,.]?\s*",
        r"(?i)^(I've (also|additionally)\s+)",
        r"(?i)(let me know if .*$)",
        r"(?i)(feel free to .*$)",
        r"(?i)(if you('d| would) like.*$)",
        r"(?i)^(the key (changes?|updates?|things?) (are|is|include)[:\s]*)",
    ]
    lines = text.split("\n")
    cleaned = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        # Skip lines that are just labels or single words
        if len(line) < 8:
            continue
        for pat in filler:
            line = re.sub(pat, "", line).strip()
        if line and len(line) > 5:
            cleaned.append(line)
    text = " ".join(cleaned)

    # Remove parenthetical asides
    text = re.sub(r"\s*\([^)]{0,100}\)\s*", " ", text)

    return text.strip()


def filter_for_speech(text: str) -> str:
    """Strip code, markdown, redact secrets, and clean up for TTS."""
    text = strip_markdown(text)
    text = redact_secrets(text)
    text = condense_for_speech(text)

    # Final whitespace cleanup
    text = re.sub(r"\n{2,}", " ", text)
    text = re.sub(r"  +", " ", text)

    return text.strip()


def main() -> int:
    # 1. Read stdin (may be empty on Windows — see issue #46601)
    raw = ""
    try:
        if not sys.stdin.isatty():
            raw = sys.stdin.read()
    except Exception:
        pass

    try:
        payload = json.loads(raw) if raw.strip() else {}
    except Exception:
        payload = {}

    # 2. Read state
    home = os.environ.get("CLAUDEBOOST_HOME") or os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..")
    )
    state = read_json(Path(home) / "state" / "speak-state.json", {})

    if not state.get("enabled", False):
        return 0

    voice = state.get("voice", DEFAULT_VOICE)

    # 3. Prevent infinite loops
    if payload.get("stop_hook_active", False):
        return 0

    # 4. Get assistant text — prefer stdin field, fall back to transcript
    text = payload.get("last_assistant_message", "")
    if not text:
        transcript_path = payload.get("transcript_path", "")
        if transcript_path and Path(transcript_path).exists():
            text = extract_from_transcript(transcript_path)

    if not text:
        return 0

    # 5. Filter for speech
    text = filter_for_speech(text)
    if len(text) < MIN_SPEAK_CHARS:
        return 0

    # 6. Write to temp file and spawn background player
    temp_dir = os.environ.get("TEMP", tempfile.gettempdir())
    text_file = os.path.join(temp_dir, "claudeboost_tts_text.txt")
    try:
        Path(text_file).write_text(text, encoding="utf-8")
    except Exception:
        return 0

    # Kill any existing TTS playback before starting new
    kill_existing_player(temp_dir)

    # Clear stale stop file so the new player doesn't immediately exit
    stale_stop = os.path.join(temp_dir, "claudeboost_tts.stop")
    try:
        Path(stale_stop).unlink(missing_ok=True)
    except Exception:
        pass

    play_script = str(Path(home) / "scripts" / "speak-play.py")
    try:
        subprocess.Popen(
            [sys.executable, play_script, text_file, voice, temp_dir],
            creationflags=DETACHED_PROCESS,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
        )
    except Exception:
        pass

    return 0


if __name__ == "__main__":
    sys.exit(main())
