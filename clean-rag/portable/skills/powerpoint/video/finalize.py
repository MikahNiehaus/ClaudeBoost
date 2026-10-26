import subprocess, json, hashlib, shutil, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent
AUDIO = ROOT / "audio"
FINAL = ROOT / "final"
MUX = "--mux" in sys.argv  # put the narration into the mp4 so it plays anywhere
if set(sys.argv[1:]) - {"--mux"}:
    sys.exit("usage: python finalize.py [--mux]")
OUT = ROOT / "out"
missing = [t for t in ("ffmpeg", "ffprobe") if not shutil.which(t)]
if missing:
    sys.exit(f"not on PATH: {', '.join(missing)}. Install ffmpeg, which ships both.")
FINAL.mkdir(exist_ok=True)

def probe(path, *args):
    r = subprocess.run(["ffprobe", "-v", "error", *args, "-of", "json", str(path)], capture_output=True, text=True)
    return json.loads(r.stdout or "{}")

def moov_first(path):
    data = open(path, "rb").read(1 << 16)
    i = data.find(b"moov"); j = data.find(b"mdat")
    return i != -1 and (j == -1 or i < j)

bad = []
mp3s = sorted(AUDIO.glob("*.mp3"))
if not mp3s:
    bad.append(("*", f"no mp3 in {AUDIO}"))
for mp3 in mp3s:
    ep = mp3.stem
    src = OUT / f"{ep}.mp4"
    dst = FINAL / f"{ep}.mp4"
    tmp = OUT / f"{ep}.fast.mp4"
    if not src.exists():
        bad.append((ep, "no render")); continue
    inputs = ["-i", str(src), "-i", str(mp3), "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "160k"] if MUX else ["-i", str(src), "-c", "copy"]
    r = subprocess.run(["ffmpeg", "-y", "-v", "error", *inputs, "-movflags", "+faststart", str(tmp)], capture_output=True, text=True)
    if r.returncode:
        tmp.unlink(missing_ok=True)
        bad.append((ep, "remux " + r.stderr[:200])); continue
    # format=duration is the longest stream, so it would hide a short video.
    vs = probe(tmp, "-select_streams", "v:0", "-show_entries", "stream=duration").get("streams") or [{}]
    try:
        vd = float(vs[0].get("duration"))
    except (TypeError, ValueError):
        tmp.unlink(missing_ok=True)
        bad.append((ep, "video stream has no duration")); continue
    try:
        ad = float(probe(mp3, "-show_entries", "format=duration").get("format", {}).get("duration"))
    except (TypeError, ValueError):
        tmp.unlink(missing_ok=True)
        bad.append((ep, "audio has no duration")); continue
    pk = probe(tmp, "-select_streams", "v:0", "-skip_frame", "nokey", "-show_entries", "frame=pts_time")
    ts = [float(f["pts_time"]) for f in pk.get("frames", []) if "pts_time" in f]
    gap = max((b - a for a, b in zip(ts, ts[1:])), default=99)
    mb = tmp.stat().st_size / 1e6
    probs = []
    if abs(vd - ad) > 1 / 30 + 0.05: probs.append(f"duration {vd:.2f} vs {ad:.2f}")
    if not moov_first(tmp): probs.append("moov not first")
    if gap > 1.0 + 1e-3: probs.append(f"keyframe gap {gap:.2f}")
    if mb > 150: probs.append(f"size {mb:.0f}MB")
    print(ep, f"v={vd:.2f} a={ad:.2f} gap={gap:.2f} {mb:.0f}MB", probs or "OK", flush=True)
    if probs:
        tmp.unlink(missing_ok=True)
        bad.append((ep, probs)); continue
    tmp.replace(dst)
    side = {"mp4_sha256": hashlib.sha256(dst.read_bytes()).hexdigest(), "mp3_sha256": hashlib.sha256(mp3.read_bytes()).hexdigest()}
    (OUT / f"{ep}.build.json").write_text(json.dumps(side))
print("FAILED", bad, flush=True)
print("DONE", flush=True)
sys.exit(1 if bad else 0)
