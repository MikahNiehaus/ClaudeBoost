"""
ClaudeBoost comment humanness check, PostToolUse on Edit/Write/MultiEdit.

EXIT CODES:
  0 = nudge only (style issues printed to stderr)
  2 = BLOCK (dashes found, must rewrite before continuing)

For every blocked comment the hook prints a rewrite form:

  COMMENT 1 of N
  Original : // sets the non-blocking value
  Issue    : hyphenated compound 'non-blocking'
  Rewrite  : // sets the not blocking value

Claude must fill in each Rewrite line (auto-suggested where mechanical,
template placeholder where judgment is needed) and rewrite the code before
continuing. The user sees this output so they know what is being changed.

DASH RULE (hard block, exit 2):
  Any dash in any comment is blocked.
  Catches: em-dash, en-dash, figure dash, spaced hyphen separator,
  hyphenated compound words like non-blocking or hard-coded.
  Exception: dashes inside backtick-quoted identifiers, file paths,
  and negative numbers are not flagged.

NUDGE PATTERNS (exit 0, stderr):
  1. Formal opener: "// This [function|method|class|variable|code]"
  2. Complete sentence uniformity: 3+ comments ending with "."
  3. Spacing uniformity: 5+ comments all using "// " with no variation
  4. Structural uniformity: 4+ consecutive comments within 5 chars of same length
  5. Banned vocab (from human-voice.xml and CLAUDE.md)

INLINE COMMENTS:
  Checks both standalone comment lines and inline comments on code lines.
  Triple-quoted string content is skipped.
"""
from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass


BANNED_IN_COMMENTS = (
    "facilitates", "seamless", "leverage", "leverages", "leveraging",
    "utilize", "utilizes", "utilizing", "robust", "comprehensive",
    "pivotal", "nuanced", "harness", "bolster", "intricate",
    "transformative", "paradigm", "holistic", "empower", "empowers",
    "it is worth noting", "it's worth noting", "please note",
    "this function", "this method", "this class", "this variable",
    "this code", "this module", "the purpose of",
)

BANNED_REPLACEMENTS = {
    "facilitates": "handles",
    "seamless": "smooth",
    "leverage": "use",
    "leverages": "uses",
    "leveraging": "using",
    "utilize": "use",
    "utilizes": "uses",
    "utilizing": "using",
    "robust": "solid",
    "comprehensive": "full",
    "pivotal": "key",
    "nuanced": "subtle",
    "harness": "use",
    "bolster": "improve",
    "intricate": "complex",
    "transformative": "impactful",
    "paradigm": "pattern",
    "holistic": "overall",
    "empower": "let",
    "empowers": "lets",
}

_FORMAL_OPENER_RE = re.compile(
    r"^((?://+|#+)\s+)[Tt]his\s+(?:function|method|class|variable|code|module|script|file)\s*",
)

_UNICODE_DASHES = re.compile(r"[\u2014\u2013\u2012]")
_SPACED_HYPHEN_SEP = re.compile(r" - (?![->\d])")
_BACKTICK_RE = re.compile(r"`[^`]*`")

_COMPOUND_PREFIX = re.compile(
    r"\b(non|well|hard|step|pre|auto|type|thread|lazy|self|read|write|compile|run|long|short|high|low|two|one|event|promise|callback|value|error|zero|null|empty)-([a-z]+)",
    re.IGNORECASE,
)

# Words that join as one when hyphen is removed
_JOIN_PREFIXES = {"hard", "pre", "auto", "type", "lazy", "compile"}
# Words that stay as two when hyphen is removed
_SPACE_PREFIXES = {"non", "well", "step", "thread", "self", "read", "write",
                   "run", "long", "short", "high", "low", "two", "one",
                   "event", "promise", "callback", "value", "error", "zero",
                   "null", "empty"}


@dataclass
class BlockFinding:
    comment: str
    issue: str
    suggestion: str


def _suggest_compound_fix(comment: str) -> str:
    """Auto-generate a rewrite with hyphenated compounds removed."""
    def replace_match(m: re.Match) -> str:
        prefix = m.group(1).lower()
        suffix = m.group(2).lower()
        if prefix == "non":
            return f"not {suffix}"
        if prefix == "step" and suffix == "by":
            return "step by step"
        if prefix in _JOIN_PREFIXES:
            return prefix + suffix
        return f"{prefix} {suffix}"

    return _COMPOUND_PREFIX.sub(replace_match, comment)


def _suggest_unicode_dash_fix(comment: str) -> str:
    return _UNICODE_DASHES.sub(",", comment)


def _suggest_spaced_hyphen_fix(comment: str) -> str:
    return _SPACED_HYPHEN_SEP.sub(", ", comment)


def extract_comment_texts(text: str) -> list[str]:
    """Return comment text from standalone and inline comments.

    Skips triple-quoted string content so docstring examples are not flagged.
    """
    texts: list[str] = []
    in_triple = False
    triple_char = ""

    for line in text.splitlines():
        stripped = line.strip()

        if not in_triple:
            for marker in ('"""', "'''"):
                count = stripped.count(marker)
                if count == 1:
                    in_triple = True
                    triple_char = marker
                    break
                if count >= 2:
                    break
        else:
            if triple_char in stripped:
                in_triple = False
            continue

        if stripped.startswith("//"):
            texts.append(stripped)
            continue

        if stripped.startswith("#") and not stripped.startswith("#!"):
            texts.append(stripped)
            continue

        idx = stripped.find("//")
        if idx > 0:
            before = stripped[:idx]
            if before.rstrip().endswith(":") or before.rstrip().endswith("/"):
                continue
            q_double = before.count('"') - before.count('\\"')
            q_single = before.count("'") - before.count("\\'")
            if q_double % 2 == 0 and q_single % 2 == 0:
                texts.append("//" + stripped[idx + 2:])

    return texts


def check_dashes(comments: list[str]) -> list[BlockFinding]:
    findings: list[BlockFinding] = []

    for comment in comments:
        clean = _BACKTICK_RE.sub("", comment)

        if _UNICODE_DASHES.search(clean):
            suggestion = _suggest_unicode_dash_fix(comment)
            findings.append(BlockFinding(
                comment=comment,
                issue="unicode dash (em/en/figure dash)",
                suggestion=suggestion,
            ))
            continue

        if _SPACED_HYPHEN_SEP.search(clean):
            suggestion = _suggest_spaced_hyphen_fix(comment)
            findings.append(BlockFinding(
                comment=comment,
                issue="spaced hyphen used as separator",
                suggestion=suggestion,
            ))
            continue

        m = _COMPOUND_PREFIX.search(clean)
        if m:
            nearby = clean[max(0, m.start() - 1):m.end() + 5]
            if "." not in nearby and "/" not in nearby and "\\" not in nearby:
                suggestion = _suggest_compound_fix(comment)
                findings.append(BlockFinding(
                    comment=comment,
                    issue=f"hyphenated compound '{m.group(0)}'",
                    suggestion=suggestion,
                ))

    return findings


def _suggest_formal_opener_fix(comment: str) -> str:
    m = _FORMAL_OPENER_RE.match(comment)
    if not m:
        return comment
    marker = m.group(1)
    rest = comment[m.end():].strip()
    if rest:
        return f"{marker.rstrip()} {rest}"
    return f"{marker.rstrip()} [REWRITE: describe what it does or why it exists]"


def _suggest_banned_vocab_fix(comment: str) -> str:
    result = comment
    lower = comment.lower()
    for phrase, replacement in BANNED_REPLACEMENTS.items():
        if phrase in lower:
            result = re.sub(re.escape(phrase), replacement, result, flags=re.IGNORECASE)
    return result


def check_formal_opener(comments: list[str]) -> list[tuple[str, str]]:
    out = []
    for c in comments:
        if _FORMAL_OPENER_RE.match(c):
            out.append((c, _suggest_formal_opener_fix(c)))
    return out


def check_complete_sentence_uniformity(comments: list[str]) -> str | None:
    if len(comments) < 3:
        return None
    ending_with_dot = [c for c in comments if c.rstrip().endswith(".")]
    if len(ending_with_dot) >= 3 and len(ending_with_dot) >= len(comments) * 0.7:
        return f"{len(ending_with_dot)}/{len(comments)} comments end with '.'"
    return None


def check_spacing_uniformity(comments: list[str]) -> str | None:
    if len(comments) < 5:
        return None
    single = [c for c in comments if re.match(r"^//\s\S", c)]
    no_sp = [c for c in comments if re.match(r"^//\S", c)]
    double = [c for c in comments if re.match(r"^//\s{2,}", c)]
    if len(single) == len(comments) and not no_sp and not double:
        return f"All {len(comments)} comments use '// ' (one space, no variation)"
    return None


def check_structural_uniformity(comments: list[str]) -> str | None:
    if len(comments) < 4:
        return None
    for i in range(len(comments) - 3):
        window = comments[i:i + 4]
        lengths = [len(c) for c in window]
        if max(lengths) - min(lengths) <= 5:
            return f"4 consecutive comments all {min(lengths)}-{max(lengths)} chars (identical rhythm)"
    return None


def check_banned_vocab(comments: list[str]) -> list[tuple[str, str]]:
    out = []
    for comment in comments:
        lower = comment.lower()
        for phrase in BANNED_IN_COMMENTS:
            if phrase in lower:
                suggestion = _suggest_banned_vocab_fix(comment)
                out.append((comment, suggestion))
                break
    return out


def get_new_content(payload: dict) -> str:
    tool_input = payload.get("tool_input") or {}
    if "new_string" in tool_input:
        return tool_input["new_string"]
    if "content" in tool_input:
        return tool_input["content"]
    if "edits" in tool_input:
        parts = [e.get("new_string", "") for e in tool_input.get("edits", []) if isinstance(e, dict)]
        return "\n".join(parts)
    return ""


def _format_form_block(n: int, total: int, original: str, issue: str, suggestion: str) -> str:
    w = 60
    lines = [
        f"  COMMENT {n} of {total}",
        f"  {'Original':<10}: {original}",
        f"  {'Issue':<10}: {issue}",
        f"  {'Rewrite':<10}: {suggestion}",
    ]
    return "\n".join(lines)


def main() -> int:
    raw = sys.stdin.read() if not sys.stdin.isatty() else ""
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except Exception:
        return 0

    content = get_new_content(payload)
    if not content:
        return 0

    comments = extract_comment_texts(content)
    if not comments:
        return 0

    dash_findings = check_dashes(comments)
    if dash_findings:
        total = len(dash_findings)
        lines = [
            f"BLOCKED: {total} comment(s) contain dashes. Fill in each Rewrite below, then redo the edit.",
            "",
            "Human Voice Standard (CLAUDE.md): no dashes of any kind, even when grammatically correct.",
            "",
        ]
        for i, f in enumerate(dash_findings, 1):
            lines.append(_format_form_block(i, total, f.comment, f.issue, f.suggestion))
            lines.append("")
        lines += [
            "Rules for the Rewrite field:",
            "  Hyphenated compound: remove the hyphen ('non-blocking' becomes 'not blocking')",
            "  Spaced separator: use a comma or colon instead of ' - '",
            "  Unicode dash: use a comma or period",
            "  If the auto-suggestion above is wrong, write your own. No dashes allowed in the result.",
        ]
        print("\n".join(lines), file=sys.stderr)
        return 2

    if len(comments) < 3:
        return 0

    nudge_lines: list[str] = []

    formal = check_formal_opener(comments)
    if formal:
        nudge_lines.append("[formal-opener] Comments starting with 'This [noun]':")
        for i, (orig, sug) in enumerate(formal, 1):
            nudge_lines.append(f"  COMMENT {i}")
            nudge_lines.append(f"  {'Original':<10}: {orig}")
            nudge_lines.append(f"  {'Rewrite':<10}: {sug}")
            nudge_lines.append("")

    banned = check_banned_vocab(comments)
    if banned:
        nudge_lines.append("[banned-vocab] Comments with banned vocabulary:")
        for i, (orig, sug) in enumerate(banned, 1):
            nudge_lines.append(f"  COMMENT {i}")
            nudge_lines.append(f"  {'Original':<10}: {orig}")
            nudge_lines.append(f"  {'Rewrite':<10}: {sug}")
            nudge_lines.append("")

    for label, msg in [
        ("complete-sentence-uniformity", check_complete_sentence_uniformity(comments)),
        ("spacing-uniformity", check_spacing_uniformity(comments)),
        ("structural-uniformity", check_structural_uniformity(comments)),
    ]:
        if msg:
            nudge_lines.append(f"[{label}] {msg}")
            nudge_lines.append("  No per-comment form needed. Vary structure naturally.")
            nudge_lines.append("")

    if nudge_lines:
        out = ["[comment-humanness] Style issues found. Review and rewrite where needed.", ""]
        out += nudge_lines
        out += [
            "Human Voice Standard (CLAUDE.md):",
            "  Fragments over complete sentences. Say WHY not WHAT.",
            "  Non-formal, concise, polite, professional.",
        ]
        print("\n".join(out), file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
