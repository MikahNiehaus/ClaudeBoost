"""The arithmetic and the retention gate behind `docs/HEADROOM-EVALUATION.md` §7.

§7 is the sole evidence for a "do not adopt this dependency" decision, and until
this file existed none of the numbers in it were checked by anything. Four
mutations of the harness all produced a clean exit-0 run and silently wrong
output:

- swapping the baseline in the savings formula, `(after - before) / after`,
  turned "+14.8% median saved" into "-17.5%" with no failure anywhere;
- reporting `median(crush) - median(compact)` instead of the median of the
  per-payload differences overstated headroom's contribution by 48%
  (0.40 points against a true 0.27);
- relaxing the retention checker's field comparison to
  `str(...).strip().lower()` made it report PASS on a payload whose `file` path
  had been case-folded -- a critical field silently altered and scored as
  preserved;
- dropping the `all(isinstance(x, dict))` guard in `retention._results` made the
  checker crash with `AttributeError` on a `results` that was no longer an array
  of dicts, instead of reporting the structural failure.

Every test below fails on at least one of those four. The last group is the
different kind of check: it pins the figures quoted in the doc to the recorded
output of the scripts, which is what makes "every number in §7 is reproducible"
a checked property rather than an intention. The original §7.2 table -- 78.8% /
21.2% -- was produced by no committed code at all and did not match the wire
bytes it claimed to describe.

Those pins address each figure to the place that states it -- a table cell by row
and column, a prose figure by a figure-free anchor on its own line -- rather than
asking whether the numeral occurs somewhere in the document. §7's figures repeat
legitimately, so a whole-document substring check does not pin them: with `11.8%`
written in four places, corrupting the single §7.3 cell a reader makes the
decision from left three correct copies standing and the suite stayed green.

`metrics` and `retention` are importable here only because they are stdlib-only.
`measure.py` and `control.py` import `headroom`, which lives in an isolated 3.13
venv (§4) and is deliberately not a dependency of this repo, so the arithmetic
worth testing was moved out of them into `metrics`.

Run: python -m pytest tests/test_headroom_stage1_metrics.py -v
"""

import json
import re
import statistics
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
HARNESS = REPO / "benchmarks" / "headroom-stage1"
sys.path.insert(0, str(HARNESS))

import metrics  # noqa: E402
from retention import check  # noqa: E402

DOC = REPO / "docs" / "HEADROOM-EVALUATION.md"
STAGE1 = HARNESS / "stage1_results.json"
CONTROL = HARNESS / "control_results.json"
HOOKBLOCK = HARNESS / "hookblock_results.json"

# Scrubbed, not inherited. retention.py's self-test must pass with nothing from
# the developer's shell available to it.
SCRUBBED_ENV = {"PATH": "/usr/bin:/bin"}


def stage1() -> dict:
    return json.loads(STAGE1.read_text())


def control() -> list[dict]:
    return json.loads(CONTROL.read_text())


def _spread(rows: list[dict], key: str) -> dict[str, str]:
    """One percentage column as the doc writes it, keyed by §7.3's column headers."""
    vals = [r[key] for r in rows]
    return {"median": f"{statistics.median(vals):.1f}%",
            "min": f"{min(vals):.1f}%", "max": f"{max(vals):.1f}%"}


# §7.3's preset table counts how many of the 18 payloads each preset did something
# to. Keyed by the doc's own column headers, so a renamed column fails to address.
_PRESET_COUNTS = {
    "chose lossless:table": lambda c: c["strategy"] == "lossless:table",
    "passes retention": lambda c: c["retention"] == "PASS",
    "content replaced by CCR pointer": lambda c: c["ccr_placeholders"] > 0,
}


# ── addressing a figure to the place the doc states it ──
#
# Table parsing follows the GFM tables extension
# (https://github.github.com/gfm/#tables-extension-): a header row, a delimiter
# row of at least three hyphens per column with optional alignment colons, then
# data rows; cells are separated by `|`, surrounding space is trimmed, and `\|`
# is a literal pipe.

_DELIMITER = re.compile(r"^\s*\|?(\s*:?-{3,}:?\s*\|)*\s*:?-{3,}:?\s*\|?\s*$")
_MARKUP = re.compile(r"[*`]")


def _plain(cell: str) -> str:
    """Cell text without emphasis or code ticks: `**72.5%**` -> `72.5%`."""
    return _MARKUP.sub("", cell).strip()


def _row_cells(line: str) -> list[str]:
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|") and not line.endswith("\\|"):
        line = line[:-1]
    return [c.strip().replace("\\|", "|") for c in re.split(r"(?<!\\)\|", line)]


def _tables(doc: str) -> list[tuple[list[str], list[tuple[int, list[str]]]]]:
    """Every pipe table, as (plain header cells, [(line number, raw cells)])."""
    lines = doc.splitlines()
    found, i = [], 0
    while i + 1 < len(lines):
        if "|" in lines[i] and _DELIMITER.match(lines[i + 1]):
            header = [_plain(c) for c in _row_cells(lines[i])]
            rows, j = [], i + 2
            while j < len(lines) and lines[j].strip() and "|" in lines[j]:
                rows.append((j + 1, _row_cells(lines[j])))
                j += 1
            found.append((header, rows))
            i = j
        else:
            i += 1
    return found


def _locate_cell(doc: str, row: str, column: str) -> tuple[int, str]:
    """The one cell under `column` whose row label contains `row`.

    An address that resolves to no cell, or to more than one, raises instead of
    quietly matching something else. A pin that stopped pointing at a real cell
    has stopped guarding a figure, and that has to be louder than a pass.
    """
    hits = []
    for header, rows in _tables(doc):
        if column not in header:
            continue
        at = header.index(column)
        for lineno, cells in rows:
            if row in _plain(cells[0]) and at < len(cells):
                hits.append((lineno, _plain(cells[at])))
    if len(hits) != 1:
        where = f" at lines {[n for n, _ in hits]}" if hits else ""
        raise AssertionError(
            f"cannot address [row containing {row!r} | column {column!r}] in "
            f"{DOC.name}: matched {len(hits)} cells{where}. The table was "
            f"renamed, moved or restructured, so this figure is no longer pinned."
        )
    return hits[0]


def _assert_cells(doc: str, *pins: tuple[str, str, str]) -> None:
    """Each pin is (row label substring, exact column header, expected cell)."""
    wrong = []
    for row, column, expected in pins:
        lineno, actual = _locate_cell(doc, row, column)
        if actual != expected:
            wrong.append((lineno, row, column, expected, actual))
    assert wrong == [], (
        "figures in the doc disagree with the recorded run:\n"
        + "\n".join(
            f"  {DOC.name}:{lineno}  [{row} | {column}]  "
            f"doc says {actual!r}, recorded run gives {expected!r}"
            for lineno, row, column, expected, actual in wrong
        )
    )


def _assert_on_line(doc: str, anchor: str, expected: str) -> None:
    """`expected` must appear on the one line containing `anchor`.

    No anchor contains the figure it locates, so a corrupted figure still resolves
    to its line and the failure names the figure rather than a missing anchor.
    """
    hits = [(n, ln) for n, ln in enumerate(doc.splitlines(), 1) if anchor in ln]
    assert len(hits) == 1, (
        f"anchor {anchor!r} matches {len(hits)} lines in {DOC.name}"
        f"{' at ' + str([n for n, _ in hits]) if hits else ''}; the sentence this "
        f"figure was pinned to was reworded, so it is no longer pinned."
    )
    lineno, line = hits[0]
    assert expected in line, (
        f"{DOC.name}:{lineno} disagrees with the recorded run:\n"
        f"  recorded run gives {expected!r}\n"
        f"  line says          {line.strip()!r}"
    )


# ── savings arithmetic: the formula that produces every "% saved" in the doc ──

def test_saved_pct_is_space_savings_against_the_before_size():
    # 10MB -> 2MB is 80% saved, the textbook case (Wikipedia, Data compression
    # ratio). Not the 5.0 compression ratio, and not 400%.
    assert metrics.saved_pct(10, 2) == 80.0
    assert metrics.saved_pct(100, 50) == 50.0


def test_saved_pct_reports_growth_as_a_negative_saving():
    """A compressor that inflates the payload must not read as a positive win.

    This is the mutation that survived: `(after - before) / after * 100` scores
    1000 -> 1500 as +33.3% saved. Against the before size it is -50%.
    """
    assert metrics.saved_pct(1000, 1500) == -50.0
    assert metrics.saved_pct(1000, 2000) == -100.0


def test_saved_pct_of_an_unchanged_payload_is_zero():
    assert metrics.saved_pct(4321, 4321) == 0.0


def test_saved_pct_with_no_baseline_is_zero_not_a_crash():
    assert metrics.saved_pct(0, 0) == 0.0
    assert metrics.saved_pct(0, 10) == 0.0


# ── the paired statistic: what headroom adds over plain JSON compaction ──

def test_paired_gains_are_elementwise():
    assert metrics.paired_gains([10.0, 20.0], [1.0, 5.0]) == [9.0, 15.0]


def test_paired_gains_rejects_unequal_lengths_instead_of_truncating():
    """`zip` would silently drop the extra row and average over a wrong n."""
    with pytest.raises(ValueError, match="same length"):
        metrics.paired_gains([1.0, 2.0, 3.0], [1.0, 2.0])


def test_median_paired_gain_is_not_the_difference_of_medians():
    """The two are different statistics, and on this data they disagree by 48%.

    The median does not commute with subtraction the way the mean does, so a
    paired comparison has to be made row by row. If these two ever came out
    equal on the real data the test would stop guarding anything, so it asserts
    they differ as well as which one is correct.
    """
    rows = [r for r in control() if not r["table"]]
    crush = [r["crush_pct"] for r in rows]
    compact = [r["compact_pct"] for r in rows]

    paired = statistics.median(metrics.paired_gains(crush, compact))
    unpaired = statistics.median(crush) - statistics.median(compact)

    assert paired == pytest.approx(0.27, abs=0.005)
    assert unpaired == pytest.approx(0.40, abs=0.005)
    assert paired != pytest.approx(unpaired, abs=0.01)


def test_recorded_gain_is_the_per_row_paired_difference():
    """Each recorded row carries its own gain, so the median is auditable."""
    for row in control():
        assert row["headroom_gain_pts"] == pytest.approx(
            row["crush_pct"] - row["compact_pct"]), row["file"]


# ── the byte split: §7.2, measured against real wire bytes ──

def _wire_payload() -> tuple[str, dict]:
    payload = {"results": [{"content": "def f():\n\treturn 1", "file": "a/b.py",
                            "line_start": 1, "score": 0.5}],
               "search_id": "abc123", "fallback_triggered": False}
    return json.dumps(payload, indent=2), payload


def test_wire_byte_split_accounts_for_every_byte():
    """The three buckets are exhaustive: nothing is double-counted or dropped."""
    wire, payload = _wire_payload()
    split = metrics.wire_byte_split(wire, payload)
    assert (split["content_bytes"] + split["metadata_bytes"]
            + split["framing_bytes"]) == split["wire_bytes"] == len(wire.encode())


def test_wire_byte_split_counts_framing_that_compaction_would_remove():
    """The indented wire has framing; the compacted form has measurably less.

    This is the property the original 78.8% figure violated: it divided the
    content bytes by a re-compacted copy, which has ~15KB less framing than the
    wire it claimed to be describing.
    """
    wire, payload = _wire_payload()
    compact = json.dumps(payload, separators=(",", ":"))

    indented = metrics.wire_byte_split(wire, payload)
    compacted = metrics.wire_byte_split(compact, payload)

    assert indented["framing_bytes"] > compacted["framing_bytes"]
    assert indented["content_bytes"] == compacted["content_bytes"]
    # Same content, bigger denominator: content's share must be lower on the wire.
    assert (indented["content_bytes"] / indented["wire_bytes"]
            < compacted["content_bytes"] / compacted["wire_bytes"])


def test_wire_byte_split_rejects_content_that_is_not_in_the_wire():
    """Guards against measuring a payload the string never carried."""
    wire, payload = _wire_payload()
    other = json.loads(json.dumps(payload))
    other["results"][0]["content"] = "something else entirely"
    with pytest.raises(ValueError, match="not present verbatim"):
        metrics.wire_byte_split(wire, other)


# ── the retention gate: it has to bite ──

BASE = {"file": "src/Auth/Handler.PY", "content": "def f():\n    return 1",
        "line_start": 1, "line_end": 2, "relation": "imports",
        "seed_file": "src/Auth/Caller.PY"}


@pytest.mark.parametrize("field,altered,why", [
    ("file", "src/auth/handler.py", "case-folded"),
    ("file", " src/Auth/Handler.PY ", "whitespace-padded"),
    ("line_start", "1", "int arrived back as a string"),
])
def test_an_altered_critical_field_is_a_loss_not_a_match(field, altered, why):
    """Exact equality is the contract; a normalized comparison reports PASS here.

    You cannot re-derive which file a result came from once the path has been
    rewritten, so an altered critical field is indistinguishable from a lost one.
    """
    before = {"results": [dict(BASE)]}
    after = {"results": [dict(BASE, **{field: altered})]}

    got = check(before, after)

    assert got["verdict"] == "FAIL", why
    assert {d["field"] for d in got["lost_critical"]} == {field}, why


def test_an_unaltered_payload_still_passes():
    """The counterpart: the check above must not be satisfied by always failing."""
    before = {"results": [dict(BASE)]}
    got = check(before, json.loads(json.dumps(before)))
    assert got["verdict"] == "PASS", got
    assert not got["lost_critical"], got


def test_results_that_is_not_an_array_of_dicts_fails_rather_than_crashing():
    """`results` as bare strings is not addressable as `results[i]["file"]`."""
    string_rows = {"results": ["a/b.py", "c/d.py"]}

    got = check(string_rows, string_rows)

    assert got["verdict"].startswith("FAIL"), got
    assert got["results_before"] == 0, got


def test_a_de_structured_after_fails_even_when_the_before_is_fine():
    got = check({"results": [dict(BASE)]}, {"results": ["a/b.py"]})
    assert got["verdict"].startswith("FAIL"), got
    assert got["structure_preserved"] is False, got


def test_retention_self_test_passes_with_a_scrubbed_environment():
    """The script's own 10 cases, run as the README tells a reader to run them."""
    done = subprocess.run([sys.executable, str(HARNESS / "retention.py")],
                          capture_output=True, text=True, env=dict(SCRUBBED_ENV))
    assert done.returncode == 0, done.stderr
    assert "10/10 PASS" in done.stdout, done.stdout


# ── the doc: every figure in §7 comes out of a recorded run ──

def test_recorded_totals_are_the_sum_of_the_recorded_rows():
    data = stage1()
    totals, rows = data["totals"], data["eligible"]
    for key in ("results", "wire_bytes", "content_bytes", "metadata_bytes",
                "framing_bytes", "tokens_before"):
        assert totals[key] == sum(r[key] for r in rows), key
    assert (totals["content_bytes"] + totals["metadata_bytes"]
            + totals["framing_bytes"]) == totals["wire_bytes"]


def test_the_byte_shares_in_the_doc_match_the_recorded_totals():
    """§7.2's partition table, cell by cell. The figures it replaced -- 145,025 /
    78.8% and 39,122 / 21.2% -- were consistent with each other but not with the
    wire bytes: the same 145,025 is 72.5% of the 200,059 bytes the server actually
    sent."""
    totals = stage1()["totals"]
    doc = DOC.read_text()

    _assert_cells(
        doc,
        ("(the source code)", "Bytes", f"{totals['content_bytes']:,}"),
        ("(the source code)", "Share", f"{totals['content_bytes_pct']}%"),
        ("every non-content value", "Bytes", f"{totals['metadata_bytes']:,}"),
        ("every non-content value", "Share", f"{totals['metadata_bytes_pct']}%"),
        ("JSON framing", "Bytes", f"{totals['framing_bytes']:,}"),
        ("JSON framing", "Share", f"{totals['framing_bytes_pct']}%"),
    )
    # The share the old table got wrong, and the one it was actually computing.
    assert totals["content_bytes_pct"] == pytest.approx(72.5)
    # A stale figure anywhere is stale, so absence is checked against the whole doc.
    assert "78.8" not in doc


def test_the_savings_ceiling_in_the_doc_matches_the_recorded_run():
    """§7.2's second table -- the cap on compression that may not touch `content`.

    Nothing covered this table before: all four of its cells could be corrupted
    with the suite staying green, including the two the prose then reasons from
    ("between a third and two fifths of the payload").
    """
    data = stage1()
    doc = DOC.read_text()
    rows, totals = data["eligible"], data["totals"]

    wire_form = statistics.median(r["ceiling_wire_form_pct"] for r in rows)
    code_only = statistics.median(r["ceiling_code_only_pct"] for r in rows)

    _assert_cells(
        doc,
        ("kept in wire form", "median payload", f"{wire_form:.1f}%"),
        ("kept in wire form", "pooled", f"{totals['ceiling_wire_form_pct']}%"),
        ("only the code text", "median payload", f"{code_only:.1f}%"),
        ("only the code text", "pooled", f"{totals['ceiling_code_only_pct']}%"),
    )


def test_the_control_figures_in_the_doc_match_the_recorded_run():
    """§7.3's headline table and the two populations under it, cell by cell.

    These are the figures the "do not adopt" call is read off, and they are also
    the ones that repeat. Addressed by row and column, each is pinned where it is
    written, so corrupting the `moderate` cell no longer passes on the strength of
    a correct copy two tables away.
    """
    rows = control()
    doc = DOC.read_text()

    compact = _spread(rows, "compact_pct")
    crush = _spread(rows, "crush_pct")
    on_compact = _spread(rows, "crush_on_compact_pct")

    _assert_cells(
        doc,
        *[("Compact JSON only", col, compact[col]) for col in compact],
        *[("SmartCrusher on wire bytes", col, crush[col]) for col in crush],
        *[("SmartCrusher after compacting", col, on_compact[col])
          for col in on_compact],
    )

    for label, is_table in (("none:adaptive_at_limit", False),
                            ("lossless:table", True)):
        subset = [r for r in rows if r["table"] is is_table]
        gain = statistics.median(r["headroom_gain_pts"] for r in subset)
        _assert_cells(
            doc,
            (label, "n", str(len(subset))),
            (label, "headroom saving", _spread(subset, "crush_pct")["median"]),
            (label, "compaction alone", _spread(subset, "compact_pct")["median"]),
            (label, "headroom's own contribution", f"{gain:+.2f} pts"),
        )

    # The difference of medians, which the doc used to quote instead.
    assert "+0.4 pts" not in doc


def test_the_prose_restating_the_control_figures_agrees_with_the_tables():
    """The verdict and the summary quote §7.3's two headline figures again.

    These are the copies that masked the defect: with `11.8%` written in four
    places, a whole-document substring check passed while the §7.3 cell read
    11.9%. Each restatement is pinned to its own sentence, so a figure that drifts
    in the summary fails there rather than being covered by the table.
    """
    rows = control()
    doc = DOC.read_text()

    compaction = _spread(rows, "compact_pct")["median"]
    non_table = [r for r in rows if not r["table"]]
    contribution = statistics.median(r["headroom_gain_pts"] for r in non_table)

    _assert_on_line(doc, "points over a one-line change",
                    f"{contribution:.2f} points")
    _assert_on_line(doc, "available from compacting our own JSON", compaction)
    _assert_on_line(doc, "serve compact JSON from clean-rag",
                    f"Median {compaction}")
    _assert_on_line(doc, "from compact JSON. Do not adopt headroom", compaction)


def test_the_preset_sweep_in_the_doc_matches_the_recorded_run():
    """§7.3's tuning table: the aggressive preset is where the doc was wrong.

    It claimed raising bias to 50.0 "does not change the decision". bias is a
    multiplier where >1 keeps MORE (headroom/config.py), so that tested the
    direction that compresses less. Swept the other way, headroom's own
    `aggressive` preset takes the table transform on every payload and fails
    retention on every payload.
    """
    rows = control()
    doc = DOC.read_text()
    n = len(rows)

    for preset in ("aggressive", "moderate", "conservative"):
        cells = [r["by_preset"][preset] for r in rows]
        biases = {c["bias"] for c in cells}
        assert len(biases) == 1, f"{preset} swept more than one bias: {biases}"
        median_saved = statistics.median(c["saved_pct"] for c in cells)
        _assert_cells(
            doc,
            (preset, "bias", str(biases.pop())),
            (preset, "median saved", f"{median_saved:.1f}%"),
            *[(preset, column, f"{sum(map(counts, cells))}/{n}")
              for column, counts in _PRESET_COUNTS.items()],
        )

    aggressive = [r["by_preset"]["aggressive"] for r in rows]
    assert all(c["strategy"] == "lossless:table" for c in aggressive)
    assert not any(c["retention"] == "PASS" for c in aggressive)
    assert all(c["ccr_placeholders"] > 0 for c in aggressive)
    assert "50.0" not in doc


def test_the_hook_block_figures_in_the_doc_match_the_recorded_run():
    """§7.1. The doc used to say ~310 tokens, "below every headroom threshold".

    The block clears both gates (200 and 250) and headroom still leaves it
    byte-identical, so the threshold argument was both wrong and unnecessary.
    """
    blocks = json.loads(HOOKBLOCK.read_text())["blocks"]
    thresholds = stage1()["thresholds"]
    doc = DOC.read_text()

    size = [b["bytes"] for b in blocks]
    tokens = [b["tokens"] for b in blocks]
    # One pin over the whole range: the upper byte bound was the figure no
    # assertion reached, since only `min(bytes)` was ever checked.
    _assert_on_line(
        doc, "whatever the prompt",
        f"{min(size):,}–{max(size):,} bytes "
        f"({min(tokens)}–{max(tokens)} tokens)")

    # The two gates the block clears, the claim that replaced the wrong threshold
    # argument. They straddle a line break, so each gets its own anchor.
    _assert_on_line(doc, "the block clears both",
                    f"`min_tokens_to_crush` ({thresholds['min_tokens_to_crush']})")
    _assert_on_line(
        doc, "There is simply nothing here",
        f"`min_tokens_to_compress` ({thresholds['min_tokens_to_compress']})")

    assert all(b["byte_identical"] for b in blocks)
    assert all(b["crusher_strategy"] == "passthrough" for b in blocks)
    assert "~310 tokens" not in doc


# ── the pins themselves have to bite ──
#
# Every test above asserts the doc and the recorded run agree. None of them can
# tell whether the comparison still happens: with a correct doc, a `_assert_cells`
# that never compared and one that compared perfectly are indistinguishable, and
# all of them stay green. That is the same shape as the defect this group was
# written for -- an assertion that cannot fail -- one level up, so the locator's
# behaviour on a wrong figure is checked here rather than trusted.


def _corrupt_cell(doc: str, row: str, column: str,
                  replacement: str) -> tuple[int, str, str]:
    """Rewrite one located cell, leaving every other copy of the figure alone."""
    lineno, correct = _locate_cell(doc, row, column)
    lines = doc.splitlines()
    lines[lineno - 1] = lines[lineno - 1].replace(correct, replacement)
    return lineno, correct, "\n".join(lines)


def test_a_corrupted_cell_is_caught_even_though_correct_copies_survive():
    """The defect itself, as a standing test.

    `11.8%` is written in four places, so `assert "11.8%" in doc` passed while the
    §7.3 cell a reader makes the decision from read 11.9%. The pin is addressed to
    the cell, so the surviving copies have no bearing on it.
    """
    doc = DOC.read_text()
    lineno, correct, corrupted = _corrupt_cell(
        doc, "Compact JSON only", "median", "11.9%")

    # The condition that made the old assertion useless has to hold, or this is
    # not the case that was failing.
    assert corrupted.count(correct) >= 2, "other copies must survive"

    with pytest.raises(AssertionError) as err:
        _assert_cells(corrupted, ("Compact JSON only", "median", correct))

    message = str(err.value)
    assert f"{DOC.name}:{lineno}" in message, message
    assert "Compact JSON only | median" in message, message
    assert "doc says '11.9%'" in message, message
    assert f"recorded run gives {correct!r}" in message, message


def test_a_correct_cell_raises_nothing():
    """The counterpart: the check above must not be satisfied by always failing."""
    doc = DOC.read_text()
    _, correct = _locate_cell(doc, "Compact JSON only", "median")
    _assert_cells(doc, ("Compact JSON only", "median", correct))


def test_an_address_that_stopped_resolving_fails_rather_than_passing():
    """A renamed column or a deleted row must not read as "nothing disagreed".

    This is the quiet way a pin dies: the cell it names stops existing, the lookup
    finds nothing, and treating a miss as a pass leaves the figure unguarded with
    the suite green.
    """
    doc = DOC.read_text()
    with pytest.raises(AssertionError, match="no longer pinned"):
        _locate_cell(doc, "Compact JSON only", "no such column")
    with pytest.raises(AssertionError, match="no longer pinned"):
        _locate_cell(doc, "no such row", "median")


def test_an_ambiguous_address_fails_rather_than_taking_the_first_match():
    """`SmartCrusher` names two rows of §7.3's table, so it identifies no figure."""
    with pytest.raises(AssertionError, match="matched 2 cells"):
        _locate_cell(DOC.read_text(), "SmartCrusher", "median")


def test_a_corrupted_prose_figure_is_caught_with_its_line():
    doc = DOC.read_text()
    figure = "1,248–1,250 bytes"
    corrupted = doc.replace(figure, "1,248–1,260 bytes")

    with pytest.raises(AssertionError) as err:
        _assert_on_line(corrupted, "whatever the prompt", figure)

    message = str(err.value)
    assert f"recorded run gives {figure!r}" in message, message
    assert "1,260" in message, message


def test_a_reworded_anchor_fails_rather_than_matching_nothing():
    with pytest.raises(AssertionError, match="no longer pinned"):
        _assert_on_line(DOC.read_text(), "no such sentence", "11.8%")
