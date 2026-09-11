"""The human-voice skill's own cross-references have to resolve.

The skill shipped for months with `references/patterns.md` cut off mid-sentence
at exactly 40,000 characters, the default `max_chars` of
`server/github_search.py:github_fetch_file`. Whoever cloned it pasted a
fetch-capped response, and the last 54,568 characters of upstream never arrived.

Nothing noticed, for two reasons that this file closes:

* `.gitignore` ignored every `references/` directory repo-wide, so the file had
  no git history and no diff ever showed the cut. That negation is fixed
  separately; a test is still needed for reference files in directories that
  stay ignored, and for a corruption committed alongside the un-ignoring.
* The damage was invisible from SKILL.md. It kept naming eleven `--voice` and
  `--context` values, five P1 patterns, a tolerance matrix and a confidence
  calibration section, all of which lived in the missing tail. A skill that
  names a rule it cannot load is worse than one that never mentioned it: the
  model is told the rule exists and gets no text for it.

So four things are pinned, each one a real defect that shipped:

1. no reference file is truncated
2. every `--voice` and `--context` value has a profile definition
3. every `lint.py` check name has a repair entry in `fixes.md`
4. every word the blocking Stop hook bans appears in the skill's own catalog

Truth comes from the real files and from `lint.py`'s real source, never from a
list mirrored into this test, the same approach as test_skill_rag_routes.py.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SKILL = REPO / "clean-rag" / "portable" / "skills" / "human-voice"
REFS = SKILL / "references"
LINT = SKILL / "scripts" / "lint.py"
GUARD = REPO / "scripts" / "human-voice-guard.py"

VOICES = ("casual", "professional", "technical", "warm", "blunt")
CONTEXTS = ("linkedin", "blog", "technical-blog", "investor-email", "docs", "casual")

#: A markdown file cut mid-sentence ends on a word that cannot end one. Cheap,
#: and it catches the real failure: the shipped file ended "Use sentence case for".
DANGLING_TAIL = {
    "a", "an", "and", "are", "as", "at", "be", "but", "by", "for", "from",
    "in", "into", "is", "of", "on", "or", "than", "that", "the", "their",
    "then", "these", "this", "to", "was", "were", "which", "with",
}


def reference_files():
    return sorted(REFS.glob("*.md")) + [SKILL / "SKILL.md"]


def test_skill_layout_is_present():
    """Guard the paths this whole file depends on, so a rename fails loudly."""
    assert SKILL.is_dir(), f"skill directory missing: {SKILL}"
    assert LINT.is_file(), f"scorer missing: {LINT}"
    for name in ("patterns.md", "patterns-full.md", "profiles.md", "fixes.md"):
        assert (REFS / name).is_file(), f"reference missing: {name}"


@pytest.mark.parametrize("path", reference_files(), ids=lambda p: p.name)
def test_reference_file_is_not_truncated(path: Path):
    text = path.read_text(encoding="utf-8")

    assert "[truncated]" not in text, (
        f"{path.name} contains a truncation marker. A fetch was pasted in whole, "
        "cap and all. Re-fetch the file with a max_chars above its real size: "
        "github_fetch_file defaults to 40,000 and reports truncated=True."
    )

    stripped = text.rstrip()
    assert stripped, f"{path.name} is empty"

    last = stripped.splitlines()[-1].strip()
    final_word = re.sub(r"[^\w'-]+$", "", last.split()[-1]) if last.split() else ""
    assert final_word.lower() not in DANGLING_TAIL, (
        f"{path.name} ends mid-sentence on {final_word!r}. Last line: {last[:120]!r}"
    )


@pytest.mark.parametrize("voice", VOICES)
def test_every_voice_value_is_defined(voice: str):
    prof = (REFS / "profiles.md").read_text(encoding="utf-8")
    assert re.search(r"\*\*`" + re.escape(voice) + r"`\*\*\s*[—-]", prof), (
        f"SKILL.md offers --voice {voice} but profiles.md defines no such profile"
    )


@pytest.mark.parametrize("context", CONTEXTS)
def test_every_context_value_is_defined(context: str):
    prof = (REFS / "profiles.md").read_text(encoding="utf-8")
    assert re.search(r"\*\*`" + re.escape(context) + r"`\*\*\s*[—-]", prof), (
        f"SKILL.md offers --context {context} but profiles.md defines no such profile"
    )


def lint_check_names():
    """The check names lint.py really emits, read out of its source."""
    names = set(re.findall(r'"check":\s*"(\w+)"', LINT.read_text(encoding="utf-8")))
    assert names, "parsed no check names out of lint.py"
    return sorted(names)


def test_every_lint_check_has_a_repair_entry():
    """lint.py's own footer points at fixes.md, so every flag needs an entry."""
    fixes = (REFS / "fixes.md").read_text(encoding="utf-8")
    headings = "\n".join(ln for ln in fixes.splitlines() if ln.startswith("##"))
    missing = [c for c in lint_check_names() if not re.search(r"\b" + re.escape(c) + r"\b", headings)]
    assert not missing, (
        "lint.py emits these checks with no repair entry in fixes.md, which is "
        f"the file its own output tells the reader to open: {missing}"
    )


def guard_banned_words():
    """The blocking hook's word list, read out of its source."""
    src = GUARD.read_text(encoding="utf-8")
    block = src.split("BANNED_WORDS: set[str] = {", 1)[1].split("}", 1)[0]
    words = set(re.findall(r'"([a-z\' -]+)"', block))
    assert words, "parsed no banned words out of human-voice-guard.py"
    return words


@pytest.mark.skipif(not GUARD.is_file(), reason="hook not installed in this checkout")
def test_hook_banned_words_are_covered_by_the_catalog():
    """The hook blocks and the skill only nudges, so the hook's list is the floor.

    A word that blocks an assistant message has to be in the skill's own tier,
    or a message gets refused for a word the skill never raised. Three words
    were missing when this was first measured; the restore covered
    "revolutionary" and the other two were added to Tier 1A by hand.
    """
    catalog = "\n".join(
        p.read_text(encoding="utf-8") for p in reference_files()
    ).lower()

    def covered(word: str) -> bool:
        if re.search(r"\b" + re.escape(word), catalog):
            return True
        # "delving" is covered by "delve", "synergies" by "synergy".
        return any(len(word) > n and re.search(r"\b" + re.escape(word[:n]), catalog)
                   for n in (5, 4))

    missing = sorted(w for w in guard_banned_words() if not covered(w))
    assert not missing, (
        "scripts/human-voice-guard.py blocks these words and the skill's catalog "
        f"never mentions them, so a message is refused with no rule to point at: {missing}"
    )
