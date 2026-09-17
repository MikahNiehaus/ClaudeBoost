"""fact_diff.py bites: the 10 injected defects SKILL.md claims it catches.

SKILL.md says "Verified against 10 injected defects ... All 10 fail the check."
Until this file, nothing in the repo backed that. Each test below injects one
defect into a clean candidate and asserts `compare()` reports it. The clean
candidate itself passes, and the two documented false positive classes (a banned
phrase already in the baseline, a qualifier split by a blockquote marker) do not
fire.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "clean-rag" / "portable" / "skills" / "human-voice" / "scripts" / "fact_diff.py"

BASE = """# Report

## Retrieval

Scored 0.687 average NDCG@10 across 6 languages [GIT], benchmarked on the
CoIR CodeSearchNet suite. See `bench/results.md:12`. Ticket ABC-1234.
Wrote 70 of the 87 test files added in 2025. Shipped a regression test on
34% of bug fixes, four times the team median. 77,571 hand written lines.

> As the README puts it, "best-effort open reproduction".

Never say "submitted to the leaderboard".
"""

RULES = {
    "qualifiers": [
        {"anchor": "70 of the 87", "must_keep": "in 2025", "window": 120},
        {"anchor": "0.687", "must_keep": "average", "window": 60},
        {"anchor": "34%", "must_keep": "team median", "window": 160},
        {"anchor": "77,571", "must_keep": "hand written", "window": 60},
    ],
    "banned": ["submitted to the leaderboard"],
    "verbatim": ["best-effort open reproduction"],
}


@pytest.fixture(scope="module")
def fd():
    spec = importlib.util.spec_from_file_location("fact_diff", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_clean_candidate_passes(fd):
    assert fd.compare(BASE, BASE, RULES) == []


@pytest.mark.parametrize("old, new, expect", [
    ("0.687", "0.678", "numbers"),                                  # 1 changed digit
    ("[GIT]", "[SELF]", "tags"),                                    # 2 swapped tag
    ("`bench/results.md:12`", "`bench/results.md:21`", "citations"),  # 3 altered citation
    ("ABC-1234", "ABC-1243", "tickets"),                            # 4 changed ticket id
    ("best-effort open reproduction", "best effort open reproduction", "VERBATIM"),  # 5
    ("## Retrieval", "### Retrieval", "structure headings"),        # 6 demoted heading
    ("added in 2025", "added", "QUALIFIER DROPPED '70 of the 87'"),  # 7
    ("0.687 average", "0.687", "QUALIFIER DROPPED '0.687'"),        # 8
    ("four times the team median", "four times the next best", "QUALIFIER DROPPED '34%'"),  # 9
    ("77,571 hand written lines", "77,571 lines", "QUALIFIER DROPPED '77,571'"),  # 10
])
def test_injected_defect_fails(fd, old, new, expect):
    assert old in BASE
    cand = BASE.replace(old, new)
    fails = fd.compare(BASE, cand, RULES)
    assert any(expect in f for f in fails), "%s not caught, got %r" % (expect, fails)


def test_banned_phrase_appearing_fails(fd):
    cand = BASE.replace("benchmarked on", "submitted to the leaderboard for")
    fails = fd.compare(BASE, cand, RULES)
    assert any("BANNED" in f for f in fails)


def test_banned_phrase_already_in_baseline_does_not_fire(fd):
    # BASE quotes the banned phrase on purpose; the count did not rise.
    assert not any("BANNED" in f for f in fd.compare(BASE, BASE, RULES))


def test_qualifier_split_by_blockquote_marker_still_counts(fd):
    cand = BASE.replace("test files added in 2025", "test files added\n> in 2025")
    fails = fd.compare(BASE, cand, RULES)
    assert not any("70 of the 87" in f for f in fails), fails


def test_cli_exit_codes(fd, tmp_path):
    b, c = tmp_path / "b.md", tmp_path / "c.md"
    b.write_text(BASE, encoding="utf-8")
    c.write_text(BASE.replace("0.687", "0.678"), encoding="utf-8")
    assert fd.main([str(b), str(b)]) == 0
    assert fd.main([str(b), str(c)]) == 1
    assert fd.main([str(b), str(tmp_path / "missing.md")]) == 2
