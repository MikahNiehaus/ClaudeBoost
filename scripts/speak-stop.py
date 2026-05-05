"""
ClaudeBoost TTS interrupt — stop any playing speech immediately.

Creates a stop signal file that speak-play.py polls during playback,
and kills the player process by PID as a backup.

Called by:
  - UserPromptSubmit hook (auto-interrupt when user sends input)
  - Manual: python speak-stop.py
"""
from __future__ import annotations

import os
import signal
import sys
import tempfile
from pathlib import Path


def main() -> int:
    temp_dir = os.environ.get("TEMP", tempfile.gettempdir())

    # Signal graceful stop via file
    stop_file = Path(temp_dir) / "claudeboost_tts.stop"
    try:
        stop_file.write_text("stop", encoding="utf-8")
    except Exception:
        pass

    # Kill by PID as backup
    pid_file = Path(temp_dir) / "claudeboost_tts.pid"
    try:
        pid = int(pid_file.read_text(encoding="utf-8").strip())
        os.kill(pid, signal.SIGTERM)
    except Exception:
        pass
    try:
        pid_file.unlink(missing_ok=True)
    except Exception:
        pass

    return 0


if __name__ == "__main__":
    sys.exit(main())
