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
    python lint.py draft.md --strict    (exit 1 on vocabulary flags too)

Exit codes: 0 clean, 1 flags found, 2 the file could not be read.
"""

import argparse
import json
import re
import statistics
import sys

# ---------------------------------------------------------------- vocabulary

#: Abbreviations that end in a period without ending a sentence. Subset of
#: pySBD's list (nipunsadvilkar/pySBD, MIT, pysbd/lang/common/standard.py),
#: kept to the forms that turn up in prose this linter reads. Without these the
#: splitter cut "Dr. Smith reviewed the code" into "Dr." and a 6-word remainder,
#: so every length statistic was wrong on any text containing a title.
ABBREVIATIONS = frozenset("""
adm approx apr attys aug ave brig capt cmdr co col comdr con corp cpl ct dec
dept det dr drs e.g ed eds eg esp esq est etc ext feb fig figs gen gov hon hr
hrs i.e ie inc insp jan jr jul jun lt ltd maj mar messrs mfg min mr mrs ms
msgr mssrs mt no nos nov oct op p pp prof pvt rep reps rev sec sen sens sep
sept sgt sr st supt u.k u.s univ v vol vols vs
""".split())

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

EM_DASH = "—"

#: The first five shapes are explicit enough that one sighting means something.
#: The bare trailing negation is not: see WEAK_CONTRAST below.
CONTRAST_PATTERNS = [
    (r"\bnot\s+(just\s+|merely\s+|simply\s+)?[\w\s]{2,30},\s*but\s+", "not X, but Y"),
    (r"\bisn't\s+[\w\s]{2,30}[.,]\s*(it's|it is)\s+", "X isn't Y, it's Z"),
    (r"\bis not\s+[\w\s]{2,30}[.,]\s*(it's|it is)\s+", "X is not Y, it is Z"),
    (r"\bless about\s+[\w\s]{2,30}\s+(and\s+)?more about\b", "less about X, more about Y"),
    (r"\bnot\s+because\s+[\w\s]{2,40},\s*but\s+because\b", "not because X, but because Y"),
]

#: Trailing negation. Real, and the shape most rulesets miss, but far too common
#: in ordinary English to treat as one violation per sighting: ", not a", ", not
#: the", ", not who" are plain contrastive apposition. Measured on this repo's
#: own hand-written prose it fired 24 times in CLAUDE.md and 6 times in a
#: 344-word style guide, which is a habit worth one note, not 30 findings. The
#: corroboration gate calls this class weak alone, so it reports as a density
#: note and never as a per-instance flag.
WEAK_CONTRAST = r",\s*not\s+(?!only\b)[\w'-]+"

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


def mask_exempt(text):
    """Blank out spans the catalog exempts, keeping every byte offset intact.

    The corroboration gate in references/patterns.md refuses to act on a watched
    phrase "inside a quotation, a title, a proper name, or a passage that
    discusses the phrase rather than uses it". A style guide's own list of
    phrases to avoid is the common case: this linter used to flag every entry in
    one. Code is exempt for the same reason, and vocabulary checks read raw text
    where strip_markdown never reached it.

    Spaces rather than deletion so `context` slices still line up with the
    original. Only double quotes are masked; matching single quotes would eat
    every apostrophe.
    """
    def blank(m):
        return re.sub(r"[^\n]", " ", m.group(0))

    text = re.sub(r"```.*?```", blank, text, flags=re.S)
    text = re.sub(r"`[^`\n]*`", blank, text)
    text = re.sub(r"\"[^\"\n]{0,200}\"", blank, text)
    text = re.sub(r"\u201c[^\u201d\n]{0,200}\u201d", blank, text)
    return text


def get_title(text):
    """The document's markdown H1, or "" when it has none.

    No first-line fallback. The rule this feeds is "A heading repeated in the
    first sentence" (references/patterns-full.md): with no heading there is
    nothing to repeat, and the fallback compared the opening line against
    itself, so every headingless document scored a trivial 100% overlap.
    """
    for line in text.splitlines():
        m = re.match(r"^\s{0,3}#\s+(.*)", line)
        if m:
            return m.group(1).strip()
    return ""


def _ends_in_abbreviation(chunk):
    """Is the period ending `chunk` an abbreviation's rather than a sentence's?"""
    m = re.search(r"([A-Za-z][A-Za-z.]*)\.\s*$", chunk)
    if not m:
        return False
    token = m.group(1).lower().rstrip(".")
    # A lone initial ("I. Brown", "J. R. R. Tolkien") never ends a sentence.
    return token in ABBREVIATIONS or len(token) == 1


def split_sentences(text):
    out = []
    for block in re.split(r"\n\s*\n", text):
        block = re.sub(r"\s+", " ", block).strip()
        if not block:
            continue
        parts, start = [], 0
        for m in re.finditer(r"(?<=[.!?])\s+(?=[A-Z\"'\u201c(])", block):
            head = block[start:m.start()]
            if _ends_in_abbreviation(head):
                continue
            parts.append(head)
            start = m.end()
        parts.append(block[start:])
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


#: patterns.md's own Formatting carve-out: an em dash separating a bolded lead
#: term or a markdown link from its description, inside a list item, is
#: typography rather than a prose splice. It was documented but never coded, so
#: every reference list in this repo's own markdown scored as a splice.
LIST_LEAD = re.compile(r"^\s*(?:[-*+]|\d+\.)\s+(?:\*\*[^*]+\*\*|\[[^\]]+\]\([^)]*\)|`[^`]+`)\s*$")


def _dash_positions_by_line(text):
    """Em dash offsets grouped by the line holding them, with that line's text."""
    lines = {}
    for m in re.finditer(EM_DASH, text):
        start = text.rfind("\n", 0, m.start()) + 1
        end = text.find("\n", m.start())
        line = text[start:end if end != -1 else len(text)]
        lines.setdefault(start, (line, []))[1].append(m.start())
    return lines


def _paired_offsets(text, positions):
    """Offsets belonging to a paired-dash parenthetical, and how many pairs."""
    paired, count = set(), 0
    for left, right in zip(positions, positions[1:]):
        inner = text[left + 1:right]
        if "\n" not in inner and len(inner.split()) <= 12:
            paired.update((left, right))
            count += 1
    return paired, count


def _classify_em_dashes(text):
    """Split every em dash into prose splices and parenthetical asides."""
    splices, asides = [], 0
    for start, (line, positions) in _dash_positions_by_line(text).items():
        paired, count = _paired_offsets(text, positions)
        asides += count
        for pos in positions:
            before, after = text[max(0, pos - 40):pos], text[pos + 1:pos + 41]
            is_range = re.search(r"\d\s*$", before) and re.match(r"\s*\d", after)
            if pos in paired or is_range or LIST_LEAD.match(line[:pos - start]):
                continue
            splices.append((before, after))
    return splices, asides


def check_em_dash_connectors(text, words=0):
    """Em dash splices, against the rate ceiling patterns.md actually names.

    Three things are not splices. A range between digits. The list-item
    separator carved out in patterns.md's Formatting rule. And a pair of dashes
    bracketing a short phrase mid-sentence, which is a parenthetical aside:
    references/fixes.md keeps that one, and the corroboration gate calls it weak
    alone, so it is counted and reported rather than flagged per dash.

    Splices are reported against "one per 1,000 words", the ceiling patterns.md
    states, instead of one flag per dash. At 5 dashes in 5,700 words the old
    behaviour reported five violations of a rule the text was inside.
    """
    findings = []
    splices, asides = _classify_em_dashes(text)
    if not splices and not asides:
        return findings

    allowed = max(1, round(words / 1000)) if words else 1
    if len(splices) > allowed:
        for before, after in splices[allowed:]:
            findings.append({
                "check": "em_dash_connector",
                "severity": "structural",
                "detail": (
                    f"Em dash used as a connector. {len(splices)} splices in "
                    f"{words} words; the ceiling is one per 1,000."
                ),
                "context": (before[-30:] + EM_DASH + after[:30]).strip(),
            })
    if asides:
        findings.append({
            "check": "em_dash_aside",
            "severity": "note",
            "detail": (
                f"{asides} paired-dash parenthetical(s). Kept by fixes.md and weak "
                "alone. Act only if other tells share the passage."
            ),
            "context": "",
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
        # Two conditions, because title coverage alone is not restatement. A
        # first sentence that reuses the title's nouns while adding real content
        # is an ordinary opening: "# Deploying the worker pool" followed by "the
        # worker pool spins up five processes on boot" covers 2 of 3 title words
        # and is not a repeat. The rule (patterns-full.md, "A heading repeated in
        # the first sentence") is about a sentence that adds nothing before the
        # real content starts, so the novelty test is the load-bearing half.
        if tw and len(tw & fw) / len(tw) >= 0.6 and len(fw - tw) <= 3:
            findings.append({
                "check": "opening_restates_title",
                "severity": "structural",
                "detail": "First sentence repeats the title and adds nothing. Cut it.",
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


def check_repeated_paragraph_openings(text):
    """Three or more paragraphs opening on the same word.

    "Same-opener sentence runs" in references/patterns-full.md covers a run of
    consecutive sentences. It misses the commoner shape, where the repeat lands
    once per paragraph: five paragraphs each opening "So" reads as a tic, and no
    two of those sentences are adjacent, so a consecutive-sentence check sees
    nothing. Word-agnostic on purpose, because the offending word changes with
    the model.

    Measured as a share, never a raw count, and only the worst offender is
    reported. A count alone fires on ordinary prose: this repo's own CLAUDE.md
    opens 5 of 87 paragraphs with "the", 5.7%, which means nothing, while the
    sample this check exists for opens 5 of 5 with "so". The 40% floor sits
    above the highest share measured on hand-written files here (fixes.md's
    structured Before/After pairs, 31%) and below the tic it targets.
    """
    opens = []
    for para in paragraphs(strip_markdown(text)):
        w = re.findall(r"[A-Za-z']+", para)
        if w:
            opens.append(w[0].lower())
    if len(opens) < 4:
        return []
    counts = {}
    for w in opens:
        counts[w] = counts.get(w, 0) + 1
    word, n = max(counts.items(), key=lambda kv: kv[1])
    if n < 3 or n / len(opens) < 0.4:
        return []
    return [{
        "check": "repeated_paragraph_opening",
        "severity": "structural",
        "detail": (
            f"{n} of {len(opens)} paragraphs ({n / len(opens):.0%}) open with "
            f"'{word}'. Vary the openings or merge the paragraphs."
        ),
        "context": "",
    }]


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


def check_contrast(text, words=0):
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

    weak = [m.group(0).strip() for m in re.finditer(WEAK_CONTRAST, text, re.I)]
    if len(weak) > 2:
        rate = f", {len(weak) / words * 1000:.1f} per 1,000 words" if words else ""
        findings.append({
            "check": "trailing_negation_density",
            "severity": "note",
            "detail": (
                f"{len(weak)} trailing negations ('X, not Y'){rate}. Weak alone, so "
                "this is a habit to notice, not a list of violations. Vary a few if "
                "they cluster in one passage."
            ),
            "context": "; ".join(weak[:4]),
        })
    return findings


#: Words title case leaves lowercase, so they say nothing either way.
TITLE_CASE_SKIP = {
    "a", "an", "and", "as", "at", "but", "by", "for", "from", "if", "in", "into",
    "nor", "of", "off", "on", "or", "out", "over", "per", "the", "to", "up",
    "via", "vs", "with", "without",
}


def check_heading_case(text):
    """Markdown headings capitalizing every major word.

    The rule is in references/patterns-full.md ("Title case headings") and the
    skill instructs a rewrite to fix it, but nothing measured it: a rewrite
    could turn a heading into Title Case and still score clean. Sentence case is
    the target; only the piece's own top-level title is allowed title case.

    An acronym, a single-word heading, and a heading of two major words are all
    left alone, because proper nouns are indistinguishable from title case at
    that length.

    An H1 reports as a note rather than a flag: patterns.md allows title case for
    "the piece's main title, if at all", so it is discouraged and not a
    violation. Subheadings have no such allowance.
    """
    findings = []
    for line in text.splitlines():
        m = re.match(r"^\s{0,3}(#{1,6})\s+(.*)", line)
        if not m:
            continue
        top = len(m.group(1)) == 1
        heading = re.sub(r"[`*_\[\]()]|\{[^}]*\}", "", m.group(2)).strip()
        heading = re.sub(r"^\d+[.)]\s*", "", heading)
        words = [w for w in re.findall(r"[A-Za-z][\w'-]*", heading)]
        major = [w for w in words[1:] if w.lower() not in TITLE_CASE_SKIP]
        if len(major) < 2:
            continue
        capped = [w for w in major if w[0].isupper() and not w.isupper()]
        if len(capped) >= 2 and len(capped) / len(major) >= 0.75:
            findings.append({
                "check": "title_case_heading",
                "severity": "note" if top else "structural",
                "detail": (
                    "Top-level title is in Title Case. patterns.md allows it "
                    "there \"if at all\"; sentence case is the default."
                    if top else
                    "Subheading is in Title Case. Use sentence case: capitalize "
                    "the first word and proper nouns only."
                ),
                "context": heading[:70],
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
    words = len(clean.split())
    # Vocabulary and dash checks read the raw document, so they need the
    # exemptions applied here rather than in strip_markdown.
    prose = mask_exempt(text)

    findings = []
    findings += check_em_dash_connectors(prose, words)
    findings += check_vocabulary(prose, short_mode)

    if short_mode:
        findings += check_short_form(clean, sentences)
    else:
        findings += check_sentence_variance(sentences)
        findings += check_opening(text, sentences)
        findings += check_closing_restatement(text, sentences)
        findings += check_repeated_openings(sentences)
        findings += check_repeated_paragraph_openings(text)
        findings += check_contrast(mask_exempt(clean), words)
        findings += check_participle_tails(clean)
        findings += check_heading_case(text)

    lengths = [len(s.split()) for s in sentences]
    stats = {
        "sentences": len(sentences),
        "words": words,
        "mean_sentence_length": round(statistics.mean(lengths), 1) if lengths else 0,
        "sentence_length_sd": round(statistics.pstdev(lengths), 1) if len(lengths) > 1 else 0,
        "structural_flags": sum(1 for f in findings if f["severity"] == "structural"),
        "vocabulary_flags": sum(1 for f in findings if f["severity"] == "vocabulary"),
        "notes": sum(1 for f in findings if f["severity"] == "note"),
    }
    # Capped checks allow one instance silently. Linting a site page by page
    # therefore grants one free pass per file and the pattern disappears.
    # Report totals so a run across many files still shows the habit.
    masked = mask_exempt(clean)
    contrast_total = sum(len(re.findall(p, masked, re.I)) for p, _ in CONTRAST_PATTERNS)
    contrast_total += len(re.findall(WEAK_CONTRAST, masked, re.I))
    tail_total = len([m for m in re.finditer(PARTICIPLE_TAIL, clean, re.I)
                      if not _in_gerund_list(clean, m)])
    stats["contrast_constructions"] = contrast_total
    stats["participle_tails"] = tail_total
    return findings, stats


def _force_utf8_output():
    """Findings quote em dashes and curly quotes.

    Without this a redirect on Windows encodes them cp1252 and the saved file is
    mojibake, which is how evidence gets collected and then misread.
    """
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")


def _read_input(path):
    """The document's text, or None when it could not be read."""
    if path == "-":
        return sys.stdin.read()
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except OSError as exc:
        print(f"lint.py: cannot read {path}: {exc.strerror}", file=sys.stderr)
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path", help="file to lint, or - for stdin")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--short", action="store_true",
                    help="short-form mode for chat, email, push")
    ap.add_argument("--strict", action="store_true",
                    help="exit 1 on vocabulary flags too, not just structural")
    args = ap.parse_args()

    _force_utf8_output()
    text = _read_input(args.path)
    if text is None:
        return 2

    findings, stats = lint(text, args.short)
    failed = stats["structural_flags"] or (args.strict and stats["vocabulary_flags"])

    if args.json:
        print(json.dumps({"stats": stats, "findings": findings}, indent=2))
        return 1 if failed else 0

    print(f"\n{stats['words']} words, {stats['sentences']} sentences")
    print(f"Mean sentence length {stats['mean_sentence_length']}, "
          f"standard deviation {stats['sentence_length_sd']}")
    print(f"Structural flags: {stats['structural_flags']}   "
          f"Vocabulary flags: {stats['vocabulary_flags']}   "
          f"Notes: {stats['notes']}")
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

    for severity in ("structural", "vocabulary", "note"):
        group = [f for f in findings if f["severity"] == severity]
        if not group:
            continue
        label = "NOTES (weak alone, need corroboration)" if severity == "note" \
            else severity.upper()
        print(f"--- {label} ({len(group)}) ---")
        for f in group:
            print(f"  [{f['check']}] {f['detail']}")
            if f["context"]:
                print(f"      > {f['context']}")
        print()

    print("Repairs for each flag type are in references/fixes.md")
    print("Whether a flag earns an edit: references/patterns.md, "
          "'Before you act on a pattern'\n")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
