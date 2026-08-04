"""Adversarial tests for swiper.md changes.

Tests:
1. github-file curl fields match server (owner/repo/path)
2. stackoverflow-search curl fields match server (query)
3. MATCH_STRATEGY is exactly two values, no adapt
4. REQUIRED_ADAPTATIONS position (inside clone-and-patch, not top-level)
5. language-mismatch text says pattern-only and still quotes the reference
6. stackoverflow-search ordering in swiper vs research-routing SKILL.md
7. REQUIRED_ADAPTATIONS: none does not look like a parseable stamp
8. Tension check: language-mismatch vs "even when different framework or scale"
"""
import re
from pathlib import Path

SWIPER_PATH = Path(__file__).resolve().parent.parent / "clean-rag/portable/agents/swiper.md"
SKILL_PATH = Path(__file__).resolve().parent.parent / "clean-rag/portable/skills/research-routing/SKILL.md"
ROOT_CLAUDE_PATH = Path(__file__).resolve().parent.parent / "CLAUDE.md"
PORTABLE_CLAUDE_PATH = Path(__file__).resolve().parent.parent / "clean-rag/portable/CLAUDE.md"
CANONICAL_CLAUDE_PATH = Path(__file__).resolve().parent.parent / "clean-rag/CLAUDE.md"

swiper = SWIPER_PATH.read_text(encoding="utf-8")
skill = SKILL_PATH.read_text(encoding="utf-8")
root_claude = ROOT_CLAUDE_PATH.read_text(encoding="utf-8")
portable_claude = PORTABLE_CLAUDE_PATH.read_text(encoding="utf-8")
canonical_claude = CANONICAL_CLAUDE_PATH.read_text(encoding="utf-8")


# ── 1. github-file curl example fields ──────────────────────────────────────

def _find_curl_block(text: str, endpoint: str) -> str:
    """Return the content of the first fenced block that contains the given endpoint URL."""
    # Find all fenced blocks (``` ... ```)
    fence_re = re.compile(r'```[^\n]*\n(.*?)```', re.DOTALL)
    for m in fence_re.finditer(text):
        block = m.group(1)
        if endpoint in block and "curl" in block:
            return block
    return ""


def test_github_file_curl_has_owner():
    """github-file curl must include 'owner' field — server requires it (app.py:575-579)."""
    block = _find_curl_block(swiper, "/github-file")
    assert block, "Could not find a curl block containing /github-file"
    assert '"owner"' in block, (
        f"github-file curl block missing 'owner' field. Block:\n{block}"
    )


def test_github_file_curl_has_repo():
    """github-file curl must include 'repo' field — server requires it (app.py:575-579)."""
    block = _find_curl_block(swiper, "/github-file")
    assert block, "Could not find a curl block containing /github-file"
    assert '"repo"' in block, (
        f"github-file curl block missing 'repo' field. Block:\n{block}"
    )


def test_github_file_curl_has_path():
    """github-file curl must include 'path' field — server requires it (app.py:575-579)."""
    block = _find_curl_block(swiper, "/github-file")
    assert block, "Could not find a curl block containing /github-file"
    assert '"path"' in block, (
        f"github-file curl block missing 'path' field. Block:\n{block}"
    )


def test_github_file_curl_does_not_use_wrong_fields():
    """github-file must NOT use 'url', 'file', 'filepath' — wrong field names return silent 400."""
    block = _find_curl_block(swiper, "/github-file")
    assert block, "Could not find a curl block containing /github-file"
    bad_fields = ['"url"', '"file"', '"filepath"', '"filename"']
    for bad in bad_fields:
        assert bad not in block, (
            f"github-file curl block uses wrong field {bad!r}. Block:\n{block}"
        )


# ── 2. stackoverflow-search curl example fields ──────────────────────────────

def test_stackoverflow_search_curl_has_query():
    """stackoverflow-search curl must include 'query' field — server requires it."""
    m = re.search(r'stackoverflow-search.*?```(.*?)```', swiper, re.DOTALL)
    assert m, "Could not find stackoverflow-search curl block"
    block = m.group(1)
    assert '"query"' in block, (
        f"stackoverflow-search curl block missing 'query' field. Block:\n{block}"
    )


def test_stackoverflow_search_curl_does_not_use_wrong_fields():
    """stackoverflow-search must NOT use 'search', 'q', or 'text' (wrong field names return empty/400)."""
    m = re.search(r'stackoverflow-search.*?```(.*?)```', swiper, re.DOTALL)
    assert m, "Could not find stackoverflow-search curl block"
    block = m.group(1)
    # Only 'query' is valid per server line 602: query = (body.get("query") or "").strip()
    bad_fields = ['"q"', '"search"', '"text"', '"term"']
    for bad in bad_fields:
        assert bad not in block, (
            f"stackoverflow-search curl block uses wrong field {bad!r}. Block:\n{block}"
        )


# ── 3. MATCH_STRATEGY two value enum, no adapt ──────────────────────────────

def test_match_strategy_line_is_two_value_only():
    """MATCH_STRATEGY line must show exactly clone-and-patch | pattern-only, no adapt."""
    # Anchor to start of line so we hit the template declaration, not a prose mention
    m = re.search(r'^MATCH_STRATEGY:.*', swiper, re.MULTILINE)
    assert m, "No MATCH_STRATEGY: line at start of line in swiper.md"
    line = m.group()
    assert "adapt" not in line.lower(), (
        f"MATCH_STRATEGY line contains 'adapt': {line!r}"
    )
    assert "clone-and-patch" in line, f"MATCH_STRATEGY line missing clone-and-patch: {line!r}"
    assert "pattern-only" in line, f"MATCH_STRATEGY line missing pattern-only: {line!r}"


def test_no_adapt_tier_in_swiper_except_historical_note():
    """'adapt' as a standalone word in swiper.md should only appear in the historical explanation."""
    # Use word-boundary match so REQUIRED_ADAPTATIONS does not trigger
    adapt_lines = [
        (i + 1, line.strip())
        for i, line in enumerate(swiper.splitlines())
        if re.search(r'\badapt\b', line, re.IGNORECASE)
    ]
    for lineno, line in adapt_lines:
        # Acceptable: the historical note explaining why 'adapt' was removed
        acceptable = (
            "adapt` tier" in line
            or "adapt` and" in line
            or "adapt tier" in line.lower()
            or "no `adapt`" in line
        )
        assert acceptable, (
            f"swiper.md line {lineno} uses 'adapt' as a word outside the historical note: {line!r}"
        )


def test_no_adapt_in_claude_md_files():
    """CLAUDE.md and clean-rag/portable/CLAUDE.md must not list 'adapt' as a strategy (only in 'no adapt tier' note)."""
    for name, text in [("CLAUDE.md", root_claude), ("portable/CLAUDE.md", portable_claude)]:
        for i, line in enumerate(text.splitlines(), 1):
            if "adapt" in line.lower():
                # Acceptable: "There is no `adapt` tier"
                assert "no `adapt` tier" in line or "no adapt tier" in line.lower(), (
                    f"{name} line {i} mentions 'adapt' in unexpected context: {line!r}"
                )


# ── 4. REQUIRED_ADAPTATIONS position ────────────────────────────────────────

def test_required_adaptations_is_inside_clone_and_patch_section():
    """REQUIRED_ADAPTATIONS block must appear AFTER the clone-and-patch description, not before pattern-only."""
    cp_pos = swiper.find("**`clone-and-patch`**")
    po_pos = swiper.find("**`pattern-only`**")
    ra_pos = swiper.find("REQUIRED_ADAPTATIONS:")
    assert cp_pos != -1, "clone-and-patch section not found"
    assert po_pos != -1, "pattern-only section not found"
    assert ra_pos != -1, "REQUIRED_ADAPTATIONS: not found"
    assert cp_pos < ra_pos < po_pos, (
        f"REQUIRED_ADAPTATIONS (pos {ra_pos}) must be between clone-and-patch "
        f"(pos {cp_pos}) and pattern-only (pos {po_pos})"
    )


def test_required_adaptations_is_not_a_top_level_section():
    """REQUIRED_ADAPTATIONS must not be a top-level ## heading."""
    for i, line in enumerate(swiper.splitlines(), 1):
        assert not re.match(r'^#{1,3}\s+REQUIRED_ADAPTATIONS', line), (
            f"swiper.md line {i}: REQUIRED_ADAPTATIONS is a heading, should be inline: {line!r}"
        )


# ── 5. Language-mismatch still says clone-and-patch and quotes the reference ─

def test_language_mismatch_forces_pattern_only():
    """Language mismatch text must say it forces pattern-only."""
    m = re.search(r'[Ll]anguage mismatch.*?pattern-only', swiper, re.DOTALL)
    assert m, (
        "Language mismatch text does not mention pattern-only. "
        "Correctness property: language mismatch forces pattern-only."
    )


def test_language_mismatch_still_says_cite_and_quote():
    """Even on language mismatch (pattern-only), swiper must still cite and quote the reference."""
    # Find the language mismatch paragraph
    m = re.search(r'[Ll]anguage mismatch(.*?)(?:\n\n|\Z)', swiper, re.DOTALL)
    assert m, "Language mismatch paragraph not found"
    para = m.group(1)
    assert "quote" in para or "cite" in para, (
        "Language mismatch paragraph does not instruct to still cite/quote the reference. "
        f"Paragraph: {para!r}"
    )


# ── 6. stackoverflow-search ordering: swiper vs research-routing SKILL ───────

def test_stackoverflow_ordering_not_contradicted_by_skill():
    """
    swiper now says 'reach for stackoverflow-search first' for SO answers.
    research-routing SKILL.md says SO is for 'error message, or the few lines that do X'.
    These must not conflict: swiper's ordering (SO-first, WebFetch-second) must be
    consistent with the skill's routing rule.
    """
    # Swiper says: use stackoverflow-search first, then WebFetch for specific URLs
    assert "stackoverflow-search" in swiper, "stackoverflow-search endpoint not mentioned in swiper"
    # The skill says SO is the right door for error messages and code snippets
    assert "stackoverflow-search" in skill, "stackoverflow-search not in research-routing SKILL"

    # Check swiper doesn't contradict the skill by reversing the order globally
    swiper_so_section = re.search(
        r'\*StackOverflow\*:(.*?)(?=\n\nThen,|\Z)',
        swiper, re.DOTALL
    )
    assert swiper_so_section, "Cannot find StackOverflow section in swiper"
    so_text = swiper_so_section.group(1)

    # swiper should say 'reach for stackoverflow-search first'
    assert "stackoverflow-search first" in so_text or "reach for `stackoverflow-search` first" in so_text, (
        "Swiper SO section doesn't clearly state stackoverflow-search as first choice. "
        f"Section: {so_text[:300]!r}"
    )


# ── 7. REQUIRED_ADAPTATIONS: none — stamp confusion risk ────────────────────

def test_required_adaptations_none_format_not_confused_with_covers_stamp():
    """
    'REQUIRED_ADAPTATIONS: none' must not match the COVERS: regex used by research-record.py.
    The hook parses lines starting with COVERS: (case-insensitive). REQUIRED_ADAPTATIONS: none
    is a different prefix and must not be misread as a file-scope stamp.
    """
    import re as re2
    covers_re = re2.compile(r'^COVERS:.*$', re2.MULTILINE | re2.IGNORECASE)
    verified_re = re2.compile(r'^VERIFIED:.*$', re2.MULTILINE | re2.IGNORECASE)

    fake_report = "REQUIRED_ADAPTATIONS:\n- none\n\nCOVERS: "
    # 'none' on its own line after REQUIRED_ADAPTATIONS should not be parsed as COVERS scope
    assert not covers_re.search("REQUIRED_ADAPTATIONS:\n- none"), (
        "REQUIRED_ADAPTATIONS: none matches COVERS: regex — parsing confusion risk"
    )
    assert not verified_re.search("REQUIRED_ADAPTATIONS:\n- none"), (
        "REQUIRED_ADAPTATIONS: none matches VERIFIED: regex"
    )

    # Also confirm the prose form "write `none`" is what the prompt says
    assert "write `none`" in swiper, (
        "swiper.md must say 'write `none`' for the REQUIRED_ADAPTATIONS empty case, "
        "not some other format that could look like a stamp"
    )


# ── 8. Internal tension: language-mismatch vs framework/scale exception ──────

def test_no_contradiction_between_language_mismatch_and_framework_exception():
    """
    The old text said clone-and-patch applies 'even when the fetched reference
    came from a different framework or scale'. The new text adds language mismatch
    forces pattern-only. These must not directly contradict each other in the
    same sentence or paragraph.
    The key correctness property: framework/scale != language mismatch.
    Language mismatch (different PL) → pattern-only.
    Framework mismatch (same PL, different framework) → still clone-and-patch.
    """
    # Find the relevant paragraph
    m = re.search(
        r'ceiling on the diff.*?(?=\n\n- \*\*`pattern-only`\*\*)',
        swiper, re.DOTALL
    )
    assert m, "Cannot find clone-and-patch description paragraph"
    para = m.group()

    # Both phrases should be present in the same section
    assert "different framework or scale" in para, (
        "Old framework/scale exception text was dropped — was that intentional?"
    )
    assert "Language mismatch" in para or "language mismatch" in para, (
        "Language mismatch exception not found in clone-and-patch paragraph"
    )

    # They must be DISTINGUISHABLE — language mismatch must be called out
    # as the exception to the framework/scale rule, not as the same thing
    # Check the text doesn't say "language mismatch" forces pattern-only
    # while also saying the framework exception applies, without distinguishing them
    framework_pos = para.find("different framework or scale")
    lang_pos = para.find("Language mismatch") if "Language mismatch" in para else para.find("language mismatch")
    assert lang_pos > framework_pos, (
        "Language mismatch clause must come AFTER the framework/scale exception "
        "so it reads as a clarifying carve-out, not a contradiction. "
        f"framework_pos={framework_pos}, lang_pos={lang_pos}"
    )


# ── 9. CLAUDE.md phrasing matches canonical clean-rag/CLAUDE.md ─────────────

def test_claude_md_adapt_removal_matches_canonical():
    """
    CLAUDE.md and portable/CLAUDE.md must say 'There is no `adapt` tier' (same phrasing as canonical).
    """
    canonical_phrase = "There is no `adapt` tier"
    for name, text in [("CLAUDE.md", root_claude), ("portable/CLAUDE.md", portable_claude)]:
        assert canonical_phrase in text, (
            f"{name} doesn't contain the canonical phrase {canonical_phrase!r}. "
            "Check the adapt removal sentence matches clean-rag/CLAUDE.md."
        )


if __name__ == "__main__":
    import sys
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
        except AssertionError as e:
            print(f"  FAIL  {t.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"  ERROR {t.__name__}: {type(e).__name__}: {e}")
            failed += 1
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
