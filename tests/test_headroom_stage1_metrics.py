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

`metrics` and `retention` are importable here only because they are stdlib-only.
`measure.py` and `control.py` import `headroom`, which lives in an isolated 3.13
venv (§4) and is deliberately not a dependency of this repo, so the arithmetic
worth testing was moved out of them into `metrics`.

Run: python -m pytest tests/test_headroom_stage1_metrics.py -v
"""

import json
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
    """§7.2's table. The figures it replaced -- 145,025 / 78.8% and 39,122 /
    21.2% -- were consistent with each other but not with the wire bytes: the
    same 145,025 is 72.5% of the 200,059 bytes the server actually sent."""
    totals = stage1()["totals"]
    doc = DOC.read_text()

    assert f"{totals['content_bytes']:,}" in doc
    assert f"{totals['metadata_bytes']:,}" in doc
    assert f"{totals['framing_bytes']:,}" in doc
    assert f"{totals['content_bytes_pct']}%" in doc
    assert f"{totals['metadata_bytes_pct']}%" in doc
    assert f"{totals['framing_bytes_pct']}%" in doc
    # The share the old table got wrong, and the one it was actually computing.
    assert totals["content_bytes_pct"] == pytest.approx(72.5)
    assert "78.8" not in doc


def test_the_control_figures_in_the_doc_match_the_recorded_run():
    rows = control()
    doc = DOC.read_text()

    compaction = statistics.median(r["compact_pct"] for r in rows)
    assert f"{compaction:.1f}%" in doc

    non_table = [r for r in rows if not r["table"]]
    gain = statistics.median(r["headroom_gain_pts"] for r in non_table)
    assert f"{gain:.2f}" in doc
    # The difference of medians, which the doc used to quote instead.
    assert "+0.4 pts" not in doc


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

    for preset in ("aggressive", "moderate", "conservative"):
        cells = [r["by_preset"][preset] for r in rows]
        median_saved = statistics.median(c["saved_pct"] for c in cells)
        assert f"{median_saved:.1f}%" in doc, preset

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
    doc = DOC.read_text()

    assert f"{min(b['bytes'] for b in blocks):,}" in doc
    assert str(min(b["tokens"] for b in blocks)) in doc
    assert str(max(b["tokens"] for b in blocks)) in doc
    assert all(b["byte_identical"] for b in blocks)
    assert all(b["crusher_strategy"] == "passthrough" for b in blocks)
    assert "~310 tokens" not in doc
