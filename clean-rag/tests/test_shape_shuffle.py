"""shape_shuffle.py: the structure changes, the words never do.

1. Word identity: the multiset of whitespace collapsed sentences is the same in
   every variant. One dropped word, one duplicated bullet, fails it.
2. Heading lines are never touched.
3. A section containing a date range keeps its bullet order; a heading that
   carries a date does not freeze its section, only body lines do.
4. --no-merge leaves every bullet a bullet. --no-reorder keeps every order.
5. Determinism: same seed, same bytes. Variant K is identical whether you ask
   for K or K+2 variants, because sub seeds are drawn in order.
6. --glue keeps bullets that share a fact_diff anchor or qualifier adjacent.
7. The CLI writes dest.variantK.txt.
8. A marker prefixed line is a bullet even when ALL CAPS; numbered lists and
   pipe tables are left byte identical; month qualified date ranges freeze.
   fact_diff.py itself passes on every variant.
"""

from __future__ import annotations

import collections
import importlib.util
import random
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "clean-rag" / "portable" / "skills" / "human-voice" / "scripts" / "shape_shuffle.py"
FACT_DIFF = SCRIPT.with_name("fact_diff.py")

DOC = """TITLE LINE

# Summary

Eight years full stack. Shipped a Flutter app. Built a GPT-4 invoice platform, solo.

EXPERIENCE

Acme (Remote)
Apr 2025 to Present
Engineer

- First thing done here. It took forty five minutes before the rewrite.
- Second thing, sixteen CTEs. Under thirty seconds now, measured twice.
- Third thing on its own line.
- Fourth thing with a number, 70 of the 87 files in 2025.

SKILLS

- Alpha tools for building things.
- Beta tools for testing things.
- Gamma tools for shipping things.
- Delta tools, the qualifier lives here in 2025.
- Epsilon tools that were 70 of the 87 added.
"""


@pytest.fixture(scope="module")
def ss():
    spec = importlib.util.spec_from_file_location("shape_shuffle", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def fd():
    spec = importlib.util.spec_from_file_location("fact_diff", FACT_DIFF)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def bag(ss, text):
    return ss.sentence_bag(ss.parse(text))


def bullets_in_section(ss, text, heading):
    chunks = ss.parse(text)
    out, inside = [], False
    for kind, body in chunks:
        if kind == "heading":
            inside = body.strip() == heading
        elif inside and kind == "bullets":
            out.extend(t for _, t in body)
    return out


@pytest.mark.parametrize("seed", range(12))
def test_word_multiset_survives_every_variant(ss, seed):
    out, _ = ss.variant(DOC, random.Random(seed), False, False)
    assert bag(ss, out) == bag(ss, DOC)


def test_word_multiset_survives_hard_wrapped_paragraph(ss):
    doc = "INTRO\n\nOne sentence that wraps\nacross a line. Second sentence here\nalso wraps. Third one too.\n"
    for seed in range(8):
        out, _ = ss.variant(doc, random.Random(seed), False, False)
        assert bag(ss, out) == bag(ss, doc)


def test_headings_untouched_and_in_order(ss):
    heads = [b for k, b in ss.parse(DOC) if k == "heading"]
    assert heads == ["TITLE LINE", "# Summary", "EXPERIENCE", "SKILLS"]
    for seed in range(12):
        out, _ = ss.variant(DOC, random.Random(seed), False, False)
        assert [b for k, b in ss.parse(out) if k == "heading"] == heads


def test_dated_section_keeps_order_undated_section_shuffles(ss):
    src_exp = bullets_in_section(ss, DOC, "EXPERIENCE")
    moved = False
    for seed in range(20):
        out, knobs = ss.variant(DOC, random.Random(seed), True, False)
        exp = bullets_in_section(ss, out, "EXPERIENCE")
        # order of first words survives even when bullets are split or joined
        firsts = [t.split()[0] for t in exp]
        src_firsts = [t.split()[0] for t in src_exp]
        assert [w for w in firsts if w in src_firsts] == [w for w in src_firsts if w in firsts]
        if knobs["reorder"] and bullets_in_section(ss, out, "SKILLS")[:3] != bullets_in_section(ss, DOC, "SKILLS")[:3]:
            moved = True
    assert moved, "SKILLS never reordered across 20 seeds"


def test_date_in_heading_does_not_freeze_section(ss):
    doc = "2018 TO 2020 HIGHLIGHTS\n\n- one thing.\n- two thing.\n- three thing.\n- four thing.\n"
    assert ss.frozen_sections(ss.parse(doc)) == set()
    doc2 = "HIGHLIGHTS\n\n2018 to 2020\n\n- one thing.\n- two thing.\n"
    assert ss.frozen_sections(ss.parse(doc2)) == {1}


def test_no_merge_keeps_every_bullet_a_bullet(ss):
    n_src = sum(len(b) for k, b in ss.parse(DOC) if k == "bullets")
    for seed in range(12):
        out, _ = ss.variant(DOC, random.Random(seed), True, True)
        paras = [b for k, b in ss.parse(out) if k == "para"]
        # only the two label paragraphs and the summary may be paragraphs; no bullet text leaks into one
        assert not any("Alpha tools" in l or "First thing" in l for p in paras for l in p)
        assert sum(len(b) for k, b in ss.parse(out) if k == "bullets") >= n_src - 2  # joins allowed, prose not


def test_no_reorder_keeps_every_order(ss):
    for seed in range(12):
        out, knobs = ss.variant(DOC, random.Random(seed), False, True)
        assert knobs["reorder"] is False
        sk = [t.split()[0] for t in bullets_in_section(ss, out, "SKILLS")]
        assert sk == [w for w in ["Alpha", "Beta", "Gamma", "Delta", "Epsilon"] if w in sk]


def test_glue_keeps_anchor_and_qualifier_adjacent(ss):
    groups = [["70 of the 87", "in 2025"]]
    for seed in range(30):
        out, _ = ss.variant(DOC, random.Random(seed), True, False, groups)
        sk = bullets_in_section(ss, out, "SKILLS")
        i = next(i for i, t in enumerate(sk) if "Delta" in t)
        j = next(j for j, t in enumerate(sk) if "Epsilon" in t)
        assert abs(i - j) <= 1, (seed, sk)  # adjacent, or joined into one bullet


def test_determinism_and_variant_count_independence(ss, tmp_path):
    src = tmp_path / "in.txt"
    src.write_text(DOC, encoding="utf-8")
    a, b = tmp_path / "a.txt", tmp_path / "b.txt"
    ss.main([str(src), str(a), "--seed", "5", "--variants", "2"])
    ss.main([str(src), str(b), "--seed", "5", "--variants", "4"])
    for k in (1, 2):
        assert (tmp_path / f"a.variant{k}.txt").read_bytes() == (tmp_path / f"b.variant{k}.txt").read_bytes()
    assert (tmp_path / "b.variant4.txt").is_file()
    assert (tmp_path / "b.variant1.txt").read_bytes() != (tmp_path / "b.variant2.txt").read_bytes()


def test_adjacent_seeds_do_not_share_variants(ss, tmp_path):
    # seed + k as the sub seed makes seed 0 variant 2 identical to seed 1 variant 1
    src = tmp_path / "in.txt"
    src.write_text(DOC, encoding="utf-8")
    ss.main([str(src), str(tmp_path / "s0.txt"), "--seed", "0", "--variants", "3"])
    ss.main([str(src), str(tmp_path / "s1.txt"), "--seed", "1", "--variants", "3"])
    s0 = {(tmp_path / f"s0.variant{k}.txt").read_bytes() for k in (1, 2, 3)}
    s1 = {(tmp_path / f"s1.variant{k}.txt").read_bytes() for k in (1, 2, 3)}
    assert not (s0 & s1)


def test_cli_glue_reads_fact_diff_rules(ss, tmp_path):
    rules = tmp_path / "rules.json"
    rules.write_text('{"qualifiers": [{"anchor": "70 of the 87", "must_keep": ["in 2025"]}]}', encoding="utf-8")
    assert ss.load_glue(str(rules)) == [["70 of the 87", "in 2025"]]
    assert ss.load_glue(None) == []


def test_all_caps_bullet_is_not_a_heading(ss):
    doc = ("EXPERIENCE\n\n"
           "- BUILT SCALABLE SYSTEMS FOR RETAIL.\n"
           "- Wrote normal lowercase bullet text here today.\n"
           "- Another normal bullet about testing things properly.\n")
    kinds = [k for k, _ in ss.parse(doc)]
    assert kinds.count("heading") == 1, kinds
    assert sum(len(b) for k, b in ss.parse(doc) if k == "bullets") == 3


def test_date_range_matches_month_qualified_years(ss):
    for s in ["Jan 2020 to Dec 2022", "March 2019 to June 2021", "Sept. 2021 - Present", "2018 to 2020"]:
        assert ss.DATE_RANGE.search(s), s
    assert not ss.DATE_RANGE.search("released in 2020, then 2021 followed")


def test_all_caps_bullet_does_not_unfreeze_a_dated_section(ss):
    doc = ("EXPERIENCE\n\nAcme Corp, 2018 to 2020\n\n"
           "- First real accomplishment happened here today.\n"
           "- LED A CROSS FUNCTIONAL TEAM OF ENGINEERS ACROSS OFFICES.\n"
           "- Second real accomplishment happened here as well.\n"
           "- Third real accomplishment happened here too somehow.\n"
           "- Fourth real accomplishment happened here also indeed.\n")
    assert ss.frozen_sections(ss.parse(doc)) == {1}
    openers = ["First", "LED", "Second", "Third", "Fourth"]
    for seed in range(60):
        out, _ = ss.variant(doc, random.Random(seed), True, False)
        # relative order survives splits and joins; only a reorder would change it
        seen = [w for t in bullets_in_section(ss, out, "EXPERIENCE") for w in t.split() if w in openers]
        assert seen == openers, (seed, seen)


def test_bulletize_leaves_a_markdown_table_alone_and_fact_diff_passes(ss, fd):
    doc = ("REVIEW\n\n"
           "Summary of scores below. Reviewer one gave it a great score. Reviewer two "
           "also liked it a lot. Reviewer three thought it was fine overall.\n"
           "| Name | Score |\n|---|---|\n| Alice | 9 |\n| Bob | 8 |\n")
    for seed in range(12):
        out, _ = ss.variant(doc, random.Random(seed), False, False)
        assert "| Name | Score |\n|---|---|\n| Alice | 9 |\n| Bob | 8 |" in out, (seed, out)
        assert fd.compare(doc, out, {}) == [], (seed, out)


def test_numbered_lists_are_left_byte_identical_and_fact_diff_passes(ss, fd):
    doc = ("STEPS\n\n"
           "1. First bullet here today for numbering. Then a second sentence with enough words.\n"
           "2) Second bullet here for numbering too.\n"
           "3. Third bullet here as well for numbering.\n"
           "4. Fourth bullet here as well for numbering too.\n\n"
           "NOTES\n\n- Alpha note about things.\n- Beta note about other things.\n- Gamma note about more things.\n")
    steps = doc.split("STEPS\n\n")[1].split("\n\nNOTES")[0]
    for seed in range(12):
        out, _ = ss.variant(doc, random.Random(seed), False, False)
        assert steps in out, (seed, out)
        assert fd.compare(doc, out, {}) == [], (seed, out)


def test_bulletize_never_borrows_a_numbered_marker(ss, fd):
    # the only marker in the doc is numbered; a bulletized paragraph must not copy it
    doc = "1. a thing here.\n2. b thing here.\n\nOne sentence here. Two sentence here. Three sentence here.\n"
    bulletized = False
    for seed in range(20):
        out, _ = ss.variant(doc, random.Random(seed), False, False)
        assert fd.compare(doc, out, {}) == [], (seed, out)
        new = [m for k, b in ss.parse(out) if k == "bullets" for m, t in b if "sentence" in t]
        bulletized |= bool(new)
        assert all(m == "- " for m in new), (seed, new)
    assert bulletized, "p_bulletize never fired across 20 seeds"
