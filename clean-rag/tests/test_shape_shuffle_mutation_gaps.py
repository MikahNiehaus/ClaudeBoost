"""Kill tests for mutation-resistance gaps found in a bad-cop test-quality pass
on test_shape_shuffle.py (2026-09-13). Each test here passes on the current
shape_shuffle.py and fails on a specific mutant that the existing suite let
survive. See the accompanying QA report for the pytest tail proving each
mutant survived before these tests were added.

Do not delete without re-running the mutation check these replace:
  1. shard word-count guard (>= 4 words) in the bullet split path
  2. the sentence-bag self-check (last line of defence for word identity)
  3. p_bulletize actually turning a paragraph into bullets
"""
from __future__ import annotations

import importlib.util
import random
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "clean-rag" / "portable" / "skills" / "human-voice" / "scripts" / "shape_shuffle.py"


@pytest.fixture(scope="module")
def ss():
    spec = importlib.util.spec_from_file_location("shape_shuffle_gaps", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_split_never_produces_a_shard_under_four_words(ss):
    """Kills: `min(len(left.split()), len(right.split())) >= 4` weakened to `>= 1`.

    A long first sentence next to a two word second sentence must NOT split,
    because the right shard would be "A a." (2 words) -- exactly the
    "45 minutes." style fragment the guard's own comment calls out.
    """
    bullets = [("- ", "This is a genuinely long first sentence with plenty of words in it. A a.")]
    knobs = {"p_split": 1.0, "p_join": 0.0, "p_prose": 0.0, "p_bulletize": 0.0,
             "reorder": False, "p_double": 0.0}
    out = ss.shuffle_chunk(random.Random(0), "bullets", bullets, knobs, False, "- ", [])
    assert out == [("bullets", bullets)], "guard should have refused the 2-word shard"


def test_split_does_happen_when_both_shards_are_long_enough(ss):
    """Sanity companion: the guard must not be so strict it blocks every split."""
    bullets = [("- ", "This first sentence has plenty of words indeed. This second sentence also has enough words.")]
    knobs = {"p_split": 1.0, "p_join": 0.0, "p_prose": 0.0, "p_bulletize": 0.0,
             "reorder": False, "p_double": 0.0}
    out = ss.shuffle_chunk(random.Random(0), "bullets", bullets, knobs, False, "- ", [])
    assert len(out[0][1]) == 2, "two long-enough sentences should split into two bullets"


def test_self_check_fires_on_a_corrupted_bag(ss, monkeypatch):
    """Kills: removing the `if sentence_bag(...) != sentence_bag(chunks): raise` guard
    in variant(). Forces sentence_bag to lie on its second call (the post-render
    check) and asserts variant() actually refuses to emit instead of silently
    returning corrupted output."""
    real_bag = ss.sentence_bag
    calls = {"n": 0}

    def lying_bag(chunks):
        calls["n"] += 1
        result = real_bag(chunks)
        if calls["n"] > 1:
            result = result.copy()
            result["SOMETHING THAT WAS NEVER THERE"] += 1
        return result

    monkeypatch.setattr(ss, "sentence_bag", lying_bag)
    with pytest.raises(AssertionError, match="sentence multiset changed"):
        ss.variant("HEADING\n\n- one thing here.\n- two thing here.\n- three thing here.\n",
                   random.Random(0), False, False)


NON_RESUME_DOC = """MEETING NOTES

# Kickoff

We discussed the migration timeline. Nobody objected to the plan. Sarah will
own the rollout.

ACTION ITEMS

- Write the migration script by Friday.
- Review the script with the platform team before merging.
- Schedule a follow up once the script lands.
- Announce the change in the team channel after it ships.

RECIPE

- Chop two onions finely.
- Saute the onions in butter for ten minutes.
- Add the stock and simmer for thirty minutes.
- Season with salt before serving.
"""


def test_generality_non_resume_document_survives_a_variant(ss):
    """The user's stated requirement is "a general tool not just meant for
    resumes." Every fixture the existing suite exercises (DOC) is resume
    shaped (EXPERIENCE, SKILLS, Acme, Engineer). This proves the tool holds
    its two hardest invariants -- word identity and untouched headings -- on
    a document with no resume vocabulary at all (meeting notes + a recipe)."""
    heads = [b for k, b in ss.parse(NON_RESUME_DOC) if k == "heading"]
    for seed in range(8):
        out, _ = ss.variant(NON_RESUME_DOC, random.Random(seed), False, False)
        assert bag(ss, out) == bag(ss, NON_RESUME_DOC)
        assert [b for k, b in ss.parse(out) if k == "heading"] == heads


def bag(ss, text):
    return ss.sentence_bag(ss.parse(text))


MARKER_BODY_DOCS = {
    "digits": "NUMBERS\n\n- First prose bullet here with several words. Second sentence with enough words too.\n"
              "- 42.\n- Third prose bullet about something else entirely.\n- $9,000.\n"
              "- Fifth prose bullet with plenty more words in it.\n",
    "dash": "T\n\n- - nested looking thing here.\n- Second prose bullet with words.\n- Third prose bullet with words.\n",
    "hash": "T\n\n- # not a heading really.\n- Second prose bullet with words.\n- Third prose bullet with words.\n",
    "caps": "T\n\n- ALL CAPS ONE.\n- ALL CAPS TWO.\n- Third prose bullet with words.\n- Fourth prose bullet with words.\n",
}


@pytest.mark.parametrize("name", sorted(MARKER_BODY_DOCS))
def test_bullet_body_that_is_a_block_marker_never_opens_a_paragraph(ss, name):
    """Kills: dropping the `parse(line) == [("para", [line])]` round trip guard in
    the bullets-to-paragraph branch. A bullet whose body is "42.", "- x", "# x"
    or a short ALL CAPS line re-parses as a numbered item, bullet or heading once
    it opens a paragraph line, and the sentence bag loses it. Before the guard
    20 to 38 of 201 seeds raised on each of these docs."""
    doc = MARKER_BODY_DOCS[name]
    for seed in range(201):
        out, _ = ss.variant(doc, random.Random(seed), False, False)
        assert bag(ss, out) == bag(ss, doc), (seed, out)


def test_cli_skips_a_refused_variant_instead_of_crashing(ss, tmp_path, monkeypatch, capsys):
    """Kills: removing the try/except around variant() in main(). One refused
    variant must be reported and skipped, the others still written, and the
    exit status must say something was skipped."""
    real = ss.variant

    def refuse_second(text, rng, *args):
        out, knobs = real(text, rng, *args)
        if getattr(refuse_second, "n", 0) == 1:
            refuse_second.n = 2
            raise AssertionError("sentence multiset changed; refusing to emit this variant")
        refuse_second.n = getattr(refuse_second, "n", 0) + 1
        return out, knobs

    monkeypatch.setattr(ss, "variant", refuse_second)
    src = tmp_path / "in.txt"
    src.write_text(NON_RESUME_DOC, encoding="utf-8")
    rc = ss.main([str(src), str(tmp_path / "o.txt"), "--seed", "3", "--variants", "3"])
    assert rc == 1
    assert (tmp_path / "o.variant1.txt").is_file()
    assert not (tmp_path / "o.variant2.txt").exists()
    assert (tmp_path / "o.variant3.txt").is_file()
    assert "o.variant2.txt  SKIPPED (seed 3)" in capsys.readouterr().err


def test_inline_pipe_in_prose_does_not_block_bulletize_but_a_table_row_does(ss):
    """Kills: the pipe guard reverting to `"|" in l` (blocks any stray pipe) or
    being removed (bulletizes a table row, which breaks fact_diff's table_rules)."""
    knobs = {"p_split": 0.0, "p_join": 0.0, "p_prose": 0.0, "p_bulletize": 1.0,
             "reorder": False, "p_double": 0.0}
    prose = ["Run ls | grep foo to find it. Then read the output. Then fix the thing."]
    assert ss.shuffle_chunk(random.Random(0), "para", prose, knobs, False, "- ", [])[0][0] == "bullets"
    table = ["Scores below. Alice won. Bob came second.", "| Name | Score |", "|---|---|", "| Alice | 9 |"]
    assert ss.shuffle_chunk(random.Random(0), "para", table, knobs, False, "- ", []) == [("para", table)]


def test_bulletize_actually_turns_a_long_paragraph_into_bullets(ss):
    """Kills: the p_bulletize branch being removed/disabled (`if False:` or similar).
    With p_bulletize forced to 1.0 on a 3+ sentence paragraph, the feature the
    module's own docstring advertises ("turns a paragraph into bullets") must
    actually fire."""
    body = ["One sentence here. Two sentence here. Three sentence here."]
    knobs = {"p_split": 0.0, "p_join": 0.0, "p_prose": 0.0, "p_bulletize": 1.0,
             "reorder": False, "p_double": 0.0}
    out = ss.shuffle_chunk(random.Random(0), "para", body, knobs, False, "- ", [])
    assert out[0][0] == "bullets", "p_bulletize=1.0 on a 3-sentence paragraph must produce bullets"
    assert len(out[0][1]) == 3
