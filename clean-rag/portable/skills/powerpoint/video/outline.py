"""python outline.py name  prints each spoken paragraph: index, start time, word count, text with word indexes every 5 words."""
import json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent
if len(sys.argv) != 2:
    sys.exit(__doc__)
mp =json.loads((ROOT / "map" / f"{sys.argv[1]}.json").read_text(encoding="utf-8"))
print("duration", mp["duration"])
for p in mp["paragraphs"]:
    if not p["spoken"]:
        print(f"[{p['index']}] UNSPOKEN skip"); continue
    ws = p["words"]
    txt = " ".join((f"{{{i}}}" if i % 5 == 0 else "") + w["w"] for i, w in enumerate(ws))
    print(f"[{p['index']}] t={p['start']:.1f}s words={len(ws)}\n   {txt}")
