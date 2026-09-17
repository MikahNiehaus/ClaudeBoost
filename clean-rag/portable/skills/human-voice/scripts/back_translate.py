#!/usr/bin/env python
"""Round trip text through a chain of languages and back.

Why this exists: a back translation chain is the one published adversarial
technique that moves a classifier based AI detector and that a careful writer
could plausibly have produced. Of RAID's 11 attacks it and synonym substitution
are the only two that survive an ATS safe filter; the rest insert homoglyphs,
zero width characters or deliberate misspellings and are out of scope here.

What it costs is fact fidelity. Machine translation silently drops qualifiers,
strengthens verbs and reformats numbers. So this ships next to `fact_diff.py`
and is close to useless without it. Translate, diff, repair, in that order.

Approach taken from `nidhaloff/deep-translator` (MIT), which drives the same
public endpoint `translate.googleapis.com/translate_a/single` with `client=gtx`.
Reimplemented on the standard library so nothing needs installing, and chunked
by paragraph because the endpoint truncates long payloads without saying so.

Every hop is written next to the destination (`out.hop1.zh-CN.txt`, ...), so a
bad hop can be identified rather than guessed at.

Token masking (protecting `0.687` or `T-SQL` from the translator) is deliberately
not done here. `fact_diff.py` detects what the round trip damaged and `fact-medic`
repairs it; a masked token the translator mangles anyway would fail silently.

Usage:
    python back_translate.py in.txt out.txt
    python back_translate.py in.txt out.txt --chain zh-CN,tr,ja
    python back_translate.py in.txt out.txt --chain de --pause 0.5
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ENDPOINT = "https://translate.googleapis.com/translate_a/single"
# A browser User-Agent is required. The endpoint returns 403 to a bare urllib.
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")
# The endpoint truncates silently past roughly this many characters of URL. It is
# measured AFTER percent encoding: a CJK glyph is 3 UTF-8 bytes and becomes 9
# characters on the wire, so a raw count is 4.4x too generous on the zh-CN and
# ja legs of the default chain (measured: 90 raw chars became 394).
CHUNK = 1800
DEFAULT_CHAIN = ["zh-CN", "tr", "ja"]
# Only these can clear on their own. A 403 means the User-Agent was rejected and
# retrying it is waste. Same split as urllib3's Retry.status_forcelist.
RETRY_STATUS = {408, 429, 500, 502, 503, 504}
# Sentence end: an ASCII terminator plus the one whitespace char after it, or a
# full width terminator on its own (CJK puts no space after 。). Zero width, so
# re.split keeps every character and "".join(pieces) round trips. Same lookbehind
# lint.py uses; abbreviations ("e.g. ") are not special cased, a wrong boundary
# only costs a slightly worse chunk edge.
SENTENCE_END = re.compile(r"(?<=[.!?]\s)|(?<=[。！？])")


def _encoded_len(text: str) -> int:
    return len(urllib.parse.quote(text))


def _request(text: str, src: str, dst: str, timeout: int = 30) -> str:
    url = "%s?client=gtx&sl=%s&tl=%s&dt=t&q=%s" % (
        ENDPOINT, src, dst, urllib.parse.quote(text))
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    # shape is [[[translated, original, ...], ...], ...]. Each segment carries its
    # own trailing newline, so a plain join keeps the source's line structure.
    return "".join(seg[0] for seg in payload[0] if seg and seg[0])


def _split(para: str) -> list[str]:
    """Pieces of one paragraph, never mid sentence, budgeted on encoded length.

    Zero width split, so "".join(pieces) == para. The paragraph loop lives in
    `translate()`, which is the only place that knows which pieces belong to the
    same paragraph and so the only place the "\\n\\n" separator can be restored.

    Splitting mid sentence is what makes a round trip incoherent, because each
    piece is translated without the context of its neighbours. So a single
    sentence that alone exceeds CHUNK is emitted whole with a warning on stderr
    rather than cut at a word: the endpoint's truncation is silent, this is not,
    and `fact_diff.py` catches what a truncated piece dropped.
    """
    if _encoded_len(para) <= CHUNK:
        return [para]
    out: list[str] = []
    buf = ""
    for sentence in SENTENCE_END.split(para):
        if buf and _encoded_len(buf + sentence) > CHUNK:
            out.append(buf)
            buf = ""
        if _encoded_len(sentence) > CHUNK:
            print("warning: one sentence is %d encoded chars, over the %d budget; "
                  "the endpoint may truncate it: %.60r"
                  % (_encoded_len(sentence), CHUNK, sentence), file=sys.stderr)
        buf += sentence
    if buf:
        out.append(buf)
    return out


def _backoff(attempt: int, factor: float = 1.0, cap: float = 30.0) -> float:
    """urllib3's formula: factor * 2**attempt, plus jitter, capped."""
    return min(cap, factor * (2 ** attempt) + random.random() * 0.5)


def translate(text: str, src: str, dst: str, pause: float = 0.4,
              retries: int = 3, fetch=None, sleep=time.sleep) -> str:
    """`fetch` and `sleep` are injectable so the driver is testable offline."""
    fetch = fetch or _request
    paras = []
    i = 0
    # "\n\n".join(text.split("\n\n")) == text, so "\n\n\n" runs, leading and
    # trailing blank lines and whitespace only paragraphs all round trip.
    for para in text.split("\n\n"):
        pieces = []
        for piece in _split(para):
            i += 1
            if not piece.strip():
                pieces.append(piece)
                continue
            for attempt in range(retries):
                try:
                    pieces.append(fetch(piece, src, dst))
                    break
                except urllib.error.HTTPError as err:
                    if err.code not in RETRY_STATUS or attempt == retries - 1:
                        raise SystemExit("translate %s to %s failed on piece %d: HTTP %d"
                                         % (src, dst, i, err.code))
                    sleep(_backoff(attempt))
                except (urllib.error.URLError, ValueError, IndexError) as err:
                    if attempt == retries - 1:
                        raise SystemExit("translate %s to %s failed on piece %d: %s"
                                         % (src, dst, i, err))
                    sleep(_backoff(attempt))
            # jitter, so a long document does not look like a scripted burst
            sleep(pause + random.random() * 0.3)
        paras.append("".join(pieces))
    return "\n\n".join(paras)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Back translate text through a language chain.")
    p.add_argument("source")
    p.add_argument("dest")
    p.add_argument("--chain", default=",".join(DEFAULT_CHAIN),
                   help="comma separated language codes to pass through before returning to English")
    p.add_argument("--home", default="en", help="language to start from and return to")
    p.add_argument("--pause", type=float, default=0.4)
    args = p.parse_args(argv)

    text = Path(args.source).read_text(encoding="utf-8")
    chain = [c.strip() for c in args.chain.split(",") if c.strip()]
    legs = list(zip([args.home] + chain, chain + [args.home]))

    print("%d words in, chain %s" % (len(text.split()), " to ".join([args.home] + chain + [args.home])))
    current = text
    for n, (src, dst) in enumerate(legs, 1):
        current = translate(current, src, dst, pause=args.pause)
        hop = Path(args.dest).with_suffix(".hop%d.%s.txt" % (n, dst))
        hop.write_text(current, encoding="utf-8")
        print("  hop %d  %-6s to %-6s  %5d chars  %s" % (n, src, dst, len(current), hop.name))

    Path(args.dest).write_text(current, encoding="utf-8")
    print("%d words out, written to %s" % (len(current.split()), args.dest))
    print("NOW RUN fact_diff.py against the source. Translation drops qualifiers "
          "silently and this script does not check that.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
