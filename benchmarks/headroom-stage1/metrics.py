"""The arithmetic behind every figure in `docs/HEADROOM-EVALUATION.md` §7.

Three small functions live here rather than inline in `measure.py` and
`control.py` for one reason: those two import `headroom`, which only exists in
the isolated 3.13 venv (§4), so nothing under `tests/` can import them. This
module is stdlib-only and therefore testable by the project's own suite --
`tests/test_headroom_stage1_metrics.py` -- which is what turns "the percentages
are right" from a claim into a checked one.

`retention.py` is stdlib-only for the same reason.
"""
from __future__ import annotations

import json


def saved_pct(before: float, after: float) -> float:
    """Space savings as a percentage: `(before - after) / before * 100`.

    This is the standard definition -- "a representation that compresses a 10MB
    file to 2MB would yield a space savings of 1 - 2/10 = 0.8, often notated as
    a percentage, 80%" (Wikipedia, Data compression ratio). It is deliberately
    NOT the compression ratio (`before / after`), and the denominator is always
    the BEFORE size, so growth reads as a negative saving rather than a
    positive one against a larger baseline.

    A zero baseline reports 0.0: there is nothing to save and nothing was
    saved. No real payload reaches this -- `measure.py` excludes anything below
    the no-op thresholds before calling -- but it keeps a division by zero out
    of a measurement run.
    """
    if not before:
        return 0.0
    return (before - after) / before * 100


def paired_gains(treatment: list[float], baseline: list[float]) -> list[float]:
    """Per-row `treatment - baseline`, for a statistic over paired measurements.

    Every payload is measured under both conditions, so the two sequences are
    paired and the difference exists row by row. Taking `median(treatment) -
    median(baseline)` instead is wrong: the median is not additive, so unlike
    the mean it does not commute with subtraction. Paired methods -- the sign
    test, Wilcoxon signed-rank, Hodges-Lehmann -- are all defined on the
    per-pair differences for exactly this reason. See ACCLAB/dabestr issue #105:
    "When we work with paired data, it's usually about median difference, not
    the difference in medians. Mean change is equal to change in means, but this
    doesn't hold for medians."

    On this project's own data the two answers differ by 48%: the difference of
    medians is 0.40 points, the median paired difference is 0.27.

    Unequal lengths raise instead of silently truncating the way `zip` would,
    since a length mismatch here means the rows are no longer the same payloads.
    """
    if len(treatment) != len(baseline):
        raise ValueError(
            f"paired sequences must be the same length, got "
            f"{len(treatment)} and {len(baseline)}"
        )
    return [t - b for t, b in zip(treatment, baseline)]


def wire_byte_split(wire: str, payload: dict) -> dict:
    """Partition the real wire bytes into content, metadata and JSON framing.

    Measured against the bytes the server actually sent. Re-serializing the
    parsed payload and measuring that instead is what produced the wrong
    78.8%/21.2% split this function replaces: a compacted copy has ~15KB less
    framing than the wire, so dividing by it inflates content's share by six
    points and silently drops the indentation from the accounting entirely.

    Every value is a scalar in clean-rag's `/search` shape, and `json.dumps` of
    a scalar is byte-identical whether or not the enclosing document is
    indented, so each value's serialized length is exactly the space it takes up
    on the wire. `content` values are asserted to appear verbatim in `wire` to
    keep that true if the shape ever changes.

    The three buckets are exhaustive and non-overlapping, and the function
    asserts they sum to the wire length:

    - `content_bytes`  -- the `content` values: the source code a consumer
      quotes, the part compression may not alter.
    - `metadata_bytes` -- every key, plus every non-`content` value.
    - `framing_bytes`  -- the remainder: braces, brackets, commas, colons and
      the `indent=2` whitespace. This is the part plain JSON compaction removes.
    """
    size = lambda obj: len(json.dumps(obj).encode())  # noqa: E731

    content = metadata = 0
    for result in payload.get("results", []):
        for key, value in result.items():
            metadata += size(key)
            if key == "content":
                serialized = json.dumps(value)
                if serialized not in wire:
                    raise ValueError(
                        "content value is not present verbatim in the wire bytes; "
                        "the byte split would no longer measure the real payload"
                    )
                content += len(serialized.encode())
            else:
                metadata += size(value)
    for key, value in payload.items():
        metadata += size(key)
        if key != "results":
            metadata += size(value)

    total = len(wire.encode())
    framing = total - content - metadata
    if framing < 0:
        raise ValueError(
            f"byte split over-counts: content {content} + metadata {metadata} "
            f"exceeds the {total} wire bytes"
        )
    return {"wire_bytes": total, "content_bytes": content,
            "metadata_bytes": metadata, "framing_bytes": framing}
