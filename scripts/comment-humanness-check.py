"""
ClaudeBoost comment humanness check — PostToolUse on Edit/Write.

Scans newly written code for AI-sounding comment patterns and nudges
Claude to revise before moving on. Non-blocking (exit 0 always) — this
is a quality nudge, not a hard gate.

Patterns that trigger a nudge (research-backed, arxiv 2401.06461 / 2406.15583 / 2509.18880):
  1. Formal opener:  "// This [function|method|class|variable|code]"
  2. Complete-sentence uniformity: 3+ comments all ending with "."
  3. Spacing uniformity: 5+ comments all using "// " — zero variation
  4. Structural uniformity: 4+ consecutive comments within 5 chars of same length
  5. Banned vocab inside a comment (from human-voice.xml list)

Only fires when 3+ comment lines exist in the new content — not worth
nudging on a single-line change.
"""
from __future__ import annotations

import json
import re
import sys
from typing import NamedTuple


# Banned words from human-voice.xml — if these appear inside a comment, flag it
BANNED_IN_COMMENTS = (
    "facilitates", "seamless", "leverage", "leverages", "leveraging",
    "utilize", "utilizes", "utilizing", "robust", "comprehensive",
    "pivotal", "nuanced", "harness", "bolster", "intricate",
    "transformative", "paradigm", "holistic", "empower", "empowers",
    "it is worth noting", "it's worth noting", "please note",
    "this function", "this method", "this class", "this variable",
    "this code", "this module", "the purpose of",
)

# Comment patterns to extract — // and # style
# Skips shebangs (#!) and URLs (http://)
_COMMENT_RE = re.compile(
    r"^\s*(?://+\s*.*|#(?!!)[^\s].*|#\s+.*)$",
    re.MULTILINE,
)

# Formal opener: "// This [noun]" or "# This [noun]"
_FORMAL_OPENER_RE = re.compile(
    r"^\s*(?://+|#+)\s+[Tt]his\s+(?:function|method|class|variable|code|module|script|file)\b",
)


class Finding(NamedTuple):
    rule: str
    detail: str


def extract_comment_lines(text: str) -> list[str]:
    """Pull out lines that are pure comment lines (whole line is a comment)."""
    lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("//") or (stripped.startswith("#") and not stripped.startswith("#!")):
            lines.append(stripped)
    return lines


def check_formal_opener(comments: list[str]) -> Finding | None:
    hits = [c for c in comments if _FORMAL_OPENER_RE.match(c)]
    if hits:
        return Finding(
            "formal-opener",
            f"Comment starts with 'This [noun]' (AI tell): {hits[0]!r}",
        )
    return None


def check_complete_sentence_uniformity(comments: list[str]) -> Finding | None:
    """3+ comments all ending with '.' = complete-sentence pattern."""
    if len(comments) < 3:
        return None
    ending_with_dot = [c for c in comments if c.rstrip().endswith(".")]
    if len(ending_with_dot) >= 3 and len(ending_with_dot) >= len(comments) * 0.7:
        return Finding(
            "complete-sentence-uniformity",
            f"{len(ending_with_dot)}/{len(comments)} comments end with '.' — reads like AI prose, not dev notes",
        )
    return None


def check_spacing_uniformity(comments: list[str]) -> Finding | None:
    """5+ comments all '// word' with no variation — AI always uses exactly one space."""
    if len(comments) < 5:
        return None
    single_space = [c for c in comments if re.match(r"^//\s\S", c)]
    no_space = [c for c in comments if re.match(r"^//\S", c)]
    double_space = [c for c in comments if re.match(r"^//\s{2,}", c)]
    # If everything is exactly single-space and nothing varies, flag it
    if len(single_space) == len(comments) and not no_space and not double_space:
        return Finding(
            "spacing-uniformity",
            f"All {len(comments)} comments use '// ' (one space, always). "
            "Real devs mix //word and // word — vary it a little.",
        )
    return None


def check_structural_uniformity(comments: list[str]) -> Finding | None:
    """4+ consecutive comments within 5 chars of the same length = rhythm tell."""
    if len(comments) < 4:
        return None
    # Slide a window of 4
    for i in range(len(comments) - 3):
        window = comments[i:i+4]
        lengths = [len(c) for c in window]
        if max(lengths) - min(lengths) <= 5:
            return Finding(
                "structural-uniformity",
                f"4 consecutive comments all {min(lengths)}-{max(lengths)} chars long — "
                "identical rhythm is an AI signal. Mix short fragments with fuller thoughts.",
            )
    return None


def check_banned_vocab(comments: list[str]) -> Finding | None:
    for comment in comments:
        lower = comment.lower()
        for phrase in BANNED_IN_COMMENTS:
            if phrase in lower:
                return Finding(
                    "banned-vocab",
                    f"Banned phrase {phrase!r} in comment: {comment!r}",
                )
    return None


def get_new_content(payload: dict) -> str:
    """Extract the newly written text from Edit or Write tool input."""
    tool_input = payload.get("tool_input") or {}
    # Edit: new_string is what was inserted
    if "new_string" in tool_input:
        return tool_input["new_string"]
    # Write: content is the full file content
    if "content" in tool_input:
        return tool_input["content"]
    return ""


def main() -> int:
    raw = sys.stdin.read() if not sys.stdin.isatty() else ""
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except Exception:
        return 0

    content = get_new_content(payload)
    if not content:
        return 0

    comments = extract_comment_lines(content)
    if len(comments) < 3:
        # Not enough comments to pattern-match — skip
        return 0

    findings: list[Finding] = []
    for check in [
        check_formal_opener,
        check_complete_sentence_uniformity,
        check_spacing_uniformity,
        check_structural_uniformity,
        check_banned_vocab,
    ]:
        result = check(comments)
        if result:
            findings.append(result)

    if not findings:
        return 0

    lines = ["[comment-humanness] Comments may read as AI-generated:"]
    for f in findings:
        lines.append(f"  [{f.rule}] {f.detail}")
    lines.append("")
    lines.append("Review the comments against human-voice.xml rules C1-C7:")
    lines.append("  - Fragments over complete sentences (C1)")
    lines.append("  - Vary structure across consecutive comments (C2)")
    lines.append("  - Keep polite skepticism where honest (C3)")
    lines.append("  - Mix '//word' and '// word' spacing (C4)")

    print("\n".join(lines), file=sys.stderr)
    return 0  # nudge only, never blocks


if __name__ == "__main__":
    sys.exit(main())
