#!/usr/bin/env python3
"""
Anti-AI writing linter.

Checks prose for structural AI tells, not just banned vocabulary.
Structural checks are weighted heavier because vocabulary bans only
move the tell, they do not remove it.

Usage:
    python lint.py draft.md
    cat draft.md | python lint.py -
    python lint.py draft.md --json
    python lint.py draft.md --short     (short-form mode: chat, email, push)
"""

import argparse
import json
import re
import statistics
import sys

# ---------------------------------------------------------------- vocabulary

BANNED_WORDS = [
    "delve", "deep dive", "unpack", "robust", "holistic",
    "synergy", "comprehensive",
]

# Only flagged in figurative use; checked with context patterns below.
CONTEXTUAL_WORDS = {
    "navigate": r"\bnavigat(e|ing|es|ed)\s+(the\s+)?(complexit|challeng|landscape|nuance|world|maze|terrain)",
    "landscape": r"\b(the\s+)?(competitive|regulatory|market|industry|business|digital|media|evolving|shifting|changing)\s+landscape\b",
    "leverage": r"\bleverag(e|ing|es|ed)\s+(the\s+|our\s+|your\s+|their\s+|its\s+)?\w+",
}

CAPPED_WORDS = {"crucial": 1, "vital": 1, "essential": 1}

BANNED_PHRASES = [
    "it is worth noting that", "it's worth noting that",
    "it is important to understand", "it is important to note",
    "it's important to note", "it's important to understand",
    "it is crucial to", "it's crucial to",
    "in conclusion", "in summary", "to summarise", "to summarize",
    "to sum up",
    "not only", "but also",
    "on the one hand", "on the other hand",
]

CONTRAST_PATTERNS = [
    (r"\bnot\s+(just\s+|merely\s+|simply\s+)?[\w\s]{2,30},\s*but\s+", "not X, but Y"),
    (r"\bisn't\s+[\w\s]{2,30}[.,]\s*(it's|it is)\s+", "X isn't Y, it's Z"),
    (r"\bis not\s+[\w\s]{2,30}[.,]\s*(it's|it is)\s+", "X is not Y, it is Z"),
    (r"\bless about\s+[\w\s]{2,30}\s+(and\s+)?more about\b", "less about X, more about Y"),
    (r"\bnot\s+because\s+[\w\s]{2,40},\s*but\s+because\b", "not because X, but because Y"),
    # Trailing negation. The dominant real-world shape, and the one most
    # rulesets miss because they only look for a leading "not".
    (r",\s*not\s+(?!only\b)[\w'-]+", "X, not Y"),
]

HEDGE_PATTERN = r"\bwhile\s+[\w\s,]{5,60}\s+(it is|it's)\s+(also\s+)?(important|worth|crucial|vital)\b"

STACKED_ADJ = r"\b(\w+ly\s+)?(\w+),\s*(\w+),\s*and\s+(\w+)\s+(approach|solution|strategy|framework|guide|process|method|system|tool)\b"

SUMMARY_OPENERS = [
    "in conclusion", "in summary", "to summarise", "to summarize", "to sum up",
    "ultimately", "at the end of the day", "all in all", "in short",
    "the bottom line", "overall,",
]

PARTICIPLE_OPEN = r"^\s*\w+(ing|ed)\b"

# Result clauses tacked onto sentence ends: ", ensuring X", ", allowing Y".
# One is fine. A run of them is a strong tell.
PARTICIPLE_TAIL = (
    r",\s+(ensuring|allowing|helping|enabling|making|providing|creating|"
    r"offering|delivering|improving|reducing|increasing|giving|leading|"
    r"resulting|driving|streamlining|empowering)\b"
)

# ---------------------------------------------------------------- utilities


def strip_markdown(text):
    text = re.sub(r"```.*?```", " ", text, flags=re.S)
    text = re.sub(r"`[^`]*`", " ", text)
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", text)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"^\s{0,3}#{1,6}\s+.*$", "", text, flags=re.M)
    text = re.sub(r"[*_>]", "", text)
    return text


def get_title(text):
    for line in text.splitlines():
        m = re.match(r"^\s{0,3}#\s+(.*)", line)
        if m:
            return m.group(1).strip()
        if line.strip():
            return line.strip()
    return ""


def split_sentences(text):
    out = []
    for block in re.split(r"\n\s*\n", text):
        block = re.sub(r"\s+", " ", block).strip()
        if not block:
            continue
        parts = re.split(r"(?<=[.!?])\s+(?=[A-Z\"'\u201c(])", block)
        out += [p.strip() for p in parts if len(p.strip().split()) >= 2]
    return out


def paragraphs(text):
    return [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]


def content_words(s):
    stop = {
        "the", "a", "an", "and", "or", "but", "of", "to", "in", "on", "for",
        "with", "is", "are", "was", "were", "be", "been", "it", "its", "this",
        "that", "as", "at", "by", "from", "you", "your", "i", "we", "our",
        "they", "their", "not", "can", "will", "has", "have", "had", "do",
        "does", "if", "so", "than", "then", "there", "what", "which", "when",
    }
    words = re.findall(r"[a-z']+", s.lower())
    return [w for w in words if w not in stop and len(w) > 2]


# ---------------------------------------------------------------- checks


def check_em_dash_connectors(text):
    """Em dash joining clauses. Ranges between digits are allowed."""
    findings = []
    for m in re.finditer(r"\u2014", text):
        before = text[max(0, m.start() - 40):m.start()]
        after = text[m.end():m.end() + 40]
        if re.search(r"\d\s*$", before) and re.match(r"\s*\d", after):
            continue
        findings.append({
            "check": "em_dash_connector",
            "severity": "structural",
            "detail": "Em dash used as a connector.",
            "context": (before[-30:] + "\u2014" + after[:30]).strip(),
        })
    return findings


def check_sentence_variance(sentences, short_mode=False):
    findings = []
    if len(sentences) < 6:
        return findings
    lengths = [len(s.split()) for s in sentences]
    sd = statistics.pstdev(lengths)
    mean = statistics.mean(lengths)
    threshold = 5.0 if not short_mode else 3.0
    if sd < threshold:
        findings.append({
            "check": "low_sentence_variance",
            "severity": "structural",
            "detail": (
                f"Sentence length standard deviation is {sd:.1f} "
                f"(mean {mean:.1f} words). Below {threshold} reads as AI cadence. "
                "Add at least one very short sentence and one long one."
            ),
            "context": "",
        })
    band = [n for n in lengths if 14 <= n <= 21]
    if len(lengths) >= 8 and len(band) / len(lengths) > 0.7:
        findings.append({
            "check": "clustered_sentence_length",
            "severity": "structural",
            "detail": (
                f"{len(band)} of {len(lengths)} sentences fall in the 14-21 word band. "
                "That is the default AI range."
            ),
            "context": "",
        })
    return findings


def check_opening(text, sentences):
    findings = []
    if not sentences:
        return findings
    title = get_title(text)
    first = sentences[0]
    if title:
        tw = set(content_words(title))
        fw = set(content_words(first))
        if tw and len(tw & fw) / len(tw) >= 0.6:
            findings.append({
                "check": "opening_restates_title",
                "severity": "structural",
                "detail": "First sentence repeats most of the title. Open with a fact instead.",
                "context": first[:90],
            })
    generic = r"^(in today's|in the world of|in an era|as technology|when it comes to|whether you|the world of|there's no denying|in recent years)"
    if re.match(generic, first.strip(), re.I):
        findings.append({
            "check": "generic_opening",
            "severity": "structural",
            "detail": "Generic scene-setting opener.",
            "context": first[:90],
        })
    return findings


def check_closing_restatement(text, sentences):
    findings = []
    paras = paragraphs(strip_markdown(text))
    if len(paras) < 2 or len(sentences) < 8:
        return findings
    last = paras[-1]
    body = " ".join(paras[:-1])
    lw, bw = content_words(last), set(content_words(body))
    if lw:
        overlap = len([w for w in lw if w in bw]) / len(lw)
        if overlap > 0.85 and len(lw) > 6:
            findings.append({
                "check": "closing_restatement",
                "severity": "structural",
                "detail": (
                    f"Final paragraph reuses {overlap:.0%} of vocabulary already in the body "
                    "and introduces nothing new. Cut it or end on a concrete fact."
                ),
                "context": last[:90],
            })
    for opener in SUMMARY_OPENERS:
        if last.lower().lstrip().startswith(opener):
            findings.append({
                "check": "summary_opener",
                "severity": "structural",
                "detail": f"Final paragraph opens with '{opener}'.",
                "context": last[:90],
            })
            break
    return findings


def check_repeated_openings(sentences):
    findings = []
    runs, current = [], []
    for s in sentences:
        if re.match(PARTICIPLE_OPEN, s):
            current.append(s)
        else:
            if len(current) >= 3:
                runs.append(list(current))
            current = []
    if len(current) >= 3:
        runs.append(current)
    for run in runs:
        findings.append({
            "check": "repeated_sentence_opening",
            "severity": "structural",
            "detail": f"{len(run)} consecutive sentences open with a participle.",
            "context": run[0][:70],
        })
    firsts = [s.split()[0].lower() for s in sentences if s.split()]
    for i in range(len(firsts) - 2):
        if firsts[i] == firsts[i + 1] == firsts[i + 2]:
            findings.append({
                "check": "repeated_first_word",
                "severity": "structural",
                "detail": f"Three consecutive sentences start with '{firsts[i]}'.",
                "context": sentences[i][:70],
            })
            break
    return findings


def check_contrast(text):
    findings = []
    hits = []
    for pattern, label in CONTRAST_PATTERNS:
        for m in re.finditer(pattern, text, re.I):
            hits.append((label, m.group(0)[:70]))
    if len(hits) > 1:
        for label, ctx in hits[1:]:
            findings.append({
                "check": "contrast_construction",
                "severity": "structural",
                "detail": f"Contrast construction ({label}). One per piece maximum.",
                "context": ctx,
            })
    return findings


def check_vocabulary(text, short_mode=False):
    findings = []
    low = text.lower()

    for w in BANNED_WORDS:
        for m in re.finditer(r"\b" + re.escape(w) + r"\w*", low):
            findings.append({
                "check": "banned_word",
                "severity": "vocabulary",
                "detail": f"Banned word: {w}",
                "context": text[max(0, m.start() - 25):m.end() + 25].strip(),
            })

    for w, pattern in CONTEXTUAL_WORDS.items():
        for m in re.finditer(pattern, low):
            findings.append({
                "check": "banned_word_figurative",
                "severity": "vocabulary",
                "detail": f"Figurative use of '{w}'.",
                "context": text[max(0, m.start() - 20):m.end() + 20].strip(),
            })

    for w, cap in CAPPED_WORDS.items():
        n = len(re.findall(r"\b" + w + r"\b", low))
        if n > cap:
            findings.append({
                "check": "over_cap_word",
                "severity": "vocabulary",
                "detail": f"'{w}' used {n} times. Cap is {cap} per piece.",
                "context": "",
            })

    for phrase in BANNED_PHRASES:
        idx = low.find(phrase)
        if idx != -1:
            findings.append({
                "check": "banned_phrase",
                "severity": "vocabulary",
                "detail": f"Banned phrase: '{phrase}'",
                "context": text[max(0, idx - 20):idx + len(phrase) + 20].strip(),
            })

    for m in re.finditer(HEDGE_PATTERN, low):
        findings.append({
            "check": "hedge_structure",
            "severity": "structural",
            "detail": "Balanced hedging structure.",
            "context": text[m.start():m.end()][:70],
        })

    for m in re.finditer(STACKED_ADJ, low):
        findings.append({
            "check": "stacked_adjectives",
            "severity": "vocabulary",
            "detail": "Three stacked adjectives before a noun.",
            "context": m.group(0)[:70],
        })

    if not short_mode:
        for m in re.finditer(r"(?:^|\n)\s*(?:so\s+)?(what|why|how)\s+(does|do|is|are|can|should)\b[^?]{5,80}\?", text, re.I):
            findings.append({
                "check": "rhetorical_opener",
                "severity": "structural",
                "detail": "Section opens with a rhetorical question.",
                "context": m.group(0).strip()[:70],
            })
    return findings


def check_short_form(text, sentences):
    findings = []
    if len(sentences) > 4:
        findings.append({
            "check": "short_form_too_long",
            "severity": "structural",
            "detail": f"{len(sentences)} sentences. Short-form target is 1 to 4.",
            "context": "",
        })
    emoji = len(re.findall(
        r"[\U0001F300-\U0001FAFF\U00002600-\U000027BF]", text))
    if emoji > 1:
        findings.append({
            "check": "emoji_spam",
            "severity": "vocabulary",
            "detail": f"{emoji} emoji. Maximum is 1.",
            "context": "",
        })
    for pattern in [r"\b(i\s+)?apologi[sz]e\b", r"\bsorry for the\b", r"\bplease do not hesitate\b"]:
        if re.search(pattern, text, re.I):
            findings.append({
                "check": "over_apology",
                "severity": "vocabulary",
                "detail": "Formal apology or sign-off boilerplate.",
                "context": "",
            })
    return findings


def _in_gerund_list(text, m):
    """', leading' inside 'sharing, leading and listening' is a list item."""
    before = text[max(0, m.start() - 30):m.start()]
    after = text[m.end():m.end() + 30]
    if re.search(r"\w+ing\s*$", before):
        return True
    if re.match(r"\s+and\s+\w+ing\b", after):
        return True
    return False


def check_participle_tails(text):
    """Result clauses tacked onto sentence ends. Cap is one per piece."""
    findings = []
    hits = [m for m in re.finditer(PARTICIPLE_TAIL, text, re.I)
            if not _in_gerund_list(text, m)]
    for m in hits[1:]:
        findings.append({
            "check": "participle_tail",
            "severity": "structural",
            "detail": (
                "Result clause tacked on with a participle. One per piece maximum. "
                "Split it into its own sentence or cut it."
            ),
            "context": text[max(0, m.start() - 35):m.end() + 25].strip(),
        })
    return findings


# ---------------------------------------------------------------- runner


def lint(text, short_mode=False):
    clean = strip_markdown(text)
    sentences = split_sentences(clean)

    findings = []
    findings += check_em_dash_connectors(text)
    findings += check_vocabulary(text, short_mode)

    if short_mode:
        findings += check_short_form(clean, sentences)
    else:
        findings += check_sentence_variance(sentences)
        findings += check_opening(text, sentences)
        findings += check_closing_restatement(text, sentences)
        findings += check_repeated_openings(sentences)
        findings += check_contrast(clean)
        findings += check_participle_tails(clean)

    lengths = [len(s.split()) for s in sentences]
    stats = {
        "sentences": len(sentences),
        "words": len(clean.split()),
        "mean_sentence_length": round(statistics.mean(lengths), 1) if lengths else 0,
        "sentence_length_sd": round(statistics.pstdev(lengths), 1) if len(lengths) > 1 else 0,
        "structural_flags": sum(1 for f in findings if f["severity"] == "structural"),
        "vocabulary_flags": sum(1 for f in findings if f["severity"] == "vocabulary"),
    }
    # Capped checks allow one instance silently. Linting a site page by page
    # therefore grants one free pass per file and the pattern disappears.
    # Report totals so a run across many files still shows the habit.
    contrast_total = sum(len(re.findall(p, clean, re.I)) for p, _ in CONTRAST_PATTERNS)
    tail_total = len([m for m in re.finditer(PARTICIPLE_TAIL, clean, re.I)
                      if not _in_gerund_list(clean, m)])
    stats["contrast_constructions"] = contrast_total
    stats["participle_tails"] = tail_total
    return findings, stats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path", help="file to lint, or - for stdin")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--short", action="store_true",
                    help="short-form mode for chat, email, push")
    args = ap.parse_args()

    text = sys.stdin.read() if args.path == "-" else open(args.path, encoding="utf-8").read()
    findings, stats = lint(text, args.short)

    if args.json:
        print(json.dumps({"stats": stats, "findings": findings}, indent=2))
        return 1 if stats["structural_flags"] else 0

    print(f"\n{stats['words']} words, {stats['sentences']} sentences")
    print(f"Mean sentence length {stats['mean_sentence_length']}, "
          f"standard deviation {stats['sentence_length_sd']}")
    print(f"Structural flags: {stats['structural_flags']}   "
          f"Vocabulary flags: {stats['vocabulary_flags']}")
    capped = []
    if stats.get("contrast_constructions"):
        capped.append(f"contrast constructions {stats['contrast_constructions']}")
    if stats.get("participle_tails"):
        capped.append(f"participle tails {stats['participle_tails']}")
    if capped:
        print("Capped patterns present: " + ", ".join(capped) +
              "  (one per piece is allowed, so check the total across a whole site)")
    print()

    if not findings:
        print("Clean.\n")
        return 0

    for severity in ("structural", "vocabulary"):
        group = [f for f in findings if f["severity"] == severity]
        if not group:
            continue
        print(f"--- {severity.upper()} ({len(group)}) ---")
        for f in group:
            print(f"  [{f['check']}] {f['detail']}")
            if f["context"]:
                print(f"      > {f['context']}")
        print()

    print("Repairs for each flag type are in references/fixes.md\n")
    return 1 if stats["structural_flags"] else 0


if __name__ == "__main__":
    sys.exit(main())
