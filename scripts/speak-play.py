"""
ClaudeBoost TTS player — synthesize and play speech in background.

Spawned as a detached process by speak-tts.py so the Stop hook never
blocks Claude's main loop. Uses edge-tts for synthesis. Playback:

  - Windows: mciSendString via winmm.dll (no subprocess; push-to-talk
    space-key interrupt via user32.GetAsyncKeyState).
  - macOS:   afplay subprocess, polled for the stop file every 150ms.
  - Linux:   not supported — exits silently. (TTS support was intentionally
             scoped to Windows + macOS only.)

Stop signals checked during playback:
  - speak-tts.py creates the stop file before spawning a new player
  - speak-stop.py creates it for on-demand interrupt

Usage: python speak-play.py <text_file> <voice> [temp_dir]
"""
from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

STOP_FILE_NAME = "claudeboost_tts.stop"
PID_FILE_NAME = "claudeboost_tts.pid"

IS_WINDOWS = os.name == "nt"
IS_MACOS = sys.platform == "darwin"


async def synthesize(text: str, voice: str, mp3_path: str) -> None:
    import edge_tts

    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(mp3_path)


# ---------------------------------------------------------------------------
# Windows playback via mciSendString
# ---------------------------------------------------------------------------
VK_SPACE = 0x20


def play_mp3_windows(mp3_path: str, stop_file: str) -> None:
    """Play an MP3 via Windows mciSendString, polling for stop signal.

    Uses non-blocking 'play alias' and polls MCI status, stop file,
    and space key every 150ms. Holding space (push-to-talk) kills
    playback immediately so the user can interrupt and speak.
    """
    import ctypes

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

    while True:
        if os.path.exists(stop_file):
            try:
                os.unlink(stop_file)
            except Exception:
                pass
            break

        space_is_down = user32.GetAsyncKeyState(VK_SPACE) < 0
        if space_is_down and not space_was_down:
            break
        space_was_down = space_is_down

        winmm.mciSendStringW("status cbtts mode", buf, 256, 0)
        if buf.value != "playing":
            break

        time.sleep(0.15)

    winmm.mciSendStringW("stop cbtts", buf, 256, 0)
    winmm.mciSendStringW("close cbtts", buf, 256, 0)


# ---------------------------------------------------------------------------
# macOS playback via afplay
# ---------------------------------------------------------------------------
def play_mp3_macos(mp3_path: str, stop_file: str) -> None:
    """Play an MP3 via afplay, polling the stop file every 150ms.

    afplay is shipped with macOS (CoreAudio frontend) — no extra deps. No
    push-to-talk space-key interrupt on this platform; speak-stop.py covers
    the file-based stop signal triggered when the user submits a new prompt.
    """
    # Clear any stale stop file before playing
    if os.path.exists(stop_file):
        try:
            os.unlink(stop_file)
        except Exception:
            pass

    proc = subprocess.Popen(
        ["afplay", mp3_path],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
    )

    try:
        while proc.poll() is None:
            if os.path.exists(stop_file):
                try:
                    os.unlink(stop_file)
                except Exception:
                    pass
                proc.terminate()
                break
            time.sleep(0.15)
    finally:
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proc.kill()


def main() -> int:
    if len(sys.argv) < 3:
        return 1

    text_file = sys.argv[1]
    voice = sys.argv[2]
    temp_dir = sys.argv[3] if len(sys.argv) > 3 else tempfile.gettempdir()

    # Linux: not supported. speak-tts.py also skips spawning the player on
    # Linux, but exit early here too so a stale Stop hook from a Windows
    # install doesn't pop errors after re-running setup on Linux.
    if not (IS_WINDOWS or IS_MACOS):
        return 0

    # Write PID so speak-stop.py can kill us if needed
    pid_file = os.path.join(temp_dir, PID_FILE_NAME)
    try:
        Path(pid_file).write_text(str(os.getpid()), encoding="utf-8")
    except Exception:
        pass

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

    mp3_path = os.path.join(temp_dir, "claudeboost_tts.mp3")
    try:
        asyncio.run(synthesize(text, voice, mp3_path))
    except Exception:
        return 1

    stop_file = os.path.join(temp_dir, STOP_FILE_NAME)
    try:
        if IS_WINDOWS:
            play_mp3_windows(mp3_path, stop_file)
        elif IS_MACOS:
            play_mp3_macos(mp3_path, stop_file)
    except Exception:
        pass

    for f in [mp3_path, pid_file]:
        try:
            os.unlink(f)
        except Exception:
            pass

    return 0


if __name__ == "__main__":
    sys.exit(main())
