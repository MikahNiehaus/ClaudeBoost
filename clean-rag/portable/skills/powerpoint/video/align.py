import json, subprocess, sys
from pathlib import Path
import numpy as np
from faster_whisper import WhisperModel
mp3 = Path(sys.argv[1]); out = Path(sys.argv[2])
out.parent.mkdir(parents=True, exist_ok=True)  # before transcribing, which takes minutes
raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(mp3), "-f", "s16le", "-ac", "1", "-ar", "16000", "-"], capture_output=True, check=True).stdout
audio = np.frombuffer(raw, np.int16).astype(np.float32) / 32768.0
m = WhisperModel("small.en", device="cpu", compute_type="int8")
segs, info = m.transcribe(audio, word_timestamps=True, language="en")
words = [{"w": w.word.strip(), "s": round(w.start, 3), "e": round(w.end, 3)} for s in segs for w in s.words]
out.write_text(json.dumps({"duration": len(audio) / 16000, "words": words}), encoding="utf-8")
print(mp3.name, len(words), "words", round(len(audio) / 16000, 1), "s")
