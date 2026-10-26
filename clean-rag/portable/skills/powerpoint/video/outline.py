"""python outline.py name  prints each spoken paragraph: index, start time, word count, text with word indexes every 5 words."""
import sys
from pathlib import Path

from map import load_json, run

ROOT = Path(__file__).resolve().parent


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    mp = load_json(ROOT / "map" / f"{sys.argv[1]}.json")
    print("duration", mp["duration"])
    for p in mp["paragraphs"]:
        if not p["spoken"]:
            print(f"[{p['index']}] UNSPOKEN skip"); continue
        ws = p["words"]
        txt = " ".join((f"{{{i}}}" if i % 5 == 0 else "") + w["w"] for i, w in enumerate(ws))
        print(f"[{p['index']}] t={p['start']:.1f}s words={len(ws)}\n   {txt}")


run(main)
