"""Randomize the STRUCTURE of a text while keeping every sentence byte identical.

Splits multi sentence bullets, joins neighbours into one longer bullet, turns a
run of bullets into a paragraph, turns a paragraph into bullets, shuffles bullet
order, and varies blank line rhythm. Words never change, so fact_diff.py can
verify each variant against the source. What it attacks is uniform shape: every
bullet the same length and form, symmetrical sections. Stdlib only.

    python shape_shuffle.py in.txt out.txt --seed 7 --variants 4
    -> out.variant1.txt ... out.variant4.txt

Never touched: heading lines (`# ...` or an ALL CAPS line), numbered lists
(`1.` `2)`, since fact_diff counts the markers as numbers and any split, join or
reorder would add, drop or scramble them), and paragraphs holding a pipe table.
Order is frozen in any section that contains a date range (2018 to 2020,
Apr 2025 to Present), since that order carries meaning. --no-merge keeps every
bullet a bullet. --glue rules.json reads fact_diff qualifier rules and keeps any
bullets that share an anchor or qualifier adjacent, so the proximity check
still passes.
"""
from __future__ import annotations

import argparse
import collections
import json
import random
import re
import sys
from pathlib import Path

# Same zero width split as back_translate.py:66, so "".join(pieces) == text.
SENTENCE_END = re.compile(r"(?<=[.!?]\s)|(?<=[。！？])")
BULLET = re.compile(r"^(\s*(?:[-*•]|\d+[.)])\s+)(.*)$")
NUMBERED = re.compile(r"\s*\d")
HEADING = re.compile(r"^#{1,6} ")
TABLE_ROW = re.compile(r"^\s*\|.*\|\s*$")
_MONTH = r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+"
_YEAR = r"(?:%s)?(?:19|20)\d{2}\b" % _MONTH
DATE_RANGE = re.compile(
    r"\b%s\s*(?:-|–|—|to)\s*(?:%s|present|current)" % (_YEAR, _YEAR), re.IGNORECASE)


def is_heading(line: str) -> bool:
    s = line.strip()
    if HEADING.match(s):
        return True
    return bool(s) and len(s) <= 60 and s == s.upper() and any(c.isalpha() for c in s)


def sentences(text: str) -> list[str]:
    """Sentences with internal whitespace collapsed: a hard wrapped sentence must
    become one bullet line. The invariant is the word sequence, not the bytes
    between words, which is also what fact_diff compares after _flatten."""
    return [" ".join(p.split()) for p in SENTENCE_END.split(text) if p.strip()]


# A chunk is one of: ("heading", line) ("blank", n_lines) ("bullets", [(marker, text)]) ("para", [lines]).
def parse(text: str) -> list[tuple]:
    chunks: list[tuple] = []
    for line in text.split("\n"):
        if not line.strip():
            if chunks and chunks[-1][0] == "blank":
                chunks[-1] = ("blank", chunks[-1][1] + 1)
            else:
                chunks.append(("blank", 1))
        elif (m := BULLET.match(line)):  # marker first: "- ALL CAPS" is a bullet, not a heading
            if chunks and chunks[-1][0] == "bullets":
                chunks[-1][1].append((m.group(1), m.group(2)))
            else:
                chunks.append(("bullets", [(m.group(1), m.group(2))]))
        elif is_heading(line):
            chunks.append(("heading", line))
        elif chunks and chunks[-1][0] == "para":
            chunks[-1][1].append(line)
        else:
            chunks.append(("para", [line]))
    return chunks


def render(chunks: list[tuple]) -> str:
    out: list[str] = []
    for kind, body in chunks:
        if kind == "heading":
            out.append(body)
        elif kind == "blank":
            out.extend([""] * body)
        elif kind == "bullets":
            out.extend(m + t for m, t in body)
        else:
            out.extend(body)
    return "\n".join(out)


def sentence_bag(chunks: list[tuple]) -> collections.Counter:
    bag: collections.Counter = collections.Counter()
    for kind, body in chunks:
        if kind == "bullets":
            for _, t in body:
                bag.update(sentences(t))
        elif kind == "para":
            bag.update(sentences("\n".join(body)))
    return bag


def frozen_sections(chunks: list[tuple]) -> set[int]:
    """Section index (count of headings seen) -> frozen if any non heading line has a date range."""
    frozen, sec = set(), 0
    for kind, body in chunks:
        if kind == "heading":
            sec += 1
        elif kind == "bullets" and any(DATE_RANGE.search(t) for _, t in body):
            frozen.add(sec)
        elif kind == "para" and any(DATE_RANGE.search(l) for l in body):
            frozen.add(sec)
    return frozen


def glue_groups(bullets: list[tuple[str, str]], groups: list[list[str]]) -> list[list[int]]:
    """Index units that must stay together. Each group is one fact_diff rule:
    the anchor plus its must_keep phrases. Bullets hit by any phrase of one
    rule are one unit, so anchor and qualifier stay inside the window."""
    units = [[i] for i in range(len(bullets))]
    for group in groups:
        hits = [i for i, (_, t) in enumerate(bullets) if any(p in t for p in group)]
        if len(hits) > 1:
            lo, hi = min(hits), max(hits)
            span = list(range(lo, hi + 1))
            units = [u for u in units if not set(u) & set(span)]
            units.append(span)
    units.sort()
    return units


def shuffle_chunk(rng: random.Random, kind: str, body, knobs: dict, frozen: bool, marker: str,
                  groups: list[list[str]]) -> list[tuple]:
    if kind == "bullets":
        if any(NUMBERED.match(m) for m, _ in body):
            return [("bullets", list(body))]
        bullets = list(body)
        split = []
        for m, t in bullets:
            parts = sentences(t)
            if len(parts) > 1 and rng.random() < knobs["p_split"]:
                cut = rng.randint(1, len(parts) - 1)
                left, right = " ".join(parts[:cut]), " ".join(parts[cut:])
                if min(len(left.split()), len(right.split())) >= 4:  # no shards like "45 minutes."
                    split += [(m, left), (m, right)]
                    continue
            split.append((m, t))
        bullets = split
        if rng.random() < knobs["p_join"] and len(bullets) > 2:
            i = rng.randrange(len(bullets) - 1)
            bullets[i:i + 2] = [(bullets[i][0], bullets[i][1] + " " + bullets[i + 1][1])]
        if knobs["reorder"] and not frozen and len(bullets) > 2:
            units = glue_groups(bullets, groups)
            rng.shuffle(units)
            bullets = [bullets[i] for u in units for i in u]
        if knobs["p_prose"] and rng.random() < knobs["p_prose"] and 2 <= len(bullets) <= 6:
            k = rng.randint(2, min(3, len(bullets)))
            start = rng.randrange(len(bullets) - k + 1)
            line = " ".join(t for _, t in bullets[start:start + k])
            # A body like "42." or "- x" or "ALL CAPS." is a block marker once it opens a
            # paragraph line, so the line would re-parse as a list item or heading and lose
            # a sentence. Keep those bullets as bullets; the sentence bag must round trip.
            if parse(line) == [("para", [line])]:
                before, after = bullets[:start], bullets[start + k:]
                out: list[tuple] = []
                if before:
                    out += [("bullets", before), ("blank", 1)]
                out.append(("para", [line]))
                if after:
                    out += [("blank", 1), ("bullets", after)]
                return out
        return [("bullets", bullets)]
    if kind == "para":
        parts = sentences("\n".join(body))
        # a pipe delimited row is a table row (fact_diff counts them as ^|...|$); bulletizing
        # one would break its table_rules count. An inline "a | b" in prose is fine.
        if not any(TABLE_ROW.match(l) for l in body) and len(parts) >= 3 and rng.random() < knobs["p_bulletize"]:
            return [("bullets", [(marker, p) for p in parts])]
        return [("para", list(body))]
    if kind == "blank":
        return [("blank", 2 if body == 1 and rng.random() < knobs["p_double"] else body)]
    return [(kind, body)]


def variant(text: str, rng: random.Random, no_merge: bool, no_reorder: bool,
            groups: list[list[str]] | None = None) -> tuple[str, dict]:
    knobs = {
        "p_split": rng.uniform(0.2, 0.9),
        "p_join": rng.uniform(0.0, 0.5),
        "p_prose": 0.0 if no_merge else rng.uniform(0.1, 0.6),
        "p_bulletize": rng.uniform(0.0, 0.6),
        "reorder": (not no_reorder) and rng.random() < 0.8,
        "p_double": rng.uniform(0.0, 0.12),
    }
    chunks = parse(text)
    frozen = frozen_sections(chunks)
    markers = collections.Counter(m for k, b in chunks if k == "bullets" for m, _ in b if not NUMBERED.match(m))
    marker = markers.most_common(1)[0][0] if markers else "- "
    out, sec = [], 0
    for kind, body in chunks:
        if kind == "heading":
            sec += 1
        out.extend(shuffle_chunk(rng, kind, body, knobs, sec in frozen, marker, groups or []))
    result = render(out)
    if sentence_bag(parse(result)) != sentence_bag(chunks):
        raise AssertionError("sentence multiset changed; refusing to emit this variant")
    return result, knobs


def load_glue(path: str | None) -> list[list[str]]:
    if not path:
        return []
    rules = json.loads(Path(path).read_text(encoding="utf-8"))
    groups = []
    for q in rules.get("qualifiers", []):
        keep = q.get("must_keep", [])
        groups.append([q["anchor"]] + ([keep] if isinstance(keep, str) else list(keep)))
    return groups


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source")
    ap.add_argument("dest", help="base name; variants land at dest.variantK.txt")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--variants", type=int, default=4)
    ap.add_argument("--no-merge", action="store_true", help="never turn bullets into a paragraph")
    ap.add_argument("--no-reorder", action="store_true", help="never shuffle bullet order")
    ap.add_argument("--glue", help="fact_diff rules.json; bullets sharing an anchor or qualifier stay adjacent")
    a = ap.parse_args(argv)
    text = Path(a.source).read_text(encoding="utf-8")
    groups = load_glue(a.glue)
    master = random.Random(a.seed)
    dest = Path(a.dest)
    refused = 0
    for k in range(1, a.variants + 1):
        rng = random.Random(master.getrandbits(64))  # one draw per variant, in order
        path = dest.with_suffix(".variant%d.txt" % k)
        try:
            out, knobs = variant(text, rng, a.no_merge, a.no_reorder, groups)
        except AssertionError as e:  # the self check refused this one; the rest still run
            refused += 1
            print("%s  SKIPPED (seed %d): %s" % (path.name, a.seed, e), file=sys.stderr)
            continue
        path.write_text(out, encoding="utf-8")
        print("%s  %s" % (path.name, " ".join("%s=%s" % (n, v if isinstance(v, bool) else "%.2f" % v)
                                              for n, v in knobs.items())), file=sys.stderr)
    print("NOW RUN fact_diff.py %s <variant> [--rules rules.json] on each variant" % a.source, file=sys.stderr)
    return 1 if refused else 0


if __name__ == "__main__":
    sys.exit(main())
