"""python render.py name [--frames 0-149] [--out name.mp4] [--sb TEST]
Builds props from storyboards/<name>.json + map/<name>.json and renders with Remotion."""
import argparse, json, shutil, subprocess, sys
from pathlib import Path

from map import load_json, run

ROOT = Path(__file__).resolve().parent


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ep")
    ap.add_argument("--frames")
    ap.add_argument("--out")
    ap.add_argument("--sb")
    ap.add_argument("--crf", default="20")
    ap.add_argument("--concurrency", default="6")
    ap.add_argument("--scale", default="1")
    a = ap.parse_args()
    sb = load_json(ROOT / "storyboards" / f"{a.sb or a.ep}.json")
    mp = load_json(ROOT / "map" / f"{a.ep}.json")
    slim = {"duration": mp["duration"], "paragraphs": [
        {"index": p["index"], "spoken": p["spoken"], "start": p["start"], "end": p.get("end"), "words": p["words"]} for p in mp["paragraphs"]]}
    (ROOT / "out").mkdir(exist_ok=True)
    props = ROOT / "out" / f"{a.ep}.props.json"
    # Remotion reads props with JSON.parse, which rejects Infinity and NaN.
    props.write_text(json.dumps({"storyboard": sb, "map": slim}, allow_nan=False), encoding="utf-8")
    # A frame range or another storyboard must never land on the full render's name, which finalize ships.
    stem = a.ep + (f".sb-{a.sb}" if a.sb else "") + (f".frames-{a.frames}" if a.frames else "")
    out = ROOT / "out" / (a.out or f"{stem}.mp4")
    # which() honours PATHEXT, so Windows gets npx.cmd without a shell.
    npx = shutil.which("npx")
    if not npx:
        sys.exit("npx not found on PATH. Install Node 18 or newer, then run npm install here.")
    cmd = [npx, "remotion", "render", "src/index.ts", "Episode", str(out), f"--props={props}", "--gop=30", f"--crf={a.crf}",
           f"--concurrency={a.concurrency}", f"--scale={a.scale}", "--log=error", "--muted"]
    if a.frames:
        cmd.append(f"--frames={a.frames}")
    sys.exit(subprocess.call(cmd, cwd=ROOT))


run(main)
