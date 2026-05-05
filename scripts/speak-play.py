"""
ClaudeBoost TTS player — synthesize and play speech in background.

Spawned as a detached process by speak-tts.py so the Stop hook never
blocks Claude's main loop. Uses edge-tts for synthesis and Windows
mciSendString (winmm.dll) for playback — no PowerShell subprocess.

Monitors a stop file during playback for interrupt support:
  - speak-tts.py creates the stop file before spawning a new player
  - speak-stop.py creates it for on-demand interrupt (e.g., push-to-talk)

Usage: python speak-play.py <text_file> <voice> [temp_dir]
"""
from __future__ import annotations

import asyncio
import ctypes
import os
import sys
import tempfile
import time
from pathlib import Path

STOP_FILE_NAME = "claudeboost_tts.stop"
PID_FILE_NAME = "claudeboost_tts.pid"


async def synthesize(text: str, voice: str, mp3_path: str) -> None:
    import edge_tts

    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(mp3_path)


VK_SPACE = 0x20


def play_mp3(mp3_path: str, stop_file: str) -> None:
    """Play an MP3 via Windows mciSendString, polling for stop signal.

    Uses non-blocking 'play alias' and polls MCI status, stop file,
    and space key every 150ms. Holding space (push-to-talk) kills
    playback immediately so the user can interrupt and speak.
    """
    winmm = ctypes.windll.winmm
    user32 = ctypes.windll.user32
    buf = ctypes.create_unicode_buffer(256)

    err = winmm.mciSendStringW(
        f'open "{mp3_path}" type mpegvideo alias cbtts', buf, 256, 0
    )
    if err:
        return

    # Clear any stale stop file from previous interrupt before playing
    if os.path.exists(stop_file):
        try:
            os.unlink(stop_file)
        except Exception:
            pass

    winmm.mciSendStringW("play cbtts", buf, 256, 0)

    # Capture initial space state so we don't false-trigger
    space_was_down = user32.GetAsyncKeyState(VK_SPACE) < 0

    # Poll until done or interrupted
    while True:
        # Stop file from speak-stop.py or speak-tts.py
        if os.path.exists(stop_file):
            try:
                os.unlink(stop_file)
            except Exception:
                pass
            break

        # Space key pressed = push-to-talk interrupt
        space_is_down = user32.GetAsyncKeyState(VK_SPACE) < 0
        if space_is_down and not space_was_down:
            break
        space_was_down = space_is_down

        # Playback finished naturally
        winmm.mciSendStringW("status cbtts mode", buf, 256, 0)
        if buf.value != "playing":
            break

        time.sleep(0.15)

    winmm.mciSendStringW("stop cbtts", buf, 256, 0)
    winmm.mciSendStringW("close cbtts", buf, 256, 0)


def main() -> int:
    if len(sys.argv) < 3:
        return 1

    text_file = sys.argv[1]
    voice = sys.argv[2]
    temp_dir = sys.argv[3] if len(sys.argv) > 3 else tempfile.gettempdir()

    # Write PID so speak-stop.py can kill us if needed
    pid_file = os.path.join(temp_dir, PID_FILE_NAME)
    try:
        Path(pid_file).write_text(str(os.getpid()), encoding="utf-8")
    except Exception:
        pass

    # Read and clean up the text file
    text_path = Path(text_file)
    try:
        text = text_path.read_text(encoding="utf-8")
    except Exception:
        return 1
    finally:
        try:
            text_path.unlink(missing_ok=True)
        except Exception:
            pass

    if not text.strip():
        return 0

    # Synthesize to MP3
    mp3_path = os.path.join(temp_dir, "claudeboost_tts.mp3")
    try:
        asyncio.run(synthesize(text, voice, mp3_path))
    except Exception:
        return 1

    # Play via direct Windows API (interruptible)
    stop_file = os.path.join(temp_dir, STOP_FILE_NAME)
    try:
        play_mp3(mp3_path, stop_file)
    except Exception:
        pass

    # Clean up
    for f in [mp3_path, pid_file]:
        try:
            os.unlink(f)
        except Exception:
            pass

    return 0


if __name__ == "__main__":
    sys.exit(main())
