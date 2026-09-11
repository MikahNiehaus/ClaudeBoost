#!/usr/bin/env python
"""Did the rewrite change what the text SAYS?

`lint.py` answers how prose reads. This answers whether it still means the same
thing, which is the question a rewrite, a paraphrase or a translation round trip
actually puts at risk. Nothing else in this skill looks at a source text at all.

Two checks, and the second is the one that catches what a reader's eye slides past.

1. Token drift. Numbers, tagged markers, section references, citations, ticket
   ids and filenames are extracted from both texts and compared as multisets. A
   figure that vanishes, changes, or appears from nowhere fails.

2. Qualifier survival, optional, driven by a rules file. A number can survive
   while the word that makes it true does not. "0.687 average NDCG@10 across 6
   languages" losing "average" keeps every digit and becomes a claim about all
   six. Token drift cannot see that. A rules file names the qualifiers that have
   to stay near the figures they qualify.

Usage:
    python fact_diff.py <baseline> <candidate>
    python fact_diff.py <baseline> <candidate> --rules rules.json
    python fact_diff.py <baseline> <candidate> --rules rules.json --json

Exit 0 if nothing drifted, 1 if it did, 2 on a usage error.

Rules file shape, all keys optional:

    {
      "qualifiers": [
        {"anchor": "70 of the 87", "must_keep": "in 2025", "window": 120,
         "why": "all time is 33.2%, the year is what makes 80.5% true"}
      ],
      "banned": ["submitted to the leaderboard", "beats GPT-2"],
      "verbatim": ["a quoted passage that must survive byte for byte"]
    }

`banned` entries are regexes and only fail when their count RISES against the
baseline, because a document that documents its own banned phrases contains them
on purpose. That false positive is the single most common way a checker like this
gets switched off.
"""

from __future__ import annotations

import argparse
import collections
import json
import re
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# A comma continues a number only when digits follow, so a comma added by a
# rewritten clause is not mistaken for part of the figure.
NUMBER = re.compile(r"(?<![\w.])\d+(?:,\d{3})*(?:\.\d+)?%?")
TAG = re.compile(r"\[[A-Z][A-Z0-9 _-]{1,20}\]")
SECTION = re.compile(r"[§#]\s?\d+(?:\.\d+)*")
CITATION = re.compile(r"`[^`\n]+?:[\d,\-]+`")
TICKET = re.compile(r"\b[A-Z]{2,6}-\d{2,6}\b")
# Standards and model names wear the same shape as a ticket id. Counting SHA-256
# or RFC-7807 as a ticket produces a finding every time one is mentioned.
NOT_A_TICKET = re.compile(
    r"^(SHA|MD|RFC|ISO|AES|RSA|UTF|GPT|HS|RS|ES|PS|CVE|ANSI|IEEE|EN|BS)-", re.I)
FILENAME = re.compile(r"`[^`\n]*?\.[A-Za-z][A-Za-z0-9]{0,5}`")

FENCE = re.compile(r"```.*?```", re.S)


def _strip_code(text: str) -> str:
    """Fenced blocks are data, not prose. Their contents drift legitimately."""
    return FENCE.sub(" ", text)


def tokens(text: str) -> dict[str, collections.Counter]:
    body = _strip_code(text)
    return {
        "numbers": collections.Counter(NUMBER.findall(body)),
        "tags": collections.Counter(TAG.findall(body)),
        "sections": collections.Counter(SECTION.findall(body)),
        "citations": collections.Counter(CITATION.findall(body)),
        "tickets": collections.Counter(
            t for t in TICKET.findall(body) if not NOT_A_TICKET.match(t)),
        "filenames": collections.Counter(FILENAME.findall(body)),
    }


def structure(text: str) -> dict[str, object]:
    return {
        "headings": tuple(sorted(collections.Counter(
            re.findall(r"(?m)^(#{1,6}) ", text)).items())),
        "table_rules": len(re.findall(r"(?m)^\|[\s\-:|]+\|$", text)),
        "fences": text.count("```"),
    }


BLOCKQUOTE = re.compile(r"(?m)^\s*>+\s?")
QUOTED = re.compile(r"[\"“][^\"“”\n]{0,200}[\"”]")


def _flatten(text: str) -> str:
    """One line, with blockquote markers gone.

    Collapsing newlines inside a blockquote would otherwise leave a "> " sitting
    in the middle of a sentence, so "added in\n> 2025" becomes "added in > 2025"
    and a proximity search for "in 2025" misses a qualifier that is really there.
    """
    return re.sub(r"\s+", " ", BLOCKQUOTE.sub("", text))


def _mask_quoted(text: str) -> str:
    """Blank out quoted spans, keeping length so offsets stay valid.

    A document that lists the phrases it forbids contains every one of them. The
    skill's own rule is that a watched phrase inside a quotation, a title, or a
    passage discussing the phrase is never a violation. Masking quotations is the
    mechanical half of that; a mention outside quotes still needs judgment.
    """
    return QUOTED.sub(lambda m: " " * len(m.group(0)), text)


def _rate(haystack: str, anchor: str, keep: str, window: int) -> tuple[int, int]:
    """How many occurrences of anchor keep `keep` within window, out of how many.

    Counting matters. An anchor can appear four times in a long document, and
    damaging one of them must not pass because the other three are intact.
    """
    hits = total = 0
    low = haystack.lower()
    for m in re.finditer(re.escape(anchor.lower()), low):
        total += 1
        a = max(0, m.start() - window)
        b = min(len(low), m.end() + window)
        if keep.lower() in low[a:b]:
            hits += 1
    return hits, total


def compare(base: str, cand: str, rules: dict) -> list[str]:
    fails: list[str] = []

    tb, tc = tokens(base), tokens(cand)
    for kind in tb:
        lost = tb[kind] - tc[kind]
        gained = tc[kind] - tb[kind]
        if lost:
            fails.append("%s LOST: %s" % (kind, dict(lost)))
        if gained:
            fails.append("%s GAINED: %s" % (kind, dict(gained)))

    sb, sc = structure(base), structure(cand)
    for k in sb:
        if sb[k] != sc[k]:
            fails.append("structure %s: %s then %s" % (k, sb[k], sc[k]))

    flat_b = _flatten(base)
    flat_c = _flatten(cand)

    for q in rules.get("qualifiers", []):
        anchor = q["anchor"]
        keep = q["must_keep"]
        window = int(q.get("window", 120))
        why = q.get("why", "")
        hits, total = _rate(flat_c, anchor, keep, window)
        bhits, btotal = _rate(flat_b, anchor, keep, window)
        if total == 0:
            if btotal:
                fails.append("ANCHOR GONE %r (%s)" % (anchor, why))
            continue
        # compare as a rate, so an excerpt with fewer occurrences is judged fairly
        if btotal and (hits / total) < (bhits / btotal):
            fails.append(
                "QUALIFIER DROPPED %r needs %r near it: %d of %d kept it, "
                "baseline %d of %d. %s" % (anchor, keep, hits, total, bhits, btotal, why))

    # Quotations are masked first: a style guide listing phrases to avoid is the
    # common case, and every entry on its list would otherwise be a finding.
    unquoted_b = _mask_quoted(flat_b)
    unquoted_c = _mask_quoted(flat_c)
    for pat in rules.get("banned", []):
        n_c = len(re.findall(pat, unquoted_c, re.I))
        if not n_c:
            continue
        if n_c > len(re.findall(pat, unquoted_b, re.I)):
            m = re.search(pat, unquoted_c, re.I)
            fails.append("BANNED PHRASING APPEARED: %r" % m.group(0))

    for quote in rules.get("verbatim", []):
        if quote in base and quote not in cand:
            fails.append("VERBATIM PASSAGE DAMAGED: %r" % quote[:60])

    return fails


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Check that a rewrite did not change what the text says.")
    p.add_argument("baseline", help="the text before the rewrite")
    p.add_argument("candidate", help="the text after it")
    p.add_argument("--rules", help="optional JSON file of qualifier and banned rules")
    p.add_argument("--json", action="store_true", help="machine readable output")
    args = p.parse_args(argv)

    try:
        base = Path(args.baseline).read_text(encoding="utf-8", errors="replace")
        cand = Path(args.candidate).read_text(encoding="utf-8", errors="replace")
    except OSError as err:
        print("cannot read: %s" % err, file=sys.stderr)
        return 2

    rules: dict = {}
    if args.rules:
        try:
            rules = json.loads(Path(args.rules).read_text(encoding="utf-8"))
        except (OSError, ValueError) as err:
            print("cannot read rules: %s" % err, file=sys.stderr)
            return 2

    fails = compare(base, cand, rules)

    if args.json:
        print(json.dumps({"ok": not fails, "findings": fails}, indent=2))
        return 1 if fails else 0

    if fails:
        print("FAIL: %d fact problem(s)" % len(fails))
        for f in fails:
            print("  " + f)
        return 1
    print("OK: no drift in numbers, tags, sections, citations, tickets, "
          "filenames, structure or declared qualifiers")
    return 0


if __name__ == "__main__":
    sys.exit(main())
