"""
ClaudeBoost TTS player — synthesize and play speech in background.

Spawned as a detached process by speak-tts.py so the Stop hook never
blocks Claude's main loop. Uses edge-tts for synthesis and Windows
mciSendString (winmm.dll) for playback — no PowerShell subprocess.

Usage: python speak-play.py <text_file> <voice> [temp_dir]
"""
from __future__ import annotations

import asyncio
import ctypes
import os
import sys
import tempfile
from pathlib import Path


async def synthesize(text: str, voice: str, mp3_path: str) -> None:
    import edge_tts

    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(mp3_path)


def play_mp3(mp3_path: str) -> None:
    """Play an MP3 via Windows mciSendString (winmm.dll).

    Uses 'play alias wait' which blocks until playback finishes.
    Direct ctypes call — no PowerShell subprocess overhead.
    """
    winmm = ctypes.windll.winmm
    buf = ctypes.create_unicode_buffer(256)

    winmm.mciSendStringW(
        f'open "{mp3_path}" type mpegvideo alias cbtts', buf, 256, 0
    )
    winmm.mciSendStringW("play cbtts wait", buf, 256, 0)
    winmm.mciSendStringW("close cbtts", buf, 256, 0)


def main() -> int:
    if len(sys.argv) < 3:
        return 1

    text_file = sys.argv[1]
    voice = sys.argv[2]
    temp_dir = sys.argv[3] if len(sys.argv) > 3 else tempfile.gettempdir()

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

    # Play via direct Windows API
    try:
        play_mp3(mp3_path)
    except Exception:
        pass

    # Clean up
    try:
        os.unlink(mp3_path)
    except Exception:
        pass

    return 0


if __name__ == "__main__":
    sys.exit(main())
