"""python validate.py name [name2 ...]  checks storyboards/<name>.json against map/<name>.json."""
import math
import re
import sys
from pathlib import Path

from map import ONES, TENS, load_json, run, spell

ROOT = Path(__file__).resolve().parent
KINDS = {
    "title": ["title"], "bullets": ["items"], "flow": ["nodes"], "compare": ["left", "right"],
    "stat": ["value", "label"], "steps": ["items"], "term": ["term", "definition"],
    "graph": ["nodes", "edges"], "quote": ["text"],
    "search": ["query", "docs"], "walk": ["nodes", "edges", "path"], "trace": ["nodes", "data"],
    "code": ["lines"], "chat": ["messages"], "bars": ["bars"],
}
EXAMPLE = {"search", "walk", "trace", "code", "chat", "bars"}
MIN_EXAMPLES = 4
MAX_ITEM_WORDS = 7
WHO = {"user", "attacker", "model", "system"}
BAD = re.compile(r"[:–—]|(?<=\w)-(?=\w)|\d+ episodes|episode \d+ of")
CODE_BAD = re.compile(r"[–—]|(?<=\w)-(?=\w)")
# white-space pre draws these as extra rows or 8 column tabs inside one fixed height row.
CODE_CTRL = re.compile(r"[\x00-\x1f\x7f-\x9f  ]")
# The code panel holds about 9 lines of 75 Consolas characters, clipped past that.
MAX_CODE_LINES = 8
MAX_CODE_CHARS = 60
NUM_WORDS = set(ONES) | set(TENS[2:]) | {"hundred", "thousand", "point"}
OPTIONAL_TEXT = ("heading", "subtitle", "note", "by", "loop", "unit")
# Indexes and layout, not card text, so the number spoken rule never reads them.
STRUCTURE = {"kind", "layout", "lines", "para", "w", "cues", "edges", "path", "pick"}


def num(v):
    """Finite only: json.dumps writes inf and nan as Infinity and NaN, which JSON.parse rejects."""
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return False
    try:
        return math.isfinite(v)
    except OverflowError:  # an int beyond float range
        return False


def idx(v, n):
    return whole(v) and 0 <= v < n


def strs(v):
    return isinstance(v, list) and all(isinstance(x, str) for x in v)


def recs(v, **fields):
    """True when v is a list of dicts whose named fields all pass their predicate."""
    return isinstance(v, list) and all(isinstance(x, dict) and all(ok(x.get(f)) for f, ok in fields.items()) for x in v)


def is_str(v):
    return isinstance(v, str)


def need(ok, msg):
    return [] if ok else [msg]


def str_list(field):
    return lambda s: need(strs(s[field]), f"{field} must be a list of strings")


def compare(s):
    side = lambda v: isinstance(v, dict) and is_str(v.get("title")) and strs(v.get("items"))
    return [f"{k} must be {{title, items: [strings]}}" for k in ("left", "right") if not side(s[k])]


def linked(s):
    if not strs(s["nodes"]):
        return ["nodes must be a list of strings"]
    n = len(s["nodes"])
    pair = lambda p: isinstance(p, list) and len(p) == 2 and idx(p[0], n) and idx(p[1], n)
    e = need(isinstance(s["edges"], list) and all(map(pair, s["edges"])), "edges must be pairs of node indexes in range")
    if s["kind"] == "walk":
        path = s["path"]
        e += need(isinstance(path, list) and len(path) >= 2 and all(idx(x, n) for x in path), "path must be at least 2 node indexes in range")
    return e


def trace(s):
    if not strs(s["nodes"]):
        return ["nodes must be a list of strings"]
    return need(strs(s["data"]) and len(s["data"]) == len(s["nodes"]), "data must be strings, same count as nodes")


def search(s):
    e = need(is_str(s["query"]), "query must be a string")
    if not recs(s["docs"], text=is_str, score=lambda v: num(v) and 0 <= v <= 1):
        return e + ["docs must be a list of {text, score} with score 0 to 1"]
    pick = s.get("pick", [])
    return e + need(isinstance(pick, list) and all(idx(x, len(s["docs"])) for x in pick), "pick must be doc indexes in range")


def chat(s):
    return need(recs(s["messages"], who=lambda v: v in WHO, text=is_str), f"messages must be a list of {{who, text}} with who in {sorted(WHO)}")


def bars(s):
    if not (s["bars"] and recs(s["bars"], label=is_str, value=lambda v: num(v) and v >= 0)):
        return ["bars must be a non empty list of {label, value} with value a number of at least 0"]
    top = s.get("max") or max(b["value"] for b in s["bars"])
    if not (num(top) and top > 0):
        return ["max, or the largest value when max is absent, must be above 0"]
    return need(all(b["value"] <= top for b in s["bars"]), "max must be at least every bar value")


def code(s):
    lines = s["lines"]
    if not strs(lines):
        return ["lines must be a list of strings"]
    e = need(1 <= len(lines) <= MAX_CODE_LINES, f"lines must be 1 to {MAX_CODE_LINES} lines")
    for ln in lines:
        if len(ln) > MAX_CODE_CHARS:
            e.append(f"code line over {MAX_CODE_CHARS} characters {ln[:40]!r}")
        if CODE_CTRL.search(ln):
            e.append(f"tab, line break or control character in code line {ln[:40]!r}, use one entry per line and spaces")
        if CODE_BAD.search(ln):
            e.append(f"dash or hyphenated word in code line {ln!r}")
    return e


def text_fields(*fields):
    return lambda s: [f"{f} must be a string" for f in fields if not is_str(s[f])]


def stat(s):
    e = need(is_str(s["value"]) or num(s["value"]), "value must be a string or a number")
    return e + text_fields("label")(s)


# Shapes the Remotion components dereference; a wrong shape crashes the render or draws nothing.
SHAPES = {
    "bullets": str_list("items"), "steps": str_list("items"), "flow": str_list("nodes"), "code": code,
    "compare": compare, "graph": linked, "walk": linked, "trace": trace, "search": search, "chat": chat, "bars": bars,
    "title": text_fields("title"), "stat": stat, "term": text_fields("term", "definition"), "quote": text_fields("text"),
}


def items(k, s):
    """The short card phrases the brief limits to seven words."""
    if k in ("bullets", "steps"):
        return s["items"]
    if k == "flow":
        return s["nodes"]
    if k == "compare":
        return s["left"]["items"] + s["right"]["items"]
    return []


def texts(s):
    out = []

    def walk(v):
        if isinstance(v, str):
            out.append(v)
        elif num(v):
            out.append(str(v))
        elif isinstance(v, list):
            for x in v:
                walk(x)
        elif isinstance(v, dict):
            for x in v.values():
                walk(x)
    walk({k: v for k, v in s.items() if k not in STRUCTURE})
    return out


def spelled(text):
    """Words of text with digits spelled out the way map.py aligns them, so 10 and ten compare equal."""
    text = re.sub(r"(\d+)\.(\d+)", lambda m: f"{m[1]} point {' '.join(m[2])}", text.lower().replace(",", ""))
    text = re.sub(r"\d+", lambda m: f" {spell(m[0])} ", text)
    return re.findall(r"[a-z]+", text)


def said(number, body):
    """True when number is spoken in body as a whole number, so 5 does not match fifteen or twenty five."""
    want = spelled(number)
    k = len(want)
    for i in range(len(body) - k + 1):
        if body[i:i + k] == want and (i == 0 or body[i - 1] not in NUM_WORDS) and (i + k == len(body) or body[i + k] not in NUM_WORDS):
            return True
    return False


def whole(v):
    return isinstance(v, int) and not isinstance(v, bool)


def shape_errors(k, s):
    """Missing fields, wrong shapes, then item length, as messages without the scene prefix."""
    missing = [f"missing {f}" for f in KINDS[k] if f not in s]
    if missing:
        return missing
    e = SHAPES[k](s) + [f"{f} must be a string" for f in OPTIONAL_TEXT if f in s and not is_str(s[f])]
    return e or [f"item over {MAX_ITEM_WORDS} words {it!r}" for it in items(k, s) if len(it.split()) > MAX_ITEM_WORDS]


def cue_errors(cs, n_words):
    if not (isinstance(cs, list) and all(whole(c) for c in cs)):
        return [f"cues must be a list of word indexes {cs!r}"]
    e = need(all(b > a for a, b in zip(cs, cs[1:])), f"cues must be strictly increasing {cs}")
    return e + [f"cue {c} out of range" for c in cs if not 0 <= c < n_words]


def check(ep):
    return check_data(load_json(ROOT / "storyboards" / f"{ep}.json"), load_json(ROOT / "map" / f"{ep}.json"))


def check_data(sb, mp):
    errs = []
    paras = {p["index"]: p for p in mp["paragraphs"]}
    scenes = sb.get("scenes") if isinstance(sb, dict) else None
    if not isinstance(scenes, list):
        return ["storyboard must be an object with a scenes list"], 0
    if not scenes or not isinstance(scenes[0], dict) or scenes[0].get("kind") != "title":
        errs.append("first scene must be a title")
    last = -1.0
    examples = 0
    ts = []
    for i, s in enumerate(scenes):
        if not isinstance(s, dict):
            errs.append(f"scene {i}: must be an object")
            continue
        k = s.get("kind")
        if not isinstance(k, str) or k not in KINDS:
            errs.append(f"scene {i}: bad kind {k!r}")
            continue
        bad_shape = shape_errors(k, s)
        errs += [f"scene {i} {k}: {x}" for x in bad_shape]
        examples += k in EXAMPLE and not bad_shape
        para = s.get("para")
        p = paras.get(para) if whole(para) else None
        if p is None or not p["spoken"]:
            errs.append(f"scene {i}: para {para!r} missing or unspoken")
            continue
        n_words = len(p["words"])
        w = s.get("w", 0)
        if not (whole(w) and 0 <= w < n_words):
            errs.append(f"scene {i}: w {w!r} must be a word index 0 to {n_words - 1}")
            continue
        t = p["words"][w]["s"]
        if t < last:
            errs.append(f"scene {i}: starts at {t:.1f}s before previous {last:.1f}s")
        last = t
        ts.append(t)
        errs += [f"scene {i}: {x}" for x in cue_errors(s.get("cues", []), n_words)]
        for tx in texts(s):
            if BAD.search(tx):
                errs.append(f"scene {i}: banned punctuation or count text in {tx!r}")
            if len(tx) > 90:
                errs.append(f"scene {i}: text too long ({len(tx)}) {tx[:40]!r}")
        # every number on a card must be spoken, as digits or words, in the anchored paragraph or the next one
        body = spelled(" ".join(paras[q]["text"] for q in (para, para + 1) if q in paras))
        for tx in ([] if k in EXAMPLE else texts(s)):
            for n in re.findall(r"\d[\d,.]*", tx):
                if not said(n.strip(",."), body):
                    errs.append(f"scene {i}: number {n} not spoken in anchored paragraph text")
    ts.append(mp["duration"])
    gaps = [b - a for a, b in zip(ts, ts[1:])]
    if gaps and max(gaps) > 45:
        errs.append(f"a scene runs {max(gaps):.0f}s, add scenes")
    if gaps and min(gaps) < 2.0:
        errs.append(f"a scene is under 2s ({min(gaps):.1f}s)")
    if examples < MIN_EXAMPLES:
        errs.append(f"{examples} worked example scenes, need at least {MIN_EXAMPLES} ({', '.join(sorted(EXAMPLE))})")
    return errs, len(scenes)


def main():
    if not sys.argv[1:]:
        sys.exit(__doc__)
    bad = 0
    for ep in sys.argv[1:]:
        e, n = check(ep)
        print(ep, n, "scenes", "OK" if not e else "")
        for x in e:
            print("  ", x)
        bad += bool(e)
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    run(main)
