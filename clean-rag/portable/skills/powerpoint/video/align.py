"""python align.py audio/<name>.mp3 align/<name>.json  gets word times from faster-whisper."""
import json, shutil, subprocess, sys
from pathlib import Path

if len(sys.argv) != 3:
    sys.exit(__doc__)
if not shutil.which("ffmpeg"):
    sys.exit("ffmpeg not on PATH. Install ffmpeg.")
mp3 = Path(sys.argv[1]); out = Path(sys.argv[2])
# Decoded before the whisper import, so a bad file fails in a second, not after the model loads.
r = subprocess.run(["ffmpeg", "-v", "error", "-i", str(mp3), "-f", "s16le", "-ac", "1", "-ar", "16000", "-"], capture_output=True)
if r.returncode or not r.stdout:
    err = r.stderr.decode(errors="replace").strip().splitlines()
    sys.exit(f"ffmpeg could not decode {mp3}: {err[-1] if err else 'no audio'}")
try:
    import numpy as np
    from faster_whisper import WhisperModel
except ImportError as e:
    sys.exit(f"{e.name} is not installed. Run pip install faster-whisper numpy")
out.parent.mkdir(parents=True, exist_ok=True)  # before transcribing, which takes minutes
audio = np.frombuffer(r.stdout, np.int16).astype(np.float32) / 32768.0
m = WhisperModel("small.en", device="cpu", compute_type="int8")
segs, info = m.transcribe(audio, word_timestamps=True, language="en")
words = [{"w": w.word.strip(), "s": round(w.start, 3), "e": round(w.end, 3)} for s in segs for w in s.words]
out.write_text(json.dumps({"duration": len(audio) / 16000, "words": words}), encoding="utf-8")
print(mp3.name, len(words), "words", round(len(audio) / 16000, 1), "s")
