"""Stage 1 measurement: does headroom compression help clean-rag payloads?

Two questions, kept separate on purpose:
  1. Token delta -- how much smaller does the payload get?
  2. Field retention -- does every consumer field survive? (non-negotiable)

Tokenizer note: headroom's AnthropicProvider counts a bare string with
tiktoken cl100k_base x 1.1, NOT a real Anthropic tokenizer. Every number below
is therefore an APPROXIMATION. One tokenizer path is used for every payload so
the numbers are at least comparable to each other.

Everything is measured against the exact bytes `capture.py` recorded from the
server, never against a re-serialized copy of the parsed payload. The two are
byte-identical for clean-rag today only because it happens to use `indent=2`
with Python's default separators; measuring the recorded string directly does
not depend on that staying true.
"""
from __future__ import annotations
import json, pathlib, statistics, sys

from headroom.providers.anthropic import AnthropicProvider
from headroom.transforms.smart_crusher import SmartCrusher, SmartCrusherConfig
from headroom import compress, CompressConfig

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from metrics import saved_pct, wire_byte_split
from retention import check as retention_check

HERE = pathlib.Path(__file__).parent
# The directory capture.py writes and control.py reads: exact server bytes.
PAYLOADS = HERE / "payloads_wire"
MODEL = "claude-sonnet-4-5-20250929"

# SmartCrusher / CompressConfig no-op gates, from the installed source.
MIN_ITEMS = 5
MIN_TOKENS_CRUSH = 200
MIN_TOKENS_COMPRESS = 250

tok = AnthropicProvider().get_token_counter(MODEL)   # tiktoken cl100k x1.1 -- approximate
crusher = SmartCrusher(config=SmartCrusherConfig())


def count(text: str) -> int:
    return tok.count_text(text)


def variant_smartcrusher(raw: str):
    """What headroom would do to this payload as a tool-output string."""
    r = crusher.crush(raw, query="", bias=1.0)
    return r.compressed, {"strategy": r.strategy, "was_modified": r.was_modified}


def variant_compress(raw: str):
    """Proxy-realistic: the payload as a tool message going over the wire."""
    msgs = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Analyse the search results and answer."},
        {"role": "tool", "tool_call_id": "call_0", "content": raw},
    ]
    res = compress(msgs, model=MODEL, config=CompressConfig())
    out = ""
    for m in res.messages:
        if m.get("role") == "tool" and isinstance(m.get("content"), str):
            out = m["content"]
    return out, {"transforms": sorted(set(res.transforms_applied)),
                 "lib_tokens_before": res.tokens_before,
                 "lib_tokens_after": res.tokens_after,
                 "lib_ratio": round(res.compression_ratio, 4)}


def safe_ceilings(raw: str, payload: dict) -> dict:
    """The ceiling on SAFE savings -- two bounds, because there are two.

    If compression may not touch `content` (the source code an agent quotes
    verbatim), the most it can ever remove is everything else. What counts as
    "everything else" depends on whether the code has to stay in the encoding
    the payload carries it in, and the two answers are eight points apart, so
    reporting one of them alone overstates or understates the room available:

    - `ceiling_wire_form_pct` -- the code stays exactly as the JSON carries it,
      escaped and quoted. This is the bound on any compressor that rewrites the
      payload string and still emits valid JSON, which is what SmartCrusher does.
    - `ceiling_code_only_pct` -- only the code text itself has to survive, in
      any encoding. Higher, because dropping the newline and tab escapes is
      lossless for the code. Reaching it means emitting a different container,
      which is exactly what the `lossless:table` strategy does, and what costs
      the structure (see the retention verdicts below).

    Both denominators are `tokens_before`, the recorded wire string, so the two
    ceilings are comparable with each other and with the byte split.
    """
    res = payload.get("results", [])
    whole = count(raw)
    wire_form = sum(count(json.dumps(r.get("content") or "")) for r in res)
    code_only = sum(count(r.get("content") or "") for r in res)
    return {"content_tokens_wire_form": wire_form,
            "content_tokens_code_only": code_only,
            "ceiling_wire_form_pct": round(saved_pct(whole, wire_form), 1),
            "ceiling_code_only_pct": round(saved_pct(whole, code_only), 1)}


def eligible(raw: str, payload: dict) -> tuple[bool, str]:
    n = len(payload.get("results", []))
    t = count(raw)
    if n < MIN_ITEMS:
        return False, f"below min_items_to_analyze ({n}<{MIN_ITEMS})"
    if t < MIN_TOKENS_CRUSH:
        return False, f"below min_tokens_to_crush ({t}<{MIN_TOKENS_CRUSH})"
    if t < MIN_TOKENS_COMPRESS:
        return False, f"below min_tokens_to_compress ({t}<{MIN_TOKENS_COMPRESS})"
    return True, ""


def parse_after(s: str):
    try:
        return json.loads(s)
    except Exception:
        return s          # compressor emitted non-JSON text


def pooled(rows: list[dict]) -> dict:
    """Sum the per-payload measures so the doc's aggregate table is auditable.

    Every share is a sum of the per-row fields above it, so a reader can add the
    rows in `eligible` and land on the same number. The three byte buckets sum
    to `wire_bytes` exactly.
    """
    total = {k: sum(r[k] for r in rows) for k in
             ("results", "wire_bytes", "content_bytes", "metadata_bytes",
              "framing_bytes", "tokens_before",
              "content_tokens_wire_form", "content_tokens_code_only")}
    for k in ("content_bytes", "metadata_bytes", "framing_bytes"):
        total[f"{k}_pct"] = round(total[k] / total["wire_bytes"] * 100, 1)
    total["ceiling_wire_form_pct"] = round(
        saved_pct(total["tokens_before"], total["content_tokens_wire_form"]), 1)
    total["ceiling_code_only_pct"] = round(
        saved_pct(total["tokens_before"], total["content_tokens_code_only"]), 1)
    return total


def report(rows: list[dict], totals: dict) -> None:
    """Print the summary §7 quotes. Separated from main() so the measurement
    loop and the presentation of it can each be read on their own."""
    print(f"\n{totals['results']} results, {totals['wire_bytes']:,} wire bytes, "
          f"{totals['tokens_before']:,} tokens (pooled)")
    print("  wire bytes     content {content_bytes:>7,} ({content_bytes_pct:>4.1f}%)   "
          "metadata {metadata_bytes:>6,} ({metadata_bytes_pct:>4.1f}%)   "
          "framing {framing_bytes:>6,} ({framing_bytes_pct:>4.1f}%)".format(**totals))
    print(f"  safe ceiling   content in wire form {totals['ceiling_wire_form_pct']:.1f}% pooled "
          f"(median {statistics.median([r['ceiling_wire_form_pct'] for r in rows]):.1f}%)   "
          f"code only {totals['ceiling_code_only_pct']:.1f}% pooled "
          f"(median {statistics.median([r['ceiling_code_only_pct'] for r in rows]):.1f}%)")

    for variant in ("smartcrusher", "compress"):
        vals = [r[variant] for r in rows if "error" not in r[variant]]
        errs = [r for r in rows if "error" in r[variant]]
        print(f"\n=== {variant} ===")
        if errs:
            print(f"  errors: {len(errs)}  e.g. {errs[0][variant]['error']}")
        if not vals:
            continue
        saved = [v["saved_pct"] for v in vals]
        print(f"  token delta   median {statistics.median(saved):+.1f}%   "
              f"min {min(saved):+.1f}%   max {max(saved):+.1f}%")
        print(f"  structure preserved : {sum(v['structure_preserved'] for v in vals)}/{len(vals)}")
        print(f"  retention PASS      : {sum(v['verdict']=='PASS' for v in vals)}/{len(vals)}")
        print(f"  content altered     : {sum(v['content_altered']>0 for v in vals)}/{len(vals)} payloads")
        lost = sorted({f for v in vals for f in v["lost_critical_fields"]})
        print(f"  critical fields lost: {lost or 'none'}")
        ccr = [v["ccr_placeholders"] for v in vals]
        print(f"  CCR placeholders    : median {statistics.median(ccr):.0f} per payload "
              f"(content replaced by a retrieval pointer)")
        surv = [v["distinctive_survival_pct"] for v in vals
                if v["distinctive_survival_pct"] is not None]
        if surv:
            print(f"  distinctive metadata surviving as text: median "
                  f"{statistics.median(surv):.1f}%  min {min(surv):.1f}%")
        strat = {}
        for v in vals:
            k = v.get("strategy") or ",".join(v.get("transforms", [])) or "-"
            strat[k] = strat.get(k, 0) + 1
        print(f"  strategies/transforms: {strat}")


def main():
    files = sorted(PAYLOADS.glob("search_*.json"))
    rows, skipped = [], []
    for f in files:
        raw = f.read_text()
        payload = json.loads(raw)
        ok, why = eligible(raw, payload)
        if not ok:
            skipped.append({"file": f.name, "reason": why})
            continue
        before = count(raw)
        row = {"file": f.name, "results": len(payload.get("results", [])),
               "tokens_before": before,
               **safe_ceilings(raw, payload),
               **wire_byte_split(raw, payload)}
        for name, fn in (("smartcrusher", variant_smartcrusher),
                         ("compress", variant_compress)):
            try:
                out, meta = fn(raw)
            except Exception as e:
                row[name] = {"error": f"{type(e).__name__}: {e}"}
                continue
            after = count(out)
            ret = retention_check(payload, parse_after(out))
            row[name] = {
                "tokens_after": after,
                "saved_pct": round(saved_pct(before, after), 1),
                "verdict": ret["verdict"],
                "structure_preserved": ret["structure_preserved"],
                "lost_critical_n": len(ret["lost_critical"]),
                "lost_critical_fields": sorted({d["field"] for d in ret["lost_critical"]}),
                "content_altered": ret["content_altered_count"],
                "ccr_placeholders": ret["ccr_placeholders"],
                "distinctive_survival_pct": ret["distinctive_survival_pct"],
                "results_before": ret["results_before"],
                "results_after": ret["results_after"],
                **meta,
            }
        rows.append(row)

    print(f"payloads: {len(files)}   eligible: {len(rows)}   not eligible: {len(skipped)}")
    for s in skipped:
        print(f"  SKIP {s['file']}: {s['reason']}")
    if not rows:
        print("nothing eligible: no median to report, no results written")
        return

    totals = pooled(rows)
    out_path = HERE / "stage1_results.json"
    out_path.write_text(json.dumps({"model": MODEL,
                                    "tokenizer": "tiktoken cl100k_base x1.1 (APPROXIMATE)",
                                    "thresholds": {"min_items_to_analyze": MIN_ITEMS,
                                                   "min_tokens_to_crush": MIN_TOKENS_CRUSH,
                                                   "min_tokens_to_compress": MIN_TOKENS_COMPRESS},
                                    "totals": totals,
                                    "eligible": rows, "not_eligible": skipped}, indent=2))

    report(rows, totals)
    print(f"\nfull results -> {out_path}")


if __name__ == "__main__":
    main()
