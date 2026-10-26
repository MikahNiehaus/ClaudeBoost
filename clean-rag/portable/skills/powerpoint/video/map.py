"""Map Whisper word times onto script words and paragraphs.

Usage: python map.py name [name2 ...]   (no args = every align/*.json)
Reads align/<name>.json and scripts/<name>.md (spoken text after a "# Script" line), writes map/<name>.json.
"""
import difflib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CONTENT = ROOT / "audio"
SCRIPTS = ROOT / "scripts"
ONES = "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen".split()
TENS = "_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()


def num_words(n):
    if n < 20:
        return ONES[n]
    if n < 100:
        return TENS[n // 10] + ("" if n % 10 == 0 else " " + ONES[n % 10])
    if n < 1000:
        r = ONES[n // 100] + " hundred"
        return r + ("" if n % 100 == 0 else " " + num_words(n % 100))
    r = num_words(n // 1000) + " thousand"
    return r + ("" if n % 1000 == 0 else " " + num_words(n % 1000))


def spell(digits):
    """num_words for a digit string, read digit by digit past 15 digits so int() and recursion stay bounded."""
    if len(digits) > 15:
        return " ".join(ONES[int(d)] for d in digits)
    return num_words(int(digits))


def load_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        sys.exit(f"{path.parent.name}/{path.name} not found")
    except ValueError as e:
        sys.exit(f"{path.parent.name}/{path.name} is not valid JSON: {e}")


def run(main):
    """Calls main, so malformed input ends as one line on stderr and exit 1 instead of a traceback."""
    try:
        main()
    except (OSError, ValueError, LookupError, TypeError) as e:
        sys.exit(f"{Path(sys.argv[0]).name}: bad input, {type(e).__name__} {e}")


def norm(w):
    w = w.lower().replace("-", "").replace("%", " percent ")
    w = re.sub(r"\d+", lambda m: " " + spell(m.group()) + " ", w)
    w = re.sub(r"[^a-z ]", "", w)
    return w.replace(" ", "")


def script_paragraphs(path):
    text = path.read_text(encoding="utf-8")
    if "# Script" not in text:
        sys.exit(f"{path} has no '# Script' line; put the spoken text after one")
    body = text.split("# Script", 1)[1]
    return [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip()]


def silence_ends(mp3):
    r = subprocess.run(
        ["ffmpeg", "-i", str(mp3), "-af", "silencedetect=noise=-40dB:d=0.15", "-f", "null", "-"],
        capture_output=True, text=True)
    return [float(x) for x in re.findall(r"silence_end: ([\d.]+)", r.stderr)]


def build(ep):
    mp3 = CONTENT / f"{ep}.mp3"
    script = SCRIPTS / f"{ep}.md"
    al = load_json(ROOT / "align" / f"{ep}.json")
    wh = []
    for w in al["words"]:
        t = w["w"].strip()
        if t.startswith("-") and wh:  # fragment of previous token
            wh[-1]["w"] += t
            wh[-1]["e"] = w["e"]
        else:
            wh.append({"w": t, "s": w["s"], "e": w["e"]})
    paras = script_paragraphs(script)
    disp = []  # (display word, para idx)
    for i, p in enumerate(paras):
        for tok in p.split():
            disp.append((tok, i))
    sn = [norm(w) for w, _ in disp]
    wn = [norm(w["w"]) for w in wh]
    sm = difflib.SequenceMatcher(None, sn, wn, autojunk=False)
    times = [None] * len(disp)
    for tag, a0, a1, b0, b1 in sm.get_opcodes():
        if tag == "equal":
            for k in range(a1 - a0):
                times[a0 + k] = (wh[b0 + k]["s"], wh[b0 + k]["e"])
        elif tag == "replace" and b1 > b0:
            s, e = wh[b0]["s"], wh[b1 - 1]["e"]
            lens = [max(1, len(sn[i])) for i in range(a0, a1)]
            tot, acc = sum(lens), 0
            for k, i in enumerate(range(a0, a1)):
                times[i] = (s + (e - s) * acc / tot, s + (e - s) * (acc + lens[k]) / tot)
                acc += lens[k]
    matched = [t is not None for t in times]
    ratio = sm.ratio()
    # interpolate unmatched
    n = len(times)
    i = 0
    while i < n:
        if times[i] is None:
            j = i
            while j < n and times[j] is None:
                j += 1
            lo = times[i - 1][1] if i > 0 else 0.0
            hi = times[j][0] if j < n else None
            if hi is None:  # trailing unmatched = not in audio
                for k in range(i, n):
                    times[k] = None
                break
            lens = [max(1, len(sn[k])) for k in range(i, j)]
            tot, acc = sum(lens), 0
            for k, idx in enumerate(range(i, j)):
                times[idx] = (lo + (hi - lo) * acc / tot, lo + (hi - lo) * (acc + lens[k]) / tot)
                acc += lens[k]
            i = j
        else:
            i += 1
    ends = silence_ends(mp3)
    out = []
    for pi, p in enumerate(paras):
        idx = [k for k, (_, q) in enumerate(disp) if q == pi]
        got = [k for k in idx if times[k] is not None and matched[k]]
        frac = len(got) / len(idx)
        spoken = frac >= 0.5
        words = [{"w": disp[k][0], "s": round(times[k][0], 3), "e": round(times[k][1], 3)}
                 for k in idx if times[k] is not None] if spoken else []
        start = words[0]["s"] if words else None
        if start is not None and pi > 0:
            near = [t for t in ends if start - 0.3 <= t <= start + 0.8]
            if near:
                start = near[0]
                words[0]["s"] = min(words[0]["s"], start) if words[0]["s"] > start else words[0]["s"]
        if pi == 0:
            start = 0.0
        out.append({"index": pi, "spoken": spoken, "matched": round(frac, 3),
                    "start": start, "text": p, "words": words})
    spoken = [p for p in out if p["spoken"]]
    for k, p in enumerate(spoken):
        p["end"] = spoken[k + 1]["start"] if k + 1 < len(spoken) else al["duration"]
    result = {"episode": ep, "duration": al["duration"], "ratio": round(ratio, 4), "paragraphs": out}
    (ROOT / "map").mkdir(exist_ok=True)
    (ROOT / "map" / f"{ep}.json").write_text(json.dumps(result, indent=1), encoding="utf-8")
    uns = [p["index"] for p in out if not p["spoken"]]
    print(ep, "ratio", round(ratio, 3), "paras", len(out), "unspoken", uns,
          "unmatched", sum(1 for m in matched if not m), "of", len(matched))
    return result


def main():
    eps = sys.argv[1:] or sorted(p.stem for p in (ROOT / "align").glob("*.json"))
    if not eps:
        sys.exit("no align/*.json to map. Run align.py first.")
    if not shutil.which("ffmpeg"):
        sys.exit("ffmpeg not on PATH. Install ffmpeg.")
    for e in eps:
        build(e)


if __name__ == "__main__":
    run(main)
