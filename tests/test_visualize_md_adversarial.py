"""
Adversarial tests for .claude/commands/visualize.md changes.

Tests are structural: they parse the markdown spec itself and assert
the correctness properties that were claimed in the change description.
Run with: python -m pytest tests/test_visualize_md_adversarial.py -v
"""

import re
import pathlib

import pytest

SPEC = pathlib.Path(__file__).parent.parent / ".claude" / "commands" / "visualize.md"


def load_spec():
    return SPEC.read_text(encoding="utf-8")


# visualize.md contains the string "mermaid" zero times, and no revision in git
# history ever contained a --mermaid flag. The two tests below assert a mermaid
# mode alongside the --excalidraw one that did ship, so they have never passed:
# they describe a feature where only half the modes landed, not a regression.
#
# strict=True on purpose. Marked xfail they stop drowning real failures, and if
# --mermaid ever does land the marker turns red and says so, instead of quietly
# passing while claiming to be a known gap.
_MERMAID_MISSING = "mermaid" not in load_spec().lower()

_needs_mermaid_mode = pytest.mark.xfail(
    _MERMAID_MISSING,
    strict=True,
    reason=(
        "visualize.md has no --mermaid mode and never has. These assert a "
        "two-mode feature where only --excalidraw shipped. Remove this marker "
        "when --mermaid lands."
    ),
)


# ---------------------------------------------------------------------------
# Property 1: MODE list in Phase 0c must include mermaid and excalidraw
# ---------------------------------------------------------------------------

def test_mode_list_declares_mermaid_and_excalidraw():
    """Phase 0c declares MODE as one of: concept, self-map, project-map.
    But --mermaid and --excalidraw produce a 'mermaid'/'excalidraw' mode
    that is NOT in that declared list. Check whether the spec's own MODE
    enum is consistent with the modes it actually routes to."""
    text = load_spec()

    # Find the MODE declaration line
    mode_decl = re.search(r'\*\*MODE\*\*.*one of:.*`([^`]+)`', text)
    assert mode_decl is not None, "Could not find MODE enum declaration"

    declared_modes_line = mode_decl.group(0)

    # The spec says MODE is one of: concept, self map, project map
    # Check if mermaid/excalidraw appear in the declared set
    assert 'mermaid' in declared_modes_line or 'excalidraw' in declared_modes_line, (
        f"FAIL: MODE declaration '{declared_modes_line}' does not include 'mermaid' or "
        f"'excalidraw' even though Phase 0c routes to those modes. "
        f"An LLM following the spec strictly will carry MODE='concept' or 'project-map', "
        f"not 'mermaid'/'excalidraw', breaking every conditional check downstream."
    )


# ---------------------------------------------------------------------------
# Property 2: Step 1 must account for mermaid/excalidraw modes
# ---------------------------------------------------------------------------

@_needs_mermaid_mode
def test_step1_detection_handles_mermaid_excalidraw():
    """Step 1: Detect Mode runs ls agents/ knowledge/ and sets MODE.
    If --mermaid was passed and MODE was already set to 'mermaid' in Phase 0c,
    Step 1 must not accidentally re-derive it to self-map or project-map."""
    text = load_spec()

    # Find Step 1 section
    step1_match = re.search(r'## Step 1: Detect Mode(.+?)(?=\n##)', text, re.DOTALL)
    assert step1_match is not None, "Could not find Step 1 section"

    step1_text = step1_match.group(1)

    # Step 1 says "skip detection only if the user passed an explicit flag
    # (--self, --project) or a concept argument"
    # --mermaid and --excalidraw are NOT in this list
    has_mermaid_guard = 'mermaid' in step1_text
    has_excalidraw_guard = 'excalidraw' in step1_text

    assert has_mermaid_guard and has_excalidraw_guard, (
        f"FAIL: Step 1 skip-detection condition does not mention --mermaid or --excalidraw. "
        f"Text: '{step1_text.strip()[:400]}'. "
        f"An LLM following Step 1 literally with $ARGUMENTS='--mermaid auth flow' will "
        f"run ls agents/ knowledge/, find them, set MODE=self-map, and proceed to Step 2a "
        f"instead of Step 3c."
    )


# ---------------------------------------------------------------------------
# Property 3: Step 3e skip condition names both mermaid AND excalidraw
# ---------------------------------------------------------------------------

@_needs_mermaid_mode
def test_step3e_skip_names_both_new_modes():
    """Step 3e says 'Skip for mermaid/excalidraw modes' — verify it actually
    says both explicitly, not just one."""
    text = load_spec()

    step3e_match = re.search(r'## Step 3e:(.+?)(?=\n##)', text, re.DOTALL)
    assert step3e_match is not None, "Could not find Step 3e section"

    step3e_text = step3e_match.group(1)

    assert 'mermaid' in step3e_text and 'excalidraw' in step3e_text, (
        "Step 3e skip condition doesn't explicitly name both modes — already confirmed present, "
        "this is a sanity check."
    )


# ---------------------------------------------------------------------------
# Property 4: Step 3b (audio tour) is MANDATORY for HTML modes —
#             mermaid/excalidraw skip it. But Step 3b heading says
#             'MANDATORY — DO NOT SIMPLIFY' with no mode guard.
# ---------------------------------------------------------------------------

def test_step3b_has_html_mode_guard():
    """Step 3b is marked MANDATORY with no mode restriction in its own
    heading. Verify that either Step 3b itself has a mode guard, or that
    the 'Skip Steps 3–3b' instruction in Phase 0c is unambiguous enough
    to cover this."""
    text = load_spec()

    step3b_match = re.search(r'## Step 3b:(.+?)(?=\n## Step 3c)', text, re.DOTALL)
    assert step3b_match is not None, "Could not find Step 3b section"

    step3b_text = step3b_match.group(1)

    # Is there a mode guard in Step 3b itself?
    has_own_guard = 'mermaid' in step3b_text or 'excalidraw' in step3b_text or \
                   'HTML mode' in step3b_text or 'Only run when' in step3b_text

    assert has_own_guard, (
        f"FAIL: Step 3b ('MANDATORY — DO NOT SIMPLIFY') has no mode guard of its own. "
        f"The only skip instruction is in Phase 0c: 'Skip Steps 3–3b; go to Step 3c/3d'. "
        f"That forward-reference may be missed by an LLM that reads sections independently "
        f"and honors the MANDATORY annotation on Step 3b. Step 3c and 3d only say "
        f"'Skip Steps 3–3b entirely' — the guard must be in the section, not only the router."
    )


# ---------------------------------------------------------------------------
# Property 5: The HTML template in Step 3 uses detail-desc/detail-list
#             but Step 3e validates for detail-body. They are contradictory.
# ---------------------------------------------------------------------------

def test_step3_template_uses_detail_body_not_old_ids():
    """Step 3e check #3 requires <div id='detail-body'>. But the HTML template
    in Step 3 must also use detail-body for this check to be meaningful.
    Verify the template in Step 3 does NOT use the old detail-desc/detail-list
    pattern that Step 3e explicitly flags as wrong."""
    text = load_spec()

    # Find the HTML template in Step 3 (between ```html and the next ```)
    html_block = re.search(r'```html\n(.*?)```', text, re.DOTALL)
    assert html_block is not None, "Could not find HTML template block"

    html_template = html_block.group(1)

    # Check what IDs the template uses for the detail panel
    has_old_desc = 'id="detail-desc"' in html_template
    has_old_list = 'id="detail-list"' in html_template
    has_new_body = 'id="detail-body"' in html_template

    assert not has_old_desc and not has_old_list, (
        f"FAIL: The HTML template in Step 3 still uses the OLD detail panel IDs "
        f"(detail-desc={has_old_desc}, detail-list={has_old_list}) that Step 3e "
        f"explicitly flags as wrong. Step 3e validates for detail-body, but the "
        f"template it's supposed to validate was never updated. An LLM that copies "
        f"the template will fail its own Step 3e check every time."
    )

    assert has_new_body, (
        f"FAIL: The HTML template in Step 3 does not contain id='detail-body'. "
        f"Step 3e checks for this ID but the template doesn't include it. "
        f"An LLM copying the template faithfully will fail Step 3e check #3."
    )


# ---------------------------------------------------------------------------
# Property 6: showDetail() in the HTML template uses old pattern
#             (textContent for desc/list) but the COMPONENTS pattern
#             section requires innerHTML for html:. Check for contradiction.
# ---------------------------------------------------------------------------

def test_showdetail_in_template_uses_innerhtml():
    """The COMPONENTS pattern section says 'Detail panel must render html:
    with innerHTML, not textContent'. The showDetail() function in the HTML
    template must match this requirement."""
    text = load_spec()

    # Find the showDetail function in the HTML template (inside ```html block)
    html_block = re.search(r'```html\n(.*?)```', text, re.DOTALL)
    assert html_block is not None
    html_template = html_block.group(1)

    # Check if showDetail in the template uses detail-desc with textContent
    uses_old_textcontent_on_desc = (
        'detail-desc' in html_template and 'textContent' in html_template
    )

    assert not uses_old_textcontent_on_desc, (
        f"FAIL: The showDetail() function in the HTML template uses textContent on "
        f"detail-desc, but the COMPONENTS pattern section requires innerHTML on "
        f"detail-body. The template is teaching the wrong pattern — an LLM will "
        f"copy the template showDetail() and fail to render html: content."
    )


# ---------------------------------------------------------------------------
# Property 7: Search endpoint param shape — Step 2d search #1 and #2
#             are now identical. That is redundant dead weight.
# ---------------------------------------------------------------------------

def test_step2d_searches_are_not_identical():
    """Step 2d has two search calls. After the port fix, both use the same
    endpoint with the same parameters except limit (6 vs 8). Verify they
    serve different purposes (they don't — they're functionally identical)."""
    text = load_spec()

    step2d_match = re.search(r'## Step 2d:(.+?)(?=\n---)', text, re.DOTALL)
    assert step2d_match is not None, "Could not find Step 2d section"

    step2d_text = step2d_match.group(1)

    # Extract all search calls
    search_calls = re.findall(r'POST http://127\.0\.0\.1:8613/search.*?with.*?(\{[^}]+\})', step2d_text, re.DOTALL)

    # They should have different mode or sources to serve different purposes
    # Currently both use "mode":"both" and "project:<cwd>" — only limit differs
    if len(search_calls) >= 2:
        # Check if they're substantively different
        calls_normalized = [re.sub(r'\s+', ' ', c.strip()) for c in search_calls]
        # Both now have mode:both and project:<cwd> — only limit differs
        # That's dead weight: same index, same mode, same query, just a different page size
        limit_only_difference = all(
            re.sub(r'"limit":\d+', '"limit":N', c) == re.sub(r'"limit":\d+', '"limit":N', calls_normalized[0])
            for c in calls_normalized[1:]
        )
        assert not limit_only_difference, (
            f"FAIL: Step 2d now has two search calls that are functionally identical "
            f"(same endpoint, same query, same sources, same mode) — only 'limit' differs "
            f"(6 vs 8). The old call #1 searched a knowledge base ('scope:all') which no "
            f"longer exists; it was changed to be identical to call #2. Result: the model "
            f"makes two round-trips to the same index for the same data. One should be removed."
        )


# ---------------------------------------------------------------------------
# Property 8: MODE enum gap — 'mermaid'/'excalidraw' used downstream
#             but not declared in the MODE definition
# ---------------------------------------------------------------------------

def test_mode_enum_gap_provable():
    """Prove that mermaid and excalidraw modes are used in conditional
    checks downstream but NOT in the MODE enum declaration."""
    text = load_spec()

    # The MODE declaration
    mode_decl_match = re.search(r'\*\*MODE\*\*\s*—\s*one of:[^\n]+', text)
    assert mode_decl_match is not None
    mode_decl = mode_decl_match.group(0)

    # Count downstream uses of 'MODE = mermaid' or 'MODE = excalidraw'
    downstream_mermaid = len(re.findall(r'MODE\s*=\s*mermaid|MODE = mermaid', text))
    downstream_excalidraw = len(re.findall(r'MODE\s*=\s*excalidraw|MODE = excalidraw', text))

    assert 'mermaid' in mode_decl or downstream_mermaid == 0, (
        f"FAIL: 'mermaid' appears {downstream_mermaid} times as a MODE value downstream "
        f"but is not in the MODE declaration: '{mode_decl}'"
    )
    assert 'excalidraw' in mode_decl or downstream_excalidraw == 0, (
        f"FAIL: 'excalidraw' appears {downstream_excalidraw} times as a MODE value downstream "
        f"but is not in the MODE declaration: '{mode_decl}'"
    )


if __name__ == "__main__":
    import sys

    tests = [
        test_mode_list_declares_mermaid_and_excalidraw,
        test_step1_detection_handles_mermaid_excalidraw,
        test_step3e_skip_names_both_new_modes,
        test_step3b_has_html_mode_guard,
        test_step3_template_uses_detail_body_not_old_ids,
        test_showdetail_in_template_uses_innerhtml,
        test_step2d_searches_are_not_identical,
        test_mode_enum_gap_provable,
    ]

    passed = failed = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"  FAIL  {t.__name__}")
            print(f"        {e}")
            failed += 1
        except Exception as e:
            print(f"  ERROR {t.__name__}: {e}")
            failed += 1

    print(f"\n{passed} passed, {failed} failed")
    sys.exit(0 if failed == 0 else 1)
