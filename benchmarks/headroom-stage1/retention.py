"""Field-retention verifier for the headroom Stage 1 measurement.

The non-negotiable Stage 1 gate: a compressed search payload must still carry
every field the injection consumers read. Savings are irrelevant if a consumer
field is gone. This module knows nothing about headroom -- it compares a
before-dict to an after-string/dict and reports what was lost.
"""
from __future__ import annotations
import json, re

# Fields clean-rag's own consumers read off a /search result. `content` is
# deliberately NOT in here: it is prose/code the model reads, not a field a
# consumer parses. It gets its own verbatim check.
CONSUMER_FIELDS = ("file", "relation", "seed_file", "tree_path", "section",
                   "line_start", "line_end", "score", "source_type", "is_caller",
                   "search_mode", "rrf_score")

# The subset whose loss is unrecoverable: you cannot re-derive which file a
# result came from, or how the graph reached it.
CRITICAL_FIELDS = ("file", "relation", "seed_file", "line_start", "line_end")


def _results(payload):
    """Return a list of result dicts, or [] if the shape is not that.

    SmartCrusher's `lossless:table` strategy rewrites `results` from a JSON
    array of dicts into a single STRING holding a schema header plus CSV rows.
    That parses as JSON but is not addressable as `results[i]["file"]`, so it
    must be treated as unstructured text, not as results.
    """
    if isinstance(payload, dict):
        r = payload.get("results", [])
    else:
        r = payload
    if isinstance(r, list) and all(isinstance(x, dict) for x in r):
        return r
    return []


def is_structured(payload) -> bool:
    """True only if results is still an addressable array of dicts."""
    if isinstance(payload, str):
        return False
    r = payload.get("results") if isinstance(payload, dict) else payload
    return isinstance(r, list) and bool(r) and all(isinstance(x, dict) for x in r)


CCR_RE = re.compile(r"<<ccr:[0-9a-f]+,[^>]*>>")


def ccr_refs(text: str) -> int:
    """Count CCR placeholders -- content replaced by a retrieval pointer."""
    return len(CCR_RE.findall(text))


def check(before: dict, after) -> dict:
    """Compare a payload before and after compression.

    `after` may be a dict (structure preserved) or a str (compressor emitted
    text). A str after means every field check degrades to substring presence,
    which is the weaker but honest test.
    """
    b_res = _results(before)
    after_is_text = isinstance(after, str) or not is_structured(after)
    a_res = [] if after_is_text else _results(after)
    hay = after if isinstance(after, str) else json.dumps(after)

    lost_critical, lost_other, unverifiable, present = [], [], [], 0
    for i, r in enumerate(b_res):
        for f in CONSUMER_FIELDS:
            if f not in r:
                continue
            val = r[f]
            if after_is_text or i >= len(a_res):
                # No structure to read the field off. A substring hit only
                # means something is unverifiable rather than preserved --
                # and on a short value like line_start=1 it is satisfied by
                # accident, so it proves nothing at all.
                sval = str(val)
                if len(sval) >= 8 and sval in hay:
                    unverifiable.append({"result_index": i, "field": f,
                                         "value": val, "why": "substring only"})
                else:
                    (lost_critical if f in CRITICAL_FIELDS else lost_other).append(
                        {"result_index": i, "field": f, "value": val,
                         "why": "no structure; value too short to match meaningfully"})
                continue
            if a_res[i].get(f) == val:
                present += 1
            else:
                (lost_critical if f in CRITICAL_FIELDS else lost_other).append(
                    {"result_index": i, "field": f, "value": val})

    # Verbatim content check: did any result's source text change at all?
    content_altered = []
    for i, r in enumerate(b_res):
        c = r.get("content")
        if not c:
            continue
        if after_is_text:
            intact = c in hay
        else:
            intact = i < len(a_res) and a_res[i].get("content") == c
        if not intact:
            content_altered.append(i)

    # A text-only `after` means a JSON-parsing consumer has nothing to parse.
    # That is a structural failure regardless of which substrings survived.
    if after_is_text:
        verdict = "FAIL (structure lost: consumers parse JSON fields)"
    elif lost_critical:
        verdict = "FAIL"
    else:
        verdict = "PASS"

    # Lenient survival: do the DISTINCTIVE metadata values still appear as
    # text anywhere? This separates "restructured but lossless" from "dropped".
    distinctive_total = distinctive_found = 0
    for r in b_res:
        for f in CONSUMER_FIELDS:
            v = r.get(f)
            if isinstance(v, str) and len(v) >= 8:
                distinctive_total += 1
                if v in hay:
                    distinctive_found += 1

    return {
        "ccr_placeholders": ccr_refs(hay),
        "distinctive_values_total": distinctive_total,
        "distinctive_values_found": distinctive_found,
        "distinctive_survival_pct": (round(distinctive_found / distinctive_total * 100, 1)
                                     if distinctive_total else None),
        "results_before": len(b_res),
        "results_after": "n/a (text)" if after_is_text else len(a_res),
        "structure_preserved": not after_is_text,
        "fields_preserved": present,
        "fields_unverifiable": unverifiable,
        "lost_critical": lost_critical,
        "lost_other": lost_other,
        "content_altered_indices": content_altered,
        "content_altered_count": len(content_altered),
        "verdict": verdict,
    }


if __name__ == "__main__":
    # Self-test: the checker must bite. A hand-broken payload must FAIL.
    good = {"results": [{"file": "a/b.py", "content": "def f():\n    return 1",
                         "line_start": 1, "line_end": 2, "score": 0.9,
                         "relation": "imports", "seed_file": "a/c.py"}]}
    identical = check(good, json.loads(json.dumps(good)))
    assert identical["verdict"] == "PASS", identical
    assert identical["content_altered_count"] == 0, identical
    assert not identical["lost_other"], identical

    dropped = {"results": [{k: v for k, v in good["results"][0].items()
                            if k not in ("relation", "seed_file")}]}
    missing = check(good, dropped)
    assert missing["verdict"] == "FAIL", missing
    assert {d["field"] for d in missing["lost_critical"]} == {"relation", "seed_file"}, missing

    sliced = json.loads(json.dumps(good))
    sliced["results"][0]["content"] = "def f(): ..."
    mangled = check(good, sliced)
    assert mangled["content_altered_count"] == 1, mangled
    assert mangled["verdict"] == "PASS", "content slicing is not a field loss"

    as_text = check(good, "file a/b.py imports from a/c.py lines 1-2 score 0.9")
    assert as_text["verdict"].startswith("FAIL"), as_text
    assert as_text["structure_preserved"] is False, as_text

    # A trivially-satisfied substring must never be scored as preserved.
    assert as_text["fields_preserved"] == 0, as_text
    short = [d["field"] for d in as_text["lost_critical"]]
    assert "line_start" in short and "line_end" in short, as_text

    table_shape = {"results": "[1]{file:string}\n<<ccr:deadbeef1234,string,1.9KB>>,a/b.py",
                   "search_id": "x"}
    tbl = check(good, table_shape)
    assert tbl["verdict"].startswith("FAIL"), tbl
    assert tbl["structure_preserved"] is False, tbl
    assert tbl["ccr_placeholders"] == 1, tbl
    # a/b.py is 6 chars so it is not "distinctive"; a/c.py likewise. Both are
    # therefore reported lost, which is the honest answer for a table shape.
    assert tbl["distinctive_values_total"] == 0, tbl

    print("retention.py self-test: 8/8 PASS (bites on field loss, content "
          "slicing, text-only output, accidental substring matches, and the "
          "lossless:table de-structuring)")
